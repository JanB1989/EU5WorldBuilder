"""Publish audited navigation geography and its Constructor contract."""
from pathlib import Path
import json
import shutil
import re

from .river_network import digest

ROOT=Path(__file__).resolve().parents[2]


def validated():
    config_path=ROOT/'configs/river_navigation.json'
    config=json.loads(config_path.read_text());out=ROOT/config['output']
    manifest=json.loads((out/'manifest.json').read_text())
    if manifest['config_sha256']!=digest(config_path):
        raise ValueError('Navigation config changed: run worldbuilder navigation first')
    if manifest.get('map_code_sha256')!=digest(Path(__file__).with_name('navigation_map.py')):
        raise ValueError('Navigation exporter changed: run worldbuilder navigation first')
    if manifest.get('cleanup_code_sha256')!=digest(Path(__file__).with_name('navigation_cleanup.py')):
        raise ValueError('Navigation cleanup changed: run worldbuilder navigation first')
    if not all(manifest['checks'].values()):raise ValueError('Navigation map checks did not pass')
    for rel,expected in manifest['files'].items():
        if digest(out/'mod'/rel)!=expected:raise ValueError('Navigation export changed: '+rel)
    return out,manifest


def emit(output):
    out,manifest=validated()
    for rel in manifest['files']:
        target=Path(output)/rel;target.parent.mkdir(parents=True,exist_ok=True)
        if rel=='in_game/map_data/location_templates.txt':
            # Geography has already written the complete climate/terrain model.
            base=target.read_text(encoding='utf-8-sig')
            ports=set(manifest.get('river_port_locations',[]));floor=manifest.get('port_harbor_floor',.25)
            def harbor(m):
                if m[1] not in ports:return m[0]
                body=m[2];hit=re.search(r'natural_harbor_suitability\s*=\s*([.\d]+)',body)
                if hit:
                    value=max(floor,float(hit[1]));body=body[:hit.start()]+f'natural_harbor_suitability = {value:g}'+body[hit.end():]
                else:body+=f' natural_harbor_suitability = {floor:g} '
                return m[1]+' = {'+body+'}'
            base=re.sub(r'(\w+)\s*=\s*\{([^{}]*)\}',harbor,base)
            target.write_text(base+'\n'+(out/'sea_templates.txt').read_text(),encoding='utf-8-sig')
        else:shutil.copy2(out/'mod'/rel,target)
    # Names belong to the geography layer even in the standalone World Builder.
    import pandas as pd
    rows=pd.read_csv(out/'tiles.csv')
    loc=['l_english:', ' pp_navigation_waterways: "River Waterways"', ' pp_navigation_subcontinent: "River Waterways"', ' pp_navigation_region: "River Waterways"']
    for r in rows.itertuples():loc.append(f' {r.location}: "{r.near_location.replace("_"," ").title()} Waterway"')
    for region,g in rows.groupby('region'):
        label=region.replace('_',' ').title()
        loc.append(f' pp_nav_{region}_area: "{label} Waterways"')
        for i in range((len(g)+11)//12):loc.append(f' pp_nav_{region}_{i}_province: "{label} Waterways"')
    p=Path(output)/'main_menu/localization/english/pp_navigation_geography_l_english.yml';p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text('\n'.join(loc)+'\n',encoding='utf-8-sig')
    return {'tiles':manifest['tiles'],'edges':manifest['edges']}


def handover(output):
    cfg=json.loads((ROOT/'configs/geography_test.json').read_text())
    if not cfg.get('global_navigation'):return {}
    out,manifest=validated();target=Path(output)/'navigation';target.mkdir(parents=True,exist_ok=True)
    files={}
    for name in ['manifest.json','tiles.csv','edges.csv','shores.csv','lost_river_effects.csv','river_effect_changes.csv','preserved_river_pixels.csv']:
        shutil.copy2(out/name,target/name);files['navigation/'+name]=digest(target/name)
    return files
