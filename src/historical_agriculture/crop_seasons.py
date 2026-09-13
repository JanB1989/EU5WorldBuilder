"""Inferred crop seasons for irrigation accounting, independent of river supply.

These are climate analogues, not reconstructed medieval sowing dates. They alter
water demand timing only; crop yields, annual harvests and cultivated area stay fixed.
"""
import numpy as np


def select(temperature, precipitation, et0, spec):
    """Select one cyclic, consecutive growing window for each trailing cell.

    First minimize months outside a broad thermal envelope, then departure from
    an agronomic temperature band, then reference moisture shortage. Never look
    at runoff, historical population or a capacity target. Invalid climate keeps
    an explicitly flagged conservative consecutive high-ET fallback.
    """
    t,p,e=[np.asarray(x,dtype=np.float32) for x in (temperature,precipitation,et0)]
    if t.shape!=p.shape or t.shape!=e.shape or t.shape[0]!=12:
        raise ValueError('Expected aligned monthly climate arrays')
    n=int(spec['months']);lo,hi=spec['preferred_temperature_c']
    if not 1<=n<=12 or lo>hi:raise ValueError('Invalid season specification')
    valid=np.all(np.isfinite(t)&np.isfinite(p)&np.isfinite(e),axis=0)
    t=np.nan_to_num(t);p=np.maximum(np.nan_to_num(p),0);e=np.maximum(np.nan_to_num(e),0)
    outside=(t<spec['minimum_temperature_c'])|(t>spec['maximum_temperature_c'])
    thermal=np.maximum(lo-t,0)+np.maximum(t-hi,0)
    shortage=np.clip((e-p)/np.maximum(e,1),0,1)
    best=np.full(t.shape[1:],np.inf);start=np.zeros(t.shape[1:],dtype=np.int8)
    conflict=np.zeros(t.shape[1:],dtype=bool)
    for s in range(12):
        ix=(s+np.arange(n))%12
        bad=outside[ix].sum(axis=0)
        score=bad*10000+thermal[ix].mean(axis=0)*100+shortage[ix].mean(axis=0)
        # No unknown climate silently becomes perfect suitability.
        score=np.where(valid,score,-e[ix].sum(axis=0))
        take=score<best
        start=np.where(take,s,start);best=np.minimum(best,score)
        conflict=np.where(take,bad>0,conflict)
    active=(np.arange(12).reshape((12,)+(1,)*(t.ndim-1))-start)%12<n
    return active,start,(~valid)|conflict


def demand(active,deficit,crop,minimum_mm,paddy_extra_mm):
    """Reference-shortage proxy plus separate paddy percolation, mm/year.

    Retains the prior 100 mm seasonal engineering floor; spreading that floor
    across a different season must not change its annual amount.
    """
    a=np.asarray(active,bool);d=np.asarray(deficit)
    if a.shape!=d.shape or np.any(d<0) or not np.isfinite(d).all():
        raise ValueError('Invalid monthly deficit')
    months=a.sum(axis=0)
    floor=np.divide(minimum_mm,months,out=np.zeros(months.shape,float),where=months>0)
    return np.where(a,np.maximum(d,floor)+(np.asarray(crop)==7)*paddy_extra_mm,0).astype(np.float32)


def global_seasons(root,config,crop,domain,et0):
    """Read native-grid climate once, then operate on cropped-cell vectors."""
    from .water import wc
    shape=crop.shape;cells=np.flatnonzero(domain&(crop>0))
    t=np.stack([((wc(root/'data/raw/water','tmin',m)+wc(root/'data/raw/water','tmax',m))/2).ravel()[cells] for m in range(12)])
    p=np.stack([wc(root/'data/raw/water','prec',m).ravel()[cells] for m in range(12)])
    e=et0.reshape(12,-1)[:,cells];codes=crop.ravel()[cells]
    active=np.zeros((12,crop.size),bool);starts=np.full(crop.size,-1,np.int8);flag=np.zeros(crop.size,bool)
    records=[]
    for code,spec in config['crops'].items():
        use=codes==int(code)
        if not use.any():continue
        a,s,f=select(t[:,use],p[:,use],e[:,use],spec)
        target=cells[use];active[:,target]=a;starts[target]=s;flag[target]=f
        records.append({'crop':spec['crop'],'cells':int(use.sum()),'months':spec['months'],
                        'thermal_conflict_or_missing_cells':int(f.sum()),
                        'start_month_counts':np.bincount(s,minlength=12).tolist()})
    if np.any(active[:,cells].sum(axis=0)==0):raise ValueError('Crop has no configured season')
    return active.reshape((12,)+shape),starts.reshape(shape),flag.reshape(shape),records
