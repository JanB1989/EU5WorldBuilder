"""Native vegetation values: existing UI, concept link, map mode and fixed templates."""
import json
import re
import shutil
from pathlib import Path
import pandas as pd
from .geography_test import ROOT,write_text,sha,block_span
from .geography_test_global_soils import write_soil_texture


def named_rgb(key, channels):
    # EU5 named-color rgb uses integer byte channels, not normalized floats.
    if len(channels)!=3 or any(type(v) is not int or not 0<=v<=255 for v in channels):
        raise ValueError('Named RGB requires three integer channels in 0..255')
    return key+' = rgb { '+' '.join(map(str,channels))+' }'


def vegetation_definition(source,parent,key,color_key,color):
    _,start,end=block_span(source,parent)
    body=source[start:end]
    body,n=re.subn(r"(?m)^(\s*color\s*=\s*)\w+",lambda m:m[1]+color_key,body,count=1)
    if n!=1:raise ValueError('Vegetation parent has no named color')
    body,n=re.subn(r"debug_color\s*=\s*rgb\s*\{[^{}]*\}",
                   'debug_color = rgb { '+' '.join(map(str,color))+' }',body,count=1)
    if n!=1:raise ValueError('Vegetation parent has no debug color')
    return key+' = '+body+'\n'


def patch_global_templates(source,assignments):
    """Patch only the scalar vegetation field, preserving nested modifiers."""
    starts=list(re.finditer(r'(?m)^([\w.-]+)\s*=\s*\{',source))
    result=[source[:starts[0].start()]] if starts else [source]
    seen=set()
    for i,m in enumerate(starts):
        end=starts[i+1].start() if i+1<len(starts) else len(source)
        text=source[m.start():end];name=m[1]
        if name in assignments:
            text,n=re.subn(r'\bvegetation\s*=\s*\w+',lambda _: 'vegetation = '+assignments[name],text)
            if n!=1:raise ValueError('Missing/duplicate vegetation: '+name)
            seen.add(name)
        result.append(text)
    if set(assignments)-seen:raise ValueError('Assignment absent from live game templates')
    return ''.join(result)


def emit_vegetation(output,game):
    cfg=json.loads((ROOT/'configs/vegetation.json').read_text())
    folder=ROOT/cfg['output_directory'];manifest=json.loads((folder/'manifest.json').read_text())
    if sha(folder/'locations.csv')!=manifest['csv_sha256']:raise ValueError('Stale vegetation assignments')
    d=pd.read_csv(folder/'locations.csv',keep_default_na=False)
    if d.location_tag.duplicated().any() or d.loc[d.is_ownable,'game_vegetation'].eq('').any():raise ValueError('Incomplete vegetation map')
    source=game/'in_game/common/vegetation/00_default.txt'
    original=source.read_text(encoding='utf-8-sig')
    native=[];added=[];colors=['colors = {'];entries={}
    assets=ROOT/'assets/geography_test/vegetation'
    for name in manifest['active_types']:
        t=cfg['types'][name];key=t['game_key'];color_key='ha1300_vegetation_'+name
        definition=vegetation_definition(original,t['parent'],key,color_key,t['color'])
        (native if t['native'] else added).append(definition)
        colors.append(named_rgb(color_key,t['color']))
        if not t['native']:
            entries[key]=t['label'];entries[key+'_desc']=t['description']
            write_soil_texture(assets/(name+'.png'),output/'main_menu/gfx/interface/vegetation'/(key+'.dds'),64)
            # _big is a 386x79 scenery strip, NOT the square attribute icon.
            # Reuse the parent's native scenery rather than stretch an icon.
            dst=output/'main_menu/gfx/interface/vegetation'/(key+'_big.dds')
            dst.parent.mkdir(parents=True,exist_ok=True)
            scenery='plains' if t['parent']=='sparse' else t['parent']
            shutil.copy2(game/'main_menu/gfx/interface/vegetation'/(scenery+'_big.dds'),dst)
    colors.append('}')
    # Existing keys retain all native mechanics; only their map colors change.
    write_text(output,'in_game/common/vegetation/00_default.txt','\n'.join(native))
    write_text(output,'in_game/common/vegetation/ha1300_global_vegetation.txt','\n'.join(added))
    write_text(output,'main_menu/common/named_colors/ha1300_vegetation.txt','\n'.join(colors)+'\n')
    write_text(output,'main_menu/localization/english/ha1300_vegetation_l_english.yml',
               'l_english:\n'+''.join(f' {k}: "{v}"\n' for k,v in entries.items()))
    # Every location uses the modeled assignment; no clearing-test overrides.
    templates=game/'in_game/map_data/location_templates.txt'
    # The modeled inventory must describe this game version, not a stale install.
    if sha(templates)!=manifest['inputs']['data/raw/location_inputs/game_templates.txt']:
        raise ValueError('Game templates changed since the vegetation input snapshot')
    assignments=d[d.game_vegetation.ne('')].set_index('location_tag').game_vegetation.to_dict()
    text=patch_global_templates(templates.read_text(encoding='utf-8-sig'),assignments)
    write_text(output,'in_game/map_data/location_templates.txt',text)
    d['applied_game_vegetation']=d.game_vegetation;d['test_override']=False
    write_text(output,'vegetation_assignments.csv',d.to_csv(index=False))
    write_text(output,'vegetation_source_manifest.json',json.dumps(manifest,indent=2))
    readme=(output/'README.md').read_text(encoding='utf-8-sig')
    readme+='\n## Global vegetation\n\nRestart EU5 and start a new campaign. Use Geography > Vegetation, the EXISTING native map mode. The existing vegetation icon and blue Vegetation concept link show each new type. No extra UI attribute or monthly update is added.\n\n'+str(len(manifest['active_types']))+' values are active, including all seven original types. New types inherit their documented vanilla parent effects. Parent scenery strips are retained; each new type has a custom 64px attribute icon. Exact-key vanilla scripts do not automatically treat the new values as their parents; this is an isolated geography prototype, not a balanced release.\n\nAll ownable locations are assigned. The obsolete clearing-test overrides have been removed; modeled and applied vegetation now match everywhere.\n\nSAGE PNV, HYDE 3.4 and LUH2 year 1300 provide natural formations and land use. GLWD gives modern wetland types; reconstructed 1700–2020 wetland losses guide possible restoration. Fine historical wetland placement, canopy closure and many source gaps remain inferred. The map is not a measured 1300 vegetation survey.\n\nReproduce: `uv run ha1300 vegetation`, then `uv run ha1300 geography-test`. See vegetation_source_manifest.json for occupancy, source hashes, category fallbacks and limitations.\n'
    write_text(output,'README.md',readme)
    return {'active_types':manifest['active_types'],'ownable_locations':int(d.is_ownable.sum()),
            'ownable_missing':0,'test_overrides':[],
            'source_csv_sha256':manifest['csv_sha256'],'applied_counts':d[d.is_ownable].applied_game_vegetation.value_counts().to_dict(),
            'parent_effects':{n:cfg['types'][n]['parent'] for n in manifest['active_types']},
            'icon_manifest_sha256':sha(assets/'generation.json')}
