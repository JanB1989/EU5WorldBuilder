"""Global climate classification with native winter levels and explicit source age."""
import hashlib,json,re,zipfile
from pathlib import Path
import numpy as np
import pandas as pd
import requests,rasterio
from rasterio.windows import Window
from .soil_types import sha
from .location_inventory import read_zone_inventory
from .location_geometry import overlap_matrix
ROOT=Path(__file__).resolve().parents[2]


def native_values(text):
    result={}
    for m in re.finditer(r'(?m)^([\w.-]+)\s*=\s*\{([^{}]*)',text):
        v=re.search(r'\bclimate\s*=\s*(\w+)',m[2])
        if v: result[m[1]]=v[1]
    return result


def code_lookup(cfg):
    lookup=np.zeros(31,dtype=np.uint8)
    seen=set()
    for i,(name,t) in enumerate(cfg['types'].items(),1):
        for code in t['koppen_codes']:
            if code in seen or not 1<=code<=30: raise ValueError('Duplicate/invalid climate code')
            seen.add(code);lookup[code]=i
    if seen!=set(range(1,31)):raise ValueError('Incomplete Koppen crosswalk')
    return lookup


def prepare(cfg):
    raw=ROOT/'data/raw/climate';raw.mkdir(parents=True,exist_ok=True)
    archive=raw/'koppen_geiger_tif.zip'
    url=f"https://ndownloader.figshare.com/files/{cfg['source_file_id']}"
    if not archive.exists():
        with requests.get(url,stream=True,timeout=120) as r:
            r.raise_for_status()
            with archive.with_suffix('.part').open('wb') as f:
                for b in r.iter_content(1024*1024):f.write(b)
        archive.with_suffix('.part').replace(archive)
    if hashlib.md5(archive.read_bytes()).hexdigest()!=cfg['archive_md5']:raise ValueError('Climate archive checksum mismatch')
    member=cfg['source_period']+'/koppen_geiger_0p00833333.tif'
    with zipfile.ZipFile(archive) as z:
        for n in [member,'legend.txt']:
            target=raw/n
            if not target.exists():z.extract(n,raw)
    source=raw/member
    cache=ROOT/'data/processed/climate';cache.mkdir(parents=True,exist_ok=True)
    dest=cache/'fractions.npy';manifest=cache/'manifest.json'
    inputs={'source_sha256':sha(source),'code_sha256':sha(Path(__file__))}
    if dest.exists() and manifest.exists() and json.loads(manifest.read_text()).get('inputs')==inputs:return dest
    # Retain ALL thirty fine-source classes, rather than selecting the winning
    # category before EU5 aggregation. Zero means missing/ocean, not an arid class.
    out=np.lib.format.open_memmap(dest,mode='w+',dtype=np.float32,shape=(31,2160,4320))
    with rasterio.open(source) as ds:
        if ds.shape!=(21600,43200) or ds.crs.to_epsg()!=4326:raise ValueError('Unexpected climate grid')
        if not np.allclose(tuple(ds.transform)[:6],(1/120,0,-180,0,-1/120,90)):raise ValueError('Climate grid alignment')
        for y in range(0,21600,100):
            a=ds.read(1,window=Window(0,y,43200,100))
            if a.max()>30:raise ValueError('Unknown source class')
            # Ten by ten fine pixels per 5-minute cell, cosine latitude weighting.
            idx=(np.arange(100)[:,None]//10*4320+np.arange(43200)[None,:]//10)
            lat=90-(np.arange(y,y+100)+.5)/120
            w=np.broadcast_to(np.cos(np.deg2rad(lat))[:,None],a.shape)
            counts=np.bincount((idx*31+a).ravel(),weights=w.ravel(),minlength=10*4320*31).reshape(10,4320,31)
            counts/=counts.sum(axis=2,keepdims=True)
            out[:,y//10:y//10+10,:]=counts.transpose(2,0,1)
    out.flush();del out
    manifest.write_text(json.dumps({'inputs':inputs,'source_url':url,'article_url':'https://doi.org/10.6084/m9.figshare.21789074',
        'archive_md5':cfg['archive_md5'],'source_period':cfg['source_period'],'citation':'Beck et al. (2023), doi:10.1038/s41597-023-02549-6; archive V3, Figshare article version 2',
        'license':'CC-BY-4.0','units':'Fraction of complete 5-minute cell; band 0 is unavailable/ocean',
        'transformation':'Cosine-latitude weighted counts of aligned 1 km classes, preserving all 30 class fractions'},indent=2))
    return dest


def assign(d,shares,cfg):
    names=list(cfg['types']);lookup=code_lookup(cfg)
    grouped=np.column_stack([shares[:,lookup==i].sum(axis=1) for i in range(1,len(names)+1)])
    coverage=shares[:,1:].sum(axis=1)
    winner=np.argmax(grouped,axis=1)
    out=d.copy();out['source_coverage']=coverage
    out['climate']=[names[i] for i in winner]
    missing=(coverage<=1e-8)|(~out.is_ownable)
    out.loc[missing,'climate']=out.loc[missing,'vanilla_climate']
    out['dominant_share']=np.divide(grouped.max(axis=1),coverage,out=np.zeros(len(out)),where=coverage>0)
    out['inferred']=coverage<=1e-8
    out['low_confidence']=(coverage<.5)|(out.dominant_share<.6)
    out['assignment_source']=np.where(coverage>1e-8,'Koppen-Geiger 1901-1930 proxy','Native fallback: no source overlap')
    out.loc[~out.is_ownable,'assignment_source']='Native non-ownable zone'
    for code in range(1,31):out[f'kg_{code:02d}_share']=np.divide(shares[:,code],coverage,out=np.zeros(len(out)),where=coverage>0)
    return out


def render(raw,d,cfg,out):
    from PIL import Image
    im=Image.open(raw/'locations.png').convert('RGB');im.thumbnail((2400,1200),Image.Resampling.NEAREST)
    a=np.asarray(im,dtype=np.int32);ids=(a[:,:,0]<<16)|(a[:,:,1]<<8)|a[:,:,2]
    lut=np.full((2**24,3),[20,34,46],np.uint8)
    for r in d.itertuples():
        if r.is_ownable:lut[int(r.map_color_rgb,16)]=cfg['types'][r.climate]['color']
        elif 'sea_zones' not in r.game_zone_class and r.game_zone_class!='lakes':lut[int(r.map_color_rgb,16)]=[65,72,73]
    Image.fromarray(lut[ids]).save(out/'climate.png')
    wc={'none':[199,166,95],'mild':[127,170,147],'normal':[98,150,193],'severe':[195,207,233]}
    for r in d.itertuples():
        if r.is_ownable:lut[int(r.map_color_rgb,16)]=wc[r.winter]
    Image.fromarray(lut[ids]).save(out/'winter.png')
    counts=d[d.is_ownable].climate.value_counts()
    rows=''.join(f'<tr><td><i style="background:rgb{tuple(t["color"])}"></i>{t["label"]}</td><td>{t["winter"].title()}</td><td>{counts.get(n,0):,}</td></tr>' for n,t in cfg['types'].items())
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Climate and winter</title><style>body{background:#14222e;color:#e4e9ec;font:16px system-ui;margin:28px auto;max-width:1400px;padding:0 20px}img{width:100%}td,th{text-align:left;padding:6px 25px 6px 0}i{display:inline-block;width:16px;height:16px;margin-right:10px;border-radius:3px}a{color:#85c9ec}.note{color:#bbc8d2;max-width:950px}</style><h1>Climate and winter</h1><p>18 climate types. The existing winter severity remains inside the Climate tooltip. All ownable locations assigned. Dark grey marks non-ownable land.</p><p class="note">Geographic prototype for 1300, using the published 1901–1930 climate map as a proxy. This is not a medieval climate reconstruction. Winter levels are representative game categories. No new moisture attribute.</p><h2>Climate</h2><img src="climate.png"><table><tr><th>Climate</th><th>Winter</th><th>Locations</th></tr>'+rows+'<h2>Winter severity</h2><img src="winter.png"><p>Ochre: none · Green: mild · Blue: normal · Pale blue: severe.</p><p><a href="locations.csv">Assignments and source shares</a> · <a href="manifest.json">Evidence and limitations</a></p><p class="note">Climate data: Beck et al. (2023), CC BY 4.0. <a href="https://www.gloh2o.org/koppen/">Dataset</a>. Climate boundaries and medieval rainfall remain uncertain; small islands without source overlap use a labelled native fallback.</p>')


def build(config_path=None):
    cp=Path(config_path or ROOT/'configs/climate.json').resolve();cfg=json.loads(cp.read_text());code_lookup(cfg)
    evidence=prepare(cfg);out=ROOT/cfg['output_directory'];out.mkdir(parents=True,exist_ok=True)
    raw=ROOT/'data/raw/location_inputs';csv=out/'locations.csv';mp=out/'manifest.json'
    paths=[cp,Path(__file__),evidence.parent/'manifest.json',raw/'inventory.parquet',raw/'game_templates.txt',raw/'game_default.map',raw/'game_named_locations.txt',ROOT/'src/historical_agriculture/location_geometry.py',ROOT/'src/historical_agriculture/location_inventory.py']
    inputs={str(p.relative_to(ROOT)):sha(p) for p in paths}
    if mp.exists() and csv.exists():
        old=json.loads(mp.read_text())
        if old.get('inputs')==inputs and old.get('csv_sha256')==sha(csv):return old
    inv=pd.read_parquet(raw/'inventory.parquet').sort_values('location_tag').reset_index(drop=True)
    weights,geometry=overlap_matrix(ROOT,inv,ROOT/'artifacts/locations');den=np.asarray(weights.sum(axis=1)).ravel()
    if weights.shape!=(len(inv),2160*4320) or (den<=0).any():raise ValueError('Climate overlap mismatch')
    zones=read_zone_inventory(raw);vanilla=native_values((raw/'game_templates.txt').read_text(encoding='utf-8-sig'))
    d=inv[['location_tag','map_color_rgb','province','region','macro_region']].merge(zones[['location_tag','is_ownable','game_zone_class']],on='location_tag',validate='one_to_one',sort=False)
    if d.location_tag.tolist()!=inv.location_tag.tolist():raise ValueError('Climate overlap order')
    d['vanilla_climate']=d.location_tag.map(vanilla)
    z=np.load(evidence,mmap_mode='r');shares=np.column_stack([np.asarray(weights@z[i].ravel())/den for i in range(31)])
    d=assign(d,shares,cfg)
    extras=zones[~zones.location_tag.isin(d.location_tag)].copy()
    if extras.is_ownable.any():raise ValueError('Ownable climate missing from inventory')
    extras['vanilla_climate']=extras.location_tag.map(vanilla);extras['climate']=extras.vanilla_climate
    extras['assignment_source']='Native non-ownable zone';extras['inferred']=False;extras['low_confidence']=False
    d=pd.concat([d,extras],ignore_index=True).sort_values('location_tag').reset_index(drop=True)
    if d.climate.isna().any() or not set(d.climate)<=set(cfg['types']) or d.location_tag.duplicated().any():raise ValueError('Incomplete climate assignment')
    d['winter']=d.climate.map({n:t['winter'] for n,t in cfg['types'].items()})
    d['game_climate']=d.climate.map({n:t['game_key'] for n,t in cfg['types'].items()})
    d.to_csv(csv,index=False,float_format='%.8f');render(raw,d,cfg,out)
    counts=d[d.is_ownable].climate.value_counts().to_dict()
    report={'year':cfg['year'],'source_period':cfg['source_period'],'inputs':inputs,'csv_sha256':sha(csv),'ownable_locations':int(d.is_ownable.sum()),'total_zones':len(d),'ownable_missing':0,'ownable_distribution':counts,'winter_distribution':d[d.is_ownable].winter.value_counts().to_dict(),'native_fallback_ownable':int(d[d.is_ownable].inferred.sum()),'mixed_or_low_coverage_ownable':int(d[d.is_ownable].low_confidence.sum()),'rare_types_under_25':[n for n in cfg['types'] if counts.get(n,0)<25],'assumptions':cfg['assumptions'],'source_manifest':json.loads((evidence.parent/'manifest.json').read_text()),'geometry':geometry,'scientific_status':'1901-1930 observed climatology proxy; 1300 climatic reconstruction not implemented.'}
    mp.write_text(json.dumps(report,indent=2)+'\n');return report
