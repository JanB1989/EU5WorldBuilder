"""Crop-stage water demand and conservative seasonal irrigation-equivalent area.

This is a screening response, not AquaCrop or a reconstruction of daily stress.
The strict worst-month result is retained as a sensitivity diagnostic.
"""
import numpy as np


def requirements(active, et0, natural_deficit, crop, coefficients, minimum_mm, paddy_extra_mm):
    active=np.asarray(active,bool)
    et=np.asarray(et0,float);deficit=np.asarray(natural_deficit,float)
    if active.shape!=et.shape or et.shape!=deficit.shape:
        raise ValueError('Misaligned crop water inputs')
    if not np.isfinite(et).all() or not np.isfinite(deficit).all() or np.any(et<0) or np.any(deficit<0):
        raise ValueError('Invalid crop water inputs')
    # Find the first active month after an inactive month, including Dec/Jan.
    starts=(active & ~np.roll(active,1,axis=0)).argmax(axis=0)
    months=active.sum(axis=0)
    progress=(np.arange(12).reshape((12,)+(1,)*(active.ndim-1))-starts)%12
    stage=np.minimum((4*progress/np.maximum(months,1)).astype(int),3)
    kc=np.ones_like(et)
    for code,values in coefficients.items():
        if len(values)!=4 or min(values)<0:raise ValueError('Invalid crop coefficients')
        kc=np.where(np.asarray(crop)[None]==int(code),np.asarray(values)[stage],kc)
    natural_et=np.maximum(et-deficit,0)
    need=np.maximum(kc*et-natural_et,0)
    floor=np.divide(minimum_mm,months,out=np.zeros(months.shape,float),where=months>0)
    return np.where(active,np.maximum(need,floor)+(crop==7)*paddy_extra_mm,0).astype(np.float32)


def seasonal_response(weighted_supply, demand, worst_month, critical_weight=.25):
    """Blend seasonal delivered fraction with an explicit critical-month penalty.

    The seasonal response is bounded by the water-weighted delivered fraction,
    so it never represents more full-demand-equivalent hectares than supplied.
    The 25% penalty is a sensitivity prior, not a measured medieval coefficient.
    """
    if not 0<=critical_weight<=1:raise ValueError('Invalid critical-month weight')
    mean=np.divide(weighted_supply,demand,out=np.ones_like(np.asarray(demand),float),where=demand>0)
    return np.clip((1-critical_weight)*mean+critical_weight*worst_month,0,1)
