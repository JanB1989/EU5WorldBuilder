"""Reproduce food-rank and matched-site diagnostics; no balance fitting."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from historical_agriculture.raster import read
from historical_agriculture.accounting import annual_food
from historical_agriculture.provenance import write_json

root=Path(__file__).resolve().parents[1];out=root/'artifacts/reconstruction'
config=json.loads((root/'configs/reconstruction.json').read_text())
food,_=read(out/'food_type.tif');labels=json.loads((out/'food_coverage.json').read_text())['labels']
rows=[]
for scenario in ['lower','historical','upper']:
    values,_=read(out/f'{scenario}_people.tif')
    for code,label in labels.items():
        a=values[(food==int(code))&np.isfinite(values)]
        rows.append({'food':label,'scenario':scenario,'cells':len(a),'p10':float(np.quantile(a,.1)) if len(a) else None,'median':float(np.median(a)) if len(a) else None,'p90':float(np.quantile(a,.9)) if len(a) else None})
pd.DataFrame(rows).to_csv(out/'food_rank_review.csv',index=False)
pairs=[]
for first,second in [('WHE','BRL'),('WHE','RYE'),('FML','PML'),('SRG','WHE')]:
    for scenario in ['lower','upper']:
        x,_=read(out/'crops'/f'{first}_{scenario}.tif');y,_=read(out/'crops'/f'{second}_{scenario}.tif')
        use=np.isfinite(x)&np.isfinite(y)&(x>0)&(y>0)
        _,_,a=annual_food(x[use],config['crops'][first],1,1)
        _,_,b=annual_food(y[use],config['crops'][second],1,1)
        pairs.append({'first':first,'second':second,'scenario':scenario,'common_viable_cells':int(use.sum()),'median_energy_ratio':float(np.median(a/b)),'interpretation':'same sites and one harvest; agronomic diagnostic, not historical crop availability or assigned-system rank'})
write_json(out/'matched_crop_comparisons.json',pairs)
old=root/'artifacts/experiments/pre_food_rank_review/reconstruction'
if old.exists():
    a,_=read(old/'historical_people.tif');b,_=read(out/'historical_people.tif')
    changed=np.isfinite(a)&np.isfinite(b)&(np.abs(a-b)>1e-6)
    eco,_=read(out/'food_ecoregion.tif')
    cassava=food==config['crop_order'].index('CSV')+1
    floodplain=cassava&np.isin(eco,[469,482,496])
    allowed=cassava
    common=cassava&np.isfinite(a)&np.isfinite(b)&(a>0)
    expected=np.where(floodplain,(1/2.6)/.23,1.)/.95
    assert np.allclose(b[common]/a[common],expected[common],rtol=2e-6), 'Unexpected cassava adjustment'
    f=common&floodplain
    old_eff,_=read(old/'kcal_per_worker_day.tif');new_eff,_=read(out/'kcal_per_worker_day.tif')
    matched=f&np.isfinite(old_eff)&np.isfinite(new_eff)&(old_eff>0)
    assert np.allclose(new_eff[matched]/old_eff[matched],1/.95,rtol=2e-6), 'Rotation created unaccounted labour efficiency'
    assert not np.any(changed&~allowed),'Unrelated food values changed'
    write_json(out/'rotation_candidate_comparison.json',{'changed_cells':int(changed.sum()),'only_cassava_changed':True,'floodplain_cells':int(f.sum()),'floodplain_previous_median':float(np.median(a[f])),'floodplain_candidate_median':float(np.median(b[f])),'seed_only_ratio':1/.95,'previous_median':float(np.median(a[changed])),'candidate_median':float(np.median(b[changed])),'ratio':float(np.median(b[changed]/a[changed])),'fraction_sensitivity':[.15,.65],'floodplain_sensitivity_medians':{str(frac):float(np.median(b[f]*frac/(1/2.6))) for frac in [.15,1/2.6,.65]},'assumption_status':'explicit modern-system analogue transferred to 1300; not historical validation'})
print('Food ranking, matched-site comparisons and targeted change checks saved.')
