"""Read simple game mapping syntax and audit every named map zone."""
import re
import pandas as pd
from .provenance import write_json

def strip_comments(text):return re.sub(r'#[^\n]*','',text)

def read_zone_inventory(raw):
    # These three game source files use scalar names/hex values and flat zone lists.
    # Fail on unknown exclusions rather than interpreting every omitted row as sea.
    text=strip_comments((raw/'game_default.map').read_text(encoding='utf-8-sig'))
    classes={}
    for kind in ['sea_zones','lakes','impassable_mountains','non_ownable']:
        m=re.search(r'\b'+kind+r'\s*=\s*\{([^{}]*)\}',text,re.S)
        if not m:raise ValueError('Unsupported zone-list syntax: '+kind)
        for name in m.group(1).split():classes.setdefault(name,[]).append(kind)
    templates=strip_comments((raw/'game_templates.txt').read_text(encoding='utf-8-sig'))
    names=set(re.findall(r'(?m)^([\w.-]+)\s*=\s*\{',templates))
    named=strip_comments((raw/'game_named_locations.txt').read_text(encoding='utf-8-sig'))
    colors={m.group(1):format(int(m.group(2),16),'06x') for m in re.finditer(r'(?m)^([\w.-]+)\s*=\s*([0-9a-fA-F]+)\s*$',named)}
    if names-set(colors):raise ValueError('Template without named colour')
    return pd.DataFrame([{'location_tag':name,'map_color_rgb':colors[name],'game_zone_class':'+'.join(classes.get(name,[])) or 'settlement_land'} for name in sorted(names)])

def complete_zones(d,raw,out):
    all_zones=read_zone_inventory(raw)
    unknown=set(d.location_tag)-set(all_zones.location_tag)
    if unknown:raise ValueError('Model locations absent from game inventory')
    classes=all_zones.set_index('location_tag').game_zone_class
    d=d.copy();d['game_zone_class']=d.location_tag.map(classes);d['modelled_land']=True
    extras=all_zones[~all_zones.location_tag.isin(d.location_tag)].copy()
    if (extras.game_zone_class=='settlement_land').any():raise ValueError('Unmodeled settlement locations')
    records=[]
    for item in extras.itertuples():
        # These game zones cannot own settlement capacity. Zero is a domain rule,
        # not an assertion that their physical landscapes have no food resources.
        row={k:None for k in d.columns}
        for k in d.select_dtypes(include='number').columns:
            if 'capacity' in k or 'effective_cropland' in k:row[k]=0.
        row.update(location_tag=item.location_tag,map_color_rgb=item.map_color_rgb,game_zone_class=item.game_zone_class,modelled_land=False,capacity_multiplier=1.,province='nonsettlement_zone',region='nonsettlement_zone',super_region='nonsettlement_zone',macro_region='nonsettlement_zone',inferred_area_share=0.,coastline_transfer_share=0.,evidence_status='Game-defined nonsettlement zone; zero settlement capacity by domain',source_rule='game_default.map:nonsettlement',zero_support_reason='Nonsettlement game zone; physical food potential not evaluated',remaining_improvement_effective_cropland=0.)
        records.append(row)
    numeric_columns=list(d.select_dtypes(include='number').columns)
    d=pd.concat([d,pd.DataFrame(records)],ignore_index=True).sort_values('location_tag').reset_index(drop=True)
    for column in numeric_columns:d[column]=pd.to_numeric(d[column],errors='coerce')
    audit={'game_map_zones':len(all_zones),'modelled_land_locations':int(d.modelled_land.sum()),'explicit_nonsettlement_zero_rows':len(extras),'unclassified_exclusions':0,'modelled_rows_also_in_special_game_zone_lists':int((d.modelled_land&(d.game_zone_class!='settlement_land')).sum()),'special_list_note':'36 imported land-model locations also occur in non-ownable/wasteland lists; keep their physical estimates and expose game eligibility for later integration.'}
    write_json(out/'inventory_audit.json',audit)
    return d,all_zones,audit
