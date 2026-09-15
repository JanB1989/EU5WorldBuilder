"""Four explicit global landform refinements; all original game classes survive."""
import json,re
from pathlib import Path
import numpy as np
import pandas as pd
from .soil_types import sha
from .location_inventory import read_zone_inventory
from .location_geometry import overlap_matrix
from .topography_inputs import prepare,ROOT


def choose_classes(d,cfg):
 t=cfg['thresholds'];result=d.vanilla_topography.copy()
 eligible=d.vanilla_topography.isin(['flatland','hills','mountains','plateau']) & d.is_ownable
 # Shared thresholds, with the specific depositional settings taking priority.
 for name,mask in [
  ('rolling',(d.rolling_share>=t['rolling_share']) & (d.rolling_coverage>=.8)),
  ('valleys',(d.valleys_share>=t['valleys_share']) & (d.valleys_coverage>=.8)),
  ('floodplains',d.floodplains_share>=t['floodplains_share']),
  ('deltas',d.deltas_share>=t['deltas_share'])]:
  permitted=eligible | ((name=='deltas') & d.vanilla_topography.eq('wetlands') & d.is_ownable)
  result.loc[permitted&mask]=name
 return result


def native_values(text):
 values={}
 for m in re.finditer(r'(?m)^([\w.-]+)\s*=\s*\{([^{}]*)',text):
  v=re.search(r'\btopography\s*=\s*(\w+)',m[2])
  if v:values[m[1]]=v[1]
 return values


def render(raw,d,cfg,out):
 from PIL import Image
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 from matplotlib.patches import Patch
 native={'flatland':[121,151,81],'hills':[159,128,87],'mountains':[134,124,120],'plateau':[181,128,94],'wetlands':[94,138,126],'salt_pans':[222,206,181],'atoll':[122,196,186]}
 colors={**native,**{n:t['color'] for n,t in cfg['types'].items()}}
 im=Image.open(raw/'locations.png').convert('RGB');im.thumbnail((2400,1200),Image.Resampling.NEAREST)
 a=np.asarray(im,dtype=np.int32);lut=np.full((2**24,3),[19,33,47],np.uint8)
 for row in d.itertuples():
  n=row.topography
  if n in colors:lut[int(row.map_color_rgb,16)]=colors[n]
  elif 'wasteland' in n and 'ocean' not in n:lut[int(row.map_color_rgb,16)]=[75,78,77]
 a=lut[(a[:,:,0]<<16)|(a[:,:,1]<<8)|a[:,:,2]]
 fig,ax=plt.subplots(figsize=(16,8),facecolor='#13212f');ax.imshow(a);ax.axis('off')
 ax.set_title('Topography — four mapped landform refinements',color='white',fontsize=19)
 legend=ax.legend(handles=[Patch(color=np.array(c)/255,label=cfg['types'].get(n,{}).get('label',n.replace('_',' ').title())) for n,c in colors.items()],loc='lower center',ncol=6,facecolor='#192f40',edgecolor='none')
 for t in legend.get_texts():t.set_color('white')
 fig.tight_layout();fig.savefig(out/'topography.png',dpi=140,facecolor=fig.get_facecolor());plt.close(fig)


def build(config_path=None):
 cp=Path(config_path or ROOT/'configs/topography.json').resolve();cfg=json.loads(cp.read_text())
 evidence=prepare(cfg);out=ROOT/cfg['output_directory'];out.mkdir(parents=True,exist_ok=True)
 raw=ROOT/'data/raw/location_inputs';mp=out/'manifest.json';csv=out/'locations.csv'
 paths=[cp,Path(__file__),evidence,evidence.parent/'manifest.json',raw/'inventory.parquet',raw/'game_templates.txt',raw/'game_default.map',raw/'game_named_locations.txt',raw/'locations.png',raw/'transform.json',ROOT/'src/historical_agriculture/location_geometry.py',ROOT/'src/historical_agriculture/location_inventory.py']
 inputs={str(p.relative_to(ROOT)):sha(p) for p in paths}
 if mp.exists() and csv.exists():
  old=json.loads(mp.read_text())
  if old.get('inputs')==inputs and old.get('csv_sha256')==sha(csv):return old
 inv=pd.read_parquet(raw/'inventory.parquet').sort_values('location_tag').reset_index(drop=True)
 weights,geometry=overlap_matrix(ROOT,inv,ROOT/'artifacts/locations')
 if weights.shape!=(len(inv),2160*4320):raise ValueError('Topography overlap grid mismatch')
 den=np.asarray(weights.sum(axis=1)).ravel()
 if (den<=0).any():raise ValueError('Location has no overlap')
 d=inv[['location_tag','map_color_rgb','province','region','macro_region']].copy()
 zones=read_zone_inventory(raw)
 d=d.merge(zones[['location_tag','is_ownable','game_zone_class']],on='location_tag',validate='one_to_one',sort=False)
 if d.location_tag.tolist()!=inv.location_tag.tolist():raise ValueError('Overlap ordering changed')
 vanilla=native_values((raw/'game_templates.txt').read_text(encoding='utf-8-sig'))
 d['vanilla_topography']=d.location_tag.map(vanilla)
 t=cfg['thresholds']
 with np.load(evidence) as z:
  # Relief tests occur BEFORE aggregation. A steep half and a flat half cannot
  # average into entirely gentle rolling land or a broad valley floor.
  rolling=z['rolling']*((z['relief']>=t['rolling_min_relief_m'])&(z['relief']<=t['rolling_max_relief_m']))
  valley=z['valleys']*(z['relief']>=t['valleys_min_relief_m'])
  arrays={'rolling_share':rolling,'valleys_share':valley,'floodplains_share':np.maximum(z['floodplains'],z['riverine']),
   'gfplain_share':z['floodplains'],'riverine_share':z['riverine'],'deltas_share':z['deltas'],
   'rolling_coverage':z['rolling_coverage'],'valleys_coverage':z['valleys_coverage'],'mean_relief_m':z['relief']}
  for n,a in arrays.items():d[n]=np.asarray(weights@a.ravel())/den
 d['topography']=choose_classes(d,cfg)
 d['assignment_source']=np.where(d.topography==d.vanilla_topography,'Native baseline retained','Mapped landform refinement')
 d['low_confidence']=(d.rolling_coverage<.8)|(d.valleys_coverage<.8)|d.topography.isin(['deltas','valleys'])|((d.topography=='floodplains')&(d.gfplain_share<t['floodplains_share']))
 # All source gaps have a named, existing baseline; never invent a feature to
 # fill a mask. Native special domains and non-ownable locations remain intact.
 extras=zones[~zones.location_tag.isin(d.location_tag)].copy()
 if extras.is_ownable.any():raise ValueError('Ownable location absent from overlap inventory')
 extras['vanilla_topography']=extras.location_tag.map(vanilla)
 extras['topography']=extras.vanilla_topography
 extras['assignment_source']='Native non-ownable zone';extras['low_confidence']=False
 for n in arrays:extras[n]=0.
 d=pd.concat([d,extras],ignore_index=True).sort_values('location_tag').reset_index(drop=True)
 if d.topography.isna().any() or d.location_tag.duplicated().any():raise ValueError('Incomplete topography classification')
 d['game_topography']=d.topography.map({n:t['game_key'] for n,t in cfg['types'].items()}).fillna(d.topography)
 counts=d.loc[d.is_ownable,'topography'].value_counts().to_dict()
 if any(counts.get(n,0)<cfg['minimum_new_type_locations'] for n in cfg['types']):raise ValueError('New landform too rare: '+str(counts))
 for n in ['rolling','valleys','floodplains','deltas']:
  if not d[n+'_share'].between(-1e-6,1+1e-6).all():raise ValueError('Invalid source fraction '+n)
 d.to_csv(csv,index=False,float_format='%.8f')
 native=json.loads((ROOT/'reports/topography_game_audit.json').read_text())['types']
 report={'schema':1,'year':cfg['year'],'inputs':inputs,'csv_sha256':sha(csv),'native_types_retained':list(native),'added_types':list(cfg['types']),
  'ownable_locations':int(d.is_ownable.sum()),'total_zones':len(d),'ownable_missing':0,'ownable_distribution':counts,
  'low_confidence_ownable':int(d.loc[d.is_ownable,'low_confidence'].sum()),
  'new_types_by_macro_region':pd.crosstab(d[d.is_ownable].macro_region,d[d.is_ownable].topography).reindex(columns=list(cfg['types']),fill_value=0).to_dict(),
  'geometry':geometry,'assumptions':cfg['assumptions'],'source_manifest':json.loads((evidence.parent/'manifest.json').read_text()),
  'scientific_status':'Evidence-guided geographic prototype; modern broad landforms extrapolated to 1300, not surveyed medieval boundaries.'}
 render(raw,d,cfg,out)
 table=''.join(f'<tr><td>{cfg["types"][n]["label"]}</td><td>{counts.get(n,0):,}</td></tr>' for n in cfg['types'])
 (out/'index.html').write_text('<html><meta charset="utf-8"><title>Topography</title><style>body{background:#13212f;color:#eee;font:16px sans-serif;margin:30px}img{max-width:100%}td{padding:6px 20px}a{color:#8ccef4}</style><h1>Topography</h1><p>Four new mapped landforms. All existing types retained. Every ownable location classified.</p><img src="topography.png"><table>'+table+'</table><p>Modern geomorphology approximates 1300; delta shorelines and river courses are uncertain. New values use flatland mechanics until gameplay balancing.</p><p><a href="locations.csv">Complete assignments and source shares</a> · <a href="manifest.json">Sources, methods and limitations</a></p><p>Map: CC-BY-SA-4.0. Sources: Hengl/EcoTapestry, Amatulli/Geomorpho90m, Nardi/GFPLAIN, Edmonds et al., NOAA ETOPO and GLWD.</p></html>')
 mp.write_text(json.dumps(report,indent=2)+'\n')
 return report
