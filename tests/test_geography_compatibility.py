import json
import pytest
from historical_agriculture import geography_compatibility as compat


def test_predicate_expansion_keeps_negation_and_comments():
    groups={'vegetation': {'forest':['conifers','mixed']}}
    s='vegetation = forest vegetation != forest # vegetation = forest\n"vegetation = forest"'
    out=compat.expand_predicates(s,groups)
    assert 'OR = { vegetation = forest vegetation = conifers vegetation = mixed }' in out
    assert 'NOR = { vegetation = forest vegetation = conifers vegetation = mixed }' in out
    assert '# vegetation = forest' in out and '"vegetation = forest"' in out


def test_inactive_types_never_leak_into_game_predicates(tmp_path,monkeypatch):
    monkeypatch.setattr(compat,'ROOT',tmp_path)
    (tmp_path/'configs').mkdir()
    for attr in ['vegetation','climate','topography']:
        (tmp_path/f'artifacts/{attr}').mkdir(parents=True)
        (tmp_path/f'artifacts/{attr}/manifest.json').write_text(json.dumps({'active_types':['active']}))
        (tmp_path/f'configs/{attr}.json').write_text(json.dumps({'types':{
            'active':{'game_key':'new','parent':'old'},
            'collapsed':{'game_key':'absent','parent':'old'}}}))
    groups=compat.families()
    assert all(v=={'old':['new']} for v in groups.values())


def test_preserve_starting_potential_does_not_change_building_balance():
    original='orchard = {\n cost = 4\n location_potential = { vegetation = woods climate != arctic }\n modifier = { food = 9 }\n }'
    out=compat.preserve_potential(original,'orchard',{'cairo','rome'})
    assert 'AND = { vegetation = woods climate != arctic' in out
    assert 'this = location:cairo' in out and 'this = location:rome' in out
    assert 'cost = 4' in out and 'modifier = { food = 9 }' in out


def test_empty_preservation_leaves_original_unchanged():
    assert compat.preserve_potential('anything','no-key',set())=='anything'


def test_rivers_with_old_invalid_encoding_cannot_be_deployed(tmp_path,monkeypatch):
    monkeypatch.setattr(compat,'ROOT',tmp_path)
    (tmp_path/'configs').mkdir(); (tmp_path/'rivers').mkdir()
    cfg={'output':'rivers'}
    (tmp_path/'configs/rivers.json').write_text(json.dumps(cfg))
    (tmp_path/'rivers/export_manifest.json').write_text(json.dumps({'config':cfg,'code_sha256':{}}))
    with pytest.raises(ValueError,match='native tributary'):
        compat.emit_rivers(tmp_path/'mod')


def test_complete_compatibility_emission_preserves_setup_and_emits_terrain_support(tmp_path,monkeypatch):
    monkeypatch.setattr(compat,'ROOT',tmp_path)
    monkeypatch.setattr(compat,'families',lambda:{'vegetation':{'forest':['conifers']}})
    (tmp_path/'configs').mkdir()
    (tmp_path/'configs/topography.json').write_text(json.dumps({'types':{
        'valley':{'game_key':'valley','parent':'flatland','label':'Valley'}}}))
    game=tmp_path/'game'; out=tmp_path/'mod'
    files={
        'in_game/map_data/location_templates.txt':'timber = { raw_material = lumber }',
        'main_menu/setup/start/07_cities_and_buildings.txt':
            'irrigation_systems = { location = cairo level = 2 }\nfruit_orchard = { location = rome level = 1 }',
        'in_game/common/goods/materials.txt':'lumber = {\n location_potential = { vegetation = forest }\n}',
        'in_game/common/building_types/test.txt':
            'irrigation_systems = {\n location_potential = { has_river = yes }\n cost = 99\n}\n'
            'fruit_orchard = {\n location_potential = { vegetation = forest }\n output = 12\n}',
        'in_game/common/scripted_triggers/test.txt':'wants_lumber = { vegetation = forest }',
        'main_menu/common/modifier_type_definitions/00_modifier_types.txt':
            'flatland_proximity_impact = { decimals = 2 }',
        'main_menu/common/static_modifiers/capital_in_topography.txt':
            'capital_in_flatland = { flatland_proximity_impact = -0.2 }'}
    for rel,txt in files.items():
        p=game/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(txt)
    audit=compat.emit(out,game)
    b=(out/'in_game/common/building_types/test.txt').read_text(encoding='utf-8-sig')
    assert 'this = location:cairo' in b and 'has_river = yes' in b
    assert 'cost = 99' in b and 'output = 12' in b
    assert 'vegetation = conifers' in b and 'this = location:rome' in b
    assert audit['preserved_starting_lumber_locations']==['timber']
    assert 'this = location:timber' in (out/'in_game/common/goods/materials.txt').read_text()
    assert 'capital_in_valley' in (out/'main_menu/common/static_modifiers/ha1300_topography_capitals.txt').read_text()
    assert 'valley_proximity_impact' in (out/'main_menu/common/modifier_type_definitions/ha1300_topography_compatibility.txt').read_text()
    assert 'STATIC_MODIFIER_NAME_capital_in_valley' in (out/'main_menu/localization/english/ha1300_geography_compatibility_l_english.yml').read_text()
    assert all((game/rel).read_text()==txt for rel,txt in files.items())


@pytest.mark.parametrize('fault',[None,'config','code','png'])
def test_river_delivery_checks_fingerprints_and_copies_exactly(tmp_path,monkeypatch,fault):
    monkeypatch.setattr(compat,'ROOT',tmp_path)
    (tmp_path/'configs').mkdir();(tmp_path/'rivers').mkdir()
    source=tmp_path/'rivers/map.png';source.write_bytes(b'indexed PNG fixture')
    code=tmp_path/'exporter.py';code.write_text('original')
    cfg={'output':'rivers'}
    report={'config':cfg,'code_sha256':{'exporter.py':compat.sha(code)},
        'engineering_checks':{'native_tributary_encoding':True},
        'output_png':'rivers/map.png','output_sha256':compat.sha(source),'status':'offline validated'}
    (tmp_path/'rivers/export_manifest.json').write_text(json.dumps(report))
    if fault=='config':cfg['changed']=True
    if fault=='code':code.write_text('changed')
    if fault=='png':source.write_bytes(b'changed')
    (tmp_path/'configs/rivers.json').write_text(json.dumps(cfg))
    if fault:
        with pytest.raises(ValueError):compat.emit_rivers(tmp_path/'mod')
    else:
        compat.emit_rivers(tmp_path/'mod')
        assert (tmp_path/'mod/in_game/map_data/rivers.png').read_bytes()==source.read_bytes()


def test_unknown_custom_reference_blocks_deployment(tmp_path):
    game=tmp_path/'game';mod=tmp_path/'mod'
    defs=mod/'in_game/common/vegetation/types.txt';defs.parent.mkdir(parents=True)
    defs.write_text('ha1300_veg_active = {}')
    rules=mod/'in_game/common/building_types/rules.txt';rules.parent.mkdir(parents=True)
    rules.write_text('building = { vegetation = ha1300_veg_absent }')
    with pytest.raises(ValueError,match='Undefined vegetation'):
        compat.validate_references(mod,game)
    rules.write_text('building = { vegetation = ha1300_veg_active }')
    assert compat.validate_references(mod,game)['custom_geography_references_checked']==1
