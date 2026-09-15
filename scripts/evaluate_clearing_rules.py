"""Diagnostic only: approximate equal-area clearing targets from native categories."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'artifacts/clearing_rule_trial';out.mkdir(parents=True,exist_ok=True)
source=ROOT/'artifacts/locations/locations_equal_area.csv'
invpath=ROOT/'data/raw/location_inputs/inventory.parquet'
d=pd.read_csv(source, keep_default_na=False);d=d[d.is_ownable].copy()
attrs=['vegetation','topography','climate']
a=pd.read_parquet(invpath)
d=d.merge(a[['location_tag']+attrs],on='location_tag',how='left',validate='one_to_one')
assert d[attrs].notna().all().all(), 'Missing attributes'
y=d.maximum_clearing_improvement_units.to_numpy();m=d.capacity_multiplier.to_numpy();cap=y*m
fold=d.province.fillna(d.location_tag).map(lambda s:int(hashlib.sha256(s.encode()).hexdigest()[:8],16)%5).to_numpy()
# Dummy-coded categorical rule; ridge resolves redundant category intercepts.
X=pd.get_dummies(d[attrs],dtype=float); cols=['intercept']+list(X.columns);X=np.column_stack([np.ones(len(d)),X.to_numpy()])
def fit_predict(train,test,mode):
 target=np.log1p(y/1000) if mode=='multiplicative' else y/1000
 penalty=np.eye(X.shape[1]);penalty[0,0]=0
 b=np.linalg.solve(X[train].T@X[train]+penalty,X[train].T@target[train])
 pred=X[test]@b
 pred=np.expm1(pred)*1000 if mode=='multiplicative' else pred*1000
 return np.maximum(pred,0),b
def metrics(p,sel=None):
 if sel is None:sel=np.ones(len(y),dtype=bool)
 t=cap[sel];v=p[sel]*m[sel];pos=t>=1000;zero=t<1
 return {'n':int(sel.sum()),'target_total':float(t.sum()),'predicted_total':float(v.sum()),'weighted_absolute_error_pct':(float(abs(v-t).sum()/t.sum()*100) if t.sum()>0 else None),'median_absolute_error_capacity':float(np.median(abs(v-t))),'positive_n':int(pos.sum()),'within_25pct_positive_pct':(float(np.mean(abs(v[pos]-t[pos])<=.25*t[pos])*100) if pos.any() else None),'within_factor2_positive_pct':(float(np.mean((v[pos]>=t[pos]/2)&(v[pos]<=t[pos]*2))*100) if pos.any() else None),'zero_n':int(zero.sum()),'zero_predicted_above_1000_n':int((v[zero]>1000).sum())}
results={}; coeff={}
for mode in ['additive','multiplicative']:
 p=np.zeros(len(y))
 for f in range(5):p[fold==f],_=fit_predict(fold!=f,fold==f,mode)
 d[mode+'_predicted_units']=p;d[mode+'_predicted_capacity']=p*m
 results[mode]=metrics(p)
 _,b=fit_predict(np.ones(len(y),bool),np.ones(len(y),bool),mode)
 coeff[mode]=dict(zip(cols,map(float,b)))
# Flexible combination lookup: tests interactions, not just additive factors.
lookup=np.zeros(len(y))
for f in range(5):
 tr=d.loc[fold!=f].copy();tr['target_units']=y[fold!=f]
 means=tr.groupby(attrs).target_units.mean()
 lookup[fold==f]=pd.MultiIndex.from_frame(d.loc[fold==f,attrs]).map(means).to_numpy(dtype=float)
 lookup[(fold==f)&np.isnan(lookup)]=np.median(y[fold!=f])
d['lookup_predicted_units']=lookup;results['combination_lookup']=metrics(lookup)
# Within-category spreads are irreducible for any deterministic native-only rule.
g=d.assign(target_units=y).groupby(attrs).target_units.agg(n='size',q10=lambda s:s.quantile(.1),median='median',q90=lambda s:s.quantile(.9)).reset_index()
g['q90_q10']=g.q90/g.q10.replace(0,np.nan);g.to_csv(out/'identical_attribute_spreads.csv',index=False)
regions=[]
for name in sorted(d.super_region.unique()):
 row={'super_region':name};row.update(metrics(d.additive_predicted_units.to_numpy(),(d.super_region==name).to_numpy()));regions.append(row)
pd.DataFrame(regions).to_csv(out/'continent_results.csv',index=False)
keep=['location_tag','province','super_region']+attrs+['capacity_multiplier','maximum_clearing_improvement_units','maximum_clearing_improvement_capacity','starting_clearing_improvement_units','additive_predicted_units','additive_predicted_capacity','multiplicative_predicted_units','multiplicative_predicted_capacity','lookup_predicted_units']
d[keep].to_csv(out/'location_comparison.csv',index=False)
manifest={'status':'diagnostic; no game or map changes','target':'maximum clearing including inherited clearing; final typed equal-area output','features':attrs,'excluded':'population, area, culture, nation and location/region identifiers; province used only for split','validation':'5 folds grouped by province, SHA256 modulo 5','positive_comparison_minimum_capacity':1000,'metrics':results,'coefficients':coeff,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'inventory_sha256':hashlib.sha256(invpath.read_bytes()).hexdigest(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
(out/'results.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(results,indent=2));print('CONTINENTS',regions)
print('SAME ATTRIBUTES',g[(g.n>=100)&(g.q10>1000)].sort_values('q90_q10',ascending=False).head(8).to_dict('records'))
print('COEFFICIENTS',coeff['additive'])