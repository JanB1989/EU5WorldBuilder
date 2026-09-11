"""Explicit crop/scenario transformations; no population or cropland-area inputs."""
import numpy as np

def scale_yield(yield_kg, factor, exponent=1.0, reference_kg=1000.0):
    if not np.isfinite([factor, exponent, reference_kg]).all() or min(factor, exponent, reference_kg) <= 0:
        raise ValueError("Scale, exponent and reference must be finite and positive")
    a=np.asarray(yield_kg,dtype=float)
    return np.where(a>=0,reference_kg*factor*np.power(np.maximum(a,0)/reference_kg,exponent),np.nan)

def food_energy(yield_kg, kcal_kg, product_recovery, retention, harvests=1., cultivated_fraction=1.):
    if not 0 <= product_recovery <= 1 or not 0 <= retention <= 1 or not 0 <= cultivated_fraction <= 1:
        raise ValueError("Fractions outside [0,1]")
    if not np.isfinite([kcal_kg, harvests]).all() or kcal_kg <= 0 or harvests <= 0:
        raise ValueError("Energy and harvest frequency must be positive")
    return np.asarray(yield_kg)*kcal_kg*product_recovery*retention*harvests*cultivated_fraction

def position(observed,lower,upper):
    observed,lower,upper=np.broadcast_arrays(observed,lower,upper)
    out=np.full(observed.shape,np.nan,dtype=float)
    np.divide(observed-lower,upper-lower,out=out,where=upper>lower)
    return out  # Never clip out-of-envelope evidence.
