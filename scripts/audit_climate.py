"""Focused full-world export audit, independent of the map renderer."""
import json,re,tomllib
from pathlib import Path
import pandas as pd
from PIL import Image
from historical_agriculture.geography_test import ROOT,sha,block_span
from historical_agriculture.climate import native_values
from historical_agriculture.location_inventory import read_zone_inventory
cfg=json.loads((ROOT/'configs/climate.json').read_text())
local=tomllib.loads((ROOT/'geography_test.local.toml').read_text());game=Path(local['paths']['game_root'])/'game'
output=ROOT/'artifacts/geography_test/Land Clearance Geography Test'
live=Path(local['paths']['live_mod_parent'])/'Land Clearance Geography Test'
d=pd.read_csv(ROOT/'artifacts/climate/locations.csv',keep_default_na=False)
z=read_zone_inventory(ROOT/'data/raw/location_inputs')
assert len(d)==len(z) and not d.location_tag.duplicated().any()
assert set(d[d.is_ownable].location_tag)==set(z[z.is_ownable].location_tag)
assert d[d.is_ownable].game_climate.ne('').all()
assert set(d.winter)<=set(['none','mild','normal','severe'])
original=(game/'in_game/common/climates/00_default.txt').read_text(encoding='utf-8-sig')
keys=set()
for p in (output/'in_game/common/climates').glob('*.txt'):
    text=p.read_text(encoding='utf-8-sig')
    for key in re.findall(r'(?m)^(\w+)\s*=\s*\{',text):
        block_span(text,key)
        assert key not in keys;keys.add(key)
assert keys=={t['game_key'] for t in cfg['types'].values()}
# Native bodies remain byte-identical after removing just display colors.
def without_colors(s):
    return re.sub(r'(?m)^\s*(?:color\s*=\s*\w+|debug_color\s*=\s*(?:rgb|hsv360)\s*\{[^{}]*\})[^\n]*','',s)
new=(output/'in_game/common/climates/00_default.txt').read_text(encoding='utf-8-sig')
for n,t in cfg['types'].items():
    if t['native']:
        _,a,b=block_span(original,n);_,c,e=block_span(new,n)
        assert without_colors(original[a:b])==without_colors(new[c:e]),n
    else:
        icon=output/'main_menu/gfx/interface/icons/climate'/(t['game_key']+'.dds')
        with Image.open(icon) as im:assert im.size==(70,70) and im.getchannel('A').getextrema()==(0,255)
        assert (icon.parent/(t['game_key']+'_frame.dds')).is_file()
# Exact assignment equality, including genuine tag 'nan'.
compiled=(output/'in_game/map_data/location_templates.txt').read_text(encoding='utf-8-sig')
assert native_values(compiled)==d.set_index('location_tag').game_climate.to_dict()
# Previously mapped fields are preserved byte-for-value.
for attribute in ['topography','vegetation']:
    expected=pd.read_csv(ROOT/f'artifacts/{attribute}/locations.csv',keep_default_na=False).set_index('location_tag')['game_'+attribute].to_dict()
    actual={}
    for m in re.finditer(r'(?m)^([\w.-]+)\s*=\s*\{([^{}]*)',compiled):
        v=re.search(r'\b'+attribute+r'\s*=\s*(\w+)',m[2])
        if v:actual[m[1]]=v[1]
    expected={k:v for k,v in expected.items() if v}
    assert actual==expected,attribute
manifest=json.loads((output/'ha1300-build.json').read_text())
for rel,digest in manifest['files'].items():
    assert sha(output/rel)==digest,rel
    assert sha(live/rel)==digest,rel
loc=(output/'main_menu/localization/english/ha1300_climates_l_english.yml').read_text(encoding='utf-8-sig')
for n,t in cfg['types'].items():
    if not t['native']:
        assert ' '+t['game_key']+':' in loc and ' '+t['game_key']+'_desc:' in loc
for p in [output/'main_menu/common/named_colors/ha1300_climates.txt',output/'in_game/common/climates/00_default.txt',output/'in_game/common/climates/ha1300_climates.txt']:
    text=p.read_text(encoding='utf-8-sig')
    for key in re.findall(r'(?m)^(\w+)\s*=\s*\{',text):block_span(text,key)
# The maximum-winter display must follow the exported climate definitions.
base_modes=(game/'in_game/gfx/map/map_modes/map_modes.txt').read_text(encoding='utf-8-sig')
new_modes=(output/'in_game/gfx/map/map_modes/map_modes.txt').read_text(encoding='utf-8-sig')
a,b,c=block_span(base_modes,'winter');x,y,z=block_span(new_modes,'winter')
assert base_modes[:a].strip()==new_modes[:x].strip() and base_modes[c:]==new_modes[z:]
body=new_modes[y:z]
assert 'color_mode = winter' not in body and 'Month' not in body
assert body.count('legend_key =')==4
for t in cfg['types'].values():assert body.count('climate = '+t['game_key']+' ')==2
report={'pass':True,'ownable_locations':int(d.is_ownable.sum()),'all_zones':len(d),'climate_definitions':len(keys),'native_climates_preserved':8,'new_icons_verified':10,'maximum_winter_map_uses_climate_limits':True,'native_fallbacks':int(d[d.is_ownable].inferred.sum()),'topography_and_vegetation_preserved':True,'deployed_files_verified':len(manifest['files']),'engine_visual_check':'Requires game restart and new campaign; not automatically verified'}
(ROOT/'reports/climate_audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
