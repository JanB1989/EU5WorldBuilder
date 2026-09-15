"""HWSD component composition -> complete, source-labelled EU5 soil assignments.

No crop yields, population, capacity or fertility grades enter this classifier.
Native 30-arcsecond mapping units are sampled at four points per registered game
pixel; their component shares are retained until final location aggregation.
"""
from pathlib import Path
import hashlib
import json
import zipfile
import urllib.request

import numpy as np
import pandas as pd
from PIL import Image
from scipy.spatial import cKDTree

from .location_inventory import read_zone_inventory

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while b := f.read(4 * 1024 * 1024): h.update(b)
    return h.hexdigest()


def classify_components(d, cfg):
    """Organic material takes precedence; stones never inferred from depth."""
    result = np.zeros(len(d), dtype=np.uint8)
    for name, codes in cfg['texture_groups'].items():
        result[d.TEXTURE_USDA.isin(codes)] = cfg['types'][name]['id']
    stony = (d.COARSE >= cfg['coarse_fragment_threshold_percent']) | d.PHASE1.isin(cfg['stony_phases']) | d.PHASE2.isin(cfg['stony_phases'])
    result[stony] = cfg['types']['stony']['id']
    group = d.WRB2.fillna('').str.upper()
    result[group == 'HS'] = cfg['types']['peat']['id']
    result[group.isin(['GG', 'WR', 'ND', 'IS'])] = 0
    return result


def fetch_sources(folder):
    folder.mkdir(parents=True, exist_ok=True)
    sources = {}
    for archive, members in [('HWSD2_DB.zip', ['HWSD2.mdb']), ('HWSD2_RASTER.zip', ['HWSD2.bil', 'HWSD2.hdr', 'HWSD2.prj'])]:
        url = 'https://s3.eu-west-1.amazonaws.com/data.gaezdev.aws.fao.org/HWSD/' + archive
        p = folder / archive
        if not p.exists():
            temp = p.with_suffix('.download')
            with urllib.request.urlopen(url, timeout=120) as r, temp.open('wb') as f:
                while b := r.read(4 * 1024 * 1024): f.write(b)
            temp.replace(p)
        with zipfile.ZipFile(p) as z:
            for name in members:
                if not (folder / name).exists(): z.extract(name, folder)
        sources[archive] = {'url': url, 'sha256': sha(p)}
    return sources


def component_lookup(folder, cfg):
    from access_parser import AccessParser
    cache = folder / 'topsoil_components.parquet'
    stamp = folder / 'topsoil_components_source.sha256'
    fingerprint = sha(folder / 'HWSD2.mdb')
    if cache.exists() and stamp.exists() and stamp.read_text() == fingerprint:
        d = pd.read_parquet(cache)
    else:
        print('Reading HWSD soil components', flush=True)
        d = pd.DataFrame(AccessParser(str(folder / 'HWSD2.mdb')).parse_table('HWSD2_LAYERS'))
        d = d[d.LAYER == 'D1'].copy()
        d.to_parquet(cache, index=False); stamp.write_text(fingerprint)
    codes = classify_components(d, cfg)
    shares = np.zeros((65536, 6), dtype=np.float32)
    for k in range(1, 7):
        take = codes == k
        np.add.at(shares[:, k-1], d.loc[take, 'HWSD2_SMU_ID'].to_numpy(int), d.loc[take, 'SHARE'].to_numpy(float) / 100)
    if np.any(shares.sum(axis=1) > 1.001): raise ValueError('HWSD component shares exceed 100%')
    return shares, {'topsoil_components': len(d), 'unclassified_components': int((codes == 0).sum()), 'component_counts': {name: int((codes == v['id']).sum()) for name,v in cfg['types'].items()}}


def sample_locations(raw, source, shares, zones):
    """Four quadrature points per game pixel, latitude-weighted; not exact overlap."""
    Image.MAX_IMAGE_PIXELS = None
    im = Image.open(raw / 'locations.png').convert('RGB')
    width, height = im.size
    tf = json.loads((raw / 'transform.json').read_text())
    lut = np.full(2**24, -1, dtype=np.int32)
    lut[[int(c,16) for c in zones.map_color_rgb]] = np.arange(len(zones))
    water = zones.game_zone_class.str.contains('sea_zones|lakes').to_numpy()
    # Source dimensions and coordinate convention are checked, never assumed silently.
    import rasterio
    with rasterio.open(source / 'HWSD2.bil') as r:
        if r.shape != (21600,43200) or not np.allclose(tuple(r.transform)[:6], (1/120,0,-180,0,-1/120,90)):
            raise ValueError('Unexpected HWSD grid')
    raster = np.memmap(source / 'HWSD2.bil', mode='r', dtype='<u2', shape=(21600,43200))
    totals = np.zeros((len(zones),shares.shape[1])); denominator = np.zeros(len(zones))
    xpos = np.arange(width)
    cols = []
    for off in [-.25,.25]:
        lon = np.polynomial.polynomial.polyval((xpos + off - tf['x_mean']) / tf['x_scale'], tf['lon_coefficients'])
        cols.append(np.floor(((lon + 180) % 360) * 120).astype(int).clip(0,43199))
    sumx = np.zeros(len(zones)); sumy = np.zeros(len(zones)); pixels = np.zeros(len(zones))
    for start in range(0,height,64):
        stop = min(start+64,height)
        a = np.asarray(im.crop((0,start,width,stop)), dtype=np.int32)
        ids = lut[(a[:,:,0]<<16)|(a[:,:,1]<<8)|a[:,:,2]]
        yy,xx = np.nonzero(ids >= 0); loc = ids[yy,xx]
        if not len(loc): continue
        global_y = yy + start
        pixels += np.bincount(loc, minlength=len(zones))
        sumx += np.bincount(loc, weights=xx, minlength=len(zones))
        sumy += np.bincount(loc, weights=global_y, minlength=len(zones))
        land = ~water[loc]; yy,xx,loc,global_y = yy[land],xx[land],loc[land],global_y[land]
        # Equal-sized game pixels represent different physical latitudinal strips.
        row_y = np.arange(start,stop)
        hi = np.polynomial.polynomial.polyval((row_y-.5-tf['y_mean'])/tf['y_scale'],tf['lat_coefficients'])
        lo = np.polynomial.polynomial.polyval((row_y+.5-tf['y_mean'])/tf['y_scale'],tf['lat_coefficients'])
        w = np.abs(np.sin(np.deg2rad(hi.clip(-90,90)))-np.sin(np.deg2rad(lo.clip(-90,90))))[yy]
        denominator += np.bincount(loc, weights=w, minlength=len(zones))
        for off in [-.25,.25]:
            lat = np.polynomial.polynomial.polyval((global_y+off-tf['y_mean'])/tf['y_scale'],tf['lat_coefficients'])
            rows = np.floor((90-lat)*120).astype(int).clip(0,21599)
            for col in cols:
                values = shares[raster[rows,col[xx]]]
                for k in range(shares.shape[1]):
                    totals[:,k] += np.bincount(loc, weights=values[:,k]*w*.25, minlength=len(zones))
        if start % 1024 == 0: print(f'Soil/game sampling {start}/{height}', flush=True)
    if (pixels == 0).any(): raise ValueError('Game zones missing from bitmap')
    cx,cy = sumx/pixels,sumy/pixels
    lon = np.polynomial.polynomial.polyval((cx-tf['x_mean'])/tf['x_scale'],tf['lon_coefficients'])
    lat = np.polynomial.polynomial.polyval((cy-tf['y_mean'])/tf['y_scale'],tf['lat_coefficients'])
    return totals,denominator,lon,lat


def finalize(zones, totals, denominator, lon, lat, cfg):
    d = zones.copy(); d['longitude'] = ((lon+180)%360)-180; d['latitude'] = lat
    observed = totals.sum(axis=1)
    water = d.game_zone_class.str.contains('sea_zones|lakes').to_numpy()
    coverage = np.divide(observed,denominator,out=np.zeros(len(d)),where=denominator>0)
    fractions = np.divide(totals,observed[:,None],out=np.zeros_like(totals),where=observed[:,None]>0)
    direct = (~water)&(observed>0); missing = (~water)&(~direct)
    donors = np.flatnonzero(direct)
    if not len(donors): raise ValueError('No directly sampled soils')
    radians = np.deg2rad(np.column_stack([d.longitude,d.latitude]))
    xyz = np.column_stack([np.cos(radians[:,1])*np.cos(radians[:,0]),np.cos(radians[:,1])*np.sin(radians[:,0]),np.sin(radians[:,1])])
    d['assignment_source'] = np.where(water,'water','HWSD sampled composition')
    d['analogue_location'] = ''; d['analogue_distance_km'] = 0.
    if missing.any():
        distance,near = cKDTree(xyz[donors]).query(xyz[missing]); source = donors[near]
        fractions[missing] = fractions[source]
        d.loc[missing,'assignment_source'] = 'nearest soil-bearing location; inferred'
        d.loc[missing,'analogue_location'] = d.location_tag.iloc[source].to_numpy()
        d.loc[missing,'analogue_distance_km'] = 2*6371.0088*np.arcsin(np.minimum(distance/2,1))
    d['source_coverage'] = coverage
    d['dominant_share'] = fractions.max(axis=1)
    for k,name in enumerate(cfg['types']): d[name+'_share'] = fractions[:,k]
    names = np.array(list(cfg['types']))
    d['soil_type'] = np.where(water,'water',names[fractions.argmax(axis=1)])
    d['soil_id'] = np.where(water,0,fractions.argmax(axis=1)+1)
    d['inferred'] = missing
    d['low_confidence'] = (~water)&((coverage<.5)|(d.dominant_share<.5)|missing)
    if not np.allclose(fractions[~water].sum(axis=1),1): raise ValueError('Soil fractions fail conservation')
    if not d.loc[d.is_ownable,'soil_type'].isin(cfg['types']).all(): raise ValueError('Missing ownable soil type')
    return d


def render_preview(raw, d, cfg, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    im = Image.open(raw/'locations.png').convert('RGB'); im.thumbnail((2400,1200),Image.Resampling.NEAREST)
    a=np.asarray(im,dtype=np.int32); lut=np.full((2**24,3),[17,31,45],dtype=np.uint8)
    for row in d.itertuples():
        if row.soil_type in cfg['types']:lut[int(row.map_color_rgb,16)] = cfg['types'][row.soil_type]['color']
    colors=lut[(a[:,:,0]<<16)|(a[:,:,1]<<8)|a[:,:,2]]
    fig,ax=plt.subplots(figsize=(16,8),facecolor='#111f2d');ax.imshow(colors);ax.axis('off')
    ax.set_title('Soil type — EU5 locations',color='white',fontsize=19)
    legend=ax.legend(handles=[Patch(color=np.array(v['color'])/255,label=v['label']) for v in cfg['types'].values()],loc='lower center',ncol=6,facecolor='#172a3a',edgecolor='none')
    for t in legend.get_texts():t.set_color('white')
    fig.tight_layout();fig.savefig(output/'soil_types.png',dpi=140,facecolor=fig.get_facecolor());plt.close(fig)


def build(config_path=None):
    cp=Path(config_path or ROOT/'configs/soil_types.json').resolve();cfg=json.loads(cp.read_text())
    source=ROOT/cfg['source_directory'];out=ROOT/cfg['output_directory'];out.mkdir(parents=True,exist_ok=True)
    sources=fetch_sources(source);raw=ROOT/'data/raw/location_inputs'
    inputs={str(p.relative_to(ROOT)):sha(p) for p in [cp,Path(__file__),raw/'locations.png',raw/'transform.json',raw/'game_default.map',raw/'game_templates.txt',raw/'game_named_locations.txt']}
    inputs['archives']=sources
    manifest=out/'manifest.json'
    if manifest.exists() and (out/'locations.csv').exists():
        prior=json.loads(manifest.read_text())
        if prior.get('inputs')==inputs and prior.get('csv_sha256')==sha(out/'locations.csv'):return prior
    shares,component_audit=component_lookup(source,cfg)
    zones=read_zone_inventory(raw)
    totals,denominator,lon,lat=sample_locations(raw,source,shares,zones)
    d=finalize(zones,totals,denominator,lon,lat,cfg);d.to_csv(out/'locations.csv',index=False,float_format='%.8f')
    render_preview(raw,d,cfg,out)
    land=d[d.soil_id>0];own=d[d.is_ownable]
    report={'schema_version':1,'inputs':inputs,'csv_sha256':sha(out/'locations.csv'),'source_components':component_audit,
       'game_zones':len(d),'land_locations':len(land),'ownable_locations':len(own),'ownable_missing':int((own.soil_id==0).sum()),
       'ownable_distribution':own.soil_type.value_counts().to_dict(),'land_distribution':land.soil_type.value_counts().to_dict(),
       'inferred_land_locations':int(land.inferred.sum()),'inferred_ownable_locations':int(own.inferred.sum()),
       'low_confidence_land_locations':int(land.low_confidence.sum()),'maximum_analogue_distance_km':float(land.analogue_distance_km.max()),
       'notes':['Modern soil inventory used as approximate physical substrate; not a measured 1300 soil map.',
       'Classify native HWSD components first. Four samples per registered game pixel approximate overlap; component shares and latitudinal area weights retained.',
       'Dominant type selected at final location aggregation. Missing land uses nearest soil-bearing location with explicit donor and distance.',
       'Sand includes sandy loam; Loam includes clay loam and sandy clay loam. Peat takes precedence over Stony; depth is not a classifier.',
       'No fertility, food or capacity bonus is assigned. Geography registration and analogue records limit spatial certainty.']}
    manifest.write_text(json.dumps(report,indent=2));return report
