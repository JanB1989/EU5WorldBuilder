import base64
import hashlib
import json
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
    target.mkdir(parents=True, exist_ok=True)
    lock = target / 'reconstruction_manifest.json'
    existing = {x['name']: x for x in json.loads(lock.read_text())} if lock.exists() else {}
    records = []
    for crop in config['crop_order']:
        for scenario in config['scenarios']:
            name = filename(crop, scenario)
            path = target / name
            if name in existing:
                record = existing[name]
                if not path.exists() or digest(path) != record['sha256']:
                    raise ValueError(f'Pinned input changed or missing: {name}')
            else:
                obj = 'DATA/GAEZ-V5/MAPSET/RES05-YXX/' + name
                url = f'https://storage.googleapis.com/storage/v1/b/{BUCKET}/o/{quote(obj, safe="")}'
                response = requests.get(url, timeout=60)
                response.raise_for_status()
                meta = response.json()
                media = f'https://storage.googleapis.com/download/storage/v1/b/{BUCKET}/o/{quote(obj, safe="")}?alt=media&generation={meta["generation"]}'
                if not path.exists():
                    temporary = path.with_suffix('.partial')
                    with requests.get(media, stream=True, timeout=120) as r:
                        r.raise_for_status()
                        with temporary.open('wb') as f:
                            for chunk in r.iter_content(1048576):
                                f.write(chunk)
                    temporary.replace(path)
                md5 = hashlib.md5(path.read_bytes()).digest()
                if base64.b64encode(md5).decode() != meta['md5Hash']:
                    raise ValueError(f'Local input differs from upstream generation: {name}')
                with rasterio.open(path) as ds:
                    if ds.count != 1 or ds.crs.to_epsg() != 4326:
                        raise ValueError('Unexpected raster contract')
                record = {'name': name, 'crop': crop, 'scenario': scenario,
                          'generation': meta['generation'], 'updated': meta['updated'],
                          'url': media, 'upstream_md5': meta['md5Hash'],
                          'sha256': digest(path), 'license': 'CC-BY-4.0'}
            records.append(record)
            write_json(lock, records + [v for k, v in existing.items() if k not in {r['name'] for r in records}])
            print(f'{crop} {scenario}: verified', flush=True)
    write_json(lock, records)
    documents=acquire_documents(root)
    return {'input_count': len(records), 'manifest': str(lock),'documents':documents}

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
