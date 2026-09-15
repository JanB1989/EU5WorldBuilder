"""Minimal extra location attribute/UI experiment for the test mod."""
import json
from .geography_test import write_text, block_span
from .geography_test_ui import attribute_effect_rows

SOIL_GRADE='ha1300_soil_quality'
SOIL_LEVELS='ha1300_clearance_from_soil'

def add_soil_prototype(output, game, cfg):
    types=cfg['soil_types']
    # A new script-owned attribute, stored in static location modifiers.
    definitions=''
    for grade,(key,soil) in enumerate(types.items(),1):
        definitions+=f'''ha1300_soil_{key} = {{
 game_data = {{ category = location }}
 {SOIL_GRADE} = {grade}
 {SOIL_LEVELS} = {soil['bonus']}
 local_monthly_food_modifier = {soil['food_production_modifier']}
}}
'''
    write_text(output,'main_menu/common/static_modifiers/ha1300_soil.txt',definitions)
    write_text(output,'main_menu/common/modifier_type_definitions/ha1300_soil.txt','\n'.join(f'{key} = {{ decimals = 0 game_data = {{ category = location }} }}' for key in [SOIL_GRADE,SOIL_LEVELS])+'\n')
    p=output/'in_game/map_data/location_templates.txt';text=p.read_text(encoding='utf-8-sig')
    for case in cfg['cases']:
        _,start,end=block_span(text,case['location'])
        body=text[start:end]
        if 'modifier =' in body:raise ValueError('Test location already has a template modifier')
        text=text[:start+1]+' modifier = ha1300_soil_'+case['soil']+text[start+1:]
    write_text(output,'in_game/map_data/location_templates.txt',text)
    p=output/'in_game/common/script_values/ha1300_test.txt';text=p.read_text(encoding='utf-8-sig');_,_,end=block_span(text,'ha1300_clearance_limit')
    text=text[:end-1]+f' add = {{ desc = "HA1300_CLEARANCE_SOIL" value = modifier:{SOIL_LEVELS} }}\n'+text[end-1:]
    write_text(output,'in_game/common/script_values/ha1300_test.txt',text)
    custom='ha1300_soil_name = {\n type = location\n'
    for grade,key in enumerate(types,1):
        custom+=f' text = {{ localization_key = ha1300_soil_{key}_label trigger = {{ modifier:{SOIL_GRADE} = {grade} }} }}\n'
    custom+=' text = { localization_key = ha1300_soil_unknown_label fallback = yes }\n}\n'
    write_text(output,'in_game/common/customizable_localization/ha1300_soil.txt',custom)
    entries={'ha1300_soil_unknown_label':'Soil Quality: Unassigned',
      'HA1300_CLEARANCE_SOIL':'Soil Quality',
      SOIL_GRADE:'Soil Quality Grade',SOIL_LEVELS:'Land Clearance Levels from Soil',
      'MODIFIER_TYPE_NAME_'+SOIL_GRADE:'Soil Quality Grade',
      'MODIFIER_TYPE_NAME_'+SOIL_LEVELS:'Land Clearance Levels from Soil',
      'MODIFIER_TYPE_DESC_'+SOIL_GRADE:'The assigned soil-quality class for this test location.',
      'MODIFIER_TYPE_DESC_'+SOIL_LEVELS:'Additional land-clearance levels supplied by soil quality.',
      'HA1300_SOIL_HELP':'Soil quality affects local food production and the maximum number of Land Clearance levels.',
      'HA1300_SOIL_FOOD_TOTAL':'Local Food Production Modifiers',
      'HA1300_SOIL_EFFECT':"Land Clearance levels from soil: [LocationView.GetLocation.GetModifierValue('ha1300_clearance_from_soil')]"}
    for key,soil in types.items():
        entries['ha1300_soil_'+key]='Soil Quality: '+soil['label']
        entries['ha1300_soil_'+key+'_label']='Soil Quality: '+soil['label']
        entries['ha1300_soil_'+key+'_desc']=soil['description']
        entries['STATIC_MODIFIER_NAME_ha1300_soil_'+key]=entries['ha1300_soil_'+key]
        entries['STATIC_MODIFIER_DESC_ha1300_soil_'+key]=soil['description']
    write_text(output,'main_menu/localization/english/ha1300_soil_l_english.yml','l_english:\n'+''.join(f' {k}: "{v}"\n' for k,v in entries.items()))
    # Insert a fifth icon into the existing geography strip; reuse vanilla farmland art.
    gui=(game/'in_game/gui/location_window.gui').read_text(encoding='utf-8-sig')
    widget='''
                                # HA1300 custom soil attribute prototype
                                widget = {
                                    name = "ha1300_soil_quality_icon"
                                    size = { 30 30 }
                                    datacontext = "[LocationView.GetLocation]"
                                    background = {
                                        texture = "[GetClimateFrame(LocationView.GetLocation.GetClimate)]"
                                    }
                                    icon = {
                                        size = { 30 30 }
                                        texture = "gfx/interface/vegetation/farmland.dds"
                                    }
                                    tooltipwidget = {
                                        ContextualTooltipType = {
                                            blockoverride "title_text" {
                                                text = "[LocationView.GetLocation.Custom('ha1300_soil_name')]"
                                            }
                                            blockoverride "title_icon_texture" {
                                                texture = "gfx/interface/vegetation/farmland.dds"
                                            }
                                            blockoverride "tooltip_content" {
                                                TooltipTextBlock = {
                                                    blockoverride "text" { text = "HA1300_SOIL_HELP" }
                                                }
__HA1300_SOIL_EFFECT_ROWS__
                                            }
                                        }
                                    }
                                }
'''
    widget=widget.replace('__HA1300_SOIL_EFFECT_ROWS__',attribute_effect_rows(SOIL_GRADE,['ha1300_soil_'+key for key in types]))
    anchor='\t\t\t\t\t\t\t\t### NOT COASTAL'
    if gui.count(anchor)!=1:raise ValueError('Geography UI insertion point changed')
    write_text(output,'in_game/gui/location_window.gui',gui.replace(anchor,widget+anchor,1))
    p=output/'README.md';text=p.read_text(encoding='utf-8-sig')
    text+='\n## Soil Quality UI prototype\n\nThe earlier climate/vegetation test was confirmed working by the user. A custom script-owned Soil Quality attribute is now shown as an additional farmland icon in the geography row. It is stored as a static location modifier, not a new engine database category. Hover to see its name and actual Land Clearance allowance. Other locations show Unassigned.\n\nRestart and start a fresh Sweden game for the template soil assignments.\n\n| Location | Soil | Soil bonus | New total limit |\n|---|---|---:|---:|\n'
    for case in cfg['cases']:
        soil=types[case['soil']];total=cfg['base_levels']+case['vegetation_bonus']+case['climate_bonus']+soil['bonus']
        text+=f"| {case['location']} | {soil['label']} | {soil['bonus']} | {total} |\n"
    text+='\nSoil now also applies native local_monthly_food_modifier: Poor -10%, Average 0%, Good +10%, Excellent +20%. These are test values, not accepted balance. The soil tooltip shows only the selected soil modifier effects.\n'
    write_text(output,'README.md',text)