import copy,json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from historical_agriculture.climate import code_lookup,assign
from historical_agriculture.geography_test_climate import definition,patch_climate
CFG=json.loads((Path(__file__).resolve().parents[1]/'configs/climate.json').read_text())


def test_every_source_class_maps_once_and_all_native_climates_survive():
    codes=code_lookup(CFG)
    assert len(codes)==31 and codes[0]==0 and (codes[1:]>0).all()
    assert {n for n,t in CFG['types'].items() if t['native']}=={'tropical','subtropical','oceanic','arid','cold_arid','mediterranean','continental','arctic'}
    broken=copy.deepcopy(CFG);broken['types']['tropical']['koppen_codes'].append(2)
    with pytest.raises(ValueError):code_lookup(broken)


def test_group_before_winner_and_keep_missing_separate():
    d=pd.DataFrame({'is_ownable':[True,True,False],'vanilla_climate':['arid','oceanic','arctic']})
    a=np.zeros((3,31));a[0,25]=.3;a[0,26]=.3;a[0,4]=.4;a[1,0]=1;a[2,1]=1
    r=assign(d,a,CFG)
    assert r.climate.tolist()==['continental','oceanic','arctic']
    assert r.inferred.tolist()==[False,True,False]
    assert r.loc[0,'dominant_share']==pytest.approx(.6)
    assert r.loc[1,'source_coverage']==0


def test_climate_patch_preserves_other_attributes_and_nested_effects():
    s='a = { topography = hills vegetation = forest climate = continental modifier = { value = 2 } }\nb = { climate = oceanic }\n'
    r=patch_climate(s,{'a':'ha1300_climate_subarctic'})
    assert r.replace('ha1300_climate_subarctic','continental')==s
    with pytest.raises(ValueError):patch_climate(s,{'unknown':'arid'})


def test_steppe_has_precipitation_and_native_parent_is_preserved():
    s='arid = {\n winter = none\n color = c\n has_precipitation = no\n location_modifier = { local_population_capacity_modifier = 0.5 }\n debug_color = hsv360 { 20 50 60 }\n}\n'
    t=CFG['types']['hot_steppe'];r=definition(s,t)
    assert 'has_precipitation = yes' in r and 'local_population_capacity_modifier = 0.5' in r
    assert 'winter = none' in r and 'debug_color = rgb' in r
    assert 'has_precipitation = no' in definition(s,CFG['types']['arid'])


def test_winter_has_only_native_values_and_names_are_unique():
    assert {t['winter'] for t in CFG['types'].values()}=={'none','mild','normal','severe'}
    assert len({t['label'] for t in CFG['types'].values()})==len(CFG['types'])
    assert CFG['types']['subarctic']['parent']=='continental'


def test_winter_map_uses_climate_limits_not_seasonal_weather():
    from historical_agriculture.geography_test_climate import maximum_winter_map,WINTER_COLORS
    original='other = { color_mode = terrain }\nwinter = {\n color_mode = winter\n color_refresh_counters = { Month }\n}\nwinter_power = { value = winter_power }\n'
    mapped=maximum_winter_map(original,CFG)
    assert mapped.startswith('other = { color_mode = terrain }')
    assert mapped.endswith('winter_power = { value = winter_power }\n')
    assert 'color_mode = winter' not in mapped and 'Month' not in mapped
    assert mapped.count('legend_key =')==4
    for t in CFG['types'].values():
        assert mapped.count('climate = '+t['game_key']+' ')==2 # colour and tooltip
    for rgb in WINTER_COLORS.values():
        assert all(type(c) is int and 0<=c<=255 for c in rgb)
        assert sum(rgb)>0
