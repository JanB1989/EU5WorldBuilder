"""Independent full-inventory/export audit for the isolated terrain prototype."""
from pathlib import Path
import json,re,tomllib
import pandas as pd
from PIL import Image
from historical_agriculture.geography_test import sha,block_span,ROOT,MOD_NAME
from historical_agriculture.location_inventory import read_zone_inventory
from historical_agriculture.topography import native_values
from historical_agriculture.geography_test_vegetation import patch_global_templates

def audit():
 raw=ROOT/'data/raw/location_inputs';out=ROOT/'artifacts/geography_test'/MOD_NAME
 cfg=json.loads((ROOT/'configs/topography.json').read_text())
 m=json.loads((ROOT/'artifacts/topography/manifest.json').read_text());d=pd.read_csv(ROOT/'artifacts/topography/locations.csv',keep_default_na=False)
 zones=read_zone_inventory(raw);own=set(zones.loc[zones.is_ownable,'location_tag'])
 assert d.location_tag.is_unique and set(d.location_tag)==set(zones.location_tag)
 assert own==set(d.loc[d.is_ownable,'location_tag']) and len(own)==20893
 assert not d.game_topography.isna().any()
 game=Path(tomllib.loads((ROOT/'geography_test.local.toml').read_text())['paths']['game_root'])/'game'
 baseline=game/'in_game/common/topography/00_default.txt'
 a=json.loads((ROOT/'reports/topography_game_audit.json').read_text())
 assert sha(baseline)==a['sha256'] and len(a['types'])==22
 assert not (out/'in_game/common/topography/00_default.txt').exists()
 keys=set(a['types'])|{t['game_key'] for t in cfg['types'].values()}
 applied=native_values((out/'in_game/map_data/location_templates.txt').read_text(encoding='utf-8-sig'))
 assert set(applied.values())<=keys
 assert all(applied[r.location_tag]==r.game_topography for r in d.itertuples())
 # None of the retired test variants can be restored by this new exporter.
 assert not any('clearing' in k or 'clearable' in k for k in applied.values())
 expected_vegetation=pd.read_csv(ROOT/'artifacts/vegetation/locations.csv',keep_default_na=False)
 veg=expected_vegetation[expected_vegetation.game_vegetation.ne('')].set_index('location_tag').game_vegetation.to_dict()
 expected=patch_global_templates((raw/'game_templates.txt').read_text(encoding='utf-8-sig'),veg)
 if json.loads((ROOT/'configs/geography_test.json').read_text()).get('global_climate'):
  from historical_agriculture.geography_test_climate import patch_climate
  climates=pd.read_csv(ROOT/'artifacts/climate/locations.csv',keep_default_na=False)
  expected=patch_climate(expected,climates.set_index('location_tag').game_climate.to_dict())
 actual=(out/'in_game/map_data/location_templates.txt').read_text(encoding='utf-8-sig')
 strip=lambda s:re.sub(r'\btopography\s*=\s*\w+','topography = CHECK',s)
 assert strip(actual)==strip(expected),'Export modified vegetation/climate/non-topography content'
 definitions=(out/'in_game/common/topography/ha1300_topography.txt').read_text(encoding='utf-8-sig')
 assert set(re.findall(r'(?m)^(\w+)\s*=\s*\{',definitions))=={t['game_key'] for t in cfg['types'].values()}
 colors=(out/'main_menu/common/named_colors/ha1300_topography.txt').read_text(encoding='utf-8-sig')
 for name,t in cfg['types'].items():
  assert int((d.loc[d.is_ownable,'topography']==name).sum())>=25
  expected_body=baseline.read_text(encoding='utf-8-sig');_,x,y=block_span(expected_body,t['parent']);expected_body=expected_body[x:y]
  _,x,y=block_span(definitions,t['game_key']);body=definitions[x:y]
  clean=lambda s:re.sub(r'debug_color\s*=\s*rgb\s*\{[^{}]*\}','debug_color = CHECK',re.sub(r'(?m)^(\s*color\s*=\s*)\w+',r'\1CHECK',s))
  assert clean(expected_body)==clean(body),'Parent mechanics changed'
  assert 'rgb { '+' '.join(map(str,t['color']))+' }' in colors
  im=Image.open(out/'main_menu/gfx/interface/topography'/(t['game_key']+'.dds'))
  assert im.mode=='RGBA' and im.size==(64,64) and im.getchannel('A').getextrema()==(0,255)
 non=d.loc[~d.is_ownable]
 assert (non.topography==non.vanilla_topography).all()
 assert all(d[n+'_share'].between(-1e-6,1+1e-6).all() for n in cfg['types'])
 manifest=json.loads((out/'ha1300-build.json').read_text())
 assert all(sha(out/p)==v for p,v in manifest['files'].items())
 result={'engineering_pass':True,'ownable_locations':len(own),'total_zones':len(d),'missing':0,'native_types_retained':22,'added_types':4,'vegetation_climate_and_other_template_fields_unchanged':True,'dds_rgba':True,'native_parent_mechanics_preserved':True,'no_retired_debug_topography':True,'distribution':m['ownable_distribution'],'engine_visual_status':'Requires restart/new campaign and user check','scientific_status':m['scientific_status']}
 (ROOT/'reports/topography_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
 return result

if __name__=='__main__':audit()
