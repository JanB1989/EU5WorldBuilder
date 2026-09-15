import json
from pathlib import Path
import numpy as np
import pytest
from historical_agriculture.vegetation import make_fractions,choose_classes,allocate_restoration
from historical_agriculture.geography_test_vegetation import patch_global_templates,vegetation_definition

CFG=json.loads((Path(__file__).resolve().parents[1]/'configs/vegetation.json').read_text())

def test_loss_allocation_conserves_source_budget_and_respects_available_land():
    available=np.ones((6,12));available[:,:3]=0
    preference=np.ones_like(available);preference[0]=10
    loss=np.array([[.2,1.]])
    result=allocate_restoration(loss,available,preference)
    assert np.all(result>=0) and np.all(result<=available)
    assert np.isclose(result[:,:6].sum(),.2*36)
    assert np.isclose(result[:,6:].sum(),36)
    assert result[0,3]>result[1,3]
    with pytest.raises(ValueError):allocate_restoration(loss,np.ones((5,12)),preference)


def test_exclusive_vegetation_fractions_do_not_double_count_cropland_or_wetland():
    pnv=np.full((6,6),6,dtype=int);crop=np.full((6,6),.4)
    pasture=np.full((6,6),.2);forest=np.ones((6,6))
    wet={k:np.zeros((6,6)) for k in ['marsh','swamp','saltmarsh','mangroves']}
    wet['swamp'][:]=.3
    fractions,restored=make_fractions(pnv,crop,pasture,forest,wet,np.array([[.5]]),CFG)
    idx={n:i for i,n in enumerate(CFG['types'])}
    assert np.allclose(fractions.sum(axis=0),1)
    assert np.allclose(fractions[idx['farmland']],.4)
    assert np.allclose(fractions[idx['grasslands']],.2)
    assert np.allclose(fractions[idx['swamp']],.4)
    assert np.allclose(restored,.1)


def test_natural_formations_retain_distinct_types_without_human_use():
    pnv=np.tile(np.arange(1,16),(6,2)) # 6 x 30: five coarse parent cells
    zeros=np.zeros_like(pnv,dtype=float)
    wet={k:zeros.copy() for k in ['marsh','swamp','saltmarsh','mangroves']}
    fractions,_=make_fractions(pnv,zeros,zeros,np.ones_like(zeros),wet,np.zeros((1,5)),CFG)
    got=choose_classes(fractions.reshape(18,-1).T,CFG).reshape(pnv.shape)
    for code,name in CFG['pnv_classes'].items():assert np.all(got[pnv==int(code)]==name)
    assert np.allclose(fractions.sum(axis=0),1)


def test_global_template_patch_preserves_nested_native_modifiers_and_water():
    text='a = { vegetation = forest modifier = { nile = yes } climate = arid }\nb = { vegetation = woods }\nsea = { topography = ocean }\n'
    result=patch_global_templates(text,{'a':'ha1300_veg_swamp'})
    assert result==text.replace('vegetation = forest','vegetation = ha1300_veg_swamp')
    with pytest.raises(ValueError):patch_global_templates(text,{'missing':'forest'})
    with pytest.raises(ValueError):patch_global_templates(text,{'sea':'forest'})


def test_native_subtype_inherits_mechanics_only_changing_key_and_colors():
    source='forest = {\n color = terrain_forest\n movement_cost = 1.5\n location_modifier = { local_population_capacity_modifier = .25 }\n debug_color = rgb { 12 34 56 }\n}\n'
    result=vegetation_definition(source,'forest','ha1300_veg_swamp','new_color',[1,2,3])
    assert result==source.replace('forest =','ha1300_veg_swamp =',1).replace('color = terrain_forest','color = new_color').replace('rgb { 12 34 56 }','rgb { 1 2 3 }')


def test_named_colors_use_eu5_integer_channels_not_normalized_floats():
    from historical_agriculture.geography_test_vegetation import named_rgb
    assert named_rgb('forest_color',[54,109,64])=='forest_color = rgb { 54 109 64 }'
    for bad in [[.2,.4,.3],[0,0,256],[-1,0,0],[0,0]]:
        with pytest.raises(ValueError):named_rgb('bad',bad)
