"""Evidence-guided historical vegetation, classified before location aggregation."""
from pathlib import Path
import json,re
import numpy as np
import pandas as pd
from scipy.ndimage import distance_transform_edt
from netCDF4 import Dataset,num2date
from .soil_types import sha
from .location_inventory import read_zone_inventory
from .location_geometry import overlap_matrix
from .vegetation_inputs import prepare_wetlands
ROOT=Path(__file__).resolve().parents[2]
WET=('marsh','swamp','saltmarsh','mangroves')


def historical_wetland_loss(path):
 """Use change WITHIN the same reconstruction, not coarse-minus-fine extents."""
 from zipfile import ZipFile
 with ZipFile(path) as z:
  with Dataset('memory',memory=z.read('grid_ncdf/ensemblemean/wetland_loss_1700-2020_ensemblemean_v10.nc')) as d:
   if d['Time'][0]!=1700 or d['Time'][-1]!=2020 or d['wetland_area'].units!='km^2':raise ValueError('Unexpected wetland-loss source')
   a=d['wetland_area'][0].filled(np.nan);b=d['wetland_area'][-1].filled(np.nan)
   lat=np.asarray(d['Latitude'][:])
   area=6371.0088**2*np.deg2rad(.5)*(np.sin(np.deg2rad(lat+.25))-np.sin(np.deg2rad(lat-.25)))[:,None]
   loss=np.clip(np.nan_to_num(a-b)/area,0,1)
 result=np.zeros((360,720),np.float32);result[12:292]=loss
 return result


def allocate_restoration(coarse_loss,available,preference):
 """Bounded 6x6 allocation preserves each source half-degree loss budget.

 Allocation follows wet/flood-setting evidence, with a small uniform floor for
 wholly drained settings. Historical crop/pasture has first claim on land.
 Any unattainable restoration is left unused, never displaced into neighbours.
 """
 # Tiny test grids can also exercise the same explicit nesting contract.
 h,w=coarse_loss.shape
 if available.shape!=(h*6,w*6):raise ValueError('Wetland grids do not nest')
 pack=lambda x:x.reshape(h,6,w,6).transpose(0,2,1,3).reshape(h,w,36)
 unpack=lambda x:x.reshape(h,w,6,6).transpose(0,2,1,3).reshape(h*6,w*6)
 cap=pack(available);score=pack(preference)*cap
 budget=np.minimum(coarse_loss*36,cap.sum(axis=-1))
 amount=np.zeros_like(cap)
 for _ in range(36):
  remaining=np.maximum(budget-amount.sum(axis=-1),0)
  if not np.any(remaining>1e-6):break
  open_cap=np.maximum(cap-amount,0);weight=np.where(open_cap>1e-7,score,0)
  den=weight.sum(axis=-1)
  add=np.divide(remaining,den,out=np.zeros_like(den),where=den>0)[...,None]*weight
  amount+=np.minimum(add,open_cap)
 if np.max(np.abs(amount.sum(axis=-1)-budget))>1e-4:raise ValueError('Wetland restoration did not reconcile')
 return unpack(amount)


def render_preview(raw,d,cfg,out,active):
 from PIL import Image
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 from matplotlib.patches import Patch
 im=Image.open(raw/'locations.png').convert('RGB');im.thumbnail((2400,1200),Image.Resampling.NEAREST)
 a=np.asarray(im,dtype=np.int32);lut=np.full((2**24,3),[17,31,45],np.uint8)
 for row in d.itertuples():
  if row.vegetation in cfg['types']:lut[int(row.map_color_rgb,16)]=cfg['types'][row.vegetation]['color']
 colors=lut[(a[:,:,0]<<16)|(a[:,:,1]<<8)|a[:,:,2]]
 fig,ax=plt.subplots(figsize=(16,8),facecolor='#111f2d');ax.imshow(colors);ax.axis('off')
 ax.set_title('Vegetation around 1300 — EU5 locations',color='white',fontsize=19)
 legend=ax.legend(handles=[Patch(color=np.array(cfg['types'][n]['color'])/255,label=cfg['types'][n]['label']) for n in active],loc='lower center',ncol=6,facecolor='#172a3a',edgecolor='none')
 for t in legend.get_texts():t.set_color('white')
 fig.tight_layout();fig.savefig(out/'vegetation.png',dpi=140,facecolor=fig.get_facecolor());plt.close(fig)

def make_fractions(pnv,crop,pasture,forest_share,wet,historic,cfg):
 """Exclusive fractions. Land use does not imply every grazed hectare was cleared."""
 names=list(cfg['types']);idx={n:i for i,n in enumerate(names)}
 shape=pnv.shape
 result=np.zeros((len(names),)+shape,np.float32)
 crop=np.clip(crop,0,1);pasture=np.minimum(np.clip(pasture,0,1),1-crop)
 result[idx['farmland']]=crop
 result[idx['grasslands']]=pasture
 remainder=1-crop-pasture
 forest=np.isin(pnv,np.arange(1,9))
 fresh=wet['marsh']+wet['swamp']
 lost=allocate_restoration(historic, np.maximum(remainder-sum(wet[k] for k in WET),0), fresh+wet.get('flood',0)+0.02)
 share=np.divide(wet['swamp'],fresh,out=forest.astype(np.float32),where=fresh>0.001)
 # Later lost wetlands identify a possible historical wet setting, not proof of
 # its1300 vegetation. Keep the restored share as a separate evidence diagnostic.
 portions={k:np.array(wet[k],np.float32,copy=True) for k in WET}
 portions['swamp']+=lost*share;portions['marsh']+=lost*(1-share)
 total=sum(portions.values())
 factor=np.minimum(1,np.divide(remainder,total,out=np.ones(shape,np.float32),where=total>0))
 for name,a in portions.items():
  result[idx[name]]=a*factor
 remainder=np.maximum(remainder-total*factor,0)
 for code,name in cfg['pnv_classes'].items():
  result[idx[name]]+=np.where(pnv==int(code),remainder,0)
 # Woods means an open wooded landscape, not a measured stand-density class.
 open_wood=forest&(forest_share<cfg['wooded_landscape_forest_share_threshold'])&(forest_share>0)
 for name in ['forest','jungle','coniferous_forest','mixed_forest','dry_forest']:
  amount=np.where(open_wood,result[idx[name]],0)
  result[idx[name]]-=amount;result[idx['woods']]+=amount
 return result,lost*factor

def choose_classes(fractions,cfg):
 names=np.array(list(cfg['types']));idx={n:i for i,n in enumerate(names)}
 chosen=fractions.argmax(axis=1)
 wet_ids=[idx[k] for k in WET]
 wet_sum=fractions[:,wet_ids].sum(axis=1)
 wet_dominant=np.array(wet_ids)[fractions[:,wet_ids].argmax(axis=1)]
 chosen=np.where(wet_sum>=cfg['wetland_location_share_threshold'],wet_dominant,chosen)
 chosen=np.where(fractions[:,idx['farmland']]>=cfg['farmland_location_share_threshold'],idx['farmland'],chosen)
 return names[chosen]

def load_grids(raw,cfg):
 with Dataset(raw/'pnv.nc') as d:
  if d['vegtype'].shape[-2:]!=(2160,4320):raise ValueError('Unexpected PNV grid')
  pnv=d['vegtype'][0,0].filled(0).astype(np.uint8)
  if d['latitude'][0]<0:pnv=pnv[::-1]
 valid=(pnv>=1)&(pnv<=15)
 with np.load(raw/'luh1300.npz') as z:
  if int(z['year'][0])!=cfg['year'] or z['primf'].shape!=(720,1440) or z['lat'][0]<0:raise ValueError('Unexpected LUH year/grid')
  lift=lambda a:np.repeat(np.repeat(np.nan_to_num(a),3,0),3,1).astype(np.float32)
  luh_crop=lift(sum(z[k] for k in ['c3ann','c4ann','c3nfx','c3per','c4per']))
  forest_share=lift(z['primf']+z['secdf'])
  pasture=lift(z['pastr'])+np.where(np.isin(pnv,np.arange(1,9)),lift(z['range']),0)
 from .water import area_grid
 with Dataset(raw/'hyde/cropland.nc') as d:
  dates=num2date(d['time'][:],d['time'].units,d['time'].calendar)
  index=[i for i,t in enumerate(dates) if t.year==cfg['year']]
  if len(index)!=1 or d['cropland'].units!='km**2':raise ValueError('Unexpected HYDE year/units')
  crop=d['cropland'][index[0]].filled(np.nan).astype(np.float32)/area_grid().astype(np.float32)
  if d['lat'][0]<0:crop=crop[::-1]
  hyde_version=d.version
 crop_missing=~np.isfinite(crop)
 crop=np.where(crop_missing,luh_crop,crop)
 with np.load(prepare_wetlands()) as z:wet={k:z[k] for k in z.files}
 with np.load(ROOT/'data/processed/water_management/wet_settings.npz') as z:
  wet['flood']=z['flood']
 historic=historical_wetland_loss(ROOT/'data/raw/water_management/wetland_loss.zip')
 fractions,restored=make_fractions(pnv,crop,pasture,forest_share,wet,historic,cfg)
 if not np.allclose(fractions[:,valid].sum(axis=0),1,atol=2e-6):raise ValueError('Vegetation fractions do not conserve land')
 return fractions,valid,restored,crop_missing,hyde_version

def build(config_path=None):
 cp=Path(config_path or ROOT/'configs/vegetation.json').resolve();cfg=json.loads(cp.read_text())
 out=ROOT/cfg['output_directory'];out.mkdir(parents=True,exist_ok=True)
 raw=ROOT/'data/raw/location_inputs'
 wetcache=prepare_wetlands()
 paths=[cp,Path(__file__),ROOT/'src/historical_agriculture/vegetation_inputs.py',
  ROOT/'src/historical_agriculture/location_geometry.py',ROOT/'src/historical_agriculture/location_inventory.py',
  raw/'pnv.nc',raw/'luh1300.npz',raw/'hyde/cropland.nc',raw/'locations.png',raw/'transform.json',
  raw/'inventory.parquet',raw/'game_templates.txt',raw/'game_named_locations.txt',raw/'game_default.map',
  wetcache,ROOT/'data/processed/water_management/wet_settings.npz',ROOT/'data/raw/water_management/wetland_loss.zip']
 inputs={str(p.relative_to(ROOT)):sha(p) for p in paths}
 mp=out/'manifest.json';csv=out/'locations.csv'
 if mp.exists() and csv.exists():
  prior=json.loads(mp.read_text())
  if prior.get('inputs')==inputs and prior.get('csv_sha256')==sha(csv):return prior
 print('Building native historical vegetation fractions',flush=True)
 fractions,valid,restored,crop_missing,hyde_version=load_grids(raw,cfg)
 inv=pd.read_parquet(raw/'inventory.parquet').sort_values('location_tag').reset_index(drop=True)
 weights,geometry=overlap_matrix(ROOT,inv,ROOT/'artifacts/locations')
 if weights.shape!=(len(inv),2160*4320):raise ValueError('Wrong geometry')
 denominator=np.asarray(weights.sum(axis=1)).ravel()
 coverage=np.asarray(weights@valid.ravel())/denominator
 # The same deterministic nearest natural-land donor supplies every component.
 # Only source gaps are completed; genuine zero class fractions remain zero.
 _,nearest=distance_transform_edt(~valid,return_indices=True)
 totals=np.zeros((len(inv),len(cfg['types'])))
 for k,a in enumerate(fractions):
  filled=a.copy();filled[~valid]=a[tuple(nearest[:,~valid])]
  totals[:,k]=np.asarray(weights@filled.ravel())/denominator
 if not np.allclose(totals.sum(axis=1),1,atol=2e-6):raise ValueError('Incomplete location fractions')
 totals/=totals.sum(axis=1)[:,None]
 d=inv[['location_tag','map_color_rgb','province','region','macro_region']].copy()
 names=list(cfg['types'])
 for k,n in enumerate(names):d[n+'_share']=totals[:,k]
 d['vegetation']=choose_classes(totals,cfg)
 d['source_coverage']=coverage
 d['restored_wetland_share']=np.asarray(weights@restored.ravel())/denominator
 d['hyde_missing_share']=np.asarray(weights@crop_missing.ravel())/denominator
 d['assignment_source']='PNV + dated land use + reconstructed wet settings'
 d['low_confidence']=(coverage<.8)|(d.restored_wetland_share>.1)|(totals.max(axis=1)<.5)
 d['vanilla_vegetation']=inv.vegetation
 zones=read_zone_inventory(raw)
 d=d.merge(zones[['location_tag','game_zone_class','is_ownable']],on='location_tag',validate='one_to_one')
 # Non-settlement zones not in the settlement overlap inventory retain vanilla
 # vegetation explicitly. Every ownable location must have source aggregation.
 extras=zones[~zones.location_tag.isin(d.location_tag)].copy()
 if extras.is_ownable.any():raise ValueError('Ownable location missing from physical inventory')
 text=(raw/'game_templates.txt').read_text(encoding='utf-8-sig')
 vanilla={}
 for match in re.finditer(r'(?m)^([\w.-]+)\s*=\s*\{([^{}]*)',text):
  value=re.search(r'\bvegetation\s*=\s*(\w+)',match[2])
  if value:vanilla[match[1]]=value[1]
 extras['vegetation']=extras.location_tag.map(vanilla)
 if extras.loc[~extras.game_zone_class.str.contains('sea_zones|lakes'),'vegetation'].isna().any():raise ValueError('Non-ownable land missing native vegetation')
 extras['vegetation']=extras.vegetation.fillna('water')
 extras['vanilla_vegetation']=extras.vegetation
 extras['assignment_source']='Native non-ownable zone'
 extras['source_coverage']=0.;extras['low_confidence']=False;extras['restored_wetland_share']=0.;extras['hyde_missing_share']=0.
 for n in names:extras[n+'_share']=(extras.vegetation==n).astype(float)
 d=pd.concat([d,extras],ignore_index=True).sort_values('location_tag').reset_index(drop=True)
 counts=d[d.is_ownable].vegetation.value_counts().to_dict()
 rare={n:cfg['rare_type_fallback'][n] for n,t in cfg['types'].items() if not t['native'] and counts.get(n,0)<cfg['minimum_new_type_locations']}
 d['candidate_vegetation']=d.vegetation
 # Collapse rare proposed UI classes without inflating evidence or changing
 # thresholds to manufacture locations. Keep their fractions and candidate labels.
 for n in rare:
  target=rare[n]
  while target in rare:target=rare[target]
  d.loc[d.vegetation==n,'vegetation']=target
 active=[n for n,t in cfg['types'].items() if t['native'] or n not in rare]
 d['game_vegetation']=d.vegetation.map({n:t['game_key'] for n,t in cfg['types'].items()}).fillna('')
 d['dominant_share']=d[[n+'_share' for n in names]].max(axis=1)
 if d.location_tag.duplicated().any() or not d.loc[d.is_ownable,'vegetation'].isin(active).all():raise ValueError('Incomplete ownable vegetation')
 d.to_csv(csv,index=False,float_format='%.8f')
 report={'schema':1,'year':cfg['year'],'inputs':inputs,'csv_sha256':sha(csv),'active_types':active,
  'candidate_counts':counts,'rare_types_collapsed':rare,'ownable_locations':int(d.is_ownable.sum()),'ownable_missing':0,
  'ownable_distribution':d[d.is_ownable].vegetation.value_counts().to_dict(),
  'changed_ownable_locations':int((d[d.is_ownable].vegetation!=d[d.is_ownable].vanilla_vegetation).sum()),
  'low_confidence_ownable':int(d.loc[d.is_ownable,'low_confidence'].sum()),
  'hyde_version':hyde_version,'geometry':geometry,'assumptions':cfg['assumptions'],
  'scientific_status':'Global evidence-guided approximation; not independently validated 1300 canopy cover'}
 render_preview(raw,d,cfg,out,active)
 table=''.join(f'<tr><td>{cfg["types"][n]["label"]}</td><td>{report["ownable_distribution"].get(n,0):,}</td></tr>' for n in active)
 html='<html><meta charset="utf-8"><title>Vegetation 1300</title><style>body{background:#111f2d;color:#eee;font:16px sans-serif;margin:30px}img{max-width:100%}td{padding:6px 20px}a{color:#8ccef4}</style><h1>Vegetation around 1300</h1><p>Complete ownable-location assignment. Natural formations, reconstructed land use and wet settings; historical detail is inferred.</p><img src="vegetation.png"><table>'+table+'</table><p><a href="locations.csv">Assignments and source fractions</a> · <a href="manifest.json">Evidence and limitations</a></p></html>'
 (out/'index.html').write_text(html)
 mp.write_text(json.dumps(report,indent=2)+'\n')
 return report
