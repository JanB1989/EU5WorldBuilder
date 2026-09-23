"""Goods output modifiers from location attributes.

The game decides each location's RGO. This module only fits how well a good does where it is the
RGO, as additive rows on the displayed attributes (climate, topography, vegetation, soil, fertility,
river level, coast, lake), so the constructor can write one static modifier per attribute class with
its goods rows and no per-location value exists.

Per good:
- target: the StaticModifiersV2 labor-output efficiency score, rank-uniform over viable locations
  (score > 0), mapped to [output_min, output_max] (the mod's existing scaling);
- fit: least squares on locations where the good is the game's RGO, region-held-out for evaluation;
- relevance: a (good, attribute class) row exists only where the good is the RGO in at least
  ``min_rgo_locations_per_class`` locations of that class; rows below ``prune_below`` are dropped
  and the intercept absorbs them;
- floor: RGO locations predicted below ``rgo_floor`` (and RGO locations the data calls non-viable)
  are listed for the constructor's existing floor carve-out, which stays.

Inputs are copied from the sibling StaticModifiersV2 repository into data/raw/goods_efficiency with
a manifest (sha256 + algorithm version) so the fit is reproducible from this repository alone.
"""
import json,hashlib,shutil
from pathlib import Path
import numpy as np
import pandas as pd
from .attribute_fit_flat import load_attributes, design_reference
from .attribute_fit import region_folds
from .provenance import write_json

ROOT=Path(__file__).resolve().parents[2]


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def import_tables(cfg):
    """Copy per-good location tables from the V2 repository when present; return the local manifest."""
    local=ROOT/cfg['tables_directory'];local.mkdir(parents=True,exist_ok=True)
    manifest_path=local/'manifest.json'
    manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {'goods':{}}
    src=Path(cfg.get('import_root','')).expanduser()
    if not src.is_absolute():src=(ROOT/src).resolve()
    if src.exists():
        for good_dir in sorted(p for p in src.iterdir() if (p/'location_efficiency.csv').exists()):
            good=good_dir.name;table=good_dir/'location_efficiency.csv';target=local/f'{good}.csv'
            if not target.exists() or sha(table)!=sha(target):shutil.copyfile(table,target)
            m=good_dir/'efficiency_manifest.json';algo=json.loads(m.read_text()).get('algorithm_version') if m.exists() else None
            manifest['goods'][good]={'sha256':sha(target),'algorithm_version':algo,'imported_from':str(table)}
        manifest['note']='StaticModifiersV2 location_efficiency.csv per good (score_0_1, viable_fraction). Copied verbatim; the fit reads these local copies only.'
        write_json(manifest_path,manifest)
    return manifest


def load_rgo(cfg,index):
    t=pd.read_csv(ROOT/cfg['rgo_source'],keep_default_na=False).set_index('location_tag').raw_material
    return t.reindex(index).fillna('')


def target_scale(score,lo,hi):
    """Rank-uniform over viable locations (score > 0), mapped to [lo, hi]; NaN where not viable."""
    s=np.asarray(score,float);viable=s>0;y=np.full(len(s),np.nan)
    if viable.sum()==0:return y,viable
    rank=pd.Series(s[viable]).rank(method='average').to_numpy();u=(rank-1)/max(1,viable.sum()-1)
    y[viable]=lo+u*(hi-lo);return y,viable


def lstsq(X,y,w=None):
    if w is None:return np.linalg.lstsq(X,y,rcond=None)[0]
    sw=np.sqrt(np.asarray(w,float))[:,None];return np.linalg.lstsq(X*sw,y*sw[:,0],rcond=None)[0]


def r2(y,p):
    ss=float(((y-y.mean())**2).sum());return float(1-((y-p)**2).sum()/ss) if ss>0 else float('nan')


def fit_good(X,names,member,y,fit_mask,rgo_mask,folds,cfg):
    """Weighted least squares on fit_mask rows (RGO locations weighted rgo_weight, others 1) with relevance and
    magnitude pruning; returns beta, kept mask, held-out predictions. Relevance: a class row needs the good as RGO in
    at least max(min_rgo_locations_per_class, min_rgo_share_per_class x RGO count) locations of that class."""
    n_rgo=int(rgo_mask.sum());min_rgo=max(int(cfg['min_rgo_locations_per_class']),int(np.ceil(float(cfg.get('min_rgo_share_per_class',0.))*n_rgo)));thr=float(cfg['prune_below'])
    w=np.where(rgo_mask,float(cfg.get('rgo_weight',1.)),1.)
    keep=np.ones(X.shape[1],bool)
    for j in range(1,X.shape[1]):keep[j]=int((rgo_mask&member[:,j]).sum())>=min_rgo
    def solve(rows,kept):
        b=np.zeros(X.shape[1]);b[kept]=lstsq(X[rows][:,kept],y[rows],w[rows]);return b
    beta=solve(fit_mask,keep)
    small=np.abs(beta)<thr;small[0]=False;keep&=~small
    beta=solve(fit_mask,keep)
    ph=np.full(len(y),np.nan)
    for k in sorted(set(folds)):
        tr=fit_mask&(folds!=k);te=folds==k
        if tr.sum()<max(10,keep.sum()):continue
        ph[te]=X[te]@solve(tr,keep)
    return beta,keep,ph


def build(config_path=None,output_path=None):
    cp=Path(config_path or ROOT/'configs/goods_output_fit.json').resolve();cfg=json.loads(cp.read_text())
    out=Path(output_path or ROOT/'artifacts/goods_output_fit').resolve();out.mkdir(parents=True,exist_ok=True)
    manifest=import_tables(cfg)
    fit_cfg=json.loads((ROOT/cfg['attribute_fit_config']).read_text())
    if cfg.get('method','ols')=='constrained':
        from .goods_output_constrained import build_all
        return build_all({**cfg,**cfg.get('constrained',{})},fit_cfg,out,manifest)
    d=load_attributes(fit_cfg);features=cfg.get('features') or fit_cfg['features']
    X,names,groups=design_reference(d,features,fit_cfg['reference_classes'])
    member=X>0.5;member[:,0]=False
    folds,_=region_folds(d,fit_cfg.get('folds',5),fit_cfg.get('seed',1300));folds=np.asarray(folds)
    rgo=load_rgo(cfg,d.index)
    lo,hi=float(cfg['output_min']),float(cfg['output_max']);floor=float(cfg['rgo_floor'])
    tables=ROOT/cfg['tables_directory'];goods=sorted(p.stem for p in tables.glob('*.csv'))
    if cfg.get('goods'):goods=[g for g in goods if g in cfg['goods']]
    coef_rows=[];metric_rows=[];pred_rows=[];floor_rows=[]
    for good in goods:
        t=pd.read_csv(tables/f'{good}.csv',keep_default_na=False).set_index('location_tag')
        score=pd.to_numeric(t.score_0_1,errors='coerce').reindex(d.index).fillna(0.).to_numpy()
        y,viable=target_scale(score,lo,hi)
        is_rgo=(rgo==good).to_numpy();rgo_viable=is_rgo&viable
        fit_mask=viable if cfg.get('fit_on','weighted_viable')=='weighted_viable' else rgo_viable
        if rgo_viable.sum()<int(cfg['minimum_rgo_locations']):
            metric_rows.append({'good':good,'rgo_locations':int(is_rgo.sum()),'fitted':False,'note':'too few RGO locations; no rows (floor carve-out only)'})
            for tag in d.index[is_rgo]:floor_rows.append({'location_tag':tag,'good':good,'predicted':np.nan,'target':np.nan,'reason':'good not fitted'})
            continue
        beta,keep,ph=fit_good(X,names,member,np.nan_to_num(y),fit_mask,is_rgo,folds,cfg)
        beta=np.round(beta,int(cfg.get('round_decimals',2)))
        pred=X@beta
        coef_rows.append({'good':good,'attribute':'reference','value':'intercept','modifier':float(beta[0]),'rgo_locations':int(is_rgo.sum())})
        for j,(f,v) in enumerate(names):
            if j and keep[j]:coef_rows.append({'good':good,'attribute':f,'value':v,'modifier':float(beta[j]),'rgo_locations':int((is_rgo&member[:,j]).sum())})
        ev=rgo_viable&np.isfinite(ph)
        metric_rows.append({'good':good,'rgo_locations':int(is_rgo.sum()),'rgo_viable':int(rgo_viable.sum()),'viable_locations':int(viable.sum()),'fitted':True,'rows':int(keep[1:].sum()),
            'r2_rgo_heldout':r2(y[ev],ph[ev]) if ev.sum()>1 else float('nan'),'mae_rgo_heldout':float(np.abs(y[ev]-ph[ev]).mean()) if ev.sum() else float('nan'),'r2_rgo_insample':r2(y[rgo_viable],pred[rgo_viable]),
            'r2_viable_heldout':r2(np.nan_to_num(y)[viable&np.isfinite(ph)],ph[viable&np.isfinite(ph)]) if (viable&np.isfinite(ph)).sum()>10 else float('nan'),
            'rgo_below_floor_share':float((pred[is_rgo]<floor).mean()),'rgo_nonviable_share':float((~viable[is_rgo]).mean()),'predicted_rgo_median':float(np.median(pred[is_rgo]))})
        for tag,tv,pv,vv in zip(d.index[is_rgo],y[is_rgo],pred[is_rgo],viable[is_rgo]):
            pred_rows.append({'location_tag':tag,'good':good,'target':tv,'predicted':pv,'viable':bool(vv)})
            if not vv:floor_rows.append({'location_tag':tag,'good':good,'predicted':pv,'target':np.nan,'reason':'not viable in the efficiency data'})
            elif pv<floor:floor_rows.append({'location_tag':tag,'good':good,'predicted':pv,'target':tv,'reason':f'predicted below floor {floor}'})
    coef=pd.DataFrame(coef_rows);metrics=pd.DataFrame(metric_rows);preds=pd.DataFrame(pred_rows);floors=pd.DataFrame(floor_rows)
    coef.to_csv(out/'coefficients.csv',index=False);metrics.to_csv(out/'metrics.csv',index=False,float_format='%.4f')
    preds.to_csv(out/'location_predictions.csv',index=False,float_format='%.4f');floors.to_csv(out/'rgo_floor.csv',index=False,float_format='%.4f')
    fitted=metrics[metrics.fitted==True] if len(metrics) else metrics
    rows_per_class=coef[coef.attribute!='reference'].groupby(['attribute','value']).size() if len(coef) else pd.Series(dtype=int)
    summary={'goods':len(goods),'goods_fitted':int(len(fitted)),'total_rows':int(len(coef[coef.attribute!='reference'])) if len(coef) else 0,
        'rows_per_class_value_mean':float(rows_per_class.mean()) if len(rows_per_class) else 0.,'rows_per_class_value_max':int(rows_per_class.max()) if len(rows_per_class) else 0,
        'median_r2_rgo_heldout':float(fitted.r2_rgo_heldout.median()) if len(fitted) else float('nan'),'mean_mae_rgo_heldout':float(fitted.mae_rgo_heldout.mean()) if len(fitted) else float('nan'),
        'rgo_below_floor_share':float(fitted.rgo_below_floor_share.mean()) if len(fitted) else float('nan'),'rgo_nonviable_share':float(fitted.rgo_nonviable_share.mean()) if len(fitted) else float('nan'),
        'floor_list':int(len(floors))}
    report={'config':cfg,'summary':summary,'inputs':{'tables':manifest.get('goods',{}),'rgo_source':sha(ROOT/cfg['rgo_source'])},'reference_classes':fit_cfg['reference_classes'],'features':features,
        'scope':'Rows on displayed attributes only; the game keeps its RGO choice; the constructor keeps its floor carve-out for the actual RGO. No per-location value.'}
    write_json(out/'report.json',report)
    lines=['# Goods output modifiers from attributes','',f"{summary['goods_fitted']} of {summary['goods']} goods fitted on their RGO locations; scale {lo:+.2f}..{hi:+.2f}; rows kept where the good is the RGO in ≥ {cfg['min_rgo_locations_per_class']} locations of the class and |modifier| ≥ {cfg['prune_below']}.",'',
        f"Rows: {summary['total_rows']} total, {summary['rows_per_class_value_mean']:.1f} per attribute value on average, max {summary['rows_per_class_value_max']}. Median held-out R² on RGO locations {summary['median_r2_rgo_heldout']:.3f}, mean error {summary['mean_mae_rgo_heldout']:.3f}. RGO locations under the {floor:+.2f} floor: {100*summary['rgo_below_floor_share']:.1f}%; RGO locations the data calls non-viable: {100*summary['rgo_nonviable_share']:.1f}% (floor list {summary['floor_list']} rows).",'',
        '| Good | RGO locations | Rows | R² held-out (RGO) | Mean error | Under floor | Non-viable RGO |','|---|---:|---:|---:|---:|---:|---:|']
    for r in metrics.itertuples():
        if getattr(r,'fitted',False):lines.append(f"| {r.good} | {r.rgo_locations:,} | {r.rows} | {r.r2_rgo_heldout:.3f} | {r.mae_rgo_heldout:.3f} | {100*r.rgo_below_floor_share:.1f}% | {100*r.rgo_nonviable_share:.1f}% |")
        else:lines.append(f"| {r.good} | {r.rgo_locations:,} | — | — | — | — | not fitted |")
    lines+=['','Files: `coefficients.csv` (good, attribute, value, modifier), `metrics.csv`, `location_predictions.csv` (RGO locations), `rgo_floor.csv` (for the constructor floor carve-out).']
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    return report
