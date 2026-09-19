"""Starting development target: how intensively the land is already used.

Development is the only broad percentage in the game model,
K = flat * (1 + c * D). It is derived here from the improvement ledger and
historical land use BEFORE any building fit and is never adjusted afterwards
to close capacity gaps. A sanity suite compares the map with the regional
ordering of vanilla EU5's starting development and named spot checks; failing
checks block the building assignment unless explicitly overridden.

Components (all population-free, each in 0..1):
- crop_share: cultivated share of the physical area, saturating at a reference share
- feasible_utilisation: cultivated share of the maximum feasible cultivation
- improvement_share: improvement capacity share of starting capacity
- management_intensity: management capacity per cultivated hectare against its global p90
- pasture: pastoral land share
"""
import json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from .provenance import write_json

ROOT=Path(__file__).resolve().parents[2]
COMPONENTS=('crop_share','feasible_utilisation','improvement_share','management_intensity','pasture')


def saturate(x,reference):
    x=np.asarray(x,float);reference=float(reference)
    if reference<=0:return np.zeros(len(x))
    return -np.expm1(-np.clip(x,0,None)/reference)


def ratio(num,den):
    num=np.asarray(num,float);den=np.asarray(den,float)
    return np.clip(np.divide(num,den,out=np.zeros(len(num)),where=den>0),0,None)


def components(frame,ledger,cfg):
    led=ledger.set_index('location_tag').loc[frame.location_tag]
    area=frame.physical_location_ha.to_numpy(float);crop=frame.source_starting_crop_ha.to_numpy(float)
    natural=led.natural_capacity.to_numpy(float);imp=led.starting_ledger_total.to_numpy(float)
    mgmt=led.starting_management_capacity.to_numpy(float)
    out=pd.DataFrame(index=frame.index)
    out['crop_share']=saturate(ratio(crop,area),cfg['crop_share_reference'])
    out['feasible_utilisation']=-np.expm1(-cfg['utilisation_saturation']*np.clip(ratio(crop,frame.maximum_crop_ha.to_numpy(float)),0,None))
    out['improvement_share']=np.clip(ratio(imp,imp+natural),0,1)
    intensity=ratio(mgmt,crop)
    reference=cfg.get('management_intensity_reference') or (float(np.quantile(intensity[intensity>0],cfg['management_intensity_quantile'])) if (intensity>0).any() else 0.)
    out['management_intensity']=saturate(intensity,reference)
    out['pasture']=np.clip(ratio(frame.pastoral_area_ha.to_numpy(float),area),0,1)
    out.attrs['management_intensity_reference']=reference
    return out


def development(frame,ledger,cfg):
    """Weighted blend of the components, clipped to 0..100; non-ownable rows are 0."""
    w=cfg['weights'];total=sum(w.get(k,0) for k in COMPONENTS)
    if not np.isclose(total,1.0):raise ValueError('Development weights must sum to one')
    d=frame[['location_tag','province','region','macro_region','is_ownable','settlement_context']].copy()
    parts=components(frame,ledger,cfg)
    for k in COMPONENTS:d[k]=parts[k].to_numpy()
    score=sum(w.get(k,0)*parts[k].to_numpy() for k in COMPONENTS)
    d['development']=np.where(d.is_ownable.astype(bool),100*np.clip(score,0,1),0.)
    d.attrs['management_intensity_reference']=parts.attrs['management_intensity_reference']
    return d


def checks(d,cfg):
    c=cfg['checks'];own=d[d.is_ownable.astype(bool)]
    result={}
    p90=float(own.development.quantile(.9));lo,hi=c['p90_band']
    result['p90_in_band']={'observed':p90,'band':[lo,hi],'passed':lo<=p90<=hi}
    result['maximum']={'observed':float(own.development.max()),'limit':c['maximum'],'passed':bool(own.development.max()<=c['maximum'])}
    means=own.groupby('macro_region').development.mean()
    groups=[[r for r in group if r in means.index] for group in c['expected_ordering']]
    ordering_ok=True;violations=[]
    for i in range(len(groups)-1):
        upper=groups[i];lower=groups[i+1]
        if not upper or not lower:continue
        if means[upper].min()<means[lower].max():
            ordering_ok=False;violations.append({'higher_group':upper,'lower_group':lower,'min_of_higher':float(means[upper].min()),'max_of_lower':float(means[lower].max())})
    result['regional_ordering']={'passed':ordering_ok,'macro_region_means':means.round(2).to_dict(),'violations':violations}
    frontier=own[own.macro_region.isin(c['frontier_macro_regions'])]
    medians=frontier.groupby('macro_region').development.median()
    result['frontier_median']={'limit':c['frontier_median_below'],'observed':medians.round(2).to_dict(),'passed':bool((medians<c['frontier_median_below']).all())}
    spots={};ok=True
    values=own.set_index('location_tag').development
    for tag,(lo,hi) in c['spot_checks'].items():
        if tag not in values.index:spots[tag]={'observed':None,'band':[lo,hi],'passed':None};continue
        v=float(values[tag]);good=lo<=v<=hi;ok&=good;spots[tag]={'observed':round(v,1),'band':[lo,hi],'passed':good}
    result['spot_checks']={'passed':ok,'locations':spots}
    result['not_a_residual']={'passed':True,'note':'Development is computed from the ledger and land use before any building fit; building_assignment verifies the hash below is unchanged.'}
    result['all_passed']=all(v['passed'] for k,v in result.items() if isinstance(v,dict) and 'passed' in v)
    return result


def hash_map(d):
    frame=pd.DataFrame({'location_tag':d.location_tag.astype(str).to_numpy(),'development':np.round(pd.to_numeric(d.development,errors='raise').to_numpy(float),3)})
    return hashlib.sha256(pd.util.hash_pandas_object(frame,index=False).to_numpy().tobytes()).hexdigest()


def build(config_path=None,output_path=None):
    cp=Path(config_path or ROOT/'configs/development.json').resolve();cfg=json.loads(cp.read_text())
    out=Path(output_path or ROOT/'artifacts/development').resolve();out.mkdir(parents=True,exist_ok=True)
    loc=ROOT/'artifacts/locations'
    frame=pd.read_csv(loc/'locations_equal_area.csv',keep_default_na=False,usecols=['location_tag','province','region','macro_region','is_ownable','settlement_context','source_starting_crop_ha','maximum_crop_ha','pastoral_area_ha','physical_location_ha'])
    for c in ['source_starting_crop_ha','maximum_crop_ha','pastoral_area_ha','physical_location_ha']:frame[c]=pd.to_numeric(frame[c],errors='coerce').fillna(0.)
    frame['is_ownable']=frame.is_ownable.astype(str).eq('True')
    ledger=pd.read_csv(loc/'improvement_ledger_equal_area.csv',keep_default_na=False)
    for c in ledger.columns:
        if c.endswith('_capacity') or c.endswith('_total'):ledger[c]=pd.to_numeric(ledger[c],errors='raise')
    d=development(frame,ledger,cfg)
    result=checks(d,cfg)
    d.to_csv(out/'locations.csv',index=False,float_format='%.6f')
    # Hash the file as consumers will read it, so the building assignment can verify it byte-for-byte.
    written=pd.read_csv(out/'locations.csv',keep_default_na=False)
    own=d[d.is_ownable]
    own.groupby('macro_region').development.agg(['size','mean','median',lambda s:s.quantile(.9),'max']).rename(columns={'<lambda_0>':'p90'}).round(2).to_csv(out/'macro_regions.csv')
    report={'config':cfg,'hash':hash_map(written),'checks':result,'management_intensity_reference':d.attrs['management_intensity_reference'],
        'inputs':{'locations_equal_area.csv':hashlib.sha256((loc/'locations_equal_area.csv').read_bytes()).hexdigest(),'improvement_ledger_equal_area.csv':hashlib.sha256((loc/'improvement_ledger_equal_area.csv').read_bytes()).hexdigest()},
        'quantiles':own.development.quantile([0,.1,.25,.5,.75,.9,.99,1]).round(2).to_dict(),'component_means':{k:float(own[k].mean()) for k in COMPONENTS},
        'capacity_percent_per_point':cfg['capacity_percent_per_point'],'population_used':False,
        'note':'D = 100 * clip(sum_k w_k * component_k). Components use HYDE/LUH-derived starting cultivation, the maximum feasible cultivation, the improvement ledger and pastoral land; attributes never use HYDE, only this start-state quantity does.'}
    write_json(out/'development_checks.json',report)
    w=cfg['weights']
    lines=['# Starting development target','',f"Overall: **{'PASS' if result['all_passed'] else 'FAIL'}**. Development is derived before any building fit and never adjusted to close capacity gaps (hash `{report['hash'][:16]}`).",'',
        'Formula: D = 100 · clip('+' + '.join(f"{w.get(k,0)}·{k}" for k in COMPONENTS if w.get(k,0))+f", 0, 1); capacity multiplier {cfg['capacity_percent_per_point']*100:.1f}% per point. Management intensity reference: {report['management_intensity_reference']:.4f} people per cultivated hectare (global p{int(100*cfg['management_intensity_quantile'])}).",'',
        '| Check | Observed | Requirement | Result |','|---|---|---|:---:|',
        f"| P90 | {result['p90_in_band']['observed']:.1f} | {result['p90_in_band']['band']} | {'PASS' if result['p90_in_band']['passed'] else 'FAIL'} |",
        f"| Maximum | {result['maximum']['observed']:.1f} | <= {result['maximum']['limit']} | {'PASS' if result['maximum']['passed'] else 'FAIL'} |",
        f"| Regional ordering | {len(result['regional_ordering']['violations'])} violations | vanilla EU5 ordering | {'PASS' if result['regional_ordering']['passed'] else 'FAIL'} |",
        f"| Frontier medians | {result['frontier_median']['observed']} | < {result['frontier_median']['limit']} | {'PASS' if result['frontier_median']['passed'] else 'FAIL'} |",
        f"| Spot checks | {sum(1 for v in result['spot_checks']['locations'].values() if v['passed'])} / {len(result['spot_checks']['locations'])} | bands | {'PASS' if result['spot_checks']['passed'] else 'FAIL'} |",'']
    for v in result['regional_ordering']['violations']:
        lines.append(f"- ordering violation: min of {v['higher_group']} = {v['min_of_higher']:.1f} < max of {v['lower_group']} = {v['max_of_lower']:.1f}")
    lines+=['','## Macro-region means','','| Macro-region | Mean development |','|---|---:|']
    lines+=[f"| {k} | {v:.1f} |" for k,v in sorted(result['regional_ordering']['macro_region_means'].items(),key=lambda kv:-kv[1])]
    lines+=['','## Spot checks','','| Location | Development | Band | Result |','|---|---:|---|:---:|']
    lines+=[f"| {k} | {v['observed']} | {v['band']} | {'PASS' if v['passed'] else 'FAIL' if v['passed'] is not None else 'missing'} |" for k,v in result['spot_checks']['locations'].items()]
    lines+=['','Population is not used. Files: `locations.csv` (components and development), `macro_regions.csv`, `development_checks.json`.']
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    return report
