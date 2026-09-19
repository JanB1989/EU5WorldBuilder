"""Six native location properties, with no synthetic attribute modifiers."""
import re

from .geography_test import write_text, block_span

LOC = 'LocationView.GetLocation'


def guard_location_models(gui):
    """Keep inherited list slices/repeaters valid even while widgets are hidden.

    EU5 can evaluate hidden data models. Skipping one item from an empty model
    asks the engine to reshape to -1, so visibility conditions are insufficient.
    This only patches top-level list constructors in the window we already own.
    """
    pattern = re.compile(r'(?m)^([^#\n]*?\bdatamodel\s*=\s*"\[)(DataModelSkipFirst|DataModelRepeatedItem)\((.*)\)(\]")')
    def replace(m):
        prefix, fn, args, suffix = m.groups()
        if fn == 'DataModelRepeatedItem':
            if args.startswith("Max_int32('(int32)0', "): return m[0]
            guarded = f"Max_int32('(int32)0', {args})"
        else:
            depth = 0
            quote = None
            split = None
            for i, c in enumerate(args):
                if quote:
                    if c == quote: quote = None
                elif c in "\"'": quote = c
                elif c == '(': depth += 1
                elif c == ')': depth -= 1
                elif c == ',' and depth == 0:
                    split = i; break
            if split is None: raise ValueError('Unrecognised DataModelSkipFirst arguments')
            model, count = args[:split].strip(), args[split+1:].strip()
            if count.startswith("Max_int32('(int32)0', Min_int32("): return m[0]
            guarded = f"{model}, Max_int32('(int32)0', Min_int32({count}, GetDataModelSize({model})))"
        return f'{prefix}{fn}({guarded}){suffix}'
    return pattern.sub(replace, gui)


def tooltip(title, icon, content, concept, mapmode=None):
    # Match native geography tooltips, including their real concept link.
    button = (f'blockoverride "title_button" {{ mapmode_tooltip_button = {{ '
              f"datacontext = \"[GetMapMode('{mapmode}')]\" }} }}") if mapmode else ''
    return f'''tooltipwidget = {{
        ContextualTooltipType = {{
            blockoverride "title_text" {{ text = "{title}" }}
            blockoverride "concept_link" {{ visible = yes text = "[{concept}|E]" }}
            blockoverride "title_icon" {{
                widget = {{
                    using = tooltip_title_icon_size
                    background = {{ texture = "[GetClimateFrame({LOC}.GetClimate)]" }}
                    icon = {{ using = tooltip_title_icon_size texture = "{icon}" }}
                }}
            }}
            {button}
            blockoverride "tooltip_content" {{ {content} }}
        }}
    }}'''


def text_block(key):
    return f'TooltipTextBlock = {{ blockoverride "text" {{ text = "{key}" }} }}'


def chip(name, icon, value, tip, context=None, extra=''):
    # Match the original geography strip: framed 30px icons, values in tooltips.
    # Do not emit an empty text widget: EU5 renders its placeholder over river labels.
    art = f'icon = {{ size = {{ 30 30 }} texture = "{icon}" }}'
    if name == 'coast':
        art = f'''icon = {{ size = {{ 30 30 }} texture = "gfx/interface/icons/location_icons/coastal.dds"
                    visible = "[{LOC}.IsCoastal]" }}
                 icon = {{ size = {{ 30 30 }} texture = "gfx/interface/icons/location_icons/inland.dds"
                    visible = "[Not({LOC}.IsCoastal)]" }}'''
    return f'''widget = {{
        name = "ha1300_native_{name}"
        size = {{ 30 30 }}
        datacontext = "[{context or LOC}]"
        {tip}
        background = {{ texture = "[GetClimateFrame({LOC}.GetClimate)]" }}
        {art}
        {extra}
    }}'''


def add_native_view(output, game, cfg):
    custom = []
    entries = {
        'HA1300_COASTAL': 'Coastal', 'HA1300_INLAND': 'Inland',
        'HA1300_LAKESIDE': 'Lakeside', 'HA1300_NO_LAKE': 'No lake',
        'HA1300_LAKE_TITLE': 'Lake adjacency',
        'HA1300_LAKE_HELP': 'Whether this location borders a lake. This display adds no effects.',
        'HA1300_COAST_TITLE': 'Coastal access',
        'HA1300_COAST_HELP': 'Whether this location borders the sea. The effects below belong to its coastal status.',
        'HA1300_MAX_WINTER_TITLE': 'Maximum winter severity',
        'HA1300_MAX_WINTER_HELP': 'The maximum winter level for this location, rather than the current seasonal weather.',
        'HA1300_UNKNOWN': 'Unknown', 'HA1300_RIVER_NONE': '-',
        'HA1300_RIVER_PRESENT': '?',
    }
    for key, trigger, yes, no in [
        ('coast', 'is_coastal', 'HA1300_COASTAL', 'HA1300_INLAND'),
        ('lake', 'is_adjacent_to_lake', 'HA1300_LAKESIDE', 'HA1300_NO_LAKE'),
    ]:
        custom.append(f'''ha1300_native_{key} = {{
 type = location
 text = {{ localization_key = {yes} trigger = {{ {trigger} = yes }} }}
 text = {{ localization_key = {no} fallback = yes }}
}}''')
    winter = 'ha1300_native_max_winter = {\n type = location\n'
    for value in ['none', 'mild', 'normal', 'severe']:
        key = 'HA1300_WINTER_' + value.upper()
        entries[key] = value.capitalize()
        winter += f' text = {{ localization_key = {key} trigger = {{ location_max_winter_level = {value} }} }}\n'
    custom.append(winter + ' text = { localization_key = HA1300_UNKNOWN fallback = yes }\n}\n')

    widgets = []
    for name, getter, art, native_tip in [
        ('topography','GetTopography','GetTopographyIcon','Topography_tooltip'),
        ('climate','GetClimate','GetClimateIcon','Climate_tooltip'),
        ('vegetation','GetVegetation','GetVegetationIcon','Vegetation_tooltip'),
    ]:
        widgets.append(chip(name, f'[{art}({LOC}.{getter})]',
            f'[{LOC}.{getter}.GetNameWithNoTooltip]',
            f'tooltipwidget = {{ using = {native_tip} }}', f'{LOC}.{getter}'))

    coast_icon = 'gfx/interface/icons/location_icons/coastal.dds'
    coast_content = text_block(f"[{LOC}.Custom('ha1300_native_coast')]") + text_block('HA1300_COAST_HELP') + f'''TooltipStringPairList = {{
        visible = "[{LOC}.IsCoastal]" textcontext = "[ShowModifierEffect('coastal')]"
    }}'''
    widgets.append(chip('coast', coast_icon, f"[{LOC}.Custom('ha1300_native_coast')]",
        tooltip(f"[{LOC}.Custom('ha1300_native_coast')]", coast_icon, coast_content, 'coastal')))

    # Several size flags may coexist. Display the largest, while the native
    # tooltip continues to list every actual river-size effect.
    def no_larger(size):
        tests = [f'{LOC}.HasRiverSize{i}' for i in range(size + 1, 6)]
        expr = tests[0] if tests else ''
        for t in tests[1:]: expr = f'Or({expr}, {t})'
        return f'And({LOC}.HasRiverSize{size}, Not({expr}))' if tests else f'{LOC}.HasRiverSize{size}'
    river_text = ''
    for size in range(1, 6):
        entries[f'HA1300_RIVER_{size}'] = str(size)
        river_text += f'''text_single = {{ position = {{ 17 17 }} size = {{ 12 12 }}
            autoresize = no fontsize = 11 align = center
            using = bg_number_container_bckg
            visible = "[{no_larger(size)}]" text = "HA1300_RIVER_{size}" }}\n'''
    flags = f'{LOC}.HasRiverSize1'
    for i in range(2, 6): flags = f'Or({flags}, {LOC}.HasRiverSize{i})'
    for cond, label in [(f'Not({LOC}.HasRiver)', 'HA1300_RIVER_NONE'),
                        (f'And({LOC}.HasRiver, Not({flags}))', 'HA1300_RIVER_PRESENT')]:
        river_text += f'''text_single = {{ position = {{ 17 17 }} size = {{ 12 12 }}
            autoresize = no fontsize = 11 align = center
            using = bg_number_container_bckg
            visible = "[{cond}]" text = "{label}" }}\n'''
    widgets.append(chip('river', "[GetConceptTexture('river')]", '',
        'tooltipwidget = { using = RiverModifier_tooltip }', extra=river_text))
    lake_icon = 'gfx/interface/topography/lakes.dds'
    widgets.append(chip('lake', lake_icon, f"[{LOC}.Custom('ha1300_native_lake')]",
        tooltip(f"[{LOC}.Custom('ha1300_native_lake')]", lake_icon, text_block('HA1300_LAKE_HELP'), 'lake')))

    if cfg.get('global_soil_types'):
        from .geography_test_global_soils import soil_chip
        widgets.append(soil_chip())

    if cfg.get('global_fertility'):
        from .geography_test_fertility import fertility_chip
        widgets.append(fertility_chip())

    gui = (game/'in_game/gui/location_window.gui').read_text(encoding='utf-8-sig')
    start = gui.index('hbox = {', gui.index('# BOTTOM CONDITIONS'))
    tail = gui[start:].replace('hbox', 'ha1300_target', 1)
    _, _, end = block_span(tail, 'ha1300_target')
    consumed = end - len('ha1300_target') + len('hbox')
    row = '''hbox = {
        name = "ha1300_native_geography_row"
        layoutpolicy_horizontal = expanding
        maximumsize = { -1 40 }
        background = {
            using = color_dark_blue_texture
            alpha = 1
            modify_texture = {
                using = bg_fade_vertical_up_mask_texture
                blend_mode = alphamultiply
                alpha = 1
            }
        }
        hbox = {
            margin = { 10 8 }
            using = bg_paper_card
            using = bg_cabinet_card_frame
            hbox = {
                spacing = 5
                __CHIPS__
            }
        }
        expand = {}
    }'''.replace('__CHIPS__', '\n'.join(widgets))
    write_text(output, 'in_game/gui/location_window.gui',
               guard_location_models(gui[:start] + row + gui[start+consumed:]))
    write_text(output, 'in_game/common/customizable_localization/ha1300_native_geography.txt', '\n'.join(custom))
    write_text(output, 'main_menu/localization/english/ha1300_native_geography_l_english.yml',
               'l_english:\n' + ''.join(f' {k}: "{v}"\n' for k,v in entries.items()))
    readme = (output/'README.md').read_text(encoding='utf-8-sig')
    readme += '''\n## Native geography view\n\nThe original compact framed-icon strip shows exactly six properties: topography, climate, vegetation, coast, river (largest detected native size 1–5), and lake adjacency. All are visible even when absent. Values are shown in tooltips; the river icon has a small largest-size badge (1-5, dash for no river). No caption tiles are used.\n\nSoil, water-supply, floodplain, waterlogging and clearable-land prototype modifiers and startup assignments are no longer emitted. Restart and use a fresh game to remove those assignments from the four test locations; existing saves may retain them. The original clearing trial now has limits 2/5/4/7 again.\n\nRiver size uses the same HasRiverSize1–5 native queries as the base-game river tooltip. No river size is calculated or reassigned by this mod. Maximum winter severity remains available in the native climate tooltip.\n\nThis remains a prototype: the generated structure can be checked offline; actual game layout/tooltip rendering requires an engine observation.\n'''
    if cfg.get('global_soil_types'):
        readme=readme.replace('shows exactly six properties:', 'shows six native properties:')
        readme=readme.replace('Soil, water-supply, floodplain, waterlogging and clearable-land prototype modifiers and startup assignments are no longer emitted.',
                             'The old four-location soil-quality and water-attribute prototypes remain disabled. A separate global Soil Type attribute is now added after the native icons; see Global soil types below.')
    write_text(output, 'README.md', readme)
