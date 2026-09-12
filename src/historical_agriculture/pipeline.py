import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from .acquisition import acquire, filename
from .accounting import historical_position
from .calibration import calibrate, evaluate
from .evidence import prepare
from .provenance import digest, fingerprint, write_json
from .raster import read, grid
from .reconstruction import surfaces, assign, calculate
from .transformations import factor

STAGES=['audit','evidence','calibrate','assign','food-assign','calculate','compare','food-calculate','validate','maps']

STAGE_OUTPUTS={
    'audit':['input_audit.json'],
    'evidence':[],
    'calibrate':['parameters.json','crop_parameters.csv','candidate_comparisons.json','scenario_ordering.json','crops/*.tif'],
    'assign':['ecoregion.tif','ecoregion_ledger.json','crop.tif','alternative_crop.tif','region.tif','state.tif','confidence.tif','coverage.json'],
    'food-assign':['food_type.tif','food_evidence.tif','food_ecoregion.tif','food_geometry_inferred.tif','food_coverage.json','food_assignment_ledger.json'],
    'food-calculate':['*people.tif','food_numeric_basis.tif','food_validation.json','benchmark_people.csv'],
    'calculate':['*dm.tif','*kcal*.tif','labour*.tif','upper_system.tif','envelope_valid.tif',
                 'management_position.tif','cultivated_fraction.tif','rotation_override.tif','rotation_overrides.json','sensitivity.json',
                 'controlled_sensitivity.json','regional_distributions.csv','coverage_gaps.json'],
    'compare':['benchmark_comparison.*','benchmark_summary.json','benchmark_denominator_sensitivity.csv','independent_holdouts.json'],
    'validate':['validation.json','failure_register.json'],
    'maps':['maps/*.png','REPORT.md','FOOD_METHOD.md','index.html'],
}

def check_prerequisites(command, config_path, raw, out):
    fp,_=fingerprint(config_path,raw)
    for previous in STAGES[:STAGES.index(command)]:
        stamp=out/f'{previous}.stamp.json'
        if not stamp.exists():raise ValueError(f'Missing stage {previous}; run ha1300 run')
        saved=json.loads(stamp.read_text())
        if saved['fingerprint']!=fp:raise ValueError(f'Stale stage {previous}; run ha1300 run')
        for name,expected in saved['output_hashes'].items():
            path=out/name
            if not path.exists() or digest(path)!=expected:
                raise ValueError(f'Previous output changed: {name}; rebuild before validation')

def audit(root,config,out):
    expected=None;records=[]
    lock=root/config['inputs']/'reconstruction_manifest.json'
    pins={r['name']:r for r in json.loads(lock.read_text())}
    for c in config['crop_order']:
        for scenario in config['scenarios']:
            path=root/config['inputs']/filename(c,scenario)
            contract=grid(path)
            if expected is not None and contract!=expected:raise ValueError('Input grids differ')
            expected=contract
            actual=digest(path)
            if pins[path.name]['sha256']!=actual:raise ValueError('Pinned input checksum mismatch')
            records.append({'crop':c,'scenario':scenario,'sha256':actual})
    result={'engineering_pass':True,'inputs':records,'grid':expected,'units':config['units'],
            'scientific_qualifications':['YXX is conditional best-class yield, not a cell-average productivity.',
            'Annualization is an explicit interpretation; product metadata lacks an explicit fallow-applied flag.',
            'High input is modern industrial management before historical adjustments.']}
    write_json(out/'input_audit.json',result)
    return {'engineering_pass':True,'raster_count':len(records),'qualifications':result['scientific_qualifications']}

def compare(root,config,out):
    frame=pd.read_csv(root/'evidence/benchmarks_1300.csv')
    parameters=json.loads((out/'parameters.json').read_text())['parameters']
    rows=[];denominators=[]
    for _,r in frame.iterrows():
        p=parameters[config['crops'][r.crop]['group']]
        value=evaluate(pd.DataFrame([r]),config,p['low'],p['high'])[0]
        value.update({'crop':r.crop,'role':r.role,'source_family':r.source_family,'spatial_status':r.spatial_status})
        if value['valid']:
            value['position']=float(historical_position(value['observed'],value['lower'],value['upper']))
            value['result']='inside' if value['inside'] else 'outside'
            dry=config['crops'][r.crop]['dry_fraction']
            from .rotations import benchmark_coefficient
            annual,_,annual_status=benchmark_coefficient(root,r.region,r.cropping_coefficient)
            value['annual_cropping_coefficient']=annual;value['annualization_status']=annual_status
            value['lower_annual_fresh_kg']=value['lower']/dry*annual
            value['upper_annual_fresh_kg']=value['upper']/dry*annual
            value['observed_annual_fresh_kg']=r.harvest_t_ha_inferred*annual*1000
            for convention,observed_t in [('published_literal',r.published_yield_t_ha),('remove_relative_anchor_cropping',r.harvest_t_ha_inferred),('divide_cropping_only_diagnostic',r.published_yield_t_ha/r.cropping_coefficient)]:
                observed_dm=observed_t*1000*dry
                denominators.append({'region':r.region,'convention':convention,'observed_dm_kg_ha':observed_dm,
                    'position':float(historical_position(observed_dm,value['lower'],value['upper'])),
                    'inside':bool(value['lower']<=observed_dm<=value['upper']),
                    'status':'denominator sensitivity; conventions are alternatives, not independent observations'})
            corners=[]
            samples=json.loads(r.scenario_samples_dm)
            transformed={s:np.asarray(a)*factor(config['crops'][r.crop],s,p['low'],p['high']) for s,a in samples.items()}
            for q in [.1,.9]:
                lo=np.quantile(transformed['LRLM'],q)
                hi=np.quantile(np.maximum(transformed['HRLM'],transformed['HILM']),q)
                corners.append(float(historical_position(value['observed'],lo,hi)))
            value['spatial_position_p10_p90_scenario']=corners
        else:value['result']='unresolved'
        rows.append(value)
    pd.DataFrame(rows).drop(columns=['spatial_position_p10_p90_scenario'],errors='ignore').to_csv(out/'benchmark_comparison.csv',index=False)
    write_json(out/'benchmark_comparison.json',rows)
    pd.DataFrame(denominators).to_csv(out/'benchmark_denominator_sensitivity.csv',index=False)
    from .holdouts import independent
    external=independent(root,config,out)
    result={'rows':len(rows),'inside':sum(r['result']=='inside' for r in rows),'outside':sum(r['result']=='outside' for r in rows),'unresolved':sum(r['result']=='unresolved' for r in rows),
            'constraint_policy':'All comparable Seshat cases are mandatory calibration anchors, not holdouts',
            'seshat_enclosure_pass':bool(any(r['valid'] for r in rows) and all(r['inside'] for r in rows if r['valid'])),
            'independent_historical_validation':{'passed':sum(r['result']=='passed' for r in external),'failed':sum(r['result']=='failed' for r in external),'coverage':'English wheat only; not global validation'}}
    write_json(out/'benchmark_summary.json',result)
    return result

def validate(root,config,out):
    states,_=read(out/'state.tif');crop,_=read(out/'crop.tif')
    lo,_=read(out/'lower_dm.tif');hi,_=read(out/'upper_dm.tif');hist,_=read(out/'historical_dm.tif')
    gross,_=read(out/'gross_kcal.tif');net,_=read(out/'historical_kcal.tif')
    labour,_=read(out/'labour_days.tif');efficiency,_=read(out/'kcal_per_worker_day.tif')
    valid=np.isfinite(hist)
    checks={
        'classification_codes':bool(np.isin(states[np.isfinite(states)],[1,2,3,4,5,6]).all()),
        'agricultural_cells_have_crop':bool(np.all(crop[states==2]>0)),
        'noncrop_cells_have_no_crop':bool(np.all(crop[states==1]==0)),
        'historical_yield_within_valid_envelope':bool(np.all((hist[valid]>=lo[valid]-.001)&(hist[valid]<=hi[valid]+.001))),
        'net_not_greater_than_gross':bool(np.all(net[valid]<=gross[valid]+1)),
        'positive_labour':bool(np.all(labour[valid]>0)),
        'calorie_labour_reconciliation':bool(np.allclose(net[valid]/labour[valid],efficiency[valid],rtol=2e-6)),
        'noncrop_food_is_missing_not_fabricated':bool(np.isnan(net[states==1]).all()),
    }
    for code in ['MZE','WPO','CSV']:
        # Regional crop rules carry historical availability; these checks catch accidental global crop maximization.
        from .raster import coordinates
        _,profile=read(out/'crop.tif');x,y=coordinates(profile)
        old_world=(x[None,:]>=-20)&(x[None,:]<150)&(y[:,None]>-35)
        checks[f'no_{code}_in_old_world']=bool(not np.any(old_world&(crop==config['crop_order'].index(code)+1)))
    if (out/'food_validation.json').exists():
        food_validation=json.loads((out/'food_validation.json').read_text())
        checks.update({'food_'+k:v for k,v in food_validation['checks'].items()})
    coverage=json.loads((out/'coverage.json').read_text())
    benchmarks=json.loads((out/'benchmark_summary.json').read_text())
    scientific=[
        {'criterion':'All historical benchmarks evaluated','result':'passed' if benchmarks['unresolved']==0 else 'unresolved'},
        {'criterion':'All comparable Seshat anchor intervals enclosed','result':'passed' if benchmarks['seshat_enclosure_pass'] else 'failed'},
        {'criterion':'Independent historical source holdouts','result':'failed' if benchmarks['independent_historical_validation']['failed'] else 'passed_limited_English_wheat'},
        {'criterion':'Regional crop coverage','result':'passed' if coverage['states']['4']==0 else 'unresolved'},
        {'criterion':'Global historical management positions','result':'inferred_not_validated'},
        {'criterion':'Seasonal labour feasibility','result':'not_evaluated'},
        {'criterion':'Exact Seshat geographical support','result':'approximate_not_verified'},
        {'criterion':'Product-level fallow convention','result':'explicit_interpretation_not_independently_verified'},
        {'criterion':'Historical irrigation water feasibility','result':'conditional_water_delivery_not_verified'},
        {'criterion':'Historical climate and soil reconstruction','result':'out_of_scope_modern_proxy'},
    ]
    result={'engineering_pass':all(checks.values()),'engineering_checks':checks,'scientific_acceptance':False,'scientific_criteria':scientific,
            'status':'usable research candidate; not accepted as a validated historical reconstruction',
            'calculated_cells':int(valid.sum())}
    write_json(out/'validation.json',result)
    cases=json.loads((out/'benchmark_comparison.json').read_text())
    failures=[]
    for case in cases:
        if case['result']=='inside':continue
        failures.append({'case':case['region'],'status':case['result'],
            'evidence':'benchmark_comparison.json','lower':case.get('lower'),
            'upper':case.get('upper'),'observed':case.get('observed'),
            'next_action':('Reconcile crop proxy and approximate NGA geometry; sampled crop has no comparable positive scenario.'
                if case['result']=='unresolved' else
                'Mandatory Seshat enclosure failed: reject the candidate and correct shared scaling or the comparison contract.')})
    if coverage['states']['4']:
        failures.append({'case':'unassigned viable cells','status':'unresolved','cells':coverage['states']['4'],
            'evidence':'coverage_gaps.json','next_action':'Resolve named small-island and boundary cases with dated livelihood evidence.'})
    for item in scientific:
        if item['result'] not in ['passed','passed_limited_English_wheat','out_of_scope_modern_proxy']:
            failures.append({'case':item['criterion'],'status':item['result'],'evidence':'validation.json'})
    write_json(out/'failure_register.json',{'failures':failures,'no_population_targets':True,
        'scientific_acceptance':False,'interpretation':'Numerical engineering success does not clear these scientific qualifications.'})
    return result

def execute(command,config_path,out):
    config_path=Path(config_path).resolve();root=config_path.parents[1]
    config=json.loads(config_path.read_text());out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    if command=='acquire':return acquire(config,root)
    def run_stage(stage):
        if stage=='audit':result=audit(root,config,out)
        elif stage=='evidence':result=prepare(root,config)
        elif stage=='calibrate':
            result=calibrate(root,config,out);surfaces(root,config,out)
        elif stage=='assign':result=assign(root,config,out)
        elif stage=='food-assign':
            from .food_systems import assign_food
            result=assign_food(root,config,out)
        elif stage=='food-calculate':
            from .food_systems import calculate_food, benchmark_people
            result=calculate_food(root,config,out);benchmark_people(root,config,out)
        elif stage=='calculate':
            result=calculate(root,config,out)
            from .diagnostics import diagnostics
            result['diagnostics']=diagnostics(root,config,out)
        elif stage=='compare':result=compare(root,config,out)
        elif stage=='validate':result=validate(root,config,out)
        elif stage=='maps':
            from .reporting import report
            result=report(root,config,out)
        else:raise ValueError(stage)
        fp,details=fingerprint(config_path,root/config['inputs'])
        files=[p for pattern in STAGE_OUTPUTS[stage] for p in out.glob(pattern) if p.is_file()]
        if stage=='evidence':files += [root/'evidence/benchmarks_1300.csv',root/'evidence/benchmark_manifest.json']
        output_hashes={os.path.relpath(p,out):digest(p) for p in files}
        write_json(out/f'{stage}.stamp.json',{'fingerprint':fp,'input_hashes':details,'output_hashes':output_hashes})
        return result
    if command=='run':
        result={}
        for stage in STAGES:
            print(f'{stage}: running',flush=True)
            result[stage]=run_stage(stage)
        fp,details=fingerprint(config_path,root/config['inputs'])
        write_json(out/'manifest.json',{'fingerprint':fp,'inputs':details,'output_hashes':{str(p.relative_to(out)):digest(p) for p in out.rglob('*') if p.is_file() and p.name!='manifest.json'},'scientific_acceptance':False})
        return {'validation':result['validate'],'maps':result['maps']}
    if command in STAGES[1:]:check_prerequisites(command,config_path,root/config['inputs'],out)
    return run_stage(command)
