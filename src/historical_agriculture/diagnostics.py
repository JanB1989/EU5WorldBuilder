"""Evaluated sensitivities and regional diagnostics, separate from acceptance."""
import json
import numpy as np
import pandas as pd

from .accounting import annual_food, labour_days
from .provenance import write_json
from .raster import read, write, coordinates


def summarize(values):
    a=np.asarray(values);a=a[np.isfinite(a)]
    if not len(a):return {'count':0}
    return {'count':int(len(a)),'minimum':float(a.min()),'p10':float(np.quantile(a,.1)),
            'median':float(np.median(a)),'mean':float(a.mean()),'p90':float(np.quantile(a,.9)),
            'maximum':float(a.max())}


def diagnostics(root, config, out):
    primary,profile=read(out/'crop.tif');alternative,_=read(out/'alternative_crop.tif')
    region,_=read(out/'region.tif');state,_=read(out/'state.tif')
    position,_=read(out/'management_position.tif');fraction,_=read(out/'cultivated_fraction.tif')
    kcal,_=read(out/'historical_kcal.tif');dm,_=read(out/'historical_dm.tif')
    rules=json.loads((root/'configs/regions.json').read_text())['regions']
    frequency=np.full(primary.shape,np.nan,dtype=np.float32);maintenance=frequency.copy()
    for r in rules:
        m=config['management'][r['management']];mask=region==r['id']
        frequency[mask]=m['harvests'];maintenance[mask]=m['maintenance_days']
    alternative_kcal=np.full(primary.shape,np.nan,dtype=np.float32)
    experiments=[]
    for i,code in enumerate(config['crop_order'],1):
        c=config['crops'][code]
        a=alternative==i
        if a.any():
            low,_=read(out/'crops'/f'{code}_lower.tif');upper,_=read(out/'crops'/f'{code}_upper.tif')
            a &= np.isfinite(low)&np.isfinite(upper)&(upper>=low)&np.isfinite(position)
            yield_dm=low[a]+position[a]*(upper[a]-low[a])
            _,_,energy=annual_food(yield_dm,c,frequency[a],fraction[a])
            alternative_kcal[a]=energy
        mask=(primary==i)&np.isfinite(dm)
        if not mask.any():continue
        for variable,levels in config['sensitivity'].items():
            if variable=='note':continue
            for level in levels:
                yield_dm=dm[mask]*(level if variable=='yield_multiplier' else 1)
                harvests=frequency[mask]*(level if variable=='cropping_frequency_multiplier' else 1)
                days=c['labour_days']*(level if variable=='labour_multiplier' else 1)
                _,_,energy=annual_food(yield_dm,c,harvests,fraction[mask])
                labour=labour_days(days,harvests,fraction[mask],maintenance[mask])
                experiments.append({'crop':code,'variable':variable,'multiplier':level,
                    'median_kcal':float(np.median(energy)),
                    'median_worker_days':float(np.median(labour)),
                    'median_kcal_per_worker_day':float(np.median(energy/labour))})
    write(out/'alternative_kcal.tif',alternative_kcal,profile,'kcal / rotational ha / year; alternate crop, same management assumptions')
    ratio=np.full(primary.shape,np.nan,dtype=np.float32)
    valid=np.isfinite(alternative_kcal)&np.isfinite(kcal)&(kcal>0)
    ratio[valid]=alternative_kcal[valid]/kcal[valid]
    write(out/'alternative_kcal_ratio.tif',ratio,profile,'alternate / representative crop food; not optimized crop selection')
    write_json(out/'controlled_sensitivity.json',{'experiments':experiments,
        'alternative_crop_ratio':summarize(ratio),
        'interpretation':'One-at-a-time accounting tests. Alternate crops retain the same inferred management system. Cropping multipliers do not establish calendar feasibility.'})
    fields=['lower_dm','upper_dm','historical_dm','historical_kcal','labour_days','kcal_per_worker_day','management_position']
    distributions=[]
    for field in fields:
        values,_=read(out/f'{field}.tif')
        distributions.append({'region':'world','field':field,**summarize(values)})
        for r in rules:
            distributions.append({'region':r['name'],'field':field,**summarize(values[region==r['id']])})
    pd.DataFrame(distributions).to_csv(out/'regional_distributions.csv',index=False)
    gaps=[];x,y=coordinates(profile)
    for west in range(-180,180,30):
        for south in range(-90,90,15):
            mask=(x[None,:]>=west)&(x[None,:]<west+30)&(y[:,None]>=south)&(y[:,None]<south+15)
            n=int(np.sum(mask&(state==4)))
            if n:gaps.append({'bbox':[west,south,west+30,south+15],'unresolved_viable_cells':n})
    write_json(out/'coverage_gaps.json',{'gaps':sorted(gaps,key=lambda r:-r['unresolved_viable_cells']),
        'distribution_weighting':'Cell-unweighted descriptive statistics; these are not land-area or production totals.'})
    return {'alternative_cells_compared':int(valid.sum()),'controlled_experiments':len(experiments)}
