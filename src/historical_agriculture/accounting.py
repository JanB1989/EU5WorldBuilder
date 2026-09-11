import numpy as np

def upper_system(rainfed,irrigated):
    r,i=np.broadcast_arrays(rainfed,irrigated)
    # Missing one candidate does not certify the best system.
    complete=np.isfinite(r)&np.isfinite(i)
    choose_i=(i>r)&complete
    value=np.where(complete,np.maximum(r,i),np.nan)
    system=np.where(complete,np.where(value>0,np.where(choose_i,2,1),0),255).astype("uint8")
    return value,system

def annual_food(dm_kg,crop,frequency,fraction,loss=None):
    if not 0<crop["dry_fraction"]<=1:raise ValueError("Invalid dry fraction")
    if not 0<crop["recovery"]<=1:raise ValueError("Invalid recovery")
    if not 0<=crop["seed_share"]<1:raise ValueError("Invalid seed share")
    loss=crop["loss_share"] if loss is None else loss
    if not 0<=loss<1 or np.any(np.asarray(frequency)<=0) or np.any(np.asarray(fraction)<0) or np.any(np.asarray(fraction)>1):raise ValueError("Invalid annualization")
    annual=np.asarray(dm_kg)/crop["dry_fraction"]*frequency*fraction
    gross=annual*crop["recovery"]*crop["kcal_kg"]
    net=gross*(1-crop["seed_share"])*(1-loss)
    return annual,gross,net

def labour_days(days_per_harvest,frequency,fraction,maintenance):
    if np.any(np.asarray(days_per_harvest)<=0) or np.any(np.asarray(maintenance)<0):raise ValueError("Invalid labour")
    return days_per_harvest*frequency*fraction+maintenance

def historical_position(observed,lower,upper):
    a,b,c=np.broadcast_arrays(observed,lower,upper)
    out=np.full(a.shape,np.nan)
    np.divide(a-b,c-b,out=out,where=np.isfinite(a)&np.isfinite(b)&np.isfinite(c)&(c>b))
    return out
