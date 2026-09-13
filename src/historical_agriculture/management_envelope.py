"""Voluntary management retains a lower-input option when scenarios reverse."""
import numpy as np

def yields(low, high_rainfed, high_irrigated, position):
    low,high_rainfed,high_irrigated,position=np.broadcast_arrays(low,high_rainfed,high_irrigated,position)
    if np.any(~np.isfinite(position)|(position<0)|(position>1)):raise ValueError("Management position outside [0,1]")
    dry=(1-position)*low+position*np.maximum(high_rainfed,low)
    wet=np.maximum(dry,(1-position)*low+position*np.maximum(high_irrigated,low))
    return dry,wet
