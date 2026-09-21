import json
from pathlib import Path
import pytest
from historical_agriculture import geography_test as g


def test_clone_preserves_source_and_adds_only_requested_effect():
    source='forest = {\n location_modifier = { local_population_capacity = 25 }\n movement_cost = 1.5\n # } ignored\n}\n'
    clone=g.clone_type(source,'forest',g.VEGETATION,g.V_MOD,3)
    assert g.V_MOD+' = 3' in clone
    assert 'local_population_capacity = 25' in clone
    assert 'movement_cost = 1.5' in clone
    assert g.block_span(clone,g.VEGETATION)[2]==len(clone.rstrip())


def test_template_patch_changes_only_selected_geography():
    source='a = { topography = hills vegetation = woods climate = continental culture = swedish }\nb = { topography = hills vegetation = forest climate = arctic }\n'
    result=g.patch_templates(source,[{'location':'a','vegetation_bonus':3,'climate_bonus':2}])
    assert result.splitlines()[1]==source.splitlines()[1]
    assert 'culture = swedish' in result
    assert 'vegetation = '+g.VEGETATION in result
    assert 'climate = '+g.CLIMATE in result
    assert 'topography = flatland' in result


def test_sync_refuses_main_mod_or_unowned_directory(tmp_path):
    with pytest.raises(ValueError):g.validate_owned_destination(tmp_path/'Prosper or Perish',tmp_path)
    target=tmp_path/g.MOD_NAME;target.mkdir()
    with pytest.raises(ValueError):g.validate_owned_destination(target,tmp_path)


def test_sync_copies_exact_bytes_and_only_removes_previously_managed_files(tmp_path):
    source=tmp_path/'build';source.mkdir();(source/'new.txt').write_bytes(b'new')
    marker={'id':g.MOD_ID,'files':{'new.txt':g.sha(source/'new.txt')}}
    (source/'ha1300-build.json').write_text(json.dumps(marker))
    parent=tmp_path/'live';target=parent/g.MOD_NAME;target.mkdir(parents=True)
    (target/'old.txt').write_text('old');(target/'unrelated.txt').write_text('keep')
    (target/'ha1300-build.json').write_text(json.dumps({'id':g.MOD_ID,'files':{'old.txt':'oldhash'}}))
    result=g.sync_tree(source,target,parent)
    assert result['byte_parity'] and not (target/'old.txt').exists()
    assert (target/'unrelated.txt').read_text()=='keep'
    assert (target/'new.txt').read_bytes()==b'new'


def test_sync_rejects_manifest_path_escape(tmp_path):
    source=tmp_path/'build';source.mkdir()
    (source/'ha1300-build.json').write_text(json.dumps({'id':g.MOD_ID,'files':{'../escape':'x'}}))
    with pytest.raises(ValueError):g.sync_tree(source,tmp_path/'live'/g.MOD_NAME,tmp_path/'live')


def test_complete_fixture_build_and_default_sync(tmp_path,monkeypatch):
    monkeypatch.setattr(g,'ROOT',tmp_path)
    game=tmp_path/'install/game';assets=tmp_path/'assets/geography_test';assets.mkdir(parents=True)
    (assets/'land_clearance.dds').write_bytes(b'DDS fixture')
    files={
      'in_game/common/climates/00_default.txt':'continental = {\n winter = normal\n location_modifier = { local_population_capacity_modifier = 0.5 }\n}\n',
      'in_game/common/vegetation/00_default.txt':'forest = {\n movement_cost = 1.5\n location_modifier = { local_population_capacity = 25 }\n}\n',
      'in_game/map_data/location_templates.txt':'\n'.join(f'{name} = {{ topography = flatland vegetation = forest climate = continental }}' for name in ['norrtalje','tierp','heby','enkoping','other'])}
    for name,text in files.items():
        p=game/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
    for rel in ['vegetation/forest.dds','vegetation/forest_big.dds','icons/climate/continental.dds','icons/climate/continental_frame.dds']:
        p=game/'main_menu/gfx/interface'/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'DDS fixture')
    base_cfg=json.loads((Path(__file__).resolve().parents[1]/'configs/geography_test.json').read_text())
    base_cfg.pop('native_geography_view',None)
    base_cfg.pop('test_attributes',None)
    base_cfg.pop('soil_types',None)  # This fixture exercises the original geography-only build.
    base_cfg.pop('global_soil_types',None)
    base_cfg.pop('global_fertility',None)
    base_cfg.pop('global_vegetation',None)
    base_cfg.pop('global_topography',None)
    base_cfg.pop('global_climate',None)
    base_cfg.pop('geography_compatibility',None)
    base_cfg.pop('global_rivers',None)
    base_cfg.pop('global_navigation',None)
    # Explicit historical trial fixture; the shipped config has retired it.
    base_cfg['cases']=[{'location':name,'vegetation_bonus':v,'climate_bonus':c} for name,v,c in [('norrtalje',0,0),('tierp',3,0),('heby',0,2),('enkoping',3,2)]]
    cfg=tmp_path/'fixture_config.json';cfg.write_text(json.dumps(base_cfg))
    local=tmp_path/'local.toml';local.write_text('[paths]\ngame_root = '+json.dumps(str(game.parent))+'\nlive_mod_parent = '+json.dumps(str(tmp_path/'live')))
    result=g.build(cfg,local)
    assert result['expected_limits']=={'norrtalje':2,'tierp':5,'heby':4,'enkoping':7}
    assert result['sync']['byte_parity']
    output=Path(result['output'])
    assert (output/'in_game/common/goods_demand/ha1300_test.txt').is_file()
    template=(output/'in_game/map_data/location_templates.txt').read_text(encoding='utf-8-sig')
    assert 'other = { topography = flatland vegetation = forest climate = continental }' in template
    building=(output/'in_game/common/building_types/ha1300_test.txt').read_text(encoding='utf-8-sig')
    assert 'employment_size = 0' in building and 'raw_modifier = { local_population_capacity = 1 }' in building
    for p in output.rglob('*'):
        if p.suffix in ['.txt','.yml','.json'] and p.name!='ha1300-build.json':assert p.read_bytes().startswith(b'\xef\xbb\xbf')
    # A repeat build is allowed and idempotent, and build-only never touches live.
    before=(Path(result['sync']['target'])/'ha1300-build.json').read_bytes()
    assert 'sync' not in g.build(cfg,local,deploy=False)
    assert (Path(result['sync']['target'])/'ha1300-build.json').read_bytes()==before


def test_shipped_config_has_no_obsolete_clearing_cases():
    cfg=json.loads((Path(__file__).resolve().parents[1]/'configs/geography_test.json').read_text())
    assert cfg['cases']==[]
