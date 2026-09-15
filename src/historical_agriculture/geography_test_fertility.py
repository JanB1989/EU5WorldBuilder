"""Expose the complete fertility dataset in the isolated test mod."""
from pathlib import Path
import json
import pandas as pd
from .geography_test_global_soils import write_soil_texture
from .geography_test import ROOT,write_text,sha

VAR='ha1300_fertility'
MAP='ha1300_fertility'
ICON='gfx/interface/icons/map_modes/ha1300_fertility.dds'


def emit_fertility(output,game):
    cfg=json.loads((ROOT/'configs/fertility.json').read_text())
    source=ROOT/cfg['output_directory'];manifest=json.loads((source/'manifest.json').read_text())
    if sha(source/'locations.csv')!=manifest['csv_sha256']:raise ValueError('Stale fertility assignments')
    d=pd.read_csv(source/'locations.csv',keep_default_na=False)
    if d.location_tag.duplicated().any() or not d.loc[d.is_ownable,'fertility_id'].between(1,5).all():raise ValueError('Incomplete fertility map')
    # A single mod startup hook initializes both attributes. Avoid depending on
    # merging duplicate on_game_start definitions across files.
    soil_start=output/'in_game/common/on_action/ha1300_global_soils.txt'
    hook=soil_start.read_text(encoding='utf-8-sig')
    expected='on_actions = { ha1300_assign_soil_types }'
    if expected not in hook:raise ValueError('Missing shared soil startup hook')
    write_text(output,'in_game/common/on_action/ha1300_global_soils.txt',
               hook.replace(expected,'on_actions = { ha1300_assign_soil_types ha1300_assign_fertility }',1))
    actions=['ha1300_assign_fertility = { effect = {']
    for r in d[d.fertility_id>0].itertuples():
        actions.append(f'location:{r.location_tag} = {{ set_variable = {{ name = {VAR} value = {r.fertility_id} }} }}')
    actions.append('} }')
    write_text(output,'in_game/common/on_action/ha1300_fertility.txt','\n'.join(actions)+'\n')
    entries={
      'game_concept_ha1300_fertility':'Fertility',
      'game_concept_ha1300_fertility_desc':'Fertility describes the soil\'s underlying ability to make plant nutrients available and retain them. It is separate from soil type, climate and water management. The five grades are Very low, Low, Moderate, High and Very high. Existing cultivation and improvements are separate from this attribute.',
      'HA1300_FERTILITY_UNKNOWN':'Unassigned',
      'HA1300_FERTILITY_UNKNOWN_DESC':'Fertility is assigned when a new campaign begins.',
      'HA1300_FERTILITY_WATER':'Water',
      'mapmode_'+MAP+'_name':'Fertility',
      'mapmode_'+MAP+'_description':'The underlying soil fertility of each location.',
      'MAPMODE_HA1300_FERTILITY':'Fertility',
    }
    names=['ha1300_fertility_name = { type = location'];desc=['ha1300_fertility_desc = { type = location']
    color=[];tips=[];legends=[];triggers=[]
    for name,v in cfg['levels'].items():
        key='HA1300_FERTILITY_'+name.upper();condition=f'has_variable = {VAR} var:{VAR} = {v["id"]}'
        names.append(f'text = {{ localization_key = {key} trigger = {{ {condition} }} }}')
        desc.append(f'text = {{ localization_key = {key}_DESC trigger = {{ {condition} }} }}')
        entries[key]=v['label'];entries[key+'_DESC']=v['description']
        entries[key+'_MAP']='[ROOT.GetLocation.GetName]\\nFertility: '+v['label']
        branch='if' if v['id']==1 else 'else_if';rgb='rgb { '+' '.join(map(str,v['color']))+' }'
        color.append(f'{branch} = {{ limit = {{ {condition} }} value = {rgb} }}')
        tips.append(f'{branch} = {{ limit = {{ {condition} }} value = {key}_MAP }}')
        legends.append(f'legend_key = {{ desc = "{key}" color = {rgb} }}')
        triggers.append(f'ha1300_fertility_is_{name} = {{ {condition} }}')
    names.append('text = { localization_key = HA1300_FERTILITY_UNKNOWN fallback = yes } }')
    desc.append('text = { localization_key = HA1300_FERTILITY_UNKNOWN_DESC fallback = yes } }')
    write_text(output,'in_game/common/customizable_localization/ha1300_fertility.txt','\n'.join(names+desc)+'\n')
    write_text(output,'in_game/common/scripted_triggers/ha1300_fertility.txt','\n'.join(triggers)+'\n')
    write_text(output,'main_menu/common/game_concepts/ha1300_fertility.txt','ha1300_fertility = { texture = "map_modes/ha1300_fertility" }\n')
    write_text(output,'main_menu/localization/english/ha1300_fertility_l_english.yml','l_english:\n'+''.join(f' {k}: "{v}"\n' for k,v in entries.items()))
    assets=ROOT/'assets/geography_test/fertility'
    for name in cfg['levels']:
        write_soil_texture(assets/(name+'.png'),output/'main_menu/gfx/interface/fertility'/(name+'.dds'),64)
    for phase in ['main_menu','in_game']:
        write_soil_texture(assets/'high.png',output/phase/ICON,128)
    color.append('else = { value = rgb { 45 60 72 } }')
    tips.append('else_if = { limit = { is_land = no } value = HA1300_FERTILITY_WATER } else = { value = HA1300_FERTILITY_UNKNOWN }')
    # Share the native map rendering settings with the already working soil mode.
    soilmode=(output/'in_game/gfx/map/map_modes/ha1300_soils.txt').read_text(encoding='utf-8-sig')
    settings=soilmode[soilmode.index(' small_map_names'):]
    mode=MAP+' = {\n map_color = { '+'\n'.join(color)+' }\n tooltip_key = { '+'\n'.join(tips)+' }\n'+'\n'.join(legends)+'\n'+settings
    write_text(output,'in_game/gfx/map/map_modes/ha1300_fertility.txt',mode)
    write_text(output,'fertility_assignments.csv',d.to_csv(index=False))
    write_text(output,'fertility_source_manifest.json',json.dumps(manifest,indent=2))
    readme=(output/'README.md').read_text(encoding='utf-8-sig')
    readme+='\n## Fertility\n\nFully restart EU5 and start a NEW campaign to initialize Fertility. The eighth geography icon has five grades and a blue Fertility concept link. Its header button opens the Fertility map under Geography. Five custom plant icons show progressively stronger growth, matching each fertility grade.\n\nEvery ownable location has a grade derived from HWSD topsoil chemistry; missing evidence and spatial estimates remain flagged in fertility_assignments.csv. Modern chemistry is an approximation, not a recovered 1300 measurement. The five game grades are our shared classification, not official FAO fertility classes. No food bonus or recurring evaluation is added yet.\n\nReproduce with `uv run ha1300 fertility`, then `uv run ha1300 geography-test`. Methods and uncertainty: reports/fertility_method.md.\n'
    write_text(output,'README.md',readme)
    return {'csv_sha256':manifest['csv_sha256'],'ownable_locations':int(d.is_ownable.sum()),'icon_source_sha256':{name:sha(assets/(name+'.png')) for name in cfg['levels']}}


def fertility_chip():
    from .geography_test_native_view import chip,tooltip,LOC
    cfg=json.loads((ROOT/'configs/fertility.json').read_text())
    title=f"[{LOC}.Custom('ha1300_fertility_name')]"
    content=f"TooltipFlavorTextBlock = {{ blockoverride \"text\" {{ text = \"[{LOC}.Custom('ha1300_fertility_desc')]\" }} }}"
    variants=[]
    for name in cfg['levels']:
        icon=f'gfx/interface/fertility/{name}.dds'
        selected=f"EqualTo_string({LOC}.Custom('ha1300_fertility_name'), Localize('HA1300_FERTILITY_{name.upper()}'))"
        if name=='moderate':
            selected=f"Or({selected}, EqualTo_string({LOC}.Custom('ha1300_fertility_name'), Localize('HA1300_FERTILITY_UNKNOWN')))"
        variants.append(chip('fertility_'+name,icon,'',tooltip(title,icon,content,'ha1300_fertility',MAP),extra=f'visible = "[{selected}]"'))
    return 'widget = { name = "ha1300_native_fertility" size = { 30 30 }\n'+'\n'.join(variants)+'\n}'
