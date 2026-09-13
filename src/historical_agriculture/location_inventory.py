"""Read simple game mapping syntax and audit every named map zone."""
import re,math
import pandas as pd
from .provenance import write_json

def strip_comments(text):return re.sub(r'#[^\n]*','',text)

def read_zone_inventory(raw):
    # These three game source files use scalar names/hex values and flat zone lists.
    # Fail on unknown exclusions rather than interpreting every omitted row as sea.
    text=strip_comments((raw/'game_default.map').read_text(encoding='utf-8-sig'))
    classes={}
    for kind in ['sea_zones','lakes','impassable_mountains','non_ownable']:
        matches=re.findall(r'\b'+kind+r'\s*=\s*\{([^{}]*)\}',text,re.S)
        if not matches:raise ValueError('Unsupported zone-list syntax: '+kind)
        for body in matches:
            for name in body.split():
                if kind not in classes.setdefault(name,[]):classes[name].append(kind)
    templates=strip_comments((raw/'game_templates.txt').read_text(encoding='utf-8-sig'))
    names=set(re.findall(r'(?m)^([\w.-]+)\s*=\s*\{',templates))
    named=strip_comments((raw/'game_named_locations.txt').read_text(encoding='utf-8-sig'))
    colors={m.group(1):format(int(m.group(2),16),'06x') for m in re.finditer(r'(?m)^([\w.-]+)\s*=\s*([0-9a-fA-F]+)\s*$',named)}
    if names-set(colors):raise ValueError('Template without named colour')
    return pd.DataFrame([{'location_tag':name,'map_color_rgb':colors[name],'game_zone_class':'+'.join(classes.get(name,[])) or 'settlement_land','is_ownable':not bool(classes.get(name))} for name in sorted(names)])

def complete_zones(d,raw,out):
    all_zones=read_zone_inventory(raw)
    unknown=set(d.location_tag)-set(all_zones.location_tag)
    if unknown:raise ValueError('Model locations absent from game inventory')
    classes=all_zones.set_index('location_tag').game_zone_class
    d=d.copy();d['game_zone_class']=d.location_tag.map(classes);d['modelled_land']=True;d['is_ownable']=d.location_tag.map(all_zones.set_index('location_tag').is_ownable)
    extras=all_zones[~all_zones.location_tag.isin(d.location_tag)].copy()
    if (extras.game_zone_class=='settlement_land').any():raise ValueError('Unmodeled settlement locations')
    records=[]
    for item in extras.itertuples():
        # These game zones cannot own settlement capacity. Zero is a domain rule,
        # not an assertion that their physical landscapes have no food resources.
        row={k:None for k in d.columns}
        for k in d.select_dtypes(include='number').columns:
            if 'capacity' in k or 'effective_cropland' in k:row[k]=0.
        row.update(location_tag=item.location_tag,map_color_rgb=item.map_color_rgb,game_zone_class=item.game_zone_class,is_ownable=item.is_ownable,modelled_land=False,capacity_multiplier=1.,province='nonsettlement_zone',region='nonsettlement_zone',super_region='nonsettlement_zone',macro_region='nonsettlement_zone',inferred_area_share=0.,coastline_transfer_share=0.,evidence_status='Game-defined nonsettlement zone; zero settlement capacity by domain',source_rule='game_default.map:nonsettlement',zero_support_reason='Nonsettlement game zone; physical food potential not evaluated',remaining_improvement_effective_cropland=0.)
        records.append(row)
    numeric_columns=list(d.select_dtypes(include='number').columns)
    d=pd.concat([d,pd.DataFrame(records)],ignore_index=True).sort_values('location_tag').reset_index(drop=True)
    for column in numeric_columns:d[column]=pd.to_numeric(d[column],errors='coerce')
    audit={'game_map_zones':len(all_zones),'modelled_land_locations':int(d.modelled_land.sum()),'explicit_nonsettlement_zero_rows':len(extras),'unclassified_exclusions':0,'modelled_rows_also_in_special_game_zone_lists':int((d.modelled_land&(d.game_zone_class!='settlement_land')).sum()),'ownable_locations':int(all_zones.is_ownable.sum()),'special_list_note':'Physical estimates may exist for non-ownable corridors. is_ownable is derived independently from game default.map exclusions; these estimates do not imply settlement eligibility.'}
    write_json(out/'inventory_audit.json',audit)
    return d,all_zones,audit

def audit_settlement_values(d, inventory):
    """Independent game eligibility gate; finite zero placeholders are not usable support."""
    required=["base_effective_cropland","capacity_multiplier",
        "starting_improvement_effective_cropland","maximum_improvement_effective_cropland"]
    if d.location_tag.duplicated().any():raise ValueError("Duplicate delivered location")
    lookup=d.set_index("location_tag")
    issues=[]
    ownable=inventory[inventory.is_ownable]
    for game in ownable.itertuples():
        tag=game.location_tag
        if tag not in lookup.index:
            issues.append({"location_tag":tag,"issues":["missing_row"]});continue
        row=lookup.loc[tag];errors=[]
        if not row.get("modelled_land",False):errors.append("not_modelled_as_land")
        if not row.get("is_ownable",False):errors.append("incorrect_ownability")
        if row.get("map_color_rgb")!=game.map_color_rgb:errors.append("wrong_map_colour")
        for key in required:
            value=pd.to_numeric(row.get(key),errors="coerce")
            if not pd.notna(value) or not math.isfinite(value):
                errors.append("invalid_"+key)
            elif value<0 or (key=="capacity_multiplier" and value<=0):
                errors.append("invalid_"+key)
        for key in ["starting_capacity","maximum_capacity"]:
            value=pd.to_numeric(row.get(key),errors="coerce")
            if not pd.notna(value) or value<=0:errors.append("no_positive_"+key)
        area=pd.to_numeric(row.get("physical_location_ha"),errors="coerce")
        if not pd.notna(area) or area<=0:errors.append("missing_physical_area")
        if errors:
            pop=pd.to_numeric(row.get("eu5_start_population"),errors="coerce")
            issues.append({"location_tag":tag,"issues":errors,
                "starting_population":float(pop) if pd.notna(pop) else None,
                "starting_capacity":float(row.starting_capacity) if pd.notna(row.starting_capacity) else None,
                "maximum_capacity":float(row.maximum_capacity) if pd.notna(row.maximum_capacity) else None,
                "reason":row.get("zero_support_reason","Unresolved")})
    extra_flags=[]
    for game in inventory[~inventory.is_ownable].itertuples():
        if game.location_tag in lookup.index and lookup.loc[game.location_tag].get("is_ownable",False):
            extra_flags.append(game.location_tag)
    structural=[x for x in issues if any(not e.startswith("no_positive_") for e in x["issues"])]
    return {"passed":not issues and not extra_flags,
        "coverage_and_classification_pass":not structural and not extra_flags,
        "ownable_locations":len(ownable),"unresolved_ownable_locations":len(issues),
        "populated_unresolved_locations":sum((x.get("starting_population") or 0)>0 for x in issues),
        "incorrectly_ownable_exclusions":extra_flags,"issues":issues,
        "definition":"Template locations excluding sea_zones, lakes, impassable_mountains and non_ownable in game default.map. Independent of starting ownership or population.",
        "zero_policy":"Ownable zero-support rows fail readiness. No population floors; terrestrial analogue estimates must have explicit donor provenance."}
