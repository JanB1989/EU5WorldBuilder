"""Pinned ecological geometry, independent of historical crop-system inference."""
import json
import math
import zipfile
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.windows import Window, transform as window_transform
import shapefile
from .provenance import digest, write_json

def acquire_geometry(root, config):
    path=root/config['source_archive']
    if not path.exists():
        import requests
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix('.partial')
        with requests.get(config['source_url'],stream=True,timeout=120) as response:
            response.raise_for_status()
            with temporary.open('wb') as f:
                for chunk in response.iter_content(1048576):f.write(chunk)
        if digest(temporary)!=config['source_sha256']:raise ValueError('Unrecognized ecological geometry version')
        temporary.replace(path)
    if digest(path)!=config['source_sha256']:raise ValueError('Ecological geometry checksum mismatch')
    return path

def system_lookup(regions, source_ids):
    lookup={}
    for region in regions:
        for eco in region['ecoregion_ids']:
            if eco in lookup:raise ValueError(f'Duplicate ecoregion assignment: {eco}')
            lookup[eco]=region['id']
    if set(lookup)!=set(source_ids):raise ValueError('Ecoregion assignments do not match source catalogue')
    return lookup

def burn_polygon(array, geometry, bounds, transform, value):
    """Burn cell centres only; polygon holes and multipart outlines are retained."""
    left,bottom,right,top=bounds
    col0=max(0,math.floor((left-transform.c)/transform.a))
    col1=min(array.shape[1],math.ceil((right-transform.c)/transform.a))
    row0=max(0,math.floor((top-transform.f)/transform.e))
    row1=min(array.shape[0],math.ceil((bottom-transform.f)/transform.e))
    if col1<=col0 or row1<=row0:return
    window=Window(col0,row0,col1-col0,row1-row0)
    mask=rasterize([(geometry,1)],out_shape=(row1-row0,col1-col0),
                   transform=window_transform(window,transform),fill=0,dtype='uint8')
    tile=array[row0:row1,col0:col1]
    tile[mask==1]=value

def geometry_grid(root, config, profile, out):
    path=acquire_geometry(root,config)
    with zipfile.ZipFile(path) as z:
        crs=rasterio.crs.CRS.from_wkt(z.read('Ecoregions2017.prj').decode())
    if crs.to_epsg()!=4326 or profile['crs'].to_epsg()!=4326:raise ValueError('Ecoregion and raster CRS mismatch')
    reader=shapefile.Reader(str(path),encoding='latin1')
    records=[r.as_dict() for r in reader.records()]
    lookup=system_lookup(config['regions'],[r['ECO_ID'] for r in records])
    eco=np.full((profile['height'],profile['width']),-1,dtype=np.int16)
    for i,record in enumerate(records):
        shape=reader.shape(i)
        burn_polygon(eco,shape.__geo_interface__,shape.bbox,profile['transform'],record['ECO_ID'])
    region=np.zeros_like(eco)
    for eco_id,system in lookup.items():region[eco==eco_id]=system
    systems={r['id']:r for r in config['regions']}
    ledger=[]
    for record in records:
        eco_id=record['ECO_ID'];system=systems[lookup[eco_id]]
        ledger.append({'ecoregion_id':eco_id,'ecoregion':record['ECO_NAME'],
                      'biome':record['BIOME_NAME'],'realm':record['REALM'],
                      'system_id':system['id'],'system':system['name'],
                      'crops':system['crops'],'historical_source':system['source'],
                      'assignment_status':'inferred','cells':int(np.sum(eco==eco_id))})
    write_json(out/'ecoregion_ledger.json',{'source':config['source_url'],'sha256':config['source_sha256'],
               'license':config['source_license'],'rasterization':'polygon cell centres; unmatched coastline cells remain unresolved',
               'ecoregions':ledger})
    return eco,region
