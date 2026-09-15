"""Native Climate values and map mode; winter stays a climate property."""
import json,re,shutil
import pandas as pd
from .geography_test import ROOT,write_text,sha,block_span
from .geography_test_vegetation import named_rgb
from .geography_test_global_soils import write_soil_texture


def definition(source,t):
    _,start,end=block_span(source,t['parent']);body=source[start:end]
    color='ha1300_color_'+t['game_key']
    body,n=re.subn(r'(?m)^(\s*color\s*=\s*)\w+',lambda m:m[1]+color,body,count=1)
    if n!=1:raise ValueError('Missing climate color')
    body,n=re.subn(r'debug_color\s*=\s*(?:rgb|hsv360)\s*\{[^{}]*\}', 'debug_color = rgb { '+' '.join(map(str,t['color']))+' }',body,count=1)
    if n!=1:raise ValueError('Missing climate debug color')
    body,n=re.subn(r'\bwinter\s*=\s*\w+','winter = '+t['winter'],body,count=1)
    if n!=1:raise ValueError('Missing winter property')
    if not t['native']:
        # Arid parents disable precipitation entirely. Steppe is semi-arid.
        body=re.sub(r'\bhas_precipitation\s*=\s*no','has_precipitation = yes',body)
        body=re.sub(r'\balways_winter\s*=\s*yes','always_winter = no',body)
    return t['game_key']+' = '+body+'\n'


def patch_climate(text,assignments):
    starts=list(re.finditer(r'(?m)^([\w.-]+)\s*=\s*\{',text));seen=set()
    result=[text[:starts[0].start()]] if starts else [text]
    for i,m in enumerate(starts):
        end=starts[i+1].start() if i+1<len(starts) else len(text)
        part=text[m.start():end]
        if m[1] in assignments:
            part,n=re.subn(r'\bclimate\s*=\s*\w+',lambda _: 'climate = '+assignments[m[1]],part)
            if n!=1:raise ValueError('Missing/duplicate climate '+m[1])
            seen.add(m[1])
        result.append(part)
    if set(assignments)-seen:raise ValueError('Unknown location climate assignment')
    return ''.join(result)


WINTER_COLORS={'none':[199,166,95],'mild':[127,170,147],'normal':[98,150,193],'severe':[195,207,233]}


def maximum_winter_map(source,cfg):
    """Replace only the native seasonal Winter display, preserving other modes."""
    left,start,end=block_span(source,'winter')
    body=source[start:end]
    colors=['map_color = {'];tooltips=['tooltip_key = {'];legend=[]
    for i,(level,rgb) in enumerate(WINTER_COLORS.items()):
        keys=[t['game_key'] for t in cfg['types'].values() if t['winter']==level]
        if not keys:raise ValueError('No climates assigned to winter '+level)
        condition='OR = { '+' '.join('climate = '+k for k in keys)+' }'
        branch='if' if i==0 else 'else_if'
        value='rgb { '+' '.join(map(str,rgb))+' }';label='HA1300_MAX_WINTER_'+level.upper()
        colors.append(f' {branch} = {{ limit = {{ {condition} }} value = {value} }}')
        tooltips.append(f' {branch} = {{ limit = {{ {condition} }} value = {label}_TT }}')
        legend.append(f' legend_key = {{ desc = "{label}" color = {value} }}')
    colors.append(' else = { value = rgb { 45 60 72 } } }')
    tooltips.append(' else = { value = HA1300_MAX_WINTER_UNAVAILABLE } }')
    replacement='\n'.join(colors+tooltips+legend)+'\n enable_snow = no'
    body,n=re.subn(r'color_mode\s*=\s*winter',lambda _:replacement,body,count=1)
    if n!=1:raise ValueError('Native winter map definition changed')
    body=body.replace('color_refresh_counters = { Month }','color_refresh_counters = {}')
    return source[:left]+'\nwinter = '+body+source[end:]


def emit_maximum_winter_map(output,game,cfg):
    source=game/'in_game/gfx/map/map_modes/map_modes.txt'
    target=output/'in_game/gfx/map/map_modes/map_modes.txt'
    text=(target if target.exists() else source).read_text(encoding='utf-8-sig')
    write_text(output,'in_game/gfx/map/map_modes/map_modes.txt',maximum_winter_map(text,cfg))
    entries={'mapmode_winter_name':'Maximum Winter Severity',
      'MAPMODE_WINTER':'#T Maximum Winter Severity#!\\nThe maximum winter level assigned by local climate. Seasonal weather varies over the year.',
      'mapmode_winter_description':'The maximum winter level assigned by local climate.',
      'HA1300_MAX_WINTER_UNAVAILABLE':'Climate winter level unavailable.'}
    for level in WINTER_COLORS:
        key='HA1300_MAX_WINTER_'+level.upper();label='No Winter' if level=='none' else level.title()+' Winter'
        entries[key]=label;entries[key+'_TT']='Maximum Winter Severity: '+label+'. This is the climate limit, not current seasonal weather.'
    write_text(output,'main_menu/localization/english/ha1300_winter_l_english.yml','l_english:\n'+''.join(f' {k}: "{v}"\n' for k,v in entries.items()))
    return sha(source)


def emit_climate(output,game):
    cfg=json.loads((ROOT/'configs/climate.json').read_text());folder=ROOT/cfg['output_directory']
    manifest=json.loads((folder/'manifest.json').read_text());d=pd.read_csv(folder/'locations.csv',keep_default_na=False)
    if sha(folder/'locations.csv')!=manifest['csv_sha256']:raise ValueError('Stale climate assignments')
    if sha(game/'in_game/map_data/location_templates.txt')!=manifest['inputs']['data/raw/location_inputs/game_templates.txt']:raise ValueError('Game templates changed')
    source=game/'in_game/common/climates/00_default.txt';text=source.read_text(encoding='utf-8-sig')
    native=[];added=[];colors=['colors = {'];loc={};assets=ROOT/'assets/geography_test/climate'
    for name,t in cfg['types'].items():
        (native if t['native'] else added).append(definition(text,t))
        colors.append(named_rgb('ha1300_color_'+t['game_key'],t['color']))
        if not t['native']:
            key=t['game_key'];loc[key]=t['label'];loc[key+'_desc']=t['description']
            write_soil_texture(assets/(name+'.png'),output/'main_menu/gfx/interface/icons/climate'/(key+'.dds'),70)
            shutil.copy2(game/'main_menu/gfx/interface/icons/climate'/(t['parent']+'_frame.dds'),output/'main_menu/gfx/interface/icons/climate'/(key+'_frame.dds'))
    colors.append('}')
    write_text(output,'in_game/common/climates/00_default.txt','\n'.join(native))
    write_text(output,'in_game/common/climates/ha1300_climates.txt','\n'.join(added))
    write_text(output,'main_menu/common/named_colors/ha1300_climates.txt','\n'.join(colors)+'\n')
    write_text(output,'main_menu/localization/english/ha1300_climates_l_english.yml','l_english:\n'+''.join(f' {k}: "{v}"\n' for k,v in loc.items()))
    target=output/'in_game/map_data/location_templates.txt'
    write_text(output,'in_game/map_data/location_templates.txt',patch_climate(target.read_text(encoding='utf-8-sig'),d.set_index('location_tag').game_climate.to_dict()))
    write_text(output,'climate_assignments.csv',d.to_csv(index=False));write_text(output,'climate_source_manifest.json',json.dumps(manifest,indent=2))
    winter_map_sha=emit_maximum_winter_map(output,game,cfg)
    readme=(output/'README.md').read_text(encoding='utf-8-sig')
    readme+='\n## Climate and winter\n\nUse Geography > Climate and the existing climate icon/blue Climate concept tooltip. Geography > Maximum Winter Severity displays those climate limits, replacing the original seasonal Winter display. Weather simulation and winter_power remain unchanged. Eighteen climate names, including all eight original values. Winter stays in the existing tooltip; no extra attribute, hidden climate variants or monthly events. All ownable locations assigned. New values use their documented native parent effects with representative winter levels; steppe permits precipitation.\n\nSource: Beck et al. (2023), doi:10.1038/s41597-023-02549-6, CC BY 4.0, 1 km 1901–1930 Koppen-Geiger map. This early modern-observation baseline is a proxy for 1300, not a medieval reconstruction. All thirty input class shares are retained per location. Eight small locations without overlap use flagged native fallbacks. Exact-key script compatibility and agricultural balance remain outside this isolated geography test.\n\nReproduce: `uv run ha1300 climate`, then `uv run ha1300 geography-test`.\n'
    write_text(output,'README.md',readme)
    return {'ownable_locations':int(d.is_ownable.sum()),'ownable_missing':0,'types':list(cfg['types']),'counts':manifest['ownable_distribution'],'source_csv_sha256':sha(folder/'locations.csv'),'native_climate_sha256':sha(source),'native_winter_map_source_sha256':winter_map_sha,'icon_manifest_sha256':sha(assets/'generation.json')}
