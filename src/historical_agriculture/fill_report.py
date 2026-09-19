"""Population fill evaluation: informational only, never a formula input.

Population is joined here, after every capacity value has been written. The
report compares starting population with starting capacity globally, by
macro-region and for the configured settled Old-World regions, and counts
rural locations above capacity. Urban locations are listed separately because
food-importing cities are handled later. Nothing here gates the build.
"""
import numpy as np
import pandas as pd
from .rural_pressure import above
from .provenance import write_json

DEFAULT_TARGETS={'settled_median_fill':0.75,'rural_over_capacity_share':0.05,'min_cropland_share':0.02,
    'settled_macro_regions':['western_europe','eastern_europe','east_asia','south_asia','south_east_asia','middle_east','north_africa']}


def settled_mask(d,targets):
    """Population-free membership: configured macro-regions with a cultivated footprint."""
    share=np.divide(pd.to_numeric(d.get('source_starting_crop_ha',pd.Series(np.nan,index=d.index)),errors='coerce').to_numpy(float),
        pd.to_numeric(d.physical_location_ha,errors='coerce').to_numpy(float),out=np.zeros(len(d)),where=pd.to_numeric(d.physical_location_ha,errors='coerce').to_numpy(float)>0)
    return d.macro_region.isin(targets['settled_macro_regions']).to_numpy()&(share>=targets['min_cropland_share'])


def evaluate(d,targets=None):
    """Return the fill evaluation for an ownable location frame with population joined."""
    targets={**DEFAULT_TARGETS,**(targets or {})}
    own=d.loc[d.is_ownable.astype(bool)].copy()
    own['population']=pd.to_numeric(own.eu5_start_population,errors='coerce').fillna(0.)
    cap=own.starting_capacity.to_numpy(float);pop=own.population.to_numpy(float)
    own['fill']=np.divide(pop,cap,out=np.full(len(own),np.nan),where=cap>0)
    own['over_capacity']=above(pop,cap)
    own['context']=own.settlement_context if 'settlement_context' in own else 'unknown'
    rural=own.context.eq('rural_or_unranked').to_numpy();urban=own.context.eq('urban').to_numpy()
    settled=settled_mask(own,targets)
    def block(mask):
        q=own[mask]
        return {'locations':int(mask.sum()),'population':float(q.population.sum()),'starting_capacity':float(q.starting_capacity.sum()),
            'maximum_capacity':float(q.maximum_capacity.sum()),
            'aggregate_fill':float(q.population.sum()/q.starting_capacity.sum()) if q.starting_capacity.sum()>0 else None,
            'median_location_fill':float(q.fill.median()) if len(q) else None,
            'p90_location_fill':float(q.fill.quantile(.9)) if len(q) else None,
            'over_capacity_locations':int(q.over_capacity.sum()),
            'over_capacity_share':float(q.over_capacity.mean()) if len(q) else None}
    summary={'global':block(np.ones(len(own),bool)),'rural':block(rural),'urban':block(urban),
        'settled_old_world':block(settled),'settled_old_world_rural':block(settled&rural)}
    regions={name:block((own.macro_region==name).to_numpy()) for name in sorted(own.macro_region.unique())}
    settled_rural=summary['settled_old_world_rural']
    checks={'settled_median_fill':{'target':targets['settled_median_fill'],'observed':settled_rural['median_location_fill'],
                'passed':settled_rural['median_location_fill'] is not None and abs(settled_rural['median_location_fill']-targets['settled_median_fill'])<=0.1},
            'rural_over_capacity_share':{'target':targets['rural_over_capacity_share'],'observed':summary['rural']['over_capacity_share'],
                'passed':summary['rural']['over_capacity_share'] is not None and summary['rural']['over_capacity_share']<=targets['rural_over_capacity_share']}}
    table=own[['location_tag','province','region','macro_region','context','population','starting_capacity','maximum_capacity','fill','over_capacity']].copy()
    table['settled_old_world']=settled
    return {'targets':targets,'summary':summary,'macro_regions':regions,'checks':checks,'informational':True,
        'population_is_formula_input':False,'note':'Population enters only this evaluation. Checks are informational and never gate the build; urban food-importing cities are handled separately.'},table


def rural_balance_diagnostic(d,settings):
    """What the retired population-based allowance would have added; never applied."""
    own=d.loc[d.is_ownable.astype(bool)].copy()
    limit=float(settings['maximum_starting_fill'])
    pop=pd.to_numeric(own.eu5_start_population,errors='coerce').fillna(0.).to_numpy(float)
    rural=own.settlement_context.eq('rural_or_unranked').to_numpy() if 'settlement_context' in own else np.ones(len(own),bool)
    gain=np.where(rural,np.maximum(pop/limit-own.starting_capacity.to_numpy(float),0),0)
    own['would_add_capacity']=gain
    return own.loc[gain>0,['location_tag','province','region','eu5_start_population','starting_capacity','maximum_capacity','would_add_capacity']]


def report(out,d,cfg,fingerprint):
    evaluation,table=evaluate(d,cfg.get('fill_targets'))
    evaluation['fingerprint']=fingerprint
    write_json(out/'fill_evaluation.json',evaluation)
    table.to_csv(out/'fill_evaluation.csv',index=False,float_format='%.15g')
    diagnostic=cfg.get('rural_balance_diagnostic')
    if diagnostic and diagnostic.get('enabled'):
        rural_balance_diagnostic(d,diagnostic).to_csv(out/'rural_balance_diagnostic.csv',index=False,float_format='%.15g')
    s=evaluation['summary'];c=evaluation['checks']
    lines=['# Starting fill evaluation (informational)','',
        'Population is joined only here, after every capacity value is fixed. No population enters any formula or target. Checks report against the configured fill targets and never gate the build.','',
        '| Scope | Locations | Population | Starting capacity | Aggregate fill | Median location fill | Over capacity |','|---|---:|---:|---:|---:|---:|---:|']
    for key,label in [('global','All ownable'),('rural','Rural / unranked'),('urban','Urban (handled later)'),('settled_old_world','Settled Old World'),('settled_old_world_rural','Settled Old World, rural')]:
        b=s[key]
        lines.append(f"| {label} | {b['locations']:,} | {b['population']/1e6:,.1f}M | {b['starting_capacity']/1e6:,.1f}M | {b['aggregate_fill']:.2f} | {(b['median_location_fill'] or 0):.2f} | {b['over_capacity_locations']:,} ({100*(b['over_capacity_share'] or 0):.1f}%) |" if b['aggregate_fill'] is not None else f"| {label} | 0 | | | | | |")
    lines+=['',f"Settled rural median fill {c['settled_median_fill']['observed']:.2f} against target {c['settled_median_fill']['target']:.2f}: {'within 0.10' if c['settled_median_fill']['passed'] else 'outside 0.10'}." if c['settled_median_fill']['observed'] is not None else 'Settled rural median fill unavailable.',
        f"Rural over-capacity share {100*(c['rural_over_capacity_share']['observed'] or 0):.1f}% against target {100*c['rural_over_capacity_share']['target']:.0f}%: {'met' if c['rural_over_capacity_share']['passed'] else 'not met'}.",'',
        'Tune with `scripts/calibrate_fill.py` (global scale and exponent of the shared support conversion). Per location: `fill_evaluation.csv`.','',f'Fingerprint: `{fingerprint}`']
    (out/'FILL.md').write_text('\n'.join(lines)+'\n')
    return evaluation
