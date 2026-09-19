"""Bounded additive feasibility experiment; never modifies capacity targets."""
import hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import sparse
import osqp
from .soil_types import sha
ROOT=Path(__file__).resolve().parents[2]


def design(d,features):
    columns=[np.ones(len(d))];names=[('reference','intercept')];groups={}
    for feature in features:
        groups[feature]=[]
        for value in sorted(d[feature].astype(str).unique()):
            groups[feature].append(len(names));names.append((feature,value));columns.append((d[feature].astype(str)==value).to_numpy(float))
    return np.column_stack(columns),names,groups


def fit(X,y,names,groups,spec,cfg,objective='relative',caps=1):
    p=X.shape[1];g=len(groups);nvar=p+2*g;scale=spec['scale'];ys=y/scale
    w=np.ones(len(y)) if objective=='absolute' else (scale/np.maximum(y,spec['relative_floor']))**2
    w/=w.mean()
    P=np.zeros((nvar,nvar));P[:p,:p]=(X.T@(X*w[:,None]))/len(y)
    P[np.arange(1,p),np.arange(1,p)]+=cfg['ridge']
    q=np.zeros(nvar);q[:p]=-(X.T@(ys*w))/len(y)
    rows=[];lo=[];hi=[]
    def constraint(items,l=-np.inf,u=np.inf):
        row=np.zeros(nvar)
        for i,v in items:row[i]+=v
        rows.append(row);lo.append(l);hi.append(u)
    constraint([(0,1)],spec['minimum']/scale,spec['maximum']/scale)
    cap=spec['coefficient_cap']*caps/scale
    for i in range(1,nvar):constraint([(i,1)],-cap,cap)
    for k,(feature,ids) in enumerate(groups.items()):
        mn=p+2*k;mx=mn+1
        # A unique centring convention prevents arbitrarily moving an effect
        # between the global intercept and individual categorical attributes.
        freq=X[:,ids].mean(axis=0);constraint(list(zip(ids,freq)),0,0)
        for i in ids:
            constraint([(i,1),(mn,-1)],0,np.inf)
            constraint([(mx,1),(i,-1)],0,np.inf)
    constraint([(0,1)]+[(p+2*k,1) for k in range(g)],spec['minimum']/scale,np.inf)
    constraint([(0,1)]+[(p+2*k+1,1) for k in range(g)],-np.inf,spec['maximum']/scale)
    if spec['label']=='Multiplier' and 'fertility' in groups:
        lookup={v:i for i,(f,v) in enumerate(names) if f=='fertility'}
        order=[lookup[n] for n in cfg['fertility_order'] if n in lookup]
        for a,b in zip(order,order[1:]):constraint([(b,1),(a,-1)],0,np.inf)
    no_overshoot=cfg.get('no_overshoot',False)
    if no_overshoot:
        if np.any(y < spec['minimum']):
            raise ValueError('No-overshoot targets fall below the global prediction minimum')
        # Identical attribute profiles have identical predictions. Their smallest
        # target is the binding ceiling; grouping is exactly equivalent to one
        # upper-bound constraint per training location, without duplicate rows.
        profiles,inverse=np.unique(X,axis=0,return_inverse=True)
        ceilings=np.full(len(profiles),np.inf)
        np.minimum.at(ceilings,inverse,ys)
        for profile,ceiling in zip(profiles,ceilings):
            constraint(list(zip(np.flatnonzero(profile),profile[profile!=0])),u=ceiling)
    solver=osqp.OSQP();solver.setup(P=sparse.csc_matrix(np.triu(P)),q=q,A=sparse.csc_matrix(np.array(rows)),l=np.array(lo),u=np.array(hi),verbose=False,eps_abs=1e-9 if no_overshoot else 1e-7,eps_rel=1e-9 if no_overshoot else 1e-7,max_iter=100000,polishing=True)
    result=solver.solve(raise_error=False)
    solver_status=result.info.status;iterations=int(result.info.iter)
    solution=result.x
    if no_overshoot and result.info.status_val == 7:
        # Degenerate active ceilings can make ADMM stall. Refine the same
        # convex quadratic program with an independent active-set optimizer.
        from scipy.optimize import minimize
        A=np.asarray(rows);lower=np.asarray(lo);upper=np.asarray(hi)
        equal=np.isfinite(lower)&(lower==upper)
        lower_mask=np.isfinite(lower)&~equal;upper_mask=np.isfinite(upper)&~equal
        eq_A=A[equal];eq_b=lower[equal]
        ineq_A=np.concatenate([A[lower_mask],-A[upper_mask]])
        ineq_b=np.concatenate([lower[lower_mask],-upper[upper_mask]])
        constraints=[{'type':'eq','fun':lambda v:eq_A@v-eq_b,'jac':lambda v:eq_A},
                     {'type':'ineq','fun':lambda v:ineq_A@v-ineq_b,'jac':lambda v:ineq_A}]
        refined=minimize(lambda v:.5*v@P@v+q@v,solution,
                         jac=lambda v:P@v+q,method='SLSQP',constraints=constraints,
                         options={'ftol':1e-12,'maxiter':1000})
        if not refined.success:
            raise ValueError('No-overshoot refinement failed: '+refined.message)
        solution=refined.x;solver_status='solved (SLSQP refinement)';iterations+=int(refined.nit)
        residual=A@solution
        if np.any(residual<lower-1e-7) or np.any(residual>upper+1e-7):
            raise ValueError('Refined fit violates linear constraints')
    elif result.info.status_val not in [1,2]:
        raise ValueError('Fit failed: '+result.info.status)
    beta=solution[:p]*scale
    minimum=beta[0]+sum(min(beta[ids]) for ids in groups.values());maximum=beta[0]+sum(max(beta[ids]) for ids in groups.values())
    tol=scale*1e-5
    if minimum<spec['minimum']-tol or maximum>spec['maximum']+tol:raise ValueError('Fit violates global bounds')
    overshoot=float(np.max(X@beta-y))
    if no_overshoot and overshoot > scale*1e-7:
        raise ValueError(f'Fit violates no-overshoot constraints: {overshoot}')
    return beta,{'no_overshoot':no_overshoot,'maximum_training_overshoot':max(0.,overshoot),'no_overshoot_tolerance':scale*1e-7,'status':solver_status,'iterations':iterations,'possible_minimum':float(minimum),'possible_maximum':float(maximum),'coefficient_limit':spec['coefficient_cap']*caps}


def metrics(y,p):
    error=p-y;rel=np.abs(error)/np.maximum(y,1e-12);den=np.sum((y-y.mean())**2)
    return {'r2':float(1-np.sum(error**2)/den) if den>0 else None,'mae':float(np.abs(error).mean()),'rmse':float(np.sqrt(np.mean(error**2))),'median_absolute_percentage_error':float(np.median(rel)*100),'p90_absolute_percentage_error':float(np.quantile(rel,.9)*100),'within_20_percent':float(np.mean(rel<=.2)*100),'within_50_percent':float(np.mean(rel<=.5)*100),'within_factor_two':float(np.mean((p/y>=.5)&(p/y<=2))*100),'mean_bias':float(error.mean())}


def region_folds(d,k,seed):
    rng=np.random.default_rng(seed);groups=d.region.value_counts();order=groups.index.to_numpy().copy();rng.shuffle(order)
    # Random tie order, then balance held-out location totals across whole regions.
    order=sorted(order,key=lambda n:-groups[n]);loads=np.zeros(k);mapping={}
    for region in order:
        f=int(np.argmin(loads));mapping[region]=f;loads[f]+=groups[region]
    return d.region.map(mapping).to_numpy(int),mapping


def attach_river_levels(d,rivers,replace_presence=False):
    """Require complete, matching native categories; never fill absence of data."""
    if rivers.location_tag.duplicated().any():raise ValueError('Duplicate native river locations')
    r=rivers.set_index('location_tag').reindex(d.index)
    if r.river_level.isna().any() or not r.river_level.isin(range(6)).all():raise ValueError('Incomplete or invalid native river levels')
    if not replace_presence and not np.array_equal(r.river_level.gt(0),d.has_river):raise ValueError('Native river presence differs from paired control')
    result=d.copy();result['river_level']=r.river_level.astype(int)
    if replace_presence:result['has_river']=r.river_level.gt(0)
    return result


def load_data(river_source="vanilla"):
    path=ROOT/'artifacts/locations/locations_equal_area.csv'
    fields=['location_tag','region','macro_region','is_ownable','base_effective_cropland','capacity_multiplier','starting_improvement_effective_cropland','maximum_improvement_effective_cropland','rural_balance_added_units']
    d=pd.read_csv(path,usecols=fields,keep_default_na=False);d=d[d.is_ownable].set_index('location_tag').sort_index()
    inv=pd.read_parquet(ROOT/'data/raw/location_inputs/inventory.parquet').set_index('location_tag')
    for f in ['topography','climate','vegetation','is_coastal','has_river','is_adjacent_to_lake']:d[f]=inv[f].reindex(d.index)
    native=d.copy()
    for folder,f in [('topography','topography'),('vegetation','vegetation'),('climate','climate'),('soils','soil_type'),('fertility','fertility')]:
        a=pd.read_csv(ROOT/f'artifacts/{folder}/locations.csv',keep_default_na=False).set_index('location_tag');d[f]=a[f].reindex(d.index)
    if river_source == 'worldbuilder':
        manifest=json.loads((ROOT/'artifacts/river_network/export_manifest.json').read_text())
        if not manifest['engineering_checks'].get('native_tributary_encoding'):
            raise ValueError('River map lacks native encoding validation')
        if sha(ROOT/manifest['output_png']) != manifest['output_sha256']:
            raise ValueError('River PNG does not match its export manifest')
        r=pd.read_csv(ROOT/'artifacts/river_network/location_levels.csv',keep_default_na=False)
        d=attach_river_levels(d,r.rename(columns={'marker_aware_predicted_level':'river_level'}),replace_presence=True)
    elif river_source == 'vanilla':
        d=attach_river_levels(d,pd.read_csv(ROOT/'artifacts/rivers/locations.csv',keep_default_na=False))
    else:raise ValueError('Unknown river source: '+river_source)
    if len(d)!=20893 or not d.index.is_unique or d.isna().any().any():raise ValueError('Incomplete fit inventory')
    return d,native


def build(config_path=None,output_path=None):
    cp=Path(config_path or ROOT/'configs/attribute_fit.json').resolve();cfg=json.loads(cp.read_text());d,native=load_data(cfg.get('river_source','vanilla'))
    out=Path(output_path or ROOT/('artifacts/attribute_fit_no_overshoot' if cfg.get('no_overshoot') else 'artifacts/attribute_fit')).resolve();out.mkdir(parents=True,exist_ok=True)
    fold,fold_regions=region_folds(d,cfg['folds'],cfg['seed']);pred=d.copy();pred['validation_fold']=fold
    results=[];coefficients=[];fits={};diagnostics={};specs=cfg['targets']
    presence_features=['has_river' if f=='river_level' else f for f in cfg['features']]
    for version,data,features in [('native',native,cfg['native_features']),('presence',d,presence_features),('current',d,cfg['features'])]:
        X,names,groups=design(data,features)
        for target,spec in specs.items():
            y=d[target].to_numpy(float)
            for objective in ['absolute','relative']:
                beta,info=fit(X,y,names,groups,spec,cfg,objective)
                fitted=X@beta;oof=np.zeros(len(d));null=np.zeros(len(d))
                for k in range(cfg['folds']):
                    train=fold!=k;test=~train
                    b,_=fit(X[train],y[train],names,groups,spec,cfg,objective)
                    oof[test]=X[test]@b;null[test]=y[train].mean()
                key=f'{version}_{target}_{objective}';pred[key+'_fitted']=fitted;pred[key+'_heldout']=oof
                fits[key]=info
                results.append({'features':version,'target':target,'objective':objective,'evaluation':'full_fit',**metrics(y,fitted)})
                results.append({'features':version,'target':target,'objective':objective,'evaluation':'region_heldout',**metrics(y,oof)})
                for i,(feature,value) in enumerate(names):coefficients.append({'features':version,'target':target,'objective':objective,'attribute':feature,'value':value,'contribution':beta[i],'locations':len(d) if i==0 else int(X[:,i].sum())})
                if objective=='absolute':results.append({'features':version,'target':target,'objective':'mean_reference','evaluation':'region_heldout',**metrics(y,null)})
            # Optimistic full-data ceilings separate additive restrictions from
            # information absent even when arbitrary attribute interactions are allowed.
            ordinary=X@np.linalg.lstsq(X,y,rcond=None)[0]
            frame=data[features].copy();frame['target']=y;oracle=frame.groupby(features,dropna=False)['target'].transform('mean').to_numpy()
            diagnostics[f'{version}_{target}']={'unconstrained_additive_full_fit':metrics(y,ordinary),'identical_profile_oracle_full_fit':metrics(y,oracle),'unique_profiles':len(frame[features].drop_duplicates()),'note':'Optimistic in-sample diagnostics, not validated predictions. Profile means may memorize singletons.'}
            if version=='current':
                loose,_=fit(X,y,names,groups,spec,cfg,'relative',caps=2)
                diagnostics[f'{version}_{target}']['double_coefficient_cap_full_fit']=metrics(y,X@loose)
                if target=='base_effective_cropland':
                    before=y-d.rural_balance_added_units.to_numpy(float)
                    b,_=fit(X,before,names,groups,spec,cfg,'relative')
                    diagnostics[f'{version}_{target}']['before_rural_allowance_full_fit']=metrics(before,X@b)
    profiles=d.groupby(cfg['features']).agg(locations=('capacity_multiplier','size'),minimum_multiplier=('capacity_multiplier','min'),maximum_multiplier=('capacity_multiplier','max'),minimum_base=('base_effective_cropland','min'),maximum_base=('base_effective_cropland','max')).reset_index()
    profiles['multiplier_ratio']=profiles.maximum_multiplier/profiles.minimum_multiplier
    profiles['base_ratio']=profiles.maximum_base/profiles.minimum_base
    profiles.sort_values(['multiplier_ratio','locations'],ascending=False).to_csv(out/'identical_profile_conflicts.csv',index=False)
    diagnostics['profile_conflicts']={'locations_with_multiplier_ratio_over_two':int(profiles.loc[profiles.multiplier_ratio>2,'locations'].sum()),'locations_with_base_ratio_over_two':int(profiles.loc[profiles.base_ratio>2,'locations'].sum()),'singleton_profiles':int((profiles.locations==1).sum())}
    table=pd.DataFrame(results);table.to_csv(out/'metrics.csv',index=False)
    pd.DataFrame(coefficients).to_csv(out/'coefficients.csv',index=False)
    # What happens to capacity if just B and M are replaced? Improvements are
    # held at their existing values; this is NOT a fitted building model.
    for objective in ['absolute','relative']:
        B=pred[f'current_base_effective_cropland_{objective}_heldout'].to_numpy();M=pred[f'current_capacity_multiplier_{objective}_heldout'].to_numpy()
        for label,col in [('inert',None),('starting','starting_improvement_effective_cropland'),('maximum','maximum_improvement_effective_cropland')]:
            I=0 if col is None else d[col].to_numpy()
            truth=d.capacity_multiplier.to_numpy()*(d.base_effective_cropland.to_numpy()+I);p=M*(B+I)
            pred[label+'_target']=truth;pred[label+'_'+objective+'_heldout']=p
            diagnostics[label+'_'+objective+'_heldout_with_actual_improvements']=metrics(truth,p)
    # The B/M decomposition is a normalization choice. Measure the directly
    # meaningful inert contribution as a separate diagnostic, not a replacement.
    X,names,groups=design(d,cfg['features'])
    inert=(d.base_effective_cropland*d.capacity_multiplier).to_numpy()
    inert_spec={'label':'Inert capacity','scale':50000,'minimum':250,'maximum':2000000,'coefficient_cap':100000,'relative_floor':10000}
    direct,info=fit(X,inert,names,groups,inert_spec,cfg,'absolute')
    direct_oof=np.zeros(len(d))
    for k in range(cfg['folds']):
        train=fold!=k;b,_=fit(X[train],inert[train],names,groups,inert_spec,cfg,'absolute')
        direct_oof[~train]=X[~train]@b
    pred['direct_inert_fitted']=X@direct;pred['direct_inert_heldout']=direct_oof
    diagnostics['direct_inert_additive']={'bounds':inert_spec,'full_fit':metrics(inert,X@direct),'region_heldout':metrics(inert,direct_oof)}
    product=pred.current_base_effective_cropland_absolute_fitted*pred.current_capacity_multiplier_absolute_fitted
    diagnostics['separately_fitted_inert_full_fit']=metrics(inert,product.to_numpy())
    regional=[]
    for region,g in pred.groupby('region'):
        for target in specs:
            regional.append({'region':region,'locations':len(g),'target':target,**metrics(g[target].to_numpy(),g[f'current_{target}_{cfg["primary_objective"]}_heldout'].to_numpy())})
    pd.DataFrame(regional).to_csv(out/'regional_errors.csv',index=False)
    primary=cfg['primary_objective']
    error=np.maximum(np.abs(pred[f'current_base_effective_cropland_{primary}_fitted']/pred.base_effective_cropland-1),np.abs(pred[f'current_capacity_multiplier_{primary}_fitted']/pred.capacity_multiplier-1))
    pred['largest_relative_error']=error
    pred.to_csv(out/'location_predictions.csv',index=True,index_label='location_tag')
    pred.sort_values('largest_relative_error',ascending=False).head(100).to_csv(out/'worst_locations.csv',index_label='location_tag')
    # Paired population-capacity comparison: retain the same actual improvement
    # quantities in both variants. This isolates changing the B/M predictors.
    comparison=[]
    for evaluation,suffix in [('full_fit','fitted'),('region_heldout','heldout')]:
        for target in specs:
            old=table[(table.features=='presence')&(table.target==target)&(table.objective==primary)&(table.evaluation==evaluation)].iloc[0]
            new=table[(table.features=='current')&(table.target==target)&(table.objective==primary)&(table.evaluation==evaluation)].iloc[0]
            comparison.append({'target':target,'evaluation':evaluation,'presence_r2':old.r2,'river_level_r2':new.r2,'r2_gain_percentage_points':100*(new.r2-old.r2),'presence_rmse':old.rmse,'river_level_rmse':new.rmse,'rmse_reduction_percent':100*(1-new.rmse/old.rmse),'presence_median_error':old.median_absolute_percentage_error,'river_level_median_error':new.median_absolute_percentage_error})
        for label,col in [('inert',None),('starting','starting_improvement_effective_cropland'),('maximum','maximum_improvement_effective_cropland')]:
            I=0 if col is None else d[col].to_numpy()
            truth=d.capacity_multiplier.to_numpy()*(d.base_effective_cropland.to_numpy()+I)
            paired={}
            for version in ['presence','current']:
                B=pred[f'{version}_base_effective_cropland_{primary}_{suffix}'].to_numpy()
                M=pred[f'{version}_capacity_multiplier_{primary}_{suffix}'].to_numpy()
                paired[version]=metrics(truth,M*(B+I))
            diagnostics[f'river_comparison_{label}_{evaluation}']=paired
            old,new=paired['presence'],paired['current']
            comparison.append({'target':label+'_capacity','evaluation':evaluation,'presence_r2':old['r2'],'river_level_r2':new['r2'],'r2_gain_percentage_points':100*(new['r2']-old['r2']),'presence_rmse':old['rmse'],'river_level_rmse':new['rmse'],'rmse_reduction_percent':100*(1-new['rmse']/old['rmse']),'presence_median_error':old['median_absolute_percentage_error'],'river_level_median_error':new['median_absolute_percentage_error']})
    pd.DataFrame(comparison).to_csv(out/'river_comparison.csv',index=False)
    paths=[cp,Path(__file__),ROOT/'artifacts/locations/location_values_equal_area.csv',ROOT/'artifacts/locations/locations_equal_area.csv',ROOT/'data/raw/location_inputs/inventory.parquet',ROOT/'artifacts/rivers/locations.csv',ROOT/'artifacts/rivers/report.json']+[ROOT/f'artifacts/{f}/locations.csv' for f in ['topography','vegetation','climate','soils','fertility']]
    if cfg.get('river_source','vanilla') == 'worldbuilder':
        manifest_path=ROOT/'artifacts/river_network/export_manifest.json'
        river_source=json.loads(manifest_path.read_text())
        paths += [ROOT/'artifacts/river_network/location_levels.csv',manifest_path,ROOT/river_source['output_png']]
        limitation='World Builder ownable-only bitmap levels 0–5, including junction-marker promotion to level 5. These are bitmap predictions, not a fresh engine export or measured discharge. The presence-only control uses the same new river map.'
    else:
        river_source=json.loads((ROOT/'artifacts/rivers/report.json').read_text())['source']
        limitation='Vanilla engine-exported categories; junction markers can promote level 5. Levels absent from the source get no estimated coefficients.'
    report={'locations':len(d),'region_folds':fold_regions,'config':cfg,'fits':fits,'diagnostics':diagnostics,'inputs':{str(p.relative_to(ROOT)):sha(p) for p in paths},'metrics':results,'river_comparison':comparison,'river_source':river_source,'river_level_counts':{str(k):int(v) for k,v in d.river_level.value_counts().sort_index().items()},'river_limitation':limitation,'scope':'Current equal-area game targets; no population or improvements used as predictors. No target or deployed game values modified.'}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    render(pred,table,report,out)
    from .attribute_fit_map import render_map
    render_map(pred,out,ROOT,cfg["primary_objective"],no_overshoot=cfg.get("no_overshoot",False))
    return report


def render(pred,table,report,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axs=plt.subplots(1,2,figsize=(12,5))
    for ax,(target,spec) in zip(axs,report['config']['targets'].items()):
        x=pred[target];y=pred[f'current_{target}_{report["config"]["primary_objective"]}_heldout']
        ax.hexbin(x,y,gridsize=45,mincnt=1,cmap='viridis',xscale='log' if target.startswith('base') else 'linear',yscale='log' if target.startswith('base') else 'linear')
        lo=min(x.min(),y.min());hi=max(x.max(),y.max());ax.plot([lo,hi],[lo,hi],color='#c85242',lw=1)
        ax.set_xlabel('Current model target');ax.set_ylabel('Additive prediction');ax.set_title(spec['label']+' — held-out regions')
    fig.suptitle('Fixed attribute bonuses: absolute-error fit');fig.tight_layout();fig.savefig(out/'fit.png',dpi=150);plt.close(fig)
    lines=['# River levels: paired additive refit', '',
        'All 20,893 ownable locations. The control retains river presence; the new model replaces it with categorical river level from the same source. All other attributes, targets, bounds, losses and region folds are identical.', '',
        'This tests representation of the current equal-area game model, not historical accuracy. Targets and deployed game values are unchanged.', '',
        '## Absolute-error fit comparison', '',
        '| Evaluation | Target | Presence R² | River-level R² | R² gain (percentage points) | RMSE reduction | Median error: presence → levels |',
        '|---|---|---:|---:|---:|---:|---:|']
    for row in report['river_comparison']:
        lines.append(f"| {row['evaluation']} | {row['target']} | {row['presence_r2']:.4f} | {row['river_level_r2']:.4f} | {row['r2_gain_percentage_points']:+.3f} | {row['rmse_reduction_percent']:+.2f}% | {row['presence_median_error']:.2f}% → {row['river_level_median_error']:.2f}% |")
    lines += ['', 'Full-map fit describes how closely fixed bonuses can reproduce the known map. Region-held-out validation uses the same five folds with entire regions excluded from training; it measures geographical generalization.', '',
        'Inert capacity is fitted base × fitted multiplier. Starting/maximum capacity retains the same actual improvement quantities in both variants: fitted multiplier × (fitted base + actual improvements). Improvement quantities are not fitted or used as predictors.', '',
        '## River data', '', report['river_limitation'], '',
        'Ownable location counts: '+', '.join(f"level {k}: {v:,}" for k,v in report['river_level_counts'].items())+'.', '',
        'Each observed level gets an independent categorical effect. River level is not multiplied by one coefficient, and no monotone river ordering is imposed. Presence and size use the same selected river map. The controlled palette and showcase maps are excluded.', '',
        '## Constraints', '',
        'Base land 1,000–400,000; multiplier 0.25–5. Each categorical contribution is bounded by ±50,000 base units or ±1.5 multiplier. Effects are centred by training frequencies. Multiplier fertility effects remain nondecreasing; prediction bounds hold for all combinations.', '',
        'Absolute loss minimizes squared errors in target units. Relative loss retains the existing floors of 10,000 base units and 0.5 multiplier. Both are additive fits in original units.', '',
        '## All target fits', '',
        '| Features | Target | Objective | Evaluation | R² | Median error | Within 20% |',
        '|---|---|---|---|---:|---:|---:|']
    for row in table[~table.objective.eq('mean_reference')].itertuples():
        lines.append(f'| {row.features} | {row.target} | {row.objective} | {row.evaluation} | {row.r2:.4f} | {row.median_absolute_percentage_error:.2f}% | {row.within_20_percent:.2f}% |')
    lines += ['', '`native` uses the original game attributes with presence; `presence` uses the expanded attributes with presence; `current` uses the expanded attributes with the selected river levels.', '',
        '## Outputs', '',
        'Paired results: `river_comparison.csv`. All fitted effects: `coefficients.csv`. Predictions: `location_predictions.csv`. Regional errors: `regional_errors.csv`. Source/config/code hashes, solver checks and exploratory ceilings: `report.json`. Updated interactive residual map: `index.html`.', '',
        'Unconstrained fits and identical-profile means are optimistic in-sample diagnostics, not validation results. Only categories present in the selected source receive coefficients.', '', '![Held-out fit](fit.png)']
    if report['config'].get('no_overshoot'):
        lines[0]='# No-overshoot additive refit'
        lines[2]='All 20,893 ownable locations, using the same World Builder rivers and targets as the previous fit.'
        lines[6:6]=['Each fitted component is constrained to be at or below every training location target. These are coefficient constraints, not per-location prediction clipping. The full-map fit is therefore a lower envelope. Held-out targets are never used as constraints, so validation predictions can still overshoot. Solver tolerance: 0.005 base units and 0.0000001 multiplier.', '', 'The separate previous fit remains in ../attribute_fit/. River presence versus size below compares two constrained fits, not the previous unconstrained-in-residual fit.', '']
    (out/'report.md').write_text('\n'.join(lines)+'\n')
