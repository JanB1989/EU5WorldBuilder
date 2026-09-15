"""Acquire and aggregate published landform evidence without sampling away small features."""
from pathlib import Path
import json,hashlib,zipfile
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import reproject,Resampling
from rasterio.windows import Window
from scipy.ndimage import maximum_filter,minimum_filter
from .soil_types import sha
ROOT=Path(__file__).resolve().parents[2]
GRID=from_origin(-180,90,1/12,1/12)
SHAPE=(2160,4320)
URLS={
 'landforms.tif':'https://zenodo.org/api/records/1464846/files/dtm_landform_usgs.ecotapestry_c_250m_s0..0cm_2014_v1.0.tif/content',
 'landforms.csv':'https://zenodo.org/api/records/1464846/files/dtm_landform_usgs.ecotapestry_c_250m_s0..0cm_2014_v1.0.tif.csv/content',
 'geomorphons.tif':'https://hs.pangaea.de/Maps/DEM_Geomorpho90m/dtm_geom_merit.dem_m_250m_s0..0cm_2018_v1.0.tif',
 'gfplain.rar':'https://ndownloader.figshare.com/files/12186356',
 'deltas.xlsx':'https://media.springernature.com/original/springer-static/esm/art%3A10.1038%2Fs41467-020-18531-4/MediaObjects/41467_2020_18531_MOESM3_ESM.xlsx'}
SOURCES={
 'landforms':{'citation':'Hengl 2018, Global landform and lithology class, EcoTapestry 2014, v1.0','url':'https://doi.org/10.5281/zenodo.1464846','license':'CC-BY-SA-4.0','units':'categorical: 1 breaks/foothills, 2 flat plains, 3 high mountains/deep canyons, 4 hills, 5 low hills, 6 low mountains, 7 smooth plains; 255 missing'},
 'geomorphons':{'citation':'Amatulli et al. 2020 Geomorpho90m, 250m publication raster','url':'https://doi.org/10.1594/PANGAEA.899135','license':'CC-BY-4.0','units':'geomorphon classes 1-10; 0 missing; class9 valley, class1 flat'},
 'gfplain':{'citation':'Nardi et al. 2019 GFPLAIN250m v1','url':'https://doi.org/10.6084/m9.figshare.6665165.v1','license':'CC-BY-4.0','units':'0 mapped floodplain, 255 unclassified background, not a water-depth grid'},
 'deltas':{'citation':'Edmonds et al. 2020 Nature Communications 11:4741, Supplementary Data1','url':'https://doi.org/10.1038/s41467-020-18531-4','license':'CC-BY-4.0','units':'five latitude/longitude point pairs per delta; 2174 rows'},
 'elevation':{'citation':'NOAA ETOPO2022 60 arc-second surface, cached source','url':'https://www.ncei.noaa.gov/products/etopo-global-relief-model','license':'Public domain (US Government)','units':'metres; local relief from 11x11 neighbourhood (~20km N-S)'},
 'riverine':{'citation':'GLWD v2 riverine wet settings, existing documented preprocessing','url':'https://www.hydrosheds.org/products/glwd','license':'CC-BY-4.0','units':'5 arc-minute cell fraction from native 15 arc-second classes; supplementary positive evidence only'}}

def acquire():
 import requests,libarchive
 p=ROOT/'data/raw/topography';p.mkdir(parents=True,exist_ok=True)
 for name,url in URLS.items():
  dst=p/name
  if not dst.exists():
   with requests.get(url,stream=True,timeout=(30,120)) as r:
    r.raise_for_status()
    with dst.with_suffix(dst.suffix+'.part').open('wb') as f:
     for b in r.iter_content(1024*1024):f.write(b)
   dst.with_suffix(dst.suffix+'.part').rename(dst)
 # Verify the publisher checksum, not merely our locally calculated identity.
 if hashlib.md5((p/'landforms.tif').read_bytes()).hexdigest()!='08fb48905aaf7dc3ea66a9d6fd18edf4':raise ValueError('EcoTapestry checksum differs from publisher')
 if not list((p/'gfplain').rglob('*.TIF')):
  with libarchive.file_reader(str(p/'gfplain.rar')) as a:
   for e in a:
    if e.isfile:
     dst=p/'gfplain'/Path(e.pathname).name;dst.parent.mkdir(exist_ok=True)
     with dst.open('wb') as f:
      for b in e.get_blocks():f.write(b)
  for z in (p/'gfplain').glob('*.zip'):
   with zipfile.ZipFile(z) as a:
    for e in a.infolist():
     if e.filename.lower().endswith(('.tif','.tfw','.xml')):
      dst=p/'gfplain'/z.stem/Path(e.filename).name;dst.parent.mkdir(exist_ok=True)
      dst.write_bytes(a.read(e))
 return p

def stream_fractions(path,mode):
 """Native-pixel binary masks -> exact GDAL area average, no categorical overviews.

 Ten GAEZ rows at once keep peak memory bounded. Read a one-km halo for
 valley-floor adjacency. The 250m files have slightly different grid origins;
 every stripe uses its own real affine transform rather than forced nesting.
 """
 out={k:np.zeros(SHAPE,np.float32) for k in ('value','coverage')}
 with rasterio.open(path) as src:
  if src.crs.to_epsg()!=4326 or not .00208<src.res[0]<.00209:raise ValueError('Unexpected native landform resolution')
  for r in range(0,2160,10):
   h=min(10,2160-r);top=90-r/12;bottom=top-h/12
   a=max(0,int(np.floor((src.bounds.top-top)/src.res[1]))-5)
   b=min(src.height,int(np.ceil((src.bounds.top-bottom)/src.res[1]))+5)
   if b<=a:continue
   win=Window(0,a,src.width,b-a);v=src.read(1,window=win)
   if mode=='rolling':valid=(v>=1)&(v<=7);mask=(v==5)|(v==7)
   elif mode=='valleys':
    valid=(v>=1)&(v<=10)
    mask=(v==9)|((v==1)&maximum_filter(v==9,size=9,mode='constant'))
   else:raise ValueError(mode)
   for k,arr in [('value',mask),('coverage',valid)]:
    reproject(arr.astype('float32'),out[k][r:r+h],src_transform=src.window_transform(win),src_crs=src.crs,
      dst_transform=from_origin(-180,top,1/12,1/12),dst_crs='EPSG:4326',resampling=Resampling.average,dst_nodata=0)
   if r%300==0:print(mode,'latitude',round(top),flush=True)
 return out

def flood_fraction(paths):
 result=np.zeros(SHAPE,np.float32)
 for p in paths:
  print('Floodplain',p.name,flush=True)
  with rasterio.open(p) as src:
   # Background is encoded nodata in the publisher file; convert it to zero
   # before averaging so a tiny mapped patch cannot become 100% floodplain.
   for r in range(0,src.height,400):
    win=Window(0,r,src.width,min(400,src.height-r));a=src.read(1,window=win)
    t=src.window_transform(win);top=t.f;bottom=top-a.shape[0]*src.res[1]
    r0=max(0,int(np.floor((90-top)*12)));r1=min(2160,int(np.ceil((90-bottom)*12)))
    if r1<=r0:continue
    # Weighted contribution by actual stripe overlap. Each stripe can cover
    # partial GAEZ rows, which must be added, not maximized or renormalized.
    dst=np.zeros((r1-r0,4320),np.float32)
    reproject((a==0).astype('float32'),dst,src_transform=t,src_crs=src.crs,
      dst_transform=from_origin(-180,90-r0/12,1/12,1/12),dst_crs='EPSG:4326',resampling=Resampling.average,dst_nodata=0)
    yy=90-np.arange(r0,r1)/12
    weight=np.clip((np.minimum(yy,top)-np.maximum(yy-1/12,bottom))*12,0,1)
    result[r0:r1]+=dst*weight[:,None]
 return np.clip(result,0,1)

def terrain_context(path):
 relief=np.zeros(SHAPE,np.float32);height=np.zeros(SHAPE,np.float32)
 with rasterio.open(path) as src:
  if src.shape!=(10800,21600):raise ValueError('Unexpected ETOPO grid')
  for r in range(0,2160,20):
   a=max(0,r*5-5);b=min(src.height,(r+20)*5+5)
   v=src.read(1,window=Window(0,a,src.width,b-a)).astype('float32')
   v=np.maximum(v,0) # Do not mistake coastal ocean depth for land relief.
   rng=maximum_filter(v,size=11,mode='nearest')-minimum_filter(v,size=11,mode='nearest')
   start=r*5-a;h=min(20,2160-r)
   reduce=lambda x:x[start:start+h*5].reshape(h,5,4320,5).mean(axis=(1,3))
   relief[r:r+h]=reduce(rng);height[r:r+h]=reduce(v)
 return relief,height

def delta_fraction(path,elevation_path,max_elevation):
 from shapely.geometry import MultiPoint
 from rasterio.features import rasterize
 d=pd.read_excel(path,header=2)
 if len(d)!=2174:raise ValueError('Unexpected delta table length')
 features=[]
 for row in d.to_dict('records'):
  points=[(float(row[k+'_Lon']),float(row[k+'_Lat'])) for k in ['RM','DN','S1','S2','OB']]
  if not np.isfinite(points).all():raise ValueError('Delta missing coordinates')
  # Unwrap date-line deltas around their river mouth before hull construction.
  anchor=points[0][0];points=[(anchor+(x-anchor+180)%360-180,y) for x,y in points]
  g=MultiPoint(points).convex_hull
  from shapely.affinity import translate
  for shift in [-360,0,360]:
   q=translate(g,xoff=shift)
   if q.bounds[0]<180 and q.bounds[2]>-180:features.append(q)
 result=np.zeros(SHAPE,np.float32)
 with rasterio.open(elevation_path) as src:
  for r in range(0,2160,20):
   h=min(20,2160-r);top=90-r/12;bottom=top-h/12
   geoms=[g for g in features if g.bounds[1]<top and g.bounds[3]>bottom]
   if not geoms:continue
   win=Window(0,r*5,21600,h*5);elev=src.read(1,window=win)
   a=rasterize(((g,1) for g in geoms),out_shape=elev.shape,transform=src.window_transform(win),dtype='uint8')
   a=a*((elev>=0)&(elev<=max_elevation))
   result[r:r+h]=a.reshape(h,5,4320,5).mean(axis=(1,3))
 return result

def prepare(cfg):
 raw=acquire();out=ROOT/'data/processed/topography';out.mkdir(parents=True,exist_ok=True)
 etopo=ROOT/'data/raw/location_inputs/hydrology/ETOPO_2022_v1_60s_N90W180_surface.tif'
 wet=ROOT/'data/processed/water_management/wet_settings.npz'
 paths=[raw/n for n in URLS]+[etopo,wet,Path(__file__)]
 inputs={str(p.relative_to(ROOT)):sha(p) for p in paths}
 inputs['delta_max_elevation_m']=cfg['thresholds']['delta_max_elevation_m']
 mp=out/'manifest.json';dst=out/'evidence.npz'
 if mp.exists() and dst.exists():
  old=json.loads(mp.read_text())
  if old.get('inputs')==inputs and old.get('sha256')==sha(dst):return dst
 rolling=stream_fractions(raw/'landforms.tif','rolling')
 valley=stream_fractions(raw/'geomorphons.tif','valleys')
 flood=flood_fraction(sorted((raw/'gfplain').rglob('*.TIF')))
 relief,elevation=terrain_context(etopo)
 delta=delta_fraction(raw/'deltas.xlsx',etopo,cfg['thresholds']['delta_max_elevation_m'])
 with np.load(wet) as z:riverine=np.asarray(z['flood'],np.float32)
 np.savez_compressed(dst,rolling=rolling['value'],rolling_coverage=rolling['coverage'],valleys=valley['value'],valleys_coverage=valley['coverage'],floodplains=flood,riverine=riverine,deltas=delta,relief=relief,elevation=elevation)
 mp.write_text(json.dumps({'inputs':inputs,'sha256':sha(dst),'sources':SOURCES,'transform':list(GRID),'shape':SHAPE,'licenses_note':'EcoTapestry-derived rolling layer and combined map distributed under CC-BY-SA-4.0; other upstream attributions retained.'},indent=2))
 return dst
