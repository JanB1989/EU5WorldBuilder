"""Build and sync the EU5 World Builder geography mod."""
from __future__ import annotations
import hashlib
import json
import re
import shutil
import tomllib
from pathlib import Path

MOD_NAME = 'EU5 World Builder'
# Keep the installed identity stable when changing its display/folder name.
MOD_ID = 'ha1300_land_clearance_geography_test'
BUILDING = 'ha1300_test_land_clearance'
VEGETATION = 'ha1300_clearable_forest'
CLIMATE = 'ha1300_clearing_continental'
V_MOD = 'ha1300_clearance_from_vegetation'
C_MOD = 'ha1300_clearance_from_climate'
ROOT = Path(__file__).resolve().parents[2]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def block_span(text, key):
    """Locate one top-level-style named block; ignore braces in comments/strings."""
    matches=list(re.finditer(r'(?m)^\s*'+re.escape(key)+r'\s*=\s*\{',text))
    if len(matches)!=1:
        raise ValueError(f'Expected one {key} block; found {len(matches)}')
    start=matches[0].end()-1
    depth=0; quoted=False; comment=False; escaped=False
    for i in range(start,len(text)):
        c=text[i]
        if comment:
            if c=='\n': comment=False
            continue
        if quoted:
            if escaped: escaped=False
            elif c=='\\': escaped=True
            elif c=='"': quoted=False
            continue
        if c=='#': comment=True
        elif c=='"': quoted=True
        elif c=='{': depth+=1
        elif c=='}':
            depth-=1
            if depth==0: return matches[0].start(),start,i+1
    raise ValueError(f'Unclosed {key}')

def clone_type(text, old, new, modifier, bonus):
    _,start,end=block_span(text,old)
    body=text[start:end]
    # All selected source types already contain a location_modifier block.
    body,n=re.subn(r'(location_modifier\s*=\s*\{)',rf'\1\n\t\t{modifier} = {bonus}',body,count=1)
    if n!=1: raise ValueError('Missing source modifier block')
    return f'{new} = {body}\n'

def patch_templates(text,cases):
    result=text
    for case in cases:
        left,body_start,right=block_span(result,case['location'])
        body=result[body_start:right]
        replacements={'vegetation':VEGETATION if case['vegetation_bonus'] else 'forest',
                      'climate':CLIMATE if case['climate_bonus'] else 'continental',
                      'topography':'flatland'}
        for key,value in replacements.items():
            body,n=re.subn(r'\b'+key+r'\s*=\s*\w+',f'{key} = {value}',body)
            if n!=1: raise ValueError(f'Missing/duplicate {key} in {case}')
        result=result[:body_start]+body+result[right:]
    return result

def write_text(root,relative,text):
    p=root/relative;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(text,encoding='utf-8-sig')

def validate_owned_destination(target,parent):
    target=target.resolve();parent=parent.resolve()
    if target.parent!=parent or target.name!=MOD_NAME:
        raise ValueError('Deploy target must be the dedicated test-mod folder')
    if target.exists():
        marker=target/'ha1300-build.json'
        if not marker.is_file() or json.loads(marker.read_text()).get('id')!=MOD_ID:
            raise ValueError('Refusing to overwrite a folder not owned by this builder')
    return target

def sync_tree(source,target,parent):
    target=validate_owned_destination(target,parent)
    source=source.resolve()
    if source==target or target in source.parents or source in target.parents:
        raise ValueError('Build and deploy directories must be separate')
    # Delete only files previously emitted by this builder, never arbitrary content.
    previous={}
    marker=target/'ha1300-build.json'
    if marker.exists():previous=json.loads(marker.read_text()).get('files',{})
    current=json.loads((source/'ha1300-build.json').read_text())['files']
    for rel in previous.keys()-current.keys():
        stale=(target/rel).resolve()
        if not stale.is_relative_to(target):raise ValueError('Unsafe manifest path')
        if stale.is_file():stale.unlink()
    for rel in [*current,'ha1300-build.json']:
        src=source/rel;dst=target/rel
        if not dst.resolve().is_relative_to(target):raise ValueError('Unsafe deploy path')
        dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
    for rel,digest in current.items():
        if sha(target/rel)!=digest:raise RuntimeError(f'Deploy mismatch: {rel}')
    return {'target':str(target),'verified_files':len(current),'byte_parity':True}

def build(config_path=None,local_path=None,deploy=True,refresh_data=True):
    config_path=Path(config_path or ROOT/'configs/geography_test.json')
    local_path=Path(local_path or ROOT/'geography_test.local.toml')
    cfg=json.loads(config_path.read_text())
    local=tomllib.loads(local_path.read_text())
    game=Path(local['paths']['game_root']).expanduser().resolve()/'game'
    mod_parent=Path(local['paths']['live_mod_parent']).expanduser().resolve()
    target=mod_parent/MOD_NAME
    if deploy:validate_owned_destination(target,mod_parent)
    soil_result=None
    def cached_manifest(config_name):
        cached_cfg=json.loads((ROOT/f'configs/{config_name}.json').read_text())
        return json.loads((ROOT/cached_cfg['output_directory']/'manifest.json').read_text())
    if cfg.get('global_soil_types'):
        from .soil_types import build as build_soils
        soil_result=build_soils() if refresh_data else cached_manifest('soil_types')
    fertility_result=None
    if cfg.get('global_fertility'):
        if not cfg.get('global_soil_types'):raise ValueError('Fertility requires the shared soil geography stage')
        from .fertility import build as build_fertility
        fertility_result=build_fertility() if refresh_data else cached_manifest('fertility')
    vegetation_result=None
    if cfg.get('global_vegetation'):
        from .vegetation import build as build_vegetation
        vegetation_result=build_vegetation() if refresh_data else cached_manifest('vegetation')
    topography_result=None
    if cfg.get('global_topography'):
        from .topography import build as build_topography
        topography_result=build_topography() if refresh_data else cached_manifest('topography')
    climate_result=None
    if cfg.get('global_climate'):
        from .climate import build as build_climate
        climate_result=build_climate() if refresh_data else cached_manifest('climate')
    output=ROOT/'artifacts/geography_test'/MOD_NAME
    report=ROOT/'artifacts/geography_test';report.mkdir(parents=True,exist_ok=True)
    sources={'climate':game/'in_game/common/climates/00_default.txt',
             'vegetation':game/'in_game/common/vegetation/00_default.txt',
             'templates':game/'in_game/map_data/location_templates.txt'}
    data={k:p.read_text(encoding='utf-8-sig') for k,p in sources.items()}
    cases=cfg['cases']
    for case in cases:
        if case['vegetation_bonus'] not in (0,cfg['vegetation_bonus']) or case['climate_bonus'] not in (0,cfg['climate_bonus']):
            raise ValueError('Case expectations do not match the generated type bonuses')
    assert len({c['location'] for c in cases})==len(cases)
    expected=[]
    for case in cases:
        _,i,j=block_span(data['templates'],case['location'])
        expected.append({**case,'expected_max_levels':cfg['base_levels']+case['vegetation_bonus']+case['climate_bonus']+cfg.get('soil_types',{}).get(case.get('soil'),{}).get('bonus',0),
          'original_template':data['templates'][i:j], 'expected_starting_levels':0})
    # The local build tree has its own identity guard as well.
    if output.exists():
        validate_owned_destination(output,output.parent)
        # Remove previously emitted files so disabled prototypes cannot survive
        # the next build manifest. Unmanaged files remain untouched.
        previous = json.loads((output/'ha1300-build.json').read_text()).get('files', {})
        for rel in previous:
            stale = (output/rel).resolve()
            if not stale.is_relative_to(output.resolve()):
                raise ValueError('Unsafe old build manifest path')
            if stale.is_file(): stale.unlink()
    assets={}
    write_text(output,'in_game/map_data/location_templates.txt',data['templates'])
    if cases:
        write_text(output,'in_game/common/vegetation/ha1300_test.txt',clone_type(data['vegetation'],'forest',VEGETATION,V_MOD,cfg['vegetation_bonus']))
        write_text(output,'in_game/common/climates/ha1300_test.txt',clone_type(data['climate'],'continental',CLIMATE,C_MOD,cfg['climate_bonus']))
        write_text(output,'in_game/map_data/location_templates.txt',patch_templates(data['templates'],cases))
        types=''
        for key in [V_MOD,C_MOD]:
            types+=f'{key} = {{\n decimals = 0\n game_data = {{ category = location }}\n}}\n'
        write_text(output,'main_menu/common/modifier_type_definitions/ha1300_test.txt',types)
        limits=f'''ha1300_clearance_limit = {{
     add = {{ desc = "HA1300_CLEARANCE_BASE" value = {cfg['base_levels']} }}
     add = {{ desc = "HA1300_CLEARANCE_VEGETATION" value = modifier:{V_MOD} }}
     add = {{ desc = "HA1300_CLEARANCE_CLIMATE" value = modifier:{C_MOD} }}
    }}
    '''
        write_text(output,'in_game/common/script_values/ha1300_test.txt',limits)
        gate='\n'.join('   this = location:'+c['location'] for c in cases)
        building=f'''{BUILDING} = {{
     is_foreign = no
     audio_tier = 1
     max_levels = ha1300_clearance_limit
     increase_per_level_cost = 0
     category = infrastructure_category
     icon = {BUILDING}
     pop_type = peasants
     employment_size = 0
     rural_settlement = yes
     town = yes
     city = yes
     megalopolis = yes
     location_potential = {{ OR = {{
    {gate}
     }} }}
     price = ha1300_clearance_price
     build_time = {cfg['build_days']}
     construction_demand = ha1300_clearance_construction
     unique_production_methods = {{
      ha1300_clearance_maintenance = {{ category = building_maintenance }}
     }}
     raw_modifier = {{ local_population_capacity = {cfg['capacity_per_level']} }}
     forbidden_for_estates = yes
     ai_forbid_shutdown = yes
    }}
    '''
        write_text(output,'in_game/common/building_types/ha1300_test.txt',building)
        write_text(output,'in_game/common/prices/ha1300_test.txt','ha1300_clearance_price = { gold = 1 }\n')
        # Construction demands are economic goods-demand definitions, not prices.
        write_text(output,'in_game/common/goods_demand/ha1300_test.txt','ha1300_clearance_construction = { category = building_construction }\n')
        entries={BUILDING:'Land Clearance (Geography Test)',BUILDING+'_desc':'A controlled clearing trial. Inspect the maximum-level tooltip for the contributions from local geography.',
          'ha1300_clearance_maintenance':'Unstaffed Test Works','ha1300_clearance_price':'Test Construction',
          'ha1300_clearance_construction':'Test Construction',
          VEGETATION:'Forest — Clearing Test',VEGETATION+'_desc':'Forest with an additional allowance for land clearing.',
          CLIMATE:'Continental — Clearing Test',CLIMATE+'_desc':'Continental climate with an additional allowance for land clearing.',
          V_MOD:'Land Clearance Levels from Vegetation',C_MOD:'Land Clearance Levels from Climate',
          'MODIFIER_TYPE_NAME_'+V_MOD:'Land Clearance Levels from Vegetation','MODIFIER_TYPE_NAME_'+C_MOD:'Land Clearance Levels from Climate',
          'MODIFIER_TYPE_DESC_'+V_MOD:'Additional land-clearance levels supplied by vegetation.',
          'MODIFIER_TYPE_DESC_'+C_MOD:'Additional land-clearance levels supplied by climate.',
          'HA1300_CLEARANCE_BASE':'Base Allowance','HA1300_CLEARANCE_VEGETATION':'Vegetation','HA1300_CLEARANCE_CLIMATE':'Climate',
          'ha1300_clearance_limit':'Land Clearance Limit'}
        write_text(output,'main_menu/localization/english/ha1300_test_l_english.yml','l_english:\n'+''.join(f' {k}: "{v}"\n' for k,v in entries.items()))
        assets={
          'main_menu/gfx/interface/vegetation/'+VEGETATION+'.dds':game/'main_menu/gfx/interface/vegetation/forest.dds',
          'main_menu/gfx/interface/vegetation/'+VEGETATION+'_big.dds':game/'main_menu/gfx/interface/vegetation/forest_big.dds',
          'main_menu/gfx/interface/icons/climate/'+CLIMATE+'.dds':game/'main_menu/gfx/interface/icons/climate/continental.dds',
          'main_menu/gfx/interface/icons/climate/'+CLIMATE+'_frame.dds':game/'main_menu/gfx/interface/icons/climate/continental_frame.dds',
          'in_game/gfx/interface/icons/buildings/'+BUILDING+'.dds':ROOT/'assets/geography_test/land_clearance.dds'}
        for rel,src in assets.items():
            dst=output/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
    metadata={'name':MOD_NAME,'id':MOD_ID,'version':'0.9.0','supported_game_version':cfg['supported_game_version'],
      'short_description':'Global climate, topography, vegetation, soil type and fertility. Enable alone and start a new 1337 game.',
      'tags':['Utilities'],'relationships':[],'game_custom_data':{}}
    write_text(output,'.metadata/metadata.json',json.dumps(metadata,indent=2))
    checklist=['# '+MOD_NAME,'','Enable this mod ALONE in a test playset, restart EU5 and start a NEW 1337 game as Sweden. Geography is loaded from location templates; do not use an existing campaign. Main Prosper or Perish and other map mods must be disabled for a controlled result.','','Open the following locations and find Land Clearance (Geography Test). It starts at zero levels. Hover its maximum level to inspect Base Allowance, Vegetation and Climate.','','| Location | Vegetation addition | Climate addition | Expected limit |','|---|---:|---:|---:|']
    for c in expected:checklist.append(f"| {c['location']} | +{c['vegetation_bonus']} | +{c['climate_bonus']} | {c['expected_max_levels']} |")
    checklist+=['','## Engine checks','','- New forest/climate names, icons and tooltips render, with their extra level modifiers.','- Limits match the table; outside these four locations the test building is unavailable.','- Build one level in each: confirm its raw capacity contribution and resulting total capacity.','- Each level adds 1 game capacity unit (normally 1,000 displayed people), multiplied by the full active native relative factor. Record that factor from the local capacity tooltip; native development/rank effects may differ by location. This test does not force the agricultural model multiplier into the game.','- Build to the cap, including queued levels; verify another level cannot be built.','- Demolish one level: one slot should reopen, not change the total maximum.','- Save, reload and recheck the attributes, capacity and limits.','- Inspect error.log for ha1300 keys, missing icons, invalid modifier/types or unknown definitions.','- The new categories inherit the original forest/continental definition except for the explicit test allowance. Scripts that explicitly check the vanilla key do not automatically recognise a new subtype. This test does not implement global compatibility rewrites.','','Construction has a nominal cost of 1 gold, no goods demand or staffing, and a base duration of 2 days; native modifiers may affect the displayed cost/time. Empty maintenance is deliberate.','','## Status','','Build/parser/unit-test and deployed byte-parity checks are engineering evidence only. Loading, construction, UI and save/reload behavior remain pending until checked in the running game.','','## Rebuild and sync','','`uv run ha1300 geography-test`','','Build without syncing: `uv run ha1300 geography-test --build-only`','','The live destination comes from ignored geography_test.local.toml. Only the dedicated test folder is managed. To uninstall, disable this mod and remove that folder.']
    if not cases:
        checklist=['# '+MOD_NAME,'','Global climate, topography, vegetation, soil type and fertility using the native location interface.','','Restart EU5 and start a NEW campaign to load the updated geography. Enable the test mod alone.','','The old Swedish clearing trial, artificial forest/climate variants and test bonuses have been retired. All locations use the global vegetation assignment and mapped climate and topography.','','Build and sync: `uv run ha1300 geography-test`. Build only: `uv run ha1300 geography-test --build-only`.']
    write_text(output,'README.md','\n'.join(checklist)+'\n')
    if cfg.get('soil_types'):
        from .geography_test_soil import add_soil_prototype
        add_soil_prototype(output,game,cfg)
    if cfg.get('test_attributes'):
        from .geography_test_attributes import add_attribute_prototype
        add_attribute_prototype(output,game,cfg)
    if cfg.get('native_geography_view'):
        from .geography_test_native_view import add_native_view
        add_native_view(output,game,cfg)
    if cfg.get('global_soil_types'):
        from .geography_test_global_soils import emit_soils
        emit_soils(output,game)
    if cfg.get('global_fertility'):
        from .geography_test_fertility import emit_fertility
        fertility_export=emit_fertility(output,game)
    if cfg.get('global_vegetation'):
        from .geography_test_vegetation import emit_vegetation
        vegetation_export=emit_vegetation(output,game)
    if cfg.get('global_topography'):
        from .geography_test_topography import emit_topography
        topography_export=emit_topography(output,game)
    if cfg.get('global_climate'):
        from .geography_test_climate import emit_climate
        climate_export=emit_climate(output,game)
    if cfg.get('geography_compatibility'):
        from .geography_compatibility import emit, validate_references
        emit(output,game)
        validate_references(output,game)
    if cfg.get('global_rivers'):
        from .geography_compatibility import emit_rivers
        emit_rivers(output)
    files={str(p.relative_to(output)):sha(p) for p in sorted(output.rglob('*')) if p.is_file() and p.name!='ha1300-build.json'}
    manifest={'id':MOD_ID,'files':files,'sources':{str(p):sha(p) for p in [*sources.values(),*assets.values()]},
      'config_sha256':sha(config_path),'code_sha256':sha(Path(__file__)),'cases':expected,'engine_status':'pending manual test'}
    if climate_result:
        manifest['climate']=climate_export
        manifest['climate_code_sha256']={p.name:sha(p) for p in (ROOT/'src/historical_agriculture').glob('*climate*.py')}
    if topography_result:
        manifest['topography']=topography_export
        manifest['topography_code_sha256']={p.name:sha(p) for p in (ROOT/'src/historical_agriculture').glob('*topography*.py')}
    if vegetation_result:
        manifest['vegetation']=vegetation_export
        manifest['vegetation_code_sha256']={p.name:sha(p) for p in (ROOT/'src/historical_agriculture').glob('*vegetation*.py')}
    if fertility_result:
        manifest['fertility']=fertility_export
        manifest['fertility_code_sha256']={p.name:sha(p) for p in (ROOT/'src/historical_agriculture').glob('*fertility*.py')}
    if soil_result:
        manifest['soil_csv_sha256']=soil_result['csv_sha256']
        manifest['soil_code_sha256']={p.name:sha(p) for p in (ROOT/'src/historical_agriculture').glob('*soil*.py')}
        manifest['soil_icon_sources']={p.name:sha(p) for p in (ROOT/'assets/geography_test/soil_types').glob('*.png') if p.name!='preview.png'}
    (output/'ha1300-build.json').write_text(json.dumps(manifest,indent=2,allow_nan=False))
    (report/'expected_results.json').write_text(json.dumps(expected,indent=2))
    result={'name':MOD_NAME,'output':str(output),'expected_limits':{c['location']:c['expected_max_levels'] for c in expected},'engine_status':'pending manual test'}
    if deploy:result['sync']=sync_tree(output,target,mod_parent)
    (report/'build_result.json').write_text(json.dumps(result,indent=2))
    return result
