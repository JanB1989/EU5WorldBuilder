"""Flat-only attribute fit of the people-denominated capacity targets.

Each location's natural or maximum capacity is approximated by one intercept
(the reference location) plus one flat contribution per displayed attribute
class. There are no percent modifiers and no per-location term. The objective
is a quantile (asymmetric absolute) loss so the attributes form a low envelope
that undershoots most locations; prior spans and ordinal constraints keep the
coefficients readable. Solved as a linear program with HiGHS.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.optimize import linprog
from .attribute_fit import attach_river_levels, region_folds, metrics, sha, ROOT


def load_attributes(cfg):
    targets=pd.read_csv(ROOT/cfg['targets_source'],keep_default_na=False).set_index('location_tag')
    for c in ['natural_capacity','starting_capacity','maximum_capacity']:targets[c]=pd.to_numeric(targets[c],errors='raise')
    d=targets[targets.is_ownable.astype(str).eq('True')].copy().sort_index()
    inv=pd.read_parquet(ROOT/'data/raw/location_inputs/inventory.parquet').set_index('location_tag')
    for f in ['is_coastal','has_river','is_adjacent_to_lake']:d[f]=inv[f].reindex(d.index)
    for folder,f in [('topography','topography'),('vegetation','vegetation'),('climate','climate'),('soils','soil_type'),('fertility','fertility')]:
        a=pd.read_csv(ROOT/f'artifacts/{folder}/locations.csv',keep_default_na=False).set_index('location_tag');d[f]=a[f].reindex(d.index)
    if cfg.get('river_source','worldbuilder')=='worldbuilder':
        r=pd.read_csv(ROOT/'artifacts/river_network/location_levels.csv',keep_default_na=False)
        d=attach_river_levels(d,r.rename(columns={'marker_aware_predicted_level':'river_level'}),replace_presence=True)
    else:
        d=attach_river_levels(d,pd.read_csv(ROOT/'artifacts/rivers/locations.csv',keep_default_na=False))
    for f in cfg['features']:d[f]=d[f].astype(str)
    if d.index.duplicated().any() or d[cfg['features']+['natural_capacity','maximum_capacity']].isna().any().any():raise ValueError('Incomplete fit inventory')
    return d


def design_reference(d,features,reference):
    """Intercept = the reference location; one column per non-reference class."""
    cols=[np.ones(len(d))];names=[('reference','intercept')];groups={}
    for f in features:
        values=sorted(d[f].astype(str).unique());ref=str(reference.get(f,values[0]))
        if ref not in values:raise ValueError(f'Reference class {ref} absent for {f}')
        groups[f]={'reference':ref,'columns':{}}
        for v in values:
            if v==ref:continue
            groups[f]['columns'][v]=len(names);names.append((f,v));cols.append((d[f].astype(str)==v).to_numpy(float))
    return np.column_stack(cols),names,groups


def fit_quantile(X,y,names,groups,cfg,spans,intercept_bounds,maximum,ordinal):
    """Minimise tau*undershoot + (1-tau)*overshoot subject to spans, ordering and a global [0, maximum] range.

    Variables: beta (p), under (n), over (n), then per attribute a lower slack m_a <= min(0, coefficients)
    and an upper slack M_a >= max(0, coefficients) so that intercept + sum(m_a) >= 0 and intercept + sum(M_a) <= maximum
    hold for every attribute combination, observed or not.
    """
    tau=float(cfg['tau']);n,p=X.shape;g=len(groups);nv=p+2*n+2*g
    c=np.zeros(nv);c[p:p+n]=tau;c[p+n:p+2*n]=1-tau
    A_eq=sparse.hstack([sparse.csr_matrix(X),sparse.identity(n),-sparse.identity(n),sparse.csr_matrix((n,2*g))]).tocsr()
    bounds=[(None,None)]*p+[(0,None)]*(2*n)+[(None,0)]*g+[(0,None)]*g
    bounds[0]=intercept_bounds
    for i,(f,v) in enumerate(names):
        if f!='reference':bounds[i]=tuple(spans.get((f,v),spans[f]))
    rows=[];ub=[]
    for k,(f,info) in enumerate(groups.items()):
        m=p+2*n+k;M=m+g
        for v,i in info['columns'].items():
            r=np.zeros(nv);r[m]=1;r[i]=-1;rows.append(r);ub.append(0)      # m_a <= beta_i
            r=np.zeros(nv);r[i]=1;r[M]=-1;rows.append(r);ub.append(0)      # beta_i <= M_a
    r=np.zeros(nv);r[0]=-1;r[[p+2*n+k for k in range(g)]]=-1;rows.append(r);ub.append(0)              # -(intercept + sum m) <= 0
    r=np.zeros(nv);r[0]=1;r[[p+2*n+g+k for k in range(g)]]=1;rows.append(r);ub.append(maximum)       # intercept + sum M <= maximum
    for f,order in ordinal.items():
        if f not in groups:continue
        idx=[]
        for v in order:
            if v==groups[f]['reference']:idx.append(None)
            elif v in groups[f]['columns']:idx.append(groups[f]['columns'][v])
        for a,b in zip(idx,idx[1:]):
            r=np.zeros(nv)
            if a is not None:r[a]=1
            if b is not None:r[b]=-1
            rows.append(r);ub.append(0)                                        # beta_a <= beta_b (reference = 0)
    res=linprog(c,A_ub=sparse.csr_matrix(np.array(rows)),b_ub=np.array(ub),A_eq=A_eq,b_eq=y,bounds=bounds,method='highs')
    if not res.success:raise ValueError('Quantile fit failed: '+res.message)
    beta=res.x[:p]
    info={'status':res.message,'objective':float(res.fun),'overshoot_share':float(np.mean(X@beta>y+1e-6)),
          'possible_minimum':float(beta[0]+sum(min(0,min([beta[i] for i in gi['columns'].values()],default=0)) for gi in groups.values())),
          'possible_maximum':float(beta[0]+sum(max(0,max([beta[i] for i in gi['columns'].values()],default=0)) for gi in groups.values()))}
    return beta,info


def round_values(beta,groups,step):
    """Round every flat value to the nearest step after fitting; keep the global zero floor."""
    if not step:return beta
    b=np.round(np.asarray(beta,float)/step)*step
    floor=b[0]+sum(min(0,min([b[i] for i in gi['columns'].values()],default=0)) for gi in groups.values())
    while floor<0:b[0]+=step;floor+=step
    return b


def sensibility(beta,names,groups,spans,intercept_bounds,cfg,scale):
    checks={'inside_spans':True,'pinned':[],'ordinal':True,'signs':[]}
    step=float(cfg.get('round_to',0) or 0)
    for i,(f,v) in enumerate(names):
        if f=='reference':continue
        lo,hi=spans.get((f,v),spans[f]);tol=max(1e-6*scale,step/2)
        if beta[i]<lo-tol or beta[i]>hi+tol:checks['inside_spans']=False
        if abs(beta[i]-lo)<=tol or abs(beta[i]-hi)<=tol:checks['pinned'].append({'attribute':f,'value':v,'people':float(beta[i])})
    for f,order in cfg.get('ordinal',{}).items():
        if f not in groups:continue
        vals=[0. if v==groups[f]['reference'] else beta[groups[f]['columns'][v]] for v in order if v==groups[f]['reference'] or v in groups[f]['columns']]
        if any(b<a-1e-6*scale for a,b in zip(vals,vals[1:])):checks['ordinal']=False
    def coef(f,v):
        if f not in groups:return None
        if v==groups[f]['reference']:return 0.
        return float(beta[groups[f]['columns'][v]]) if v in groups[f]['columns'] else None
    for sign,items in cfg.get('sign_expectations',{}).items():
        for f,v in items:
            c=coef(f,v)
            if c is None:continue
            ok=(c<=0) if sign=='negative' else (c>=0)
            checks['signs'].append({'attribute':f,'value':v,'expected':sign,'people':c,'passed':bool(ok)})
    checks['signs_passed']=all(s['passed'] for s in checks['signs'])
    checks['pinned_share']=len(checks['pinned'])/max(1,sum(len(g['columns']) for g in groups.values()))
    return checks


def build_flat(config_path=None,output_path=None):
    cp=Path(config_path or ROOT/'configs/attribute_fit_flat.json').resolve();cfg=json.loads(cp.read_text())
    out=Path(output_path or ROOT/'artifacts/attribute_fit_flat').resolve();out.mkdir(parents=True,exist_ok=True)
    d=load_attributes(cfg)
    # The game multiplies every flat value by (1 + c*D). Attributes therefore fit the flat part that
    # reproduces the target at the location's starting development (natural) and at development 100 (maximum).
    c=float(cfg.get('capacity_percent_per_point',0.01))
    dev=pd.read_csv(ROOT/'artifacts/development/locations.csv',keep_default_na=False).set_index('location_tag')
    d['development']=pd.to_numeric(dev.development,errors='raise').reindex(d.index).fillna(0.)
    d['natural_capacity_people']=d.natural_capacity;d['maximum_capacity_people']=d.maximum_capacity
    # Building types carved from the ledger by explicit rules (pastoral land leaves the natural target).
    carve=np.zeros(len(d))
    if cfg.get('building_assignment_config'):
        from .ledger_extensions import extend
        bcfg=json.loads((ROOT/cfg['building_assignment_config']).read_text())
        ledger=pd.read_csv(ROOT/'artifacts/locations/improvement_ledger_equal_area.csv',keep_default_na=False)
        for col in ledger.columns:
            if col.endswith('_capacity'):ledger[col]=pd.to_numeric(ledger[col],errors='raise')
        _,carve=extend(d,ledger,bcfg)
    d['pastoral_carve_people']=carve
    # A flat term per development point (people) sits ON TOP of the physical targets: the attributes fit the land,
    # the term is the game's intensification bonus (at 1,000 per point it exceeds most natural targets, so it cannot
    # be subtracted from them without collapsing the fit).
    from .development_target import capacity_people_per_point
    kdev=capacity_people_per_point();d['development_flat_people']=kdev*d.development
    d['natural_capacity']=np.maximum(d.natural_capacity_people-carve,0)/(1+c*d.development)
    d['maximum_capacity']=np.maximum(d.maximum_capacity_people-carve,0)/(1+c*100)
    scale=float(d.natural_capacity.median())
    X,names,groups=design_reference(d,cfg['features'],cfg['reference_classes'])
    fold,fold_regions=region_folds(d.reset_index().rename(columns={'index':'location_tag'}) if 'region' not in d else d,cfg['folds'],cfg['seed'])
    pred=d[cfg['features']+['region','macro_region','development','natural_capacity','starting_capacity','maximum_capacity','natural_capacity_people','maximum_capacity_people','pastoral_carve_people']].copy();pred['validation_fold']=fold
    results=[];coefficients=[];fits={};sensibility_checks={}
    for target,spec in cfg['targets'].items():
        y=d[target].to_numpy(float);mult=float(spec.get('span_multiplier',1.0))
        spans={f:(lo*scale*mult,hi*scale*mult) for f,(lo,hi) in cfg['prior_spans'].items()}
        # Sign expectations are constraints, not just checks: a class named negative may not add capacity and vice versa.
        for sign,items in cfg.get('sign_expectations',{}).items():
            for f,v in items:
                lo,hi=spans[f];spans[(f,v)]=(lo,0.) if sign=='negative' else (0.,hi)
        ib=(cfg['intercept_span'][0]*scale*mult,cfg['intercept_span'][1]*scale*mult)
        maximum=float(y.max())*1.05
        beta,info=fit_quantile(X,y,names,groups,cfg,spans,ib,maximum,cfg.get('ordinal',{}))
        step=float(cfg.get('round_to',0) or 0)
        beta=round_values(beta,groups,step);info['rounded_to']=step;info['overshoot_share']=float(np.mean(X@beta>y+1e-6))
        fitted=X@beta;oof=np.zeros(len(d))
        for k in range(cfg['folds']):
            train=fold!=k;b,_=fit_quantile(X[train],y[train],names,groups,cfg,spans,ib,maximum,cfg.get('ordinal',{}));oof[~train]=X[~train]@round_values(b,groups,step)
        pred[target+'_fitted']=fitted;pred[target+'_heldout']=oof
        fits[target]=info
        results.append({'target':target,'evaluation':'full_fit',**metrics(y,fitted)})
        results.append({'target':target,'evaluation':'region_heldout',**metrics(y,oof)})
        for i,(f,v) in enumerate(names):
            lo,hi=(ib if f=='reference' else spans.get((f,v),spans[f]))
            coefficients.append({'target':target,'attribute':f,'value':v,'people':float(beta[i]),'share_of_reference':float(beta[i]/scale),'span_min':lo,'span_max':hi,'locations':int(X[:,i].sum()) if i else len(d)})
        sensibility_checks[target]=sensibility(beta,names,groups,spans,ib,cfg,scale)
        sensibility_checks[target]['heldout_gap_ok']=bool(abs(results[-2]['r2']-results[-1]['r2'])<=0.05)
        sensibility_checks[target]['overshoot_share']=info['overshoot_share'];sensibility_checks[target]['overshoot_within_tau']=bool(abs(info['overshoot_share']-cfg['tau'])<=0.08)
    table=pd.DataFrame(results);table.to_csv(out/'metrics.csv',index=False)
    pd.DataFrame(coefficients).to_csv(out/'coefficients.csv',index=False)
    # In people at development 100: attribute flat maximum times the full development multiplier.
    # In people: attribute flat times the development multiplier, plus the carved pastoral share (a flat building later).
    pred['attribute_maximum_people']=pred.maximum_capacity_fitted*(1+c*100)+pred.pastoral_carve_people+kdev*100
    pred['attribute_natural_people']=pred.natural_capacity_fitted*(1+c*pred.development)+pred.pastoral_carve_people+kdev*pred.development
    pred['start_exceeds_attribute_maximum']=pred.starting_capacity>pred.attribute_maximum_people
    pred.to_csv(out/'location_predictions.csv',index=True,index_label='location_tag')
    review=pred[pred.start_exceeds_attribute_maximum].copy();review['excess']=review.starting_capacity-review.attribute_maximum_people
    review.sort_values('excess',ascending=False).to_csv(out/'start_exceeds_attribute_maximum.csv',index_label='location_tag')
    audit={}
    for target in cfg['targets']:
        err=pred[target+'_fitted']-pred[target]
        by=pred.assign(over=err>0,under=err<0).groupby('macro_region').agg(locations=('over','size'),overshoot_share=('over','mean'),undershoot_share=('under','mean'))
        audit[target]=by.round(3).to_dict(orient='index')
    audit['start_exceeds_attribute_maximum']={'locations':int(pred.start_exceeds_attribute_maximum.sum()),'excess_people':float(review.excess.sum()) if len(review) else 0.}
    report={'locations':len(d),'reference_scale_people':scale,'region_folds':fold_regions,'config':cfg,'fits':fits,'sensibility':sensibility_checks,'metrics':results,'audit':audit,
        'inputs':{str(p.relative_to(ROOT)):sha(p) for p in [cp,Path(__file__),ROOT/cfg['targets_source'],ROOT/'data/raw/location_inputs/inventory.parquet']+[ROOT/f'artifacts/{f}/locations.csv' for f in ['topography','vegetation','climate','soils','fertility']]},
        'capacity_percent_per_point':c,'capacity_people_per_point':kdev,'units':'Targets are flat (pre-development) people: natural/(1+c*D_start) and maximum/(1+c*100). Columns *_people hold the original targets.',
        'scope':'Flat-only attribute values in people on the people-denominated targets; no population, no percent modifiers, no per-location term.'}
    from .provenance import write_json
    write_json(out/'report.json',report);write_json(out/'overshoot_undershoot_audit.json',audit)
    render_report(out,report,table,pd.DataFrame(coefficients))
    try:
        render_maps(pred,out,cfg)
    except Exception as e:  # maps are a convenience; the fit files are the deliverable
        (out/'map_error.txt').write_text(str(e))
    return report


def render_report(out,report,table,coefficients):
    cfg=report['config'];lines=['# Flat attribute fit (quantile envelope)','',
        f"{report['locations']:,} ownable locations. Reference location: {', '.join(f'{k}={v}' for k,v in cfg['reference_classes'].items())}; reference scale {report['reference_scale_people']:,.0f} people (median ownable natural capacity). tau = {cfg['tau']} (share of locations allowed above the attribute value).",'',
        '| Target | Evaluation | R² | Median error | Within 25% | Mean bias |','|---|---|---:|---:|---:|---:|']
    for r in table.itertuples():
        lines.append(f'| {r.target} | {r.evaluation} | {r.r2:.3f} | {r.median_absolute_percentage_error:.1f}% | {100*np.mean(np.abs(0)):.0f}%'.replace(' | 0%','')+f' | {r.mean_bias:,.0f} |')
    lines+=['','## Sensibility','']
    for target,s in report['sensibility'].items():
        lines.append(f"- **{target}**: inside spans {s['inside_spans']}; pinned classes {len(s['pinned'])} ({100*s['pinned_share']:.0f}%); ordinal {s['ordinal']}; signs {s['signs_passed']}; overshoot share {s['overshoot_share']:.2f} (tau {cfg['tau']}, ok {s['overshoot_within_tau']}); held-out gap ok {s['heldout_gap_ok']}.")
        for sign in s['signs']:
            if not sign['passed']:lines.append(f"  - sign violation: {sign['attribute']}={sign['value']} expected {sign['expected']}, got {sign['people']:,.0f} people")
        for pin in s['pinned']:lines.append(f"  - pinned: {pin['attribute']}={pin['value']} at {pin['people']:,.0f} people")
    lines+=['',f"Locations whose start exceeds the attribute maximum (hand-review list): {report['audit']['start_exceeds_attribute_maximum']['locations']:,}, excess {report['audit']['start_exceeds_attribute_maximum']['excess_people']/1e6:,.1f}M people → `start_exceeds_attribute_maximum.csv`.",'']
    for target in cfg['targets']:
        lines+=[f'## Coefficients: {target} (people)','','| Attribute | Class | People | Share of reference | Span |','|---|---|---:|---:|---|']
        c=coefficients[coefficients.target==target]
        for r in c.itertuples():lines.append(f'| {r.attribute} | {r.value} | {r.people:,.0f} | {r.share_of_reference:+.2f} | [{r.span_min:,.0f}, {r.span_max:,.0f}] |')
        lines.append('')
    lines+=['Files: `coefficients.csv`, `location_predictions.csv`, `metrics.csv`, `overshoot_undershoot_audit.json`, `report.json`, residual maps `natural_capacity_residual.png` / `maximum_capacity_residual.png`.']
    (out/'report.md').write_text('\n'.join(lines)+'\n')


def render_maps(pred,out,cfg):
    from PIL import Image
    source=ROOT/'artifacts/locations'
    raw=(source/'data.js').read_text();locations,_=json.JSONDecoder().raw_decode(raw[len('window.LOCATIONS='):]);del raw
    image=np.asarray(Image.open(source/'location_ids.png').convert('RGB'),dtype=np.uint32);ids=(image[...,0]<<16)|(image[...,1]<<8)|image[...,2]
    anchors=np.array([[42,111,187],[231,234,231],[191,53,58]],dtype=float)
    for target in cfg['targets']:
        palette=np.full((len(locations)+1,3),[66,75,84],dtype=np.uint8);palette[0]=[13,24,36]
        for i,row in enumerate(locations,1):
            tag=row['location_tag']
            if tag not in pred.index:continue
            t=float(pred.loc[tag,target]);f=float(pred.loc[tag,target+'_fitted'])
            if t<=0:continue
            v=np.clip((f/t-1),-1,1);palette[i]=anchors[1]*(1-abs(v))+anchors[0 if v<0 else 2]*abs(v)
        Image.fromarray(palette[ids]).save(out/f'{target}_residual.png')
