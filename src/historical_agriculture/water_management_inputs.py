"""Versioned global wet-setting inputs; all resampling precedes EU5 aggregation."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import rasterio
from netCDF4 import Dataset

from .provenance import digest, write_json


def mean_blocks(a,factor,nodata):
    """Exact nested-grid mean excluding missing pixels, with no integer rounding."""
    a=np.asarray(a)
    rows,cols=a.shape
    if rows%factor or cols%factor:raise ValueError('Non-nested fractional grid')
    valid=a!=nodata
    shape=(rows//factor,factor,cols//factor,factor)
    count=valid.reshape(shape).sum(axis=(1,3))
    total=np.where(valid,a,0).reshape(shape).sum(axis=(1,3),dtype=np.float64)
    mean=np.divide(total,count,out=np.zeros_like(total),where=count>0)
    return np.ma.array(mean.astype(np.float32),mask=count==0)


def prepare(root, cfg):
    raw = root / cfg['source_directory']
    out = root / cfg['cache_directory']
    out.mkdir(parents=True, exist_ok=True)
    archive = raw / 'GLWD_v2_0_area_by_class_pct_tif.zip'
    wetloss = raw / 'wetland_loss.zip'
    sources = {str(p.relative_to(root)): digest(p) for p in [archive, wetloss]}
    key = hashlib.sha256(json.dumps({'sources': sources, 'groups': cfg['glwd_classes'],
        'code': digest(Path(__file__))}, sort_keys=True).encode()).hexdigest()
    target = out / 'wet_settings.npz'
    manifest = out / 'manifest.json'
    if target.exists() and manifest.exists():
        m = json.loads(manifest.read_text())
        if m['key'] == key and m['output_sha256'] == digest(target):
            return target
    # GLWD's WGS84 15-second fractional-class cells nest exactly in 5-minute
    # cells, 20x20. No categorical nearest-neighbour or upsampled precision.
    result = {}
    coverage = None
    with ZipFile(archive) as z:
        for group, codes in cfg['glwd_classes'].items():
            total = np.zeros((2160, 4320), np.float32)
            for code in codes:
                name = next(n for n in z.namelist() if n.endswith(f'class_{code:02d}_pct.tif'))
                with rasterio.open('/vsizip/' + str(archive.resolve()) + '/' + name, OVERVIEW_LEVEL='NONE') as ds:
                    if ds.shape != (33600, 86400) or ds.crs.to_epsg() != 4326:
                        raise ValueError('Unexpected GLWD grid')
                    if not np.allclose(tuple(ds.bounds), (-180, -56, 180, 84), atol=1e-6):
                        raise ValueError('Unexpected GLWD extent')
                    # GDAL averages an integer source before casting to float,
                    # rounding away small wet fractions. Reduce native pixels
                    # explicitly to retain fractional coverage and nodata counts.
                    a=np.ma.masked_all((1680,4320),dtype=np.float32)
                    for row in range(0,1680,20):
                        n=min(20,1680-row)
                        block=ds.read(1,window=rasterio.windows.Window(0,row*20,86400,n*20))
                        a[row:row+n]=mean_blocks(block,20,ds.nodata)
                    if np.any((a.compressed()<0)|(a.compressed()>100)):
                        raise ValueError('GLWD percentages outside 0-100')
                    if coverage is None:
                        coverage = np.zeros_like(total, bool)
                        coverage[72:1752] = ~np.ma.getmaskarray(a)
                    total[72:1752] += a.filled(0) / 100
                print('Water settings: GLWD class', code, flush=True)
            result[group] = np.clip(total, 0, 1)
    result['glwd_covered'] = coverage
    with ZipFile(wetloss) as z:
        name = 'grid_ncdf/ensemblemean/wetland_loss_1700-2020_ensemblemean_v10.nc'
        with Dataset('memory', memory=z.read(name)) as ds:
            if ds['wetland_area'].units != 'km^2' or ds['Time'][0] != 1700:
                raise ValueError('Wetland reconstruction units/date changed')
            if not np.allclose(ds['Latitude'][:], np.arange(83.75, -56, -.5)):
                raise ValueError('Wetland reconstruction latitude orientation')
            if not np.allclose(ds['Longitude'][:], np.arange(-179.75, 180, .5)):
                raise ValueError('Wetland reconstruction longitude orientation')
            wet = ds['wetland_area'][0].filled(np.nan).astype(float)
            lat = np.asarray(ds['Latitude'][:])
            area = 6371.0088**2 * np.deg2rad(.5) * (
                np.sin(np.deg2rad(lat+.25))-np.sin(np.deg2rad(lat-.25)))[:, None]
            valid = np.isfinite(wet)
            # Source ensemble contains small negative areas; retain counts in
            # metadata and clamp to physical zero, never negative potential.
            negative = int(np.sum(valid & (wet < 0)))
            frac = np.clip(np.nan_to_num(wet)/area, 0, 1)
            target_wet = np.zeros((2160, 4320), np.float32)
            target_known = np.zeros_like(target_wet, bool)
            target_wet[72:1752] = np.repeat(np.repeat(frac, 6, 0), 6, 1)
            target_known[72:1752] = np.repeat(np.repeat(valid, 6, 0), 6, 1)
            result['wetland_1700'] = target_wet
            result['wetland_1700_covered'] = target_known
    np.savez_compressed(target, **result)
    write_json(manifest, {'key': key, 'source_hashes': sources,
        'output_sha256': digest(target), 'source_negative_wetland_areas_clamped': negative,
        'glwd_years': '1990-2020', 'wetland_proxy_year': 1700,
        'glwd_resampling': 'Mean subcell percentage among valid GLWD pixels; coastal fractions conditional on mapped land. Native 15-second fractions reduced to 5 minutes; source overviews explicitly disabled.',
        'wetland_resampling': 'km2 divided by spherical 0.5-degree cell area; copied to its 6x6 5-minute children without claiming finer evidence.',
        'missing': 'Coverage masks retained. Outside -56..84 and unmapped coasts use explicit climate/terrain analogue at allocation, not silent zero.',
        'related_evidence': 'Wetland-loss reconstruction includes HYDE land use and GLWD-v1 among ensemble inputs; not independent validation.'})
    return target
