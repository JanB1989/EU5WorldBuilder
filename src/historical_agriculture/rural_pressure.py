"""Contextual rural/urban pressure diagnostics, never capacity predictors."""
import json,html
import numpy as np
import pandas as pd
from .provenance import write_json,digest

URBAN={'town','city','megalopolis'}
RURAL={'rural_or_unranked','rural_settlement'}

def above(pop,cap):
    return pop>cap+np.maximum(1e-7,np.abs(cap)*1e-12)

def classify(d):
    d=d.loc[d.is_ownable].copy()
    for col in ['eu5_start_population','starting_capacity','maximum_capacity']:d[col]=pd.to_numeric(d[col],errors='raise')
    d['context']=np.where(d.starting_location_rank.isin(URBAN),'urban',np.where(d.starting_location_rank.isin(RURAL),'rural_or_unranked','unknown'))
    d['over_start']=above(d.eu5_start_population,d.starting_capacity)
    d['over_max']=above(d.eu5_start_population,d.maximum_capacity)
    d['shortfall']=np.maximum(d.eu5_start_population-d.starting_capacity,0)
    return d

def summaries(d):
    d=classify(d);r=d[d.context=='rural_or_unranked']
    p=r.groupby(['province','region'],dropna=False).agg(population=('eu5_start_population','sum'),capacity=('starting_capacity','sum'),maximum_capacity=('maximum_capacity','sum'),locations=('location_tag','size'))
    p['category']=np.where(~above(p.population,p.capacity),'within_start',np.where(~above(p.population,p.maximum_capacity),'within_maximum_only','above_maximum'))
    reg=r.groupby('region').agg(population=('eu5_start_population','sum'),capacity=('starting_capacity','sum'),maximum_capacity=('maximum_capacity','sum'),rural_locations=('location_tag','size'),over_start=('over_start','sum'),over_max=('over_max','sum'),summed_local_shortfall=('shortfall','sum'))
    summary={'ownable':len(d),'urban':int((d.context=='urban').sum()),'urban_over_start':int(d.loc[d.context=='urban','over_start'].sum()),'unknown':int((d.context=='unknown').sum()),'rural_or_unranked':len(r),'rural_over_start':int(r.over_start.sum()),'rural_over_max':int(r.over_max.sum()),'rural_provinces':len(p),'rural_province_categories':{str(k):int(v) for k,v in p.category.value_counts().items()},'rural_starting_capacity':float(r.starting_capacity.sum()),'rural_population':float(r.eu5_start_population.sum())}
    return d,p,reg,summary

def report(root,out,current,fingerprint,cfg=None):
    cfg=cfg or {}
    d,p,reg,s=summaries(current)
    source=root/'data/raw/location_inputs/starting_population_source.csv'
    baseline=root/'data/processed/rural_round_before/locations_equal_area.csv'
    system_baseline=root/'data/processed/system_round_before/locations_equal_area.csv'
    if (root/'configs/locations.json').exists() and json.loads((root/'configs/locations.json').read_text()).get('system_round_config') and system_baseline.exists():baseline=system_baseline
    if cfg.get('pressure_comparison_baseline'):baseline=root/cfg['pressure_comparison_baseline']
    before=None
    if baseline.exists():
        a=pd.read_csv(baseline,keep_default_na=False)
        if 'starting_location_rank' not in a:
            ranks=pd.read_csv(source,usecols=['location_tag','starting_location_rank'],keep_default_na=False)
            a=a.merge(ranks,on='location_tag',validate='one_to_one',how='left')
        _,_,oldreg,before=summaries(a)
        comp=reg.join(oldreg.add_prefix('before_'))
        comp['rural_capacity_change']=comp.capacity-comp.before_capacity
        comp['over_start_change']=comp.over_start-comp.before_over_start
        comp.to_csv(out/'rural_region_comparison.csv',float_format='%.15g')
        aa=a.set_index('location_tag');bb=d.set_index('location_tag')
        for col in ['starting_capacity','maximum_capacity']:
            tolerance=np.maximum(1e-6,aa.loc[bb.index,col].abs()*1e-6)
            physical_delta=(bb[col]-bb.get('base_land_floor_added_capacity',0))-(aa.loc[bb.index,col]-aa.loc[bb.index].get('base_land_floor_added_capacity',0))
            if not cfg.get('terrain_access') and (physical_delta < -tolerance).any():raise ValueError('Voluntary-management envelope decreased pre-floor support: '+col)
    d[['location_tag','province','region','starting_location_rank','context','eu5_start_population','starting_capacity','maximum_capacity','over_start','over_max','shortfall','management_envelope_refinement_share']+[x for x in ['cultivated_system_refinement_share'] if x in d]].to_csv(out/'rural_location_pressure.csv',index=False,float_format='%.15g')
    p.to_csv(out/'rural_province_pressure.csv',float_format='%.15g');reg.to_csv(out/'rural_region_pressure.csv',float_format='%.15g')
    audit={'fingerprint':fingerprint,'rank_source_sha256':digest(source),'baseline_sha256':digest(baseline) if baseline.exists() else None,'before':before,'after':s,'urban_policy':'Towns, cities and megalopolises are excluded from rural acceptance counts. Rank is contextual, never a productivity predictor.','limitations':['Rural_or_unranked is the cached source classification, not independent proof every location is rural.','Province totals pool rural locations only; urban capacity is not treated as free surplus.','Static support comparisons do not establish actual employment, food output, trade or demographic equilibrium.','Unresolved rural shortfalls remain visible; no population-fit floor.','The base-land floor can offset additional natural support while the incremental irrigation contribution shrinks. Small post-floor decreases can therefore occur even when physical support rises.']}
    write_json(out/'rural_pressure.json',audit)
    rows=[]
    for key,label in [('rural_or_unranked','Rural or unranked locations'),('rural_over_start','Above starting capacity'),('rural_over_max','Above modeled maximum'),('urban_over_start','Urban over capacity (separate)')]:
        rows.append(f'<tr><td>{label}</td><td>{before[key]:,}</td><td>{s[key]:,}</td></tr>' if before else f'<tr><td>{label}</td><td>Unavailable</td><td>{s[key]:,}</td></tr>')
    page="""<!doctype html><meta charset="utf-8"><title>Rural capacity review</title><style>body{background:#0c1420;color:#dce8ef;font:16px system-ui;max-width:960px;margin:40px auto;padding:20px}a{color:#80c4f5}p{line-height:1.6}td,th{padding:12px;border-bottom:1px solid #405269;text-align:right}td:first-child,th:first-child{text-align:left}</style><a href="index.html">← Map</a><h1>Rural capacity review</h1><p>Urban locations are reported separately. Their deficits do not trigger rural capacity adjustments. Rural/unranked status comes from the cached game snapshot, not a population-size threshold.</p><table><tr><th>Case</th><th>Before</th><th>Now</th></tr>"""+''.join(rows)+"""</table><p>This comparison uses the latest archived before-state. The global land correction evaluates fine-pixel slopes before aggregation. It can increase or decrease land access and improvement opportunity; yield coefficients remain unchanged.</p><p>Remaining shortfalls are unresolved evidence/model questions, not automatically a reason to inflate capacity. Province summaries pool rural locations only.</p><p><a href="rural_location_pressure.csv">Locations</a> · <a href="rural_province_pressure.csv">Provinces</a> · <a href="rural_region_comparison.csv">Regional before/after</a> · <a href="rural_pressure.json">Method and counts</a></p><small>"""+html.escape(fingerprint)+"</small>"
    if cfg.get('agricultural_game_calibration'):
        page=page.replace('The global land correction evaluates fine-pixel slopes before aggregation. It can increase or decrease land access and improvement opportunity; yield coefficients remain unchanged.','The shared agricultural-system game calibration is applied on the native grid before location aggregation. Historical-system inheritance and game-unit conversion are distinct from measured yields and physical land. <a href="GAME_CALIBRATION.md">Calibration details</a>.')
    (out/'rural_pressure.html').write_text(page)
