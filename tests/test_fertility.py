import json
from pathlib import Path
import numpy as np
import pandas as pd
from historical_agriculture import fertility as f

CFG=json.loads((Path(__file__).resolve().parents[1]/'configs/fertility.json').read_text())


def components():
    return pd.DataFrame({'HWSD2_SMU_ID':range(1,7),'SEQUENCE':1,'SHARE':100,'WRB2':['CM']*6,
      'PH_WATER':[6.5,6.5,6.5,4,6.5,6.5],'CEC_SOIL':[50,30,15,1,50,50],
      'BSAT':[70,70,70,10,70,70],'ELEC_COND':[0,0,0,0,20,0],
      'ESP':[0,0,0,0,0,35],'ALUM_SAT':0})


def test_chemistry_order_constraints_and_no_texture_or_population_inputs():
    d=components();grades,audit=f.classify_components(d,CFG)
    assert grades[0]==5 and grades[1]==4
    assert grades[3:].tolist()==[1,1,1]
    assert not audit.chemistry_imputed.any()
    other=d.assign(TEXTURE_USDA=13,population=100000000,ROOT_DEPTH=1)
    np.testing.assert_array_equal(f.classify_components(other,CFG)[0],grades)


def test_wholly_missing_is_not_a_grade_partial_missing_is_flagged():
    d=components();d.loc[0,list(CFG['chemistry_valid_ranges'])]=-9
    d.loc[1,'BSAT']=-9
    grades,audit=f.classify_components(d,CFG)
    assert grades[0]==0 and pd.isna(audit.loc[0,'fertility_score'])
    assert grades[1]>0 and audit.loc[1,'chemistry_imputed']
    d.loc[2,'WRB2']='WR';assert f.classify_components(d,CFG)[0][2]==0


def test_location_mixture_and_missing_donor_remain_complete():
    zones=pd.DataFrame({'location_tag':['nan','missing','sea'],'game_zone_class':['settlement_land']*2+['sea_zones'],'is_ownable':[True,True,False]})
    # Two halves: very low and very high. Mixed fertility is Moderate.
    totals=np.array([[.5,0,0,0,.5,.1],[0]*6,[0]*6])
    d=f.location_grades(zones,totals,np.ones(3),np.array([179,-179,0]),np.zeros(3),CFG)
    assert d.fertility.tolist()==['moderate','moderate','water']
    assert d.loc[1,'analogue_location']=='nan'
    assert d.loc[1,'chemistry_imputed_share']==.1
    assert d.loc[1,'source_coverage']==0 and d.loc[1,'inferred']
    assert pd.isna(d.loc[2,'fertility_score'])


def test_export_has_all_grades_native_concept_and_no_economic_or_recurring_effects(tmp_path,monkeypatch):
    from PIL import Image
    from historical_agriculture import geography_test_fertility as mod
    (tmp_path/'configs').mkdir();(tmp_path/'configs/fertility.json').write_text(json.dumps(CFG))
    data=tmp_path/CFG['output_directory'];data.mkdir(parents=True)
    pd.DataFrame([{'location_tag':k,'fertility_id':v['id'],'is_ownable':True} for k,v in CFG['levels'].items()]).to_csv(data/'locations.csv',index=False)
    (data/'manifest.json').write_text(json.dumps({'csv_sha256':mod.sha(data/'locations.csv')}))
    game=tmp_path/'game';icon=game/'main_menu/gfx/interface/icons/map_modes/food_productivity.dds';icon.parent.mkdir(parents=True)
    Image.new('RGBA',(128,128),(100,180,50,255)).save(icon,format='DDS')
    assets=tmp_path/'assets/geography_test/fertility';assets.mkdir(parents=True)
    for name in CFG['levels']:
        image=Image.new('RGBA',(512,512));image.paste((100,180,50,255),(64,64,448,448));image.save(assets/(name+'.png'))
    out=tmp_path/'out';p=out/'in_game/gfx/map/map_modes/ha1300_soils.txt';p.parent.mkdir(parents=True)
    p.write_text('soil = {\n small_map_names = location\n category = geography\n index = 2\n}\n')
    hook=out/'in_game/common/on_action/ha1300_global_soils.txt';hook.parent.mkdir(parents=True)
    hook.write_text('on_game_start = { on_actions = { ha1300_assign_soil_types } }')
    (out/'README.md').write_text('test');monkeypatch.setattr(mod,'ROOT',tmp_path)
    mod.emit_fertility(out,game)
    actions=(out/'in_game/common/on_action/ha1300_fertility.txt').read_text()
    assert actions.count('set_variable')==5
    assert 'on_game_start' not in actions
    assert 'ha1300_assign_soil_types ha1300_assign_fertility' in hook.read_text()
    assert 'on_monthly' not in actions and 'add_location_modifier' not in actions
    mode=(out/'in_game/gfx/map/map_modes/ha1300_fertility.txt').read_text()
    assert mode.count('legend_key')==5 and 'category = geography' in mode
    assert (out/'main_menu/common/game_concepts/ha1300_fertility.txt').exists()
    gui=mod.fertility_chip()
    assert 'visible = yes text = "[ha1300_fertility|E]"' in gui
    assert "GetMapMode('ha1300_fertility')" in gui
    for name in CFG['levels']:
        assert gui.count('texture = "gfx/interface/fertility/'+name+'.dds"')==2
        with Image.open(out/'main_menu/gfx/interface/fertility'/(name+'.dds')) as image:
            assert image.size==(64,64) and image.getchannel('A').getextrema()==(0,255)
    assert gui.count('visible = yes text = "[ha1300_fertility|E]"')==5
