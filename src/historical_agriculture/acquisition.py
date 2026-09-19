import base64
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests
import rasterio

from .provenance import digest, write_json

BUCKET = 'fao-gismgr-gaez-v5-data'

def filename(crop, scenario):
    return f'GAEZ-V5.RES05-YXX.HP0120.AGERA5.HIST.{crop}.{scenario}.tif'

def acquire(config, root):
    geometry=json.loads((root/'configs/regions.json').read_text())
    if geometry.get('geometry')=='RESOLVE_Ecoregions2017':
        from .ecoregions import acquire_geometry
        acquire_geometry(root,geometry)
    food_config=root/'configs/food_systems.json'
    if food_config.exists():
        food=json.loads(food_config.read_text())['forge'];path=root/food['path']
        if not path.exists():
            response=requests.get(food['url'],timeout=120);response.raise_for_status()
            path.parent.mkdir(parents=True,exist_ok=True)
            temporary=path.with_suffix('.partial');temporary.write_bytes(response.content)
            if digest(temporary)!=food['sha256']:raise ValueError('FORGE download version mismatch')
            temporary.replace(path)
        if digest(path)!=food['sha256']:raise ValueError('FORGE archive checksum mismatch')
    if food_config.exists():
        climate=json.loads(food_config.read_text()).get('climate_transfer')
        if climate:
            path=root/climate['path']
            if not path.exists():
                path.parent.mkdir(parents=True,exist_ok=True)
                temporary=path.with_suffix('.partial')
                with requests.get(climate['url'],stream=True,timeout=120) as response:
                    response.raise_for_status()
                    with temporary.open('wb') as f:
                        for chunk in response.iter_content(1048576):f.write(chunk)
                if digest(temporary)!=climate['sha256']:raise ValueError('WorldClim download version mismatch')
                temporary.replace(path)
            if digest(path)!=climate['sha256']:raise ValueError('WorldClim archive checksum mismatch')
    seshat=json.loads((root/'evidence/seshat_provenance.json').read_text())
    archive=root/'data/raw/seshat.zip'
    archive.parent.mkdir(parents=True,exist_ok=True)
    if not archive.exists():
        response=requests.get(seshat['download_url'],timeout=60)
        response.raise_for_status()
        temporary=archive.with_suffix('.partial');temporary.write_bytes(response.content)
        if digest(temporary)!=seshat['archive_sha256']:
            raise ValueError('Seshat source version differs from the pinned archive; review before use')
        temporary.replace(archive)
    elif digest(archive)!=seshat['archive_sha256']:
        raise ValueError('Pinned Seshat archive changed')
    target = root / config['inputs']
    lock = target / 'reconstruction_manifest.json'
    records, _ = acquire_rasters(root, config['crop_order'], config['scenarios'], target, lock, strict=True)
    documents=acquire_documents(root)
    return {'input_count': len(records), 'manifest': str(lock),'documents':documents}


def check_raster(path):
    with rasterio.open(path) as ds:
        if ds.count != 1 or ds.crs.to_epsg() != 4326:
            raise ValueError('Unexpected raster contract')


def download_raster(path, crop, scenario, timeout=60):
    """Fetch one GAEZ v5 RES05-YXX raster from GCS (or verify a local unpinned copy
    against the upstream generation) and return its provenance record."""
    name = path.name
    obj = 'DATA/GAEZ-V5/MAPSET/RES05-YXX/' + name
    url = f'https://storage.googleapis.com/storage/v1/b/{BUCKET}/o/{quote(obj, safe="")}'
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    meta = response.json()
    media = f'https://storage.googleapis.com/download/storage/v1/b/{BUCKET}/o/{quote(obj, safe="")}?alt=media&generation={meta["generation"]}'
    if not path.exists():
        temporary = path.with_suffix('.partial')
        with requests.get(media, stream=True, timeout=2 * timeout) as r:
            r.raise_for_status()
            with temporary.open('wb') as f:
                for chunk in r.iter_content(1048576):
                    f.write(chunk)
        temporary.replace(path)
    md5 = hashlib.md5(path.read_bytes()).digest()
    if base64.b64encode(md5).decode() != meta['md5Hash']:
        raise ValueError(f'Local input differs from upstream generation: {name}')
    check_raster(path)
    return {'name': name, 'crop': crop, 'scenario': scenario,
            'generation': meta['generation'], 'updated': meta['updated'],
            'url': media, 'upstream_md5': meta['md5Hash'],
            'sha256': digest(path), 'license': 'CC-BY-4.0'}


def import_raster(path, source):
    """Copy an external cached raster without touching the source; hashes are
    verified on both sides and the origin is recorded."""
    expected = digest(source)
    temporary = path.with_suffix('.partial')
    shutil.copyfile(source, temporary)
    if digest(temporary) != expected:
        temporary.unlink()
        raise ValueError(f'Import copy differs from source: {source.name}')
    temporary.replace(path)
    check_raster(path)
    return {'sha256': expected, 'imported_from': str(source),
            'imported': datetime.now(timezone.utc).isoformat(),
            'source': 'imported copy of an external local cache; upstream GCS generation not verified'}


def acquire_rasters(root, crops, scenarios, target_dir, manifest_path, import_directory=None, strict=True, timeout=60):
    """Pin, import or download GAEZ v5 RES05-YXX rasters for ``crops`` x ``scenarios``.

    ``manifest_path`` holds the pinned records: a plain list for the strict
    reconstruction lock, or ``{'records': [...], 'crops_missing': [...]}`` when
    ``strict`` is false. Pinned files must still hash identically. Unpinned files
    are taken from, in order: the local directory (non-strict only; cross-checked
    against ``reconstruction_manifest.json`` when pinned there), a copy from
    ``import_directory`` (never modified; sha256 and ``imported_from`` recorded),
    then a GCS download. Strict mode raises on any gap. Non-strict mode records
    unavailable crops under ``crops_missing`` and stops using the network after
    the first connection failure so an offline machine does not wait per crop.
    Returns ``(records, crops_missing)``.
    """
    target = Path(target_dir); target.mkdir(parents=True, exist_ok=True)
    lock = Path(manifest_path)
    existing = {}
    if lock.exists():
        loaded = json.loads(lock.read_text())
        existing = {x['name']: x for x in (loaded if isinstance(loaded, list) else loaded.get('records', []))}
    reconstruction = target / 'reconstruction_manifest.json'
    pinned = {}
    if reconstruction.exists() and reconstruction.resolve() != lock.resolve():
        pinned = {x['name']: x for x in json.loads(reconstruction.read_text())}
    source_dir = None
    if import_directory:
        source_dir = Path(import_directory)
        if not source_dir.is_absolute(): source_dir = (Path(root) / source_dir)
        source_dir = source_dir.resolve()
        if not source_dir.is_dir(): raise ValueError(f'Import directory missing: {source_dir}')
    records = []; missing = []; network = True

    def save(final=False):
        merged = records if final else records + [v for k, v in existing.items() if k not in {r['name'] for r in records}]
        if strict: write_json(lock, merged)
        else: write_json(lock, {'records': merged, 'crops_missing': missing,
                                'import_directory': str(source_dir) if source_dir else None})

    for crop in crops:
        for scenario in scenarios:
            name = filename(crop, scenario)
            path = target / name
            base = {'name': name, 'crop': crop, 'scenario': scenario, 'license': 'CC-BY-4.0'}
            if name in existing:
                record = existing[name]
                if not path.exists() or digest(path) != record['sha256']:
                    raise ValueError(f'Pinned input changed or missing: {name}')
            elif not strict and path.exists():
                sha = digest(path)
                if name in pinned and pinned[name]['sha256'] != sha:
                    raise ValueError(f'Local input differs from the reconstruction pin: {name}')
                check_raster(path)
                record = dict(pinned.get(name, {'source': 'pre-existing local file; upstream generation not verified'}), **base, sha256=sha)
            elif source_dir is not None and (source_dir / name).is_file():
                record = dict(base, **import_raster(path, source_dir / name))
            elif network:
                try:
                    record = download_raster(path, crop, scenario, timeout=timeout)
                except requests.RequestException as exc:
                    if strict: raise
                    if not isinstance(exc, requests.HTTPError): network = False
                    missing.append({'crop': crop, 'scenario': scenario, 'name': name,
                                    'reason': f'download failed: {type(exc).__name__}'})
                    print(f'{crop} {scenario}: unavailable ({type(exc).__name__})', flush=True)
                    continue
            else:
                missing.append({'crop': crop, 'scenario': scenario, 'name': name, 'reason': 'network unavailable; not in import directory'})
                continue
            records.append(record)
            save()
            print(f'{crop} {scenario}: verified', flush=True)
    save(final=True)
    return records, missing

def acquire_documents(root):
    sources=json.loads((root/'configs/sources.json').read_text())
    folder=root/'data/raw/documentation';folder.mkdir(parents=True,exist_ok=True)
    manifest=folder/'sources_manifest.json'
    previous=json.loads(manifest.read_text()) if manifest.exists() else {}
    records={}
    for key,source in sources.items():
        if not key.replace('_','').isalnum():raise ValueError('Invalid source key')
        destination=folder/(key+'.source')
        if key in previous and previous[key].get('sha256') and destination.exists():
            record=previous[key]
            if record['url']!=source['url'] or digest(destination)!=record['sha256']:
                raise ValueError('Pinned source changed; review its version explicitly')
        else:
            try:
                response=requests.get(source['url'],timeout=60)
                response.raise_for_status()
                destination.write_bytes(response.content)
                record={'url':source['url'],'sha256':digest(destination),'retrieved':datetime.now(timezone.utc).isoformat(),
                        'content_type':response.headers.get('Content-Type'),
                        'last_modified':response.headers.get('Last-Modified'),
                        'status':'downloaded; content interpretation remains in evidence registry',
                        'license':source.get('license','not verified; local research cache only')}
            except requests.RequestException as exc:
                record={'url':source['url'],'status':'download unavailable','error_type':type(exc).__name__}
        records[key]=record
    write_json(manifest,records)
    return {'downloaded':sum('sha256' in x for x in records.values()),'unavailable':sum('sha256' not in x for x in records.values())}
