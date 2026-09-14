"""Evaluate the shared game mapping after calculation; never select local values."""
import json
import numpy as np
import pandas as pd
from .rural_pressure import summaries,above
from .provenance import write_json,digest


def report(root,out,current,cfg,fingerprint):
    if not cfg.get('agricultural_game_calibration'):return
    c=json.loads((root/cfg['agricultural_game_calibration']).read_text())
    baseline=root/cfg['pressure_comparison_baseline']
    before=pd.read_csv(baseline,keep_default_na=False)
    a,ap,ar,sa=summaries(before);b,bp,br,sb=summaries(current)
    a=a.set_index('location_tag');b=b.set_index('location_tag').loc[a.index]
    rural=b.context.eq('rural_or_unranked')
    resolved=rural&a.over_start&~b.over_start
    new=rural&~a.over_start&b.over_start
    lower=(b.starting_capacity<a.starting_capacity-1e-6)|(b.maximum_capacity<a.maximum_capacity-1e-6)
    checks={'rural_shortfall_target':sb['rural_over_start']<=c['evaluation']['maximum_rural_starting_shortfalls'],
            'no_new_rural_shortfalls':int(new.sum())<=c['evaluation']['maximum_new_rural_shortfalls'],
            'no_capacity_reductions':not bool(lower.any()),
            'same_productivity_multipliers':bool(np.allclose(a.capacity_multiplier,b.capacity_multiplier,rtol=1e-12,atol=1e-9))}
    details=b[['province','region','context','eu5_start_population','capacity_multiplier','starting_capacity','maximum_capacity','game_conversion_added_capacity','game_inheritance_capacity','game_base_added_capacity','game_inheritance_activation_share']].copy()
    details['before_starting_capacity']=a.starting_capacity
    details['before_maximum_capacity']=a.maximum_capacity
    details['resolved_starting_shortfall']=resolved
    details.to_csv(out/'game_calibration_locations.csv',float_format='%.15g')
    residual=b.loc[rural&b.over_start,['province','region','eu5_start_population','starting_capacity','maximum_capacity','shortfall','over_max']].sort_values('shortfall',ascending=False)
    residual['exception_status']='Unresolved; not automatically an accepted historical exception'
    residual.to_csv(out/'remaining_rural_shortfalls.csv',float_format='%.15g')
    regions=ar.add_prefix('before_').join(br.add_prefix('after_'))
    regions.to_csv(out/'game_calibration_regions.csv',float_format='%.15g')
    subsets={}
    for name,mask in [('rural',rural),('urban',b.context.eq('urban')),('population_under_5000',rural&(b.eu5_start_population>0)&(b.eu5_start_population<5000))]:
        subsets[name]={}
        for label,d in [('before',a),('after',b)]:
            q=d[mask]
            subsets[name][label]={'count':len(q),'capacity_sum':float(q.starting_capacity.sum()),'maximum_sum':float(q.maximum_capacity.sum()),
                'starting_capacity_quantiles':q.starting_capacity.quantile([0,.1,.5,.9,.99,1]).to_dict(),
                'maximum_capacity_quantiles':q.maximum_capacity.quantile([0,.1,.5,.9,.99,1]).to_dict()}
    write_json(out/'game_calibration_evaluation.json',{'fingerprint':fingerprint,'baseline_sha256':digest(baseline),
        'before':sa,'after':sb,'checks':checks,'game_coverage_target_passed':all(checks.values()),
        'scientific_acceptance':False,'population_simulation_validated':False,
        'comparison_scope':'Historical game conversion experiment; new physical crop inputs also change multipliers' if cfg.get('agricultural_system_repair') else 'Same-physical-input game conversion',
        'resolved_rural_shortfalls':int(resolved.sum()),'new_rural_shortfalls':int(new.sum()),
        'subsets':subsets,'limitations':c['limitations'],
        'remaining_cases':'All remaining rural shortages retained in remaining_rural_shortfalls.csv; no automatic exclusions.'})
    lines=['# Shared agricultural-system game calibration','',
        'These are game capacities. Physical food-support estimates remain in the uncalibrated native-grid rasters and ledger. No population value enters the formula.','',
        '| Rural diagnostic | Before | Now |','|---|---:|---:|',
        f"| Above starting capacity | {sa['rural_over_start']:,} | {sb['rural_over_start']:,} |",
        f"| Above maximum capacity | {sa['rural_over_max']:,} | {sb['rural_over_max']:,} |",'',
        f'Resolved {int(resolved.sum()):,}; new rural shortfalls {int(new.sum()):,}.', '',
        'Starting inheritance uses historical crop-system classes and reconstructed cultivated extent to activate a bounded share of existing physical opportunity. A shared concave conversion compresses very low support values in game units. It can raise base support; the game conversion itself does not change productivity multipliers. Separate crop-input repairs can change their physical reference.', '',
        'This is an explicit game calibration, not evidence for previously unmeasured hectares, yields or river water. Growing populations, employment and food consumption still require integration testing in the downstream game.', '',
        '[Every location](game_calibration_locations.csv) · [Regions](game_calibration_regions.csv) · [Remaining cases](remaining_rural_shortfalls.csv) · [Checks and frontier distributions](game_calibration_evaluation.json)', '',
        f'Fingerprint: `{fingerprint}`']
    (out/'GAME_CALIBRATION.md').write_text('\n'.join(lines)+'\n')
