"""Keep native resource/building rules usable with the mapped geography classes."""
import json
import re
from collections import defaultdict
from pathlib import Path

from .geography_test import ROOT, block_span, sha, write_text


def families():
    result = {}
    for attr, file in [('vegetation', 'vegetation'), ('climate', 'climate'), ('topography', 'topography')]:
        grouped = defaultdict(list)
        manifest = json.loads((ROOT/f'artifacts/{file}/manifest.json').read_text())
        active = set(manifest['active_types']) if 'active_types' in manifest else None
        for name, t in json.loads((ROOT/f'configs/{file}.json').read_text())['types'].items():
            if active is not None and name not in active: continue
            if t['game_key'] != t['parent']:
                grouped[t['parent']].append(t['game_key'])
        result[attr] = dict(grouped)
    return result


def expand_predicates(text, groups):
    # These folders contain tests, not location-template assignments. Leave
    # comments and strings intact, including literal examples in localization.
    tokens = re.compile(r'"(?:\\.|[^"\\])*"|#[^\n]*|\b(vegetation|climate|topography)\s*(=|!=)\s*(\w+)')
    def replace(m):
        attr, op, value = m.groups()
        children = groups.get(attr, {}).get(value, [])
        if not children: return m[0]
        body = ' '.join(f'{attr} = {v}' for v in [value, *children])
        return ('OR' if op == '=' else 'NOR') + ' = { ' + body + ' }'
    return tokens.sub(replace, text)


def preserve_potential(text, key, tags):
    if not tags: return text
    left, begin, end = block_span(text, key)
    block = text[begin:end]
    _, start, stop = block_span(block, 'location_potential')
    original = block[start+1:stop-1]
    alternatives = '\n'.join(f'            this = location:{tag}' for tag in sorted(tags))
    replacement = '{\n        OR = {\n            AND = {'+original+'\n            }\n'+alternatives+'\n        }\n    }'
    block = block[:start] + replacement + block[stop:]
    return text[:begin] + block + text[end:]


def emit(output, game):
    groups = families()
    changed, sources = {}, {}
    templates_path = game/'in_game/map_data/location_templates.txt'
    templates = templates_path.read_text(encoding='utf-8-sig')
    # Existing timber resources may occupy a small forest within a location whose
    # new *representative* vegetation is open. Preserve those setup resources;
    # new forestry locations still need a suitable mapped vegetation family.
    lumber = set()
    for m in re.finditer(r'(?m)^([\w.-]+)\s*=\s*\{([^{}]*)\}', templates):
        if re.search(r'\braw_material\s*=\s*lumber\b', m[2]): lumber.add(m[1])
    setup = game/'main_menu/setup/start/07_cities_and_buildings.txt'
    startup = defaultdict(set)
    clean = re.sub(r'#[^\n]*', '', setup.read_text(encoding='utf-8-sig'))
    for m in re.finditer(r'\b(\w+)\s*=\s*\{([^{}]*)\}', clean):
        location = re.search(r'\blocation\s*=\s*([\w.-]+)', m[2])
        if location and re.search(r'\blevel\s*=', m[2]): startup[m[1]].add(location[1])
    # Existing irrigation may draw from minor channels outside our discharge
    # cutoff or miss the representative location after map registration. Keep
    # those explicit historical buildings; new sites still require water.
    # File overrides preserve the native unique-production-method definitions.
    # They are not duplicate top-level REPLACE building definitions.
    for folder in ['in_game/common/building_types', 'in_game/common/goods', 'in_game/common/scripted_triggers']:
        for source in sorted((game/folder).glob('*.txt')):
            old = source.read_text(encoding='utf-8-sig')
            new = expand_predicates(old, groups)
            if folder.endswith('goods') and re.search(r'(?m)^lumber\s*=', new):
                new = preserve_potential(new, 'lumber', lumber)
            if folder.endswith('building_types'):
                for key in ['tar_kiln', 'lumber_mill', 'fruit_orchard', 'terraces', 'irrigation_systems']:
                    if re.search(r'(?m)^'+key+r'\s*=', new):
                        allowed = startup[key] | (lumber if key in ['tar_kiln', 'lumber_mill'] else set())
                        new = preserve_potential(new, key, allowed)
            if new != old:
                relative = str(source.relative_to(game))
                write_text(output, relative, new)
                changed[relative] = sha(output/relative); sources[relative] = sha(source)
    # The engine looks up these names automatically for every topography type.
    defs_path = game/'main_menu/common/modifier_type_definitions/00_modifier_types.txt'
    caps_path = game/'main_menu/common/static_modifiers/capital_in_topography.txt'
    defs, capitals, loc, icons = [], [], {}, []
    dt, ct = defs_path.read_text(encoding='utf-8-sig'), caps_path.read_text(encoding='utf-8-sig')
    for t in json.loads((ROOT/'configs/topography.json').read_text())['types'].values():
        key, parent = t['game_key'], t['parent']
        _, a, b = block_span(dt, parent+'_proximity_impact')
        defs.append(key+'_proximity_impact = '+dt[a:b])
        _, a, b = block_span(ct, 'capital_in_'+parent)
        capitals.append('capital_in_'+key+' = '+ct[a:b].replace(parent+'_proximity_impact', key+'_proximity_impact'))
        loc['MODIFIER_TYPE_NAME_'+key+'_proximity_impact'] = t['label']+' Proximity Impact'
        loc['MODIFIER_TYPE_DESC_'+key+'_proximity_impact'] = 'Changes the effect of this terrain on proximity.'
        loc['STATIC_MODIFIER_NAME_capital_in_'+key] = 'Capital in '+t['label']
        icons.append(key+'_proximity_impact = { positive = "gfx/interface/icons/modifier_types/'+parent+'_proximity_impact.dds" }')
    write_text(output, 'main_menu/common/modifier_type_definitions/ha1300_topography_compatibility.txt', '\n'.join(defs))
    write_text(output, 'main_menu/common/static_modifiers/ha1300_topography_capitals.txt', '\n'.join(capitals))
    write_text(output, 'main_menu/common/modifier_icons/ha1300_topography_compatibility.txt', '\n'.join(icons))
    write_text(output, 'main_menu/localization/english/ha1300_geography_compatibility_l_english.yml',
        'l_english:\n'+''.join(f' {k}: "{v}"\n' for k,v in loc.items()))
    sources.update({str(p.relative_to(game)): sha(p) for p in [templates_path, setup, defs_path, caps_path]})
    audit = {'source_sha256': sources, 'patched_files': changed, 'families': groups,
        'preserved_starting_lumber_locations': sorted(lumber),
        'preserved_explicit_starting_buildings': {k: sorted(startup[k]) for k in ['tar_kiln','lumber_mill','fruit_orchard','terraces','irrigation_systems']},
        'policy': 'Expanded parent tests plus preservation of existing setup resources/buildings; no costs, outputs or levels changed.'}
    write_text(output, 'geography_compatibility.json', json.dumps(audit, indent=2))
    return audit


def emit_rivers(output):
    import shutil
    config = json.loads((ROOT/'configs/rivers.json').read_text())
    report_path = ROOT/config['output']/'export_manifest.json'
    report = json.loads(report_path.read_text())
    if report['config'] != config: raise ValueError('River configuration changed; export rivers again')
    for name, expected in report['code_sha256'].items():
        if sha(ROOT/name) != expected: raise ValueError('River exporter changed; export rivers again')
    if not report.get('engineering_checks', {}).get('native_tributary_encoding'):
        raise ValueError('River export lacks native tributary encoding validation')
    source = ROOT/report['output_png']
    if sha(source) != report['output_sha256']: raise ValueError('River export PNG does not match its manifest')
    destination = output/'in_game/map_data/rivers.png'
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    write_text(output, 'river_source_manifest.json', json.dumps(report, indent=2))
    return {'source': str(source), 'sha256': sha(source), 'status': report['status']}


def validate_references(output, game):
    """Fail before deployment if a custom terrain predicate has no definition."""
    folders = {'vegetation':'vegetation', 'climate':'climates', 'topography':'topography'}
    defined = {}
    for attribute, folder in folders.items():
        files = {p.name:p for p in (game/'in_game/common'/folder).glob('*.txt')}
        files.update({p.name:p for p in (output/'in_game/common'/folder).glob('*.txt')})
        defined[attribute] = {key for p in files.values() for key in
            re.findall(r'(?m)^([\w]+)\s*=\s*\{', p.read_text(encoding='utf-8-sig'))}
    checked = 0
    for p in (output/'in_game').rglob('*.txt'):
        text = p.read_text(encoding='utf-8-sig')
        text = re.sub(r'"(?:\\.|[^"\\])*"|#[^\n]*', '', text)
        for attr, value in re.findall(r'\b(vegetation|climate|topography)\s*!?=\s*(ha1300_\w+)', text):
            if value not in defined[attr]:
                raise ValueError(f'Undefined {attr} {value} referenced in {p}')
            checked += 1
    return {'custom_geography_references_checked':checked, 'undefined_references':0}
