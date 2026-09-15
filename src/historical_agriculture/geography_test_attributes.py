"""Four additional lightweight geography attributes for the UI/stacking trial."""
from .geography_test import write_text
from .geography_test_ui import attribute_effect_rows

def add_attribute_prototype(output, game, cfg):
    attrs=cfg['test_attributes']
    definitions='';modifier_types='';custom='';entries={};widgets=''
    for key,attr in attrs.items():
        grade_key=f'ha1300_{key}_grade'
        modifier_types+=f'{grade_key} = {{ decimals = 0 game_data = {{ category = location }} }}\n'
        entries[grade_key]=attr['label']+' Grade'
        entries['MODIFIER_TYPE_NAME_'+grade_key]=attr['label']+' Grade'
        entries['MODIFIER_TYPE_DESC_'+grade_key]='Assigned class for this geography test.'
        custom+=f'ha1300_{key}_name = {{\n type = location\n'
        for grade,(value,settings) in enumerate(attr['values'].items(),1):
            mod=f'ha1300_{key}_{value}'
            definitions+=f'''{mod} = {{
 game_data = {{ category = location }}
 {grade_key} = {grade}
 local_monthly_food_modifier = {settings['food']}
}}
'''
            entries[mod]=attr['label']+': '+settings['label']
            entries[mod+'_label']=entries[mod]
            entries[mod+'_desc']=attr['description']
            entries['STATIC_MODIFIER_NAME_'+mod]=entries[mod]
            entries['STATIC_MODIFIER_DESC_'+mod]=attr['description']
            custom+=f' text = {{ localization_key = {mod}_label trigger = {{ modifier:{grade_key} = {grade} }} }}\n'
        custom+=f' text = {{ localization_key = ha1300_{key}_unknown fallback = yes }}\n}}\n'
        entries[f'ha1300_{key}_unknown']=attr['label']+': Unassigned'
        entries[f'HA1300_{key.upper()}_HELP']=attr['description']+' Test food-production effects appear in the breakdown below.'
        icon=attr['icon']
        if not (game/'main_menu'/icon).is_file():raise ValueError('Missing icon: '+icon)
        widgets+=f'''
                                widget = {{
                                    name = "ha1300_{key}_icon"
                                    size = {{ 30 30 }}
                                    datacontext = "[LocationView.GetLocation]"
                                    background = {{ texture = "[GetClimateFrame(LocationView.GetLocation.GetClimate)]" }}
                                    icon = {{ size = {{ 30 30 }} texture = "{icon}" }}
                                    tooltipwidget = {{
                                        ContextualTooltipType = {{
                                            blockoverride "title_text" {{ text = "[LocationView.GetLocation.Custom('ha1300_{key}_name')]" }}
                                            blockoverride "title_icon_texture" {{ texture = "{icon}" }}
                                            blockoverride "tooltip_content" {{
                                                TooltipTextBlock = {{
                                                    blockoverride "text" {{ text = "HA1300_{key.upper()}_HELP" }}
                                                }}
{attribute_effect_rows(grade_key,['ha1300_'+key+'_'+value for value in attr['values']])}
                                            }}
                                        }}
                                    }}
                                }}
'''
    write_text(output,'main_menu/common/static_modifiers/ha1300_attributes.txt',definitions)
    write_text(output,'main_menu/common/modifier_type_definitions/ha1300_attributes.txt',modifier_types)
    write_text(output,'in_game/common/customizable_localization/ha1300_attributes.txt',custom)
    write_text(output,'main_menu/localization/english/ha1300_attributes_l_english.yml','l_english:\n'+''.join(f' {k}: "{v}"\n' for k,v in entries.items()))
    # Native startup location modifier lists: no monthly events or scans.
    setup='locations = {\n'
    table=[]
    for case in cfg['cases']:
        setup+=f" {case['location']} = {{\n  timed_modifiers = {{ timed_modifiers = {{\n"
        total=cfg['soil_types'][case['soil']]['food_production_modifier']
        descriptions=[]
        for key,attr in attrs.items():
            value=case['attributes'][key];settings=attr['values'][value]
            setup+=f'   {{ modifier = "ha1300_{key}_{value}" start_date = 1337.1.1 date = 9999.1.1 size = 1 }}\n'
            total+=settings['food'];descriptions.append(settings['label'])
        setup+='  } }\n }\n'
        table.append(f"| {case['location']} | "+' | '.join(descriptions)+f" | {total:+.0%} |")
    setup+='}\n'
    # EU5 concatenates startup fragments; a BOM here becomes an unexpected token.
    setup_path=output/'main_menu/setup/start/99_ha1300_attributes.txt'
    setup_path.parent.mkdir(parents=True,exist_ok=True)
    setup_path.write_text(setup,encoding='utf-8')
    p=output/'in_game/gui/location_window.gui';gui=p.read_text(encoding='utf-8-sig')
    anchor='\t\t\t\t\t\t\t\t### NOT COASTAL'
    if gui.count(anchor)!=1:raise ValueError('Missing geography strip anchor')
    write_text(output,'in_game/gui/location_window.gui',gui.replace(anchor,widgets+anchor,1))
    p=output/'README.md';readme=p.read_text(encoding='utf-8-sig')
    readme+='\n## Four additional attributes\n\nWater Supply, Floodplain Extent, Waterlogging and Clearable Land each have four possible values and a separate UI icon. They apply separate native food modifiers through startup location data. These assignments and food effects are deliberately synthetic, not historical calibration. Clearing limits remain 2/6/6/10. Restart and start a new 1337 Sweden game.\n\n| Location | Water | Floodplain | Waterlogging | Clearable land | Combined food modifier including soil |\n|---|---|---|---|---|---:|\n'+'\n'.join(table)+'\n\nCombined percentages above exclude all vanilla modifiers. The food tooltip should list separate named sources. Locations outside the four cases show Unassigned.\n'
    write_text(output,'README.md',readme)