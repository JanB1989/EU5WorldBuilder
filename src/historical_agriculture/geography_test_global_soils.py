"""Global soil-type attribute and categorical Geography map mode for the test mod."""
import json
from pathlib import Path
import pandas as pd
from PIL import Image
from .geography_test import ROOT, write_text, sha

VAR = 'ha1300_soil_type'
MAP = 'ha1300_soil_types'


def write_soil_texture(source, destination, size):
    # Match eu5_building_pipeline.generator.write_dds_icon: RGBA PNG -> DDS.
    # Geography uses native 64px textures; map-mode buttons use 128px.
    with Image.open(source) as image:
        image=image.convert('RGBA')
        if image.size!=(512,512) or image.getchannel('A').getextrema()!=(0,255):
            raise ValueError(f'Soil master must be 512px with real transparency: {source}')
        destination.parent.mkdir(parents=True,exist_ok=True)
        image.resize((size,size),Image.Resampling.LANCZOS).save(destination,format='DDS')


def emit_soils(output, game):
    cfg=json.loads((ROOT/'configs/soil_types.json').read_text())
    source=ROOT/cfg['output_directory']
    manifest=json.loads((source/'manifest.json').read_text())
    if sha(source/'locations.csv') != manifest['csv_sha256']:raise ValueError('Stale soil assignments')
    d=pd.read_csv(source/'locations.csv',keep_default_na=False)
    if d.location_tag.duplicated().any() or not d.loc[d.is_ownable,'soil_id'].between(1,6).all():
        raise ValueError('Incomplete soil assignments')
    # One startup pass, fixed location scopes, persistent variables. Do not replace
    # template modifiers: Nile and other native geographical effects must survive.
    setup=['on_game_start = { on_actions = { ha1300_assign_soil_types } }',
           'ha1300_assign_soil_types = { effect = {']
    for r in d[d.soil_id>0].itertuples():
        setup.append(f' location:{r.location_tag} = {{ set_variable = {{ name = {VAR} value = {r.soil_id} }}'
                     + (' set_variable = { name = ha1300_soil_inferred value = 1 }' if r.inferred else '')+' }')
    setup.append('} }')
    write_text(output,'in_game/common/on_action/ha1300_global_soils.txt','\n'.join(setup)+'\n')
    names=['ha1300_soil_type_name = { type = location']
    descriptions=['ha1300_soil_type_description = { type = location']
    entries={
      'mapmode_'+MAP+'_name':'Soil Type',
      'mapmode_'+MAP+'_description':'The representative soil material in each location.',
      'HA1300_SOIL_UNKNOWN':'Soil type unavailable',
      'HA1300_SOIL_UNKNOWN_HELP':'Soil assignments are initialized when a new campaign begins.',
      'HA1300_SOIL_SCOPE':'Soil type describes the ground material. Fertility is separate.',
      'game_concept_ha1300_soil_type':'Soil Type',
      'game_concept_ha1300_soil_type_desc':'Soil type describes the predominant ground material: sand, loam, silt, clay, peat or stony soil. Fertility describes its natural agricultural quality separately. A location may contain a mixture of soils; its displayed type represents the mapped mixture. Where soil observations are unavailable, a nearby mapped location provides an estimate.',
      'HA1300_SOIL_INFERRED':'Estimated from the nearest location with mapped soil evidence.',
      'HA1300_SOIL_DIRECT':'Representative type from the mapped soil mixture.',
      'HA1300_SOIL_WATER':'Water',
      'HA1300_SOIL_MAP_UNKNOWN':'Soil type is unavailable here.',
    }
    triggers=[];color=[' map_color = {'];tooltip=[' tooltip_key = {'];legend=[]
    for name,t in cfg['types'].items():
        key='HA1300_SOIL_'+name.upper();n=t['id']
        condition=f'has_variable = {VAR} var:{VAR} = {n}'
        names.append(f' text = {{ localization_key = {key}_TITLE trigger = {{ {condition} }} }}')
        descriptions.append(f' text = {{ localization_key = {key}_DESC trigger = {{ {condition} }} }}')
        entries[key]=t['label'];entries[key+'_TITLE']=t['label'];entries[key+'_DESC']=t['description']
        entries[key+'_MAP']='[ROOT.GetLocation.GetName]\\nSoil: '+t['label']+'\\n'+t['description']
        branch='if' if n==1 else 'else_if'
        rgb='rgb { '+' '.join(map(str,t['color']))+' }'
        color.append(f' {branch} = {{ limit = {{ {condition} }} value = {rgb} }}')
        tooltip.append(f' {branch} = {{ limit = {{ {condition} }} value = {key}_MAP }}')
        legend.append(f' legend_key = {{ desc = "{key}" color = {rgb} }}')
        triggers.append(f'ha1300_soil_is_{name} = {{ {condition} }}')
    names.append(' text = { localization_key = HA1300_SOIL_UNKNOWN fallback = yes } }')
    descriptions.append(' text = { localization_key = HA1300_SOIL_UNKNOWN_HELP fallback = yes } }')
    color.append(' else = { value = rgb { 45 60 72 } } }')
    tooltip.append(' else_if = { limit = { is_land = no } value = HA1300_SOIL_WATER } else = { value = HA1300_SOIL_MAP_UNKNOWN } }')
    mode=MAP+' = {\n'+'\n'.join(color+tooltip+legend)+'''
 small_map_names = location
 medium_map_names = location
 large_map_names = none
 small_tooltip_context = location
 medium_tooltip_context = location
 large_tooltip_context = location
 fill_in_impassable = yes
 enable_snow = no
 enable_rivers = yes
 flatmap_behaviour = always
 use_fow = no
 category = geography
 index = 2
 allow_allocate_hotkey = yes
 map_markers = { all = no }
 gradient_parameters = {
  zoom_step = 2
  gradient_alpha_inside = 1
  gradient_alpha_outside = 1
  gradient_width = 0.25
  gradient_color_mult = 0.9
  edge_width = 0
  edge_sharpness = 0.01
  edge_alpha = 0
  edge_color_mult = 0
  before_lighting_blend = 0.5
  after_lighting_blend = 0.5
 }
 color_refresh_counters = { LocationOwnerChanged }
}
'''
    write_text(output,'in_game/gfx/map/map_modes/ha1300_soils.txt',mode)
    evidence='''ha1300_soil_type_evidence = { type = location
 text = { localization_key = HA1300_SOIL_INFERRED trigger = { has_variable = ha1300_soil_inferred } }
 text = { localization_key = HA1300_SOIL_DIRECT fallback = yes }
}'''
    write_text(output,'in_game/common/customizable_localization/ha1300_global_soils.txt','\n'.join(names+descriptions)+evidence+'\n')
    write_text(output,'in_game/common/scripted_triggers/ha1300_global_soils.txt','\n'.join(triggers)+'\n')
    write_text(output,'main_menu/localization/english/ha1300_global_soils_l_english.yml','l_english:\n'+''.join(f' {k}: "{v}"\n' for k,v in entries.items()))
    write_text(output,'main_menu/common/game_concepts/ha1300_soils.txt',
               'ha1300_soil_type = { texture = "map_modes/ha1300_soil_types" }\n')
    assets=ROOT/'assets/geography_test/soil_types'
    for name in cfg['types']:
        write_soil_texture(assets/(name+'.png'),output/'main_menu/gfx/interface/soil_types'/(name+'.dds'),64)
    for phase in ['main_menu','in_game']:
        dst=output/phase/'gfx/interface/icons/map_modes'/f'{MAP}.dds'
        write_soil_texture(assets/'loam.png',dst,128)
    # Export the exact consumed assignments with the test build for auditing.
    write_text(output,'soil_assignments.csv',d.to_csv(index=False))
    write_text(output,'soil_source_manifest.json',json.dumps(manifest,indent=2))
    p=output/'README.md'
    text=p.read_text(encoding='utf-8-sig')
    text+='''\n## Global soil types\n\nRestart EU5 and start a NEW campaign. In the map-mode selector open Geography, then the terrain/climate/vegetation group: choose Soil Type. Its six legend colors show Sand, Loam, Silt, Clay, Peat and Stony. The location geography strip has a matching soil icon and a tooltip showing that location's type.\n\nAssignments run once at campaign startup and persist in saves; there is no monthly soil update. Existing native location modifiers are preserved. This test introduces no soil food/capacity bonuses and does not assign fertility. Existing saves predating this build have no soil assignments.\n\nThe dataset uses modern HWSD physical soil evidence as an approximation. Soil component shares are classified before aggregation; unmapped game coastlines/islands use explicitly recorded nearest-soil estimates. The six-type map is complete for all ownable locations, but inferred assignments and broad dominant classes are not precise soil surveys.\n\nReproduce data: `uv run ha1300 soils`. Build and sync: `uv run ha1300 geography-test`. See soil_assignments.csv and soil_source_manifest.json for coverage, shares and donors.\n'''
    write_text(output,'README.md',text)
    return {'locations':int((d.soil_id>0).sum()),'ownable_locations':int(d.is_ownable.sum()),'source_csv_sha256':manifest['csv_sha256']}


def soil_chip():
    from .geography_test_native_view import chip,tooltip,text_block,LOC
    # Custom localization resolves labels, but does not reliably bind GUI textures.
    # Give the engine literal asset paths for both the strip and tooltip header.
    # All variants occupy one fixed slot; only the assigned soil is visible.
    cfg=json.loads((ROOT/'configs/soil_types.json').read_text())
    content=f"TooltipFlavorTextBlock = {{ blockoverride \"text\" {{ text = \"[{LOC}.Custom('ha1300_soil_type_description')]\" }} }}"
    title=f"[{LOC}.Custom('ha1300_soil_type_name')]"
    variants=[]
    for name in cfg['types']:
        icon=f"gfx/interface/soil_types/{name}.dds"
        selected=f"EqualTo_string({LOC}.Custom('ha1300_soil_type_name'), Localize('HA1300_SOIL_{name.upper()}_TITLE'))"
        if name=='loam':
            selected=f"Or({selected}, EqualTo_string({LOC}.Custom('ha1300_soil_type_name'), Localize('HA1300_SOIL_UNKNOWN')))"
        variants.append(chip('soil_'+name,icon,'',tooltip(title,icon,content,'ha1300_soil_type',MAP),extra=f'visible = "[{selected}]"'))
    return 'widget = { name = "ha1300_native_soil" size = { 30 30 }\n'+ '\n'.join(variants)+'\n}'
