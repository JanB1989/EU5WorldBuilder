"""Flat conditional buildings on top of the flat attribute fit.

One building per ledger type. Each has a fixed flat value per level, an
eligibility gate written as attribute rules, and a level-cap equation in
attribute classes and development bands fitted as an envelope. Starting
levels come from the ledger and never exceed the cap at starting development.
No per-location term exists anywhere; leftovers are reported, not absorbed.
"""
import json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from .attribute_fit_flat import load_attributes, design_reference, fit_quantile
from .capacity_targets import LEDGER_KINDS
from .development_target import hash_map
from .provenance import write_json

ROOT=Path(__file__).resolve().parents[2]
DEV_BANDS=[(0,20,'d00_20'),(20,40,'d20_40'),(40,60,'d40_60'),(60,80,'d60_80'),(80,101,'d80_100')]


def gate(d,rules):
    """OR over rule dicts; each rule is an AND of attribute -> allowed values. Empty rules = everyone."""
    if not rules:return np.ones(len(d),bool)
    mask=np.zeros(len(d),bool)
    for rule in rules:
        m=np.ones(len(d),bool)
        for attr,allowed in rule.items():m&=d[attr].astype(str).isin([str(a) for a in allowed]).to_numpy()
        mask|=m
    return mask


def development_band(dev):
    dev=np.asarray(dev,float);out=np.empty(len(dev),dtype=object)
    for lo,hi,name in DEV_BANDS:out[(dev>=lo)&(dev<hi)]=name
    return out


def choose_unit(values,level_limit,quantiles,round_to=0):
    """Flat people per level minimising quantisation error over the positive ledger values."""
    v=np.asarray(values,float);v=v[v>0]
    if len(v)==0:return float('nan'),{'locations':0}
    best=None
    for q in quantiles:
        u=float(np.quantile(v,q))/max(1,level_limit/4)  # a location at the quantile uses ~level_limit/4 levels
        for factor in [0.5,0.75,1,1.5,2,3]:
            unit=u*factor
            n=np.clip(np.round(v/unit),0,level_limit);err=np.abs(n*unit-v).sum()
            if best is None or err<best[0]:best=(err,unit)
    unit=best[1]
    if round_to:unit=max(round_to,float(np.round(unit/round_to)*round_to))
    n=np.clip(np.round(v/unit),0,level_limit);rep=n*unit
    within=np.abs(rep-v)<=.25*v
    return unit,{'locations':int(len(v)),'captured_within_25_share':float(rep[within].sum()/v.sum()),'locations_within_25':float(within.mean()),
                 'locations_at_level_limit':int((n>=level_limit).sum()),'median_levels':float(np.median(n))}


def assign(d,ledger,dev,cfg):
    """Return per-location levels/caps and per-building summaries. d indexed by location_tag."""
    led=ledger.set_index('location_tag').loc[d.index]
    d=d.copy();d['development']=dev.reindex(d.index).to_numpy(float);d['development_band']=development_band(d.development)
    features=cfg['cap_features']+['development_band']
    reference={**cfg['reference_classes'],'development_band':'d00_20'}
    X,names,groups=design_reference(d,features,reference)
    ordinal={**cfg.get('ordinal',{}),'development_band':[b[2] for b in DEV_BANDS]}
    rows={};buildings=[];caps_out=[]
    out=pd.DataFrame(index=d.index)
    for kind in LEDGER_KINDS:
        rules=cfg['gates'].get(kind,[]);g=gate(d,rules)
        # Ledger people -> flat units: the game multiplies flat values by (1 + c*D), D at start for existing
        # works and 100 for the maximum, so the buildings only need to supply the pre-development part.
        c=float(cfg['capacity_percent_per_point']);dstart=d.development.to_numpy(float)
        Ls=led[f'starting_{kind}_capacity'].to_numpy(float)/(1+c*dstart);Lm=led[f'maximum_{kind}_capacity'].to_numpy(float)/(1+c*100)
        ungated=float(Lm[~g].sum()/Lm.sum()) if Lm.sum()>0 else 0.
        unit,quant=choose_unit(np.concatenate([Ls[g],Lm[g]]),cfg['level_limit'],cfg['unit_quantiles'],float(cfg.get('round_to',0) or 0))
        if not np.isfinite(unit):
            out[f'{kind}_levels_start']=0;out[f'{kind}_cap']=0;out[f'{kind}_leftover_start']=Ls;out[f'{kind}_leftover_max']=Lm
            buildings.append({'building':kind,'unit_people_per_level':None,'eligible_locations':int(g.sum()),'ungated_ledger_share':ungated,'note':'no ledger mass'});continue
        need=np.clip(np.ceil(Lm/unit),0,cfg['level_limit'])
        spans={f:(0.,float(cfg['level_limit'])) for f in features}
        spans.update({f:(-float(cfg['level_limit']),float(cfg['level_limit'])) for f in cfg.get('signed_cap_features',[])})
        # Fit the cap envelope over every gated location, including those with no ledger mass, so that
        # classes where works are rare receive small caps instead of inheriting their neighbours' need.
        sub=g if cfg.get('envelope_fit_scope','with_ledger')=='gated' else g&(need>0)
        beta,info=fit_quantile(X[sub],need[sub],names,groups,{'tau':cfg['envelope_quantile']},spans,(0.,float(cfg['level_limit'])),float(cfg['level_limit']),ordinal)
        beta=np.round(beta);beta[0]=max(beta[0],0)
        cap=np.clip(np.where(g,X@beta,0),0,cfg['level_limit'])
        band100=groups['development_band']['columns'].get('d80_100')
        X100=X.copy()
        for name,i in groups['development_band']['columns'].items():X100[:,i]=1. if i==band100 else 0.
        cap100=np.clip(np.where(g,X100@beta,0),0,cfg['level_limit'])
        n_start=np.minimum(np.clip(np.round(Ls/unit),0,cfg['level_limit']),cap)
        out[f'{kind}_levels_start']=n_start.astype(int);out[f'{kind}_cap']=cap.astype(int);out[f'{kind}_cap_at_development_100']=cap100.astype(int)
        out[f'{kind}_leftover_start']=Ls-n_start*unit;out[f'{kind}_leftover_max']=Lm-cap100*unit
        shortfall=g&(cap100<need);excess=g&(cap100>need)
        buildings.append({'building':kind,'unit_people_per_level':unit,'eligible_locations':int(g.sum()),'users_at_start':int((n_start>0).sum()),'ungated_ledger_share':ungated,
            **{f'quantisation_{k}':v for k,v in quant.items()},'cap_short_locations':int(shortfall.sum()),'cap_short_share_of_ledger':float(Lm[shortfall].sum()/max(Lm[g].sum(),1)),'cap_excess_locations':int(excess.sum()),'cap_excess_levels':float((cap100-need)[excess].sum()),
            'cap_intercept':float(beta[0]),'envelope_status':info['status'],'gate':json.dumps(rules)})
        for i,(f,v) in enumerate(names):
            if i:caps_out.append({'building':kind,'attribute':f,'value':v,'levels':int(beta[i])})
            else:caps_out.append({'building':kind,'attribute':'base','value':'reference','levels':int(beta[0])})
    out['development']=d.development;out['development_band']=d.development_band
    return out,pd.DataFrame(buildings),pd.DataFrame(caps_out)


def metrics(y,p):
    err=p-y;rel=np.abs(err)/np.maximum(y,1)
    return {'r2':float(1-(err**2).sum()/((y-y.mean())**2).sum()),'median_absolute_percentage_error':float(100*np.median(rel)),'within_25_percent':float(100*np.mean(rel<=.25)),'mean_bias':float(err.mean())}


def build(config_path=None,output_path=None):
    cp=Path(config_path or ROOT/'configs/building_assignment.json').resolve();cfg=json.loads(cp.read_text())
    out=Path(output_path or ROOT/'artifacts/building_assignment').resolve();out.mkdir(parents=True,exist_ok=True)
    fit_cfg=json.loads((ROOT/cfg['attribute_fit_config']).read_text())
    d=load_attributes(fit_cfg)
    pred=pd.read_csv(ROOT/cfg['attribute_fit_predictions'],keep_default_na=False).set_index('location_tag')
    for c in ['natural_capacity_fitted','maximum_capacity_fitted']:d[c]=pd.to_numeric(pred[c],errors='raise').reindex(d.index)
    ledger=pd.read_csv(ROOT/'artifacts/locations/improvement_ledger_equal_area.csv',keep_default_na=False)
    for c in ledger.columns:
        if c.endswith('_capacity'):ledger[c]=pd.to_numeric(ledger[c],errors='raise')
    devchecks=json.loads((ROOT/'artifacts/development/development_checks.json').read_text())
    devmap=pd.read_csv(ROOT/'artifacts/development/locations.csv',keep_default_na=False)
    devmap['development']=pd.to_numeric(devmap.development,errors='raise')
    if hash_map(devmap)!=devchecks['hash']:raise ValueError('Development map changed since its checks were written')
    if not devchecks['checks']['all_passed'] and not cfg.get('allow_failed_development_checks'):raise ValueError('Development sanity checks failed; fix development before assigning buildings')
    dev=devmap.set_index('location_tag').development
    result,buildings,caps=assign(d,ledger,dev,cfg)
    units={r.building:r.unit_people_per_level for r in buildings.itertuples() if r.unit_people_per_level}
    start_from_buildings=sum(result[f'{k}_levels_start']*units[k] for k in units)
    max_from_buildings=sum(result[f'{k}_cap_at_development_100']*units[k] for k in units)
    c=cfg['capacity_percent_per_point']
    result['starting_capacity_model']=(d.natural_capacity_fitted+start_from_buildings)*(1+c*result.development)
    result['maximum_capacity_model']=(d.natural_capacity_fitted+max_from_buildings)*(1+c*100)
    result['starting_capacity_target']=d.starting_capacity;result['maximum_capacity_target']=d.maximum_capacity
    result['leftover_start_total']=d.starting_capacity-result.starting_capacity_model
    result['leftover_max_total']=d.maximum_capacity-result.maximum_capacity_model
    fit={'starting':metrics(d.starting_capacity.to_numpy(float),result.starting_capacity_model.to_numpy(float)),
         'maximum':metrics(d.maximum_capacity.to_numpy(float),result.maximum_capacity_model.to_numpy(float)),
         'starting_improvements_only':metrics((d.starting_capacity-d.natural_capacity).to_numpy(float),(start_from_buildings*(1+c*result.development)).to_numpy(float)),
         'maximum_improvements_only':metrics((d.maximum_capacity-d.natural_capacity).to_numpy(float),(max_from_buildings*(1+c*100)).to_numpy(float))}
    result.to_csv(out/'locations.csv',index_label='location_tag',float_format='%.6g')
    buildings.to_csv(out/'buildings.csv',index=False,float_format='%.6g');caps.to_csv(out/'cap_coefficients.csv',index=False)
    leftover=result[['starting_capacity_target','starting_capacity_model','leftover_start_total','maximum_capacity_target','maximum_capacity_model','leftover_max_total','development']].copy()
    leftover=leftover.join(d[['province','region','macro_region']] if 'province' in d else d[['region','macro_region']])
    leftover.sort_values('leftover_start_total',ascending=False).head(500).to_csv(out/'largest_leftovers.csv',index_label='location_tag',float_format='%.6g')
    report={'config':cfg,'fit':fit,'buildings':buildings.to_dict(orient='records'),'development_hash':devchecks['hash'],'development_checks_passed':devchecks['checks']['all_passed'],
        'leftover':{'start_uncovered_people':float(np.maximum(result.leftover_start_total,0).sum()),'start_overshoot_people':float(np.maximum(-result.leftover_start_total,0).sum()),
                    'max_uncovered_people':float(np.maximum(result.leftover_max_total,0).sum()),'max_overshoot_people':float(np.maximum(-result.leftover_max_total,0).sum())},
        'scope':'Flat buildings with attribute gates and cap equations; levels from the ledger; no per-location term. Development is read, never adjusted.'}
    write_json(out/'report.json',report)
    lines=['# Building assignment','',f"Development map hash `{devchecks['hash'][:16]}` (checks {'passed' if devchecks['checks']['all_passed'] else 'FAILED'}). Capacity = (attribute flat + building flat) × (1 + {c*100:.1f}% × development).",'',
        '| Model | R² | Median error | Within 25% | Mean bias |','|---|---:|---:|---:|---:|']
    for k,v in fit.items():lines.append(f"| {k} | {v['r2']:.3f} | {v['median_absolute_percentage_error']:.1f}% | {v['within_25_percent']:.0f}% | {v['mean_bias']:,.0f} |")
    lines+=['','| Building | People / level | Eligible | Users at start | Ungated ledger share | Captured within 25% | At level limit | Cap short |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in buildings.itertuples():
        lines.append(f"| {r.building} | {(r.unit_people_per_level or 0):,.0f} | {r.eligible_locations:,} | {getattr(r,'users_at_start',0):,} | {100*r.ungated_ledger_share:.1f}% | {100*getattr(r,'quantisation_captured_within_25_share',0):.0f}% | {getattr(r,'quantisation_locations_at_level_limit',0):,} | {getattr(r,'cap_short_locations',0):,} |")
    lines+=['',f"Leftover at start: {report['leftover']['start_uncovered_people']/1e6:,.1f}M people uncovered, {report['leftover']['start_overshoot_people']/1e6:,.1f}M overshoot. At maximum: {report['leftover']['max_uncovered_people']/1e6:,.1f}M uncovered, {report['leftover']['max_overshoot_people']/1e6:,.1f}M overshoot.",'',
        'Files: `locations.csv` (levels, caps, leftovers), `buildings.csv`, `cap_coefficients.csv` (base + levels per attribute class and development band), `largest_leftovers.csv`.']
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    return report
