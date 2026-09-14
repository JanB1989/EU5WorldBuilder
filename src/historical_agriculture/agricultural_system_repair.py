"""Historical crop eligibility for location support, independent of population.

The original food-system raster describes the representative livelihood. It is
not a prohibition on subsidiary agriculture in an oasis or cultivated dryland.
"""
import copy
import json
import numpy as np


def rules(root, cfg):
    result=copy.deepcopy(json.loads((root/'configs/regions.json').read_text())['regions'])
    path=cfg.get('agricultural_system_repair')
    if not path:return result
    changes=json.loads((root/path).read_text())['crop_systems']
    for change in changes:
        ids=set(change['ecoregion_ids'])
        for rule in list(result):
            overlap=ids.intersection(rule['ecoregion_ids'])
            if not overlap:continue
            replacement=copy.deepcopy(rule)
            rule['ecoregion_ids']=[i for i in rule['ecoregion_ids'] if i not in overlap]
            replacement.update(name=change['name'],crops=change['crops'],
                               ecoregion_ids=sorted(overlap),source=change['source'])
            result.append(replacement)
    return [r for r in result if r['ecoregion_ids']]


def select_candidate(candidate_dry, candidate_upper,
                     candidate_rank, best_rank, domain):
    """Preserve viable original dry crops; replace dry failures in historical order.

    Irrigated-only systems remain candidates when no dry crop is viable. This
    avoids wheat's irrigated suitability excluding viable dry millet on the same
    cell. Neither yields nor calories are maximized across crops.
    """
    valid=domain & np.isfinite(candidate_dry) & np.isfinite(candidate_upper)
    valid &= (candidate_upper>0)&(candidate_rank<100)
    dry=valid&(candidate_dry>0)
    priority=candidate_rank+np.where(dry,0,100)
    # Existing viable representative crops have priority -1.
    take=valid&(priority<best_rank)
    return take, np.where(take,priority,best_rank)


def report(root,out,d,fingerprint):
    import pandas as pd
    from .provenance import digest,write_json
    before=root/'data/processed/rural_system_before.csv'
    old=pd.read_csv(before,keep_default_na=False).set_index('location_tag')
    new=d.set_index('location_tag').loc[old.index]
    for frame in (old,new):
        population=pd.to_numeric(frame.eu5_start_population,errors='coerce')
        if population[frame.is_ownable].isna().any():raise ValueError('Missing ownable starting population in repair comparison')
        frame['eu5_start_population']=population.fillna(0)
    own=new.is_ownable
    rural=own&new.settlement_context.ne('urban')
    counts={}
    for name,mask in [('world_rural',rural),('africa_rural',rural&new.macro_region.str.contains('africa')),
                      ('western_india_rural',rural&new.region.eq('western_india_region'))]:
        counts[name]={}
        for stage,frame in [('before',old),('after',new)]:
            q=frame.loc[mask];p=q.eu5_start_population
            counts[name][stage]={
                'above_start':int((p>q.starting_capacity).sum()),
                'above_twice_start':int((p>2*q.starting_capacity).sum()),
                'above_five_times_start':int((p>5*q.starting_capacity).sum()),
                'above_maximum':int((p>q.maximum_capacity).sum()),
                'starting_capacity':float(q.starting_capacity.sum()),
                'maximum_capacity':float(q.maximum_capacity.sum())}
    rows=new[['province','region','macro_region','is_ownable','settlement_context','eu5_start_population','starting_capacity','maximum_capacity','capacity_multiplier']].copy()
    for col in ['starting_capacity','maximum_capacity','capacity_multiplier']:rows['before_'+col]=old[col]
    rows['starting_fill']=rows.eu5_start_population/rows.starting_capacity.replace(0,np.nan)
    rows['resolved']=rural&(old.eu5_start_population>old.starting_capacity)&(new.eu5_start_population<=new.starting_capacity)
    rows['new_shortfall']=rural&(old.eu5_start_population<=old.starting_capacity)&(new.eu5_start_population>new.starting_capacity)
    rows.to_csv(out/'rural_system_comparison.csv',float_format='%.15g')
    rows.loc[rural&(rows.starting_fill>2)].sort_values('starting_fill',ascending=False).to_csv(out/'rural_extreme_residuals.csv',float_format='%.15g')
    write_json(out/'rural_system_validation.json',{'fingerprint':fingerprint,'baseline_sha256':digest(before),
        'counts':counts,'new_rural_shortfalls':int(rows.new_shortfall.sum()),
        'extreme_rural_gate_pass':counts['world_rural']['after']['above_twice_start']==0,
        'population_used_in_model':'rural_balance_added_capacity' in new,'urban_exceptions_auto_accepted':False})

    summary=['# Rural agricultural-system repair','',
        ('Explicit population-informed rural game allowance applied; source estimates remain separately visible.' if 'rural_balance_added_capacity' in new else 'Population remains an evaluation input only. No-extreme-rural-shortfall acceptance is evaluated in the linked validation.'),'',
        '| Group | Above start, before / now | Above 2x, before / now | Above 5x, before / now |',
        '|---|---:|---:|---:|']
    for name,values in counts.items():
        a,b=values['before'],values['after']
        summary.append(f"| {name} | {a['above_start']} / {b['above_start']} | {a['above_twice_start']} / {b['above_twice_start']} | {a['above_five_times_start']} / {b['above_five_times_start']} |")
    summary += ['', '[Every location](rural_system_comparison.csv) · [Extreme rural residuals](rural_extreme_residuals.csv) · [Validation](rural_system_validation.json)', '', f'Fingerprint: `{fingerprint}`']
    (out/'RURAL_SYSTEM_REPAIR.md').write_text('\n'.join(summary)+'\n')
    from html import escape
    table=pd.DataFrame({name:{key:f"{value['before'][key]} → {value['after'][key]}" for key in ['above_start','above_twice_start','above_five_times_start','above_maximum']} for name,value in counts.items()}).T
    (out/'regional_comparison.html').write_text('<!doctype html><meta charset="utf-8"><title>Rural repair comparison</title><style>body{background:#101a27;color:#def;font:16px system-ui;margin:3rem}td,th{padding:12px;border:1px solid #567}a{color:#8cf}</style><h1>Rural repair comparison</h1><p>Before → current. Residual failures are retained; urban rank is not proof of import dependence.</p>'+table.to_html()+'<p><a href="rural_system_comparison.csv">Every location</a> · <a href="rural_extreme_residuals.csv">Extreme residuals</a> · <a href="index.html#pressure">Map</a></p><p>'+escape(fingerprint)+'</p>')
