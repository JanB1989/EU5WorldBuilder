"""Flat conditional buildings on top of the flat attribute fit.

One building per ledger type. Each has a fixed flat value per level, an
eligibility gate written as attribute rules, and a level-cap equation in
attribute classes plus a linear development term (levels per point) fitted as an envelope. Starting
levels come from the ledger and never exceed the cap at starting development.
No per-location term exists anywhere; leftovers are reported, not absorbed.
"""
import json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from .attribute_fit_flat import load_attributes, design_reference, fit_quantile
from .capacity_targets import LEDGER_KINDS
from .ledger_extensions import extend, EXTENSION_KINDS
from .development_target import hash_map
from .provenance import write_json

ROOT=Path(__file__).resolve().parents[2]


def gate(d,rules):
    """OR over rule dicts; each rule is an AND of attribute -> allowed values. Empty rules = everyone."""
    if not rules:return np.ones(len(d),bool)
    mask=np.zeros(len(d),bool)
    for rule in rules:
        m=np.ones(len(d),bool)
        for attr,allowed in rule.items():m&=d[attr].astype(str).isin([str(a) for a in allowed]).to_numpy()
        mask|=m
    return mask


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
    d=d.copy();d['development']=dev.reindex(d.index).to_numpy(float)
    features=cfg['cap_features']
    X,names,groups=design_reference(d,features,cfg['reference_classes'])
    # EU5 cap equations take development only as a linear term: add = { value = development multiply = gamma }.
    X=np.column_stack([X,d.development.to_numpy(float)]);names=names+[('development','per_point')];idev=X.shape[1]-1
    # Caps are compared with the physical maximum at the location's own starting development and reported at a
    # reference development (the highest game starting value by default); the development term is a design bonus.
    dref=float(cfg.get('maximum_reference_development',45));Xref=X.copy();Xref[:,idev]=dref
    ordinal=cfg.get('ordinal',{})
    buildings=[];caps_out=[]
    out=pd.DataFrame(index=d.index)
    kinds=list(LEDGER_KINDS)+[k for k in EXTENSION_KINDS if f'starting_{k}_capacity' in led and led[f'maximum_{k}_capacity'].sum()>0]
    led=led.copy();gates=dict(cfg['gates']);gmins=dict(cfg.get('development_levels_per_point_min') or {})
    # A ledger kind may be split over several buildings: each gets its share of the people and the kind's gate.
    for src,parts in (cfg.get('split_kinds') or {}).items():
        if src not in kinds:continue
        i=kinds.index(src);kinds[i:i+1]=list(parts)
        for part,share in parts.items():
            for stage in ('starting','maximum'):led[f'{stage}_{part}_capacity']=led[f'{stage}_{src}_capacity'].to_numpy(float)*float(share)
            gates.setdefault(part,gates.get(src,[]));gmins.setdefault(part,gmins.get(src,0.))
    # Cap groups: buildings with their own gate and ledger that share ONE cap equation, fitted on their summed ledger
    # (the members' levels together never exceed it; each member is built only where its own gate holds).
    groups_cfg={name:[k for k in members if k in kinds] for name,members in (cfg.get('cap_groups') or {}).items()}
    member_of={k:name for name,members in groups_cfg.items() for k in members}
    fits=[]
    for kind in kinds:
        name=member_of.get(kind,kind)
        if name not in [f[0] for f in fits]:fits.append((name,groups_cfg.get(name,[kind])))
    limit=int(cfg['level_limit']);fixed_unit=cfg.get('unit_people_per_level')
    # Starting levels are the works already standing in 1337; with clamp_start_to_cap false they are kept in full even
    # where they exceed the cap (the engine keeps setup levels above max_levels; they just cannot be extended).
    clamp_start=bool(cfg.get('clamp_start_to_cap',True))
    c=float(cfg['capacity_percent_per_point']);dstart=d.development.to_numpy(float)
    for name,members in fits:
        mrules={m:gates.get(m,[]) for m in members}
        rules=[] if any(not r for r in mrules.values()) else [r for m in members for r in mrules[m]]
        g=gate(d,rules);gm={m:gate(d,mrules[m]) for m in members}
        # Ledger people -> flat units: the game multiplies flat values by (1 + c*D), D at start for existing
        # works and 100 for the maximum, so the buildings only need to supply the pre-development part.
        Ls_m={m:led[f'starting_{m}_capacity'].to_numpy(float)/(1+c*dstart) for m in members}
        Lm_m={m:led[f'maximum_{m}_capacity'].to_numpy(float)/(1+c*100) for m in members}
        Ls=sum(Ls_m.values());Lm=sum(Lm_m.values())
        ungated=float(Lm[~g].sum()/Lm.sum()) if Lm.sum()>0 else 0.
        if fixed_unit:
            # One people-per-level for every improvement: comparable level counts and prices (2026-10-05, Jan).
            v=np.concatenate([Ls[g],Lm[g]]);v=v[v>0];unit=float(fixed_unit) if len(v) else float('nan')
            n=np.clip(np.round(v/float(fixed_unit)),0,limit);rep=n*float(fixed_unit);within=np.abs(rep-v)<=.25*v
            quant={'locations':int(len(v)),'captured_within_25_share':float(rep[within].sum()/max(v.sum(),1)),'locations_within_25':float(within.mean()) if len(v) else 0.,
                   'locations_at_level_limit':int((n>=limit).sum()),'median_levels':float(np.median(n)) if len(v) else 0.}
        else:
            unit,quant=choose_unit(np.concatenate([Ls[g],Lm[g]]),limit,cfg['unit_quantiles'],float(cfg.get('round_to',0) or 0))
        if not np.isfinite(unit):
            for m in members:
                out[f'{m}_levels_start']=0;out[f'{m}_cap']=0;out[f'{m}_leftover_start']=Ls_m[m];out[f'{m}_leftover_max']=Lm_m[m]
                buildings.append({'building':m,'unit_people_per_level':None,'eligible_locations':int(gm[m].sum()),'ungated_ledger_share':ungated,'note':'no ledger mass','cap_group':name if len(members)>1 else ''})
            continue
        need=np.clip(np.ceil(Lm/unit),0,limit)
        spans={f:(0.,float(limit)) for f in features}
        spans.update({f:(-float(limit),float(limit)) for f in cfg.get('signed_cap_features',[])})
        # Development raises improvement caps by design: each building has a minimum levels-per-point (config),
        # so intensification arrives as extra levels even where the envelope alone would not need the term.
        gmin=float(gmins[name]) if name in gmins else max(float(gmins.get(m,0.)) for m in members)
        gmax=float(cfg.get('max_levels_per_development_point',limit/100))
        spans['development']=(min(gmin,gmax),gmax)
        # Fit the cap envelope over every gated location, including those with no ledger mass, so that
        # classes where works are rare receive small caps instead of inheriting their neighbours' need.
        sub=g if cfg.get('envelope_fit_scope','with_ledger')=='gated' else g&(need>0)
        beta,info=fit_quantile(X[sub],need[sub],names,groups,{'tau':cfg['envelope_quantile']},spans,(0.,float(limit)),float(limit),ordinal)
        gamma=max(min(gmin,gmax),round(float(beta[idev]),2));beta=np.round(beta);beta[idev]=gamma;beta[0]=max(beta[0],0)
        # Levels are whole numbers in game: the cap is floored after the linear development term.
        cap=np.clip(np.where(g,np.floor(X@beta+1e-9),0),0,limit)
        capref=np.clip(np.where(g,np.floor(Xref@beta+1e-9),0),0,limit)
        n_total=np.clip(np.round(Ls/unit),0,None)
        if clamp_start:n_total=np.minimum(np.minimum(n_total,limit),cap)
        if len(members)==1:
            n_m={members[0]:n_total}
        else:
            # The group's starting levels go to its members by their own ledger (largest remainders), only where they may stand.
            exact={m:np.where(gm[m],Ls_m[m]/unit,0.) for m in members}
            n_m={m:np.floor(exact[m]) for m in members}
            left=n_total-sum(n_m.values())
            for _ in members:
                rem=np.column_stack([exact[m]-n_m[m] for m in members]);best=rem.argmax(axis=1);take=(left>0)&(rem.max(axis=1)>0)
                for j,m in enumerate(members):n_m[m]=n_m[m]+np.where(take&(best==j),1,0)
                left=left-take
        shortfall=g&(cap<need);excess=g&(cap>need)
        for m in members:
            n_start=n_m[m];mcap=np.where(gm[m],cap,0);mref=np.where(gm[m],capref,0)
            share=np.divide(Lm_m[m],Lm,out=np.zeros(len(Lm)),where=Lm>0)
            out[f'{m}_levels_start']=n_start.astype(int);out[f'{m}_cap']=mcap.astype(int);out[f'{m}_cap_at_reference']=mref.astype(int)
            out[f'{m}_leftover_start']=Ls_m[m]-n_start*unit;out[f'{m}_leftover_max']=Lm_m[m]-cap*unit*share
            buildings.append({'building':m,'unit_people_per_level':unit,'eligible_locations':int(gm[m].sum()),'users_at_start':int((n_start>0).sum()),'ungated_ledger_share':ungated,
                **{f'quantisation_{k}':v for k,v in quant.items()},'cap_short_locations':int(shortfall.sum()),'cap_short_share_of_ledger':float(Lm[shortfall].sum()/max(Lm[g].sum(),1)),'cap_excess_locations':int(excess.sum()),'cap_excess_levels':float((cap-need)[excess].sum()),
                'cap_intercept':float(beta[0]),'levels_per_development_point':gamma,'envelope_status':info['status'],'gate':json.dumps(mrules[m]),'cap_group':name if len(members)>1 else '',
                'start_levels_above_cap':int(np.maximum(n_start-mcap,0).sum())})
            for i,(f,v) in enumerate(names):
                if i==idev:caps_out.append({'building':m,'attribute':'development','value':'per_point','levels':gamma})
                elif i:caps_out.append({'building':m,'attribute':f,'value':v,'levels':int(beta[i])})
                else:caps_out.append({'building':m,'attribute':'base','value':'reference','levels':int(beta[0])})
    out['development']=d.development
    return out,pd.DataFrame(buildings),pd.DataFrame(caps_out)


def cap_people(result,buildings,units,column):
    """People the caps allow per location; the members of a cap group share one cap, so it counts once."""
    group=dict(zip(buildings.building,buildings['cap_group'].fillna(''))) if 'cap_group' in buildings else {}
    total=0.;done=set()
    for k in units:
        name=group.get(k) or k
        if name in done:continue
        done.add(name);members=[m for m in units if (group.get(m) or m)==name]
        cap=np.max(np.column_stack([result[f'{m}_{column}'].to_numpy(float)*units[m] for m in members]),axis=1)
        # starting levels above the cap stand anyway (the engine keeps them), so they bound the maximum from below
        start=np.sum(np.column_stack([result[f'{m}_levels_start'].to_numpy(float)*units[m] for m in members]),axis=1)
        total=total+np.maximum(cap,start)
    return pd.Series(total,index=result.index)


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
    ledger,_=extend(d,ledger,cfg)
    devchecks=json.loads((ROOT/'artifacts/development/development_checks.json').read_text())
    devmap=pd.read_csv(ROOT/'artifacts/development/locations.csv',keep_default_na=False)
    devmap['development']=pd.to_numeric(devmap.development,errors='raise')
    if hash_map(devmap)!=devchecks['hash']:raise ValueError('Development map changed since its checks were written')
    if not devchecks['checks']['all_passed'] and not cfg.get('allow_failed_development_checks'):raise ValueError('Development sanity checks failed; fix development before assigning buildings')
    dev=devmap.set_index('location_tag').development
    result,buildings,caps=assign(d,ledger,dev,cfg)
    units={r.building:r.unit_people_per_level for r in buildings.itertuples() if r.unit_people_per_level}
    start_from_buildings=sum(result[f'{k}_levels_start']*units[k] for k in units)
    max_from_buildings=cap_people(result,buildings,units,'cap')
    ref_from_buildings=cap_people(result,buildings,units,'cap_at_reference')
    c=cfg['capacity_percent_per_point']
    from .development_target import capacity_people_per_point
    kdev=capacity_people_per_point();dref=float(cfg.get('maximum_reference_development',100))
    result['development_flat_people']=kdev*result.development
    result['starting_capacity_model']=(d.natural_capacity_fitted+start_from_buildings)*(1+c*result.development)+kdev*result.development
    result['maximum_capacity_model']=(d.natural_capacity_fitted+max_from_buildings)*(1+c*100)+kdev*100
    result['maximum_capacity_at_reference']=(d.natural_capacity_fitted+ref_from_buildings)+kdev*dref
    result['starting_capacity_target']=d.starting_capacity;result['maximum_capacity_target']=d.maximum_capacity
    result['leftover_start_total']=d.starting_capacity-result.starting_capacity_model
    result['leftover_max_total']=d.maximum_capacity-result.maximum_capacity_model
    fit={'starting':metrics(d.starting_capacity.to_numpy(float),result.starting_capacity_model.to_numpy(float)),
         'maximum':metrics(d.maximum_capacity.to_numpy(float),result.maximum_capacity_model.to_numpy(float)),
         'starting_improvements_only':metrics((d.starting_capacity-d.natural_capacity).to_numpy(float),(start_from_buildings*(1+c*result.development)).to_numpy(float)),
         'maximum_improvements_only':metrics((d.maximum_capacity-d.natural_capacity).to_numpy(float),(max_from_buildings*(1+c*100)).to_numpy(float)),
         'maximum_at_reference_development':metrics(d.maximum_capacity.to_numpy(float),result.maximum_capacity_at_reference.to_numpy(float))}
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
