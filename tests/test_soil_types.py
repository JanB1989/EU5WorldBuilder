import json
from pathlib import Path
import numpy as np
import pandas as pd
from historical_agriculture.soil_types import classify_components, finalize

CFG=json.loads((Path(__file__).resolve().parents[1]/'configs/soil_types.json').read_text())


def test_all_source_texture_codes_are_classified_and_depth_is_not_a_type():
    d=pd.DataFrame({'TEXTURE_USDA':list(range(1,14))*2,'COARSE':0,'PHASE1':0,'PHASE2':0,'WRB2':'CM', 'ROOT_DEPTH':[1]*13+[6]*13})
    result=classify_components(d,CFG)
    assert (result>0).all()
    np.testing.assert_array_equal(result[:13],result[13:])


def test_organic_stony_water_and_unknown_are_distinct():
    d=pd.DataFrame({'TEXTURE_USDA':[9,9,9,9,None,9], 'COARSE':[0,36,0,80,0,0],
       'PHASE1':[0,0,25,1,0,0],'PHASE2':0,'WRB2':['CM','CM','CM','HS','ND','WR']})
    assert classify_components(d,CFG).tolist()==[2,6,6,5,0,0]


def test_location_mixtures_and_dateline_donors_preserve_complete_ownable_coverage():
    zones=pd.DataFrame({'location_tag':['nan','missing','far','sea'], 'game_zone_class':['settlement_land']*3+['sea_zones'], 'is_ownable':[True]*3+[False]})
    totals=np.array([[.7,.3,0,0,0,0],[0]*6,[0,0,0,1,0,0],[0]*6])
    d=finalize(zones,totals,np.ones(4),np.array([179,-179,0,20]),np.zeros(4),CFG)
    assert d.soil_type.tolist()==['sand','sand','clay','water']
    assert d.analogue_location.iloc[1]=='nan'
    assert d.source_coverage.iloc[1]==0 and d.inferred.iloc[1]
    assert d.dominant_share.iloc[0]==.7
    np.testing.assert_allclose(d.loc[d.is_ownable,[n+'_share' for n in CFG['types']]].sum(axis=1),1)


def test_mod_uses_same_assignments_legend_and_no_recurring_or_economic_effects(tmp_path,monkeypatch):
    from historical_agriculture import geography_test_global_soils as mod
    from historical_agriculture.soil_types import sha
    (tmp_path/'configs').mkdir();(tmp_path/'configs/soil_types.json').write_text(json.dumps(CFG))
    data=tmp_path/CFG['output_directory'];data.mkdir(parents=True)
    rows=[{'location_tag':('nan' if n==1 else 'test_'+name),'soil_id':n,'soil_type':name,'is_ownable':True,'inferred':False} for n,name in enumerate(CFG['types'],1)]
    pd.DataFrame(rows).to_csv(data/'locations.csv',index=False)
    (data/'manifest.json').write_text(json.dumps({'csv_sha256':sha(data/'locations.csv')}))
    game=tmp_path/'game';icon=game/'main_menu/gfx/interface/vegetation/farmland.dds';icon.parent.mkdir(parents=True);icon.write_bytes(b'DDS fixture')
    from PIL import Image
    assets=tmp_path/'assets/geography_test/soil_types';assets.mkdir(parents=True)
    for name in CFG['types']:
        image=Image.new('RGBA',(512,512));image.paste((180,160,130,255),(64,64,448,448));image.save(assets/(name+'.png'))
    out=tmp_path/'out';out.mkdir();(out/'README.md').write_text('Test')
    monkeypatch.setattr(mod,'ROOT',tmp_path)
    mod.emit_soils(out,game)
    setup=(out/'in_game/common/on_action/ha1300_global_soils.txt').read_text()
    mode=(out/'in_game/gfx/map/map_modes/ha1300_soils.txt').read_text()
    assert 'location:nan = {' in setup
    assert setup.count('set_variable')==6
    assert 'on_monthly' not in setup and 'add_location_modifier' not in setup
    assert 'category = geography' in mode and 'index = 2' in mode
    assert mode.count('legend_key')==6
    for v in CFG['types'].values():
        assert 'rgb { '+' '.join(map(str,v['color']))+' }' in mode
    custom=(out/'in_game/common/customizable_localization/ha1300_global_soils.txt').read_text()
    assert 'ha1300_soil_type_texture' not in custom
    gui=mod.soil_chip()
    assert gui.count('blockoverride "concept_link" { visible = yes text = "[ha1300_soil_type|E]" }')==6
    assert gui.count("GetMapMode('ha1300_soil_types')")==6
    assert (out/'main_menu/common/game_concepts/ha1300_soils.txt').is_file()
    assert 'texture = "[LocationView.GetLocation.Custom' not in gui
    for name in CFG['types']:
        # Both the icon and its tooltip must use the shipped asset directly.
        assert gui.count('texture = "gfx/interface/soil_types/'+name+'.dds"')==2
        assert "Localize('HA1300_SOIL_"+name.upper()+"_TITLE')" in gui
    for name in CFG['types']:
        with Image.open(out/'main_menu/gfx/interface/soil_types'/(name+'.dds')) as image:
            assert image.size==(64,64) and image.getchannel('A').getextrema()==(0,255)
    for phase in ['main_menu','in_game']:
        with Image.open(out/phase/'gfx/interface/icons/map_modes/ha1300_soil_types.dds') as image:
            assert image.size==(128,128)
    assert not (out/'in_game/map_data/location_templates.txt').exists()
