import itertools
import numpy as np
import pandas as pd

from .provenance import write_json
from .transformations import benchmark_bounds, factor

def evaluate(frame,config,low,high):
    result=[]
    for _,r in frame.iterrows():
        obs=r.harvest_t_ha_inferred*1000*config['crops'][r.crop]['dry_fraction']
        obs_low=r.get('harvest_t_ha_lower_inferred',r.harvest_t_ha_inferred)*1000*config['crops'][r.crop]['dry_fraction']
        obs_high=r.get('harvest_t_ha_upper_inferred',r.harvest_t_ha_inferred)*1000*config['crops'][r.crop]['dry_fraction']
        lower,upper=benchmark_bounds(r,config['crops'][r.crop],low,high)
        if not np.isfinite([obs,lower,upper]).all() or obs<=0 or upper<=lower:
            result.append({'region':r.region,'valid':False,'loss':None,'observed':obs,'observed_low':obs_low,'observed_high':obs_high,'lower':lower,'upper':upper})
            continue
        distance=max(np.log(max(lower,1)/obs_low),np.log(obs_high/max(upper,1)),0)
        width=np.log1p((upper-lower)/max(obs,1))
        result.append({'region':r.region,'valid':True,'loss':float(distance+config['calibration']['width_penalty']*width),'inside':bool(lower<=obs_low and obs_high<=upper),'point_inside':bool(lower<=obs<=upper),'lower':lower,'upper':upper,'observed':obs,'observed_low':obs_low,'observed_high':obs_high})
    return result

def enclosure_constraints(frame,config):
    """Exact constraints for shared positive multiplicative factors.

    No positive factor can repair zero/missing modern support. Those cases stay
    unresolved, with their historical evidence retained in the comparison.
    """
    lower_ceiling=np.inf;upper_floor=0.;constraints=[];unresolved=[]
    for _,r in frame.iterrows():
        c=config['crops'][r.crop]
        lo,hi=benchmark_bounds(r,c,1.,1.)
        obslo=r.get('harvest_t_ha_lower_inferred',r.harvest_t_ha_inferred)*1000*c['dry_fraction']
        obshi=r.get('harvest_t_ha_upper_inferred',r.harvest_t_ha_inferred)*1000*c['dry_fraction']
        if not np.isfinite([lo,hi,obslo,obshi]).all() or hi<=0:
            unresolved.append(r.region);continue
        if lo<0 or obslo<=0 or obshi<obslo:raise ValueError(f'Invalid anchor units/range: {r.region}')
        low_limit=obslo/lo if lo>0 else np.inf
        high_limit=obshi/hi
        lower_ceiling=min(lower_ceiling,low_limit);upper_floor=max(upper_floor,high_limit)
        constraints.append({'region':r.region,'lower_factor_ceiling':low_limit,'upper_factor_floor':high_limit})
    return lower_ceiling,upper_floor,constraints,unresolved

def calibrate(root,config,out):
    frame=pd.read_csv(root/'evidence/benchmarks_1300.csv')
    cal=config['calibration'];selected={};comparisons=[]
    for group in sorted({c['group'] for c in config['crops'].values()}):
        codes=[k for k,v in config['crops'].items() if v['group']==group]
        train=frame[frame.crop.isin(codes)]
        ceiling,floor,constraints,unresolved=enclosure_constraints(train,config)
        candidates=[]
        for low,high in itertools.product(cal['low_factors'],cal['high_factors'][group]):
            values=evaluate(train,config,low,high)
            valid=[x['loss'] for x in values if x['valid']]
            score=float(np.mean(valid)) if valid else None
            # Invalid comparisons incur an explicit penalty rather than disappearing.
            if score is not None:score+=sum(not x['valid'] for x in values)/max(len(values),1)
            candidates.append({'group':group,'low':low,'high':high,'score':score,'training_rows':len(values),'valid_rows':len(valid),'results':values,
                'enclosure_pass':bool(valid and all(x['inside'] for x in values if x['valid']))})
        if constraints:
            reference=cal['reference_parameters'][group]
            margin=cal['anchor_margin_fraction']
            low=min(reference['low'],ceiling*(1-margin))
            high=max(reference['high'],floor*(1+margin))
            values=evaluate(train,config,low,high)
            if any(v['valid'] and not v['inside'] for v in values):
                raise ValueError(f'Seshat enclosure failed for {group}; no candidate can be certified')
            selected[group]={'low':low,'high':high,'selection_status':'all comparable Seshat anchor intervals enclosed; approximate geography',
                'training_rows':len(train),'comparable_anchors':len(constraints),'unresolved_anchors':unresolved,
                'lower_factor_ceiling':ceiling,'upper_factor_floor':floor,'constraints':constraints}
            candidates.append({'group':group,'low':low,'high':high,'method':'minimum change to reference parameters subject to mandatory Seshat enclosure',
                'enclosure_pass':True,'results':values})
        else:
            selected[group]={'low':cal['default_low'],'high':cal['default_high'][group],'selection_status':'unvalidated analogue prior; no usable calibration observations','training_rows':len(train)}
        comparisons.extend(candidates)
    manifest={'status':'research_candidate_not_historically_validated','parameters':selected,'candidate_ranges_frozen_in_configuration':True,'independent_source_validation':False,
        'policy':'Seshat enclosure is mandatory for every comparable case; no average-score exception',
        'uncertainty':'Encloses propagated historical yield-anchor intervals, not a complete Seshat uncertainty model',
        'seshat_cases_are_calibration_not_holdouts':True}
    write_json(out/'parameters.json',manifest)
    write_json(out/'candidate_comparisons.json',comparisons)
    crop_parameters=[]
    for code,crop in config['crops'].items():
        p=selected[crop['group']]
        for scenario in config['scenarios']:
            crop_parameters.append({'crop':code,'scenario':scenario,
                'effective_yield_factor':factor(crop,scenario,p['low'],p['high']),
                'shared_group':crop['group'],'group_training_rows':p['training_rows'],
                'direct_crop_training_rows':int((frame.crop==code).sum()),
                'status':p['selection_status'],'annualization':'separate; not included in this factor'})
    pd.DataFrame(crop_parameters).to_csv(out/'crop_parameters.csv',index=False)
    return manifest
