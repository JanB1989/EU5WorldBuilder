import json
from pathlib import Path
import pandas as pd
import pytest
from historical_agriculture.topography import choose_classes,native_values
from historical_agriculture.geography_test_topography import patch_topography
from historical_agriculture.geography_test_vegetation import vegetation_definition,named_rgb
ROOT=Path(__file__).resolve().parents[1]


def test_priority_coverage_and_native_special_domains():
 cfg=json.loads((ROOT/'configs/topography.json').read_text())
 d=pd.DataFrame({'vanilla_topography':['flatland','hills','mountains','plateau','wetlands','atoll','flatland','flatland'],
  'is_ownable':[True]*7+[False], 'rolling_share':[.6]*8,'valleys_share':[0,.3,.3,.3,.3,.3,0,.3],
  'floodplains_share':[0,0,.5,.5,.5,.5,0,.5],'deltas_share':[0,0,0,.5,.5,.5,0,.5],
  'rolling_coverage':[1]*6+[.4,1],'valleys_coverage':[1]*8})
 assert choose_classes(d,cfg).tolist()==['rolling','valleys','floodplains','deltas','deltas','atoll','flatland','flatland']


def test_export_preserves_vegetation_climate_and_nested_fields():
 source='a = { topography = hills vegetation = ha1300_veg_coniferous_forest climate = continental modifiers = { x = 2 } }\nb = { topography = ocean vegetation = sparse }\n'
 actual=patch_topography(source,{'a':'ha1300_topo_valleys'})
 assert actual==source.replace('topography = hills','topography = ha1300_topo_valleys')
 assert native_values(actual)=={'a':'ha1300_topo_valleys','b':'ocean'}
 with pytest.raises(ValueError):patch_topography(source,{'missing':'ha1300_topo_valleys'})


def test_definition_preserves_parent_and_uses_integer_map_colors():
 source='flatland = {\n color = terrain_grasslands\n movement_cost = 1.0\n debug_color = rgb { 1 2 3 }\n audio_tags = { elevation = 0.1 }\n}\n'
 actual=vegetation_definition(source,'flatland','ha1300_topo_deltas','ha1300_color',[78,118,204])
 assert 'movement_cost = 1.0' in actual and 'elevation = 0.1' in actual
 assert 'color = ha1300_color' in actual and 'rgb { 78 118 204 }' in actual
 assert named_rgb('x',[78,118,204])=='x = rgb { 78 118 204 }'
 with pytest.raises(ValueError):named_rgb('x',[.3,.4,.8])


def test_all_four_prepared_icons_have_real_alpha():
 from PIL import Image
 cfg=json.loads((ROOT/'configs/topography.json').read_text())
 for name in cfg['types']:
  im=Image.open(ROOT/'assets/geography_test/topography'/(name+'.png'))
  assert im.mode=='RGBA' and im.size==(512,512)
  assert im.getchannel('A').getextrema()==(0,255)
