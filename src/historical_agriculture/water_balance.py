"""Crop-free reference water accounting, in mm and m3. No food model inputs."""
import numpy as np
from collections import deque
DAYS=np.array([31,28,31,30,31,30,31,31,30,31,30,31],dtype=float)

def reference_et0(tmin,tmax,srad,wind,vapour,elevation,latitude,month):
    """FAO-56 Penman–Monteith from WorldClim units; monthly mean daily inputs.
    Rs kJ/m2/day -> MJ/m2/day; WorldClim wind at 2m (data-author geodata documentation).
    G=0 approximation; representative middle-of-month extraterrestrial radiation.
    """
    t=(tmin+tmax)/2
    es=(.6108*np.exp(17.27*tmin/(tmin+237.3))+.6108*np.exp(17.27*tmax/(tmax+237.3)))/2
    delta=4098*(.6108*np.exp(17.27*t/(t+237.3)))/(t+237.3)**2
    pressure=101.3*((293-.0065*np.maximum(elevation,-400))/293)**5.26
    gamma=.000665*pressure
    u2=wind
    j=float(DAYS[:month].sum()+DAYS[month]/2)
    phi=np.deg2rad(latitude)
    dr=1+.033*np.cos(2*np.pi*j/365)
    decl=.409*np.sin(2*np.pi*j/365-1.39)
    ws=np.arccos(np.clip(-np.tan(phi)*np.tan(decl),-1,1))
    ra=(24*60/np.pi)*.0820*dr*(ws*np.sin(phi)*np.sin(decl)+np.cos(phi)*np.cos(decl)*np.sin(ws))
    rs=srad/1000
    rso=(.75+2e-5*elevation)*ra
    cloud=1.35*np.clip(np.divide(rs,rso,out=np.ones_like(rs),where=rso>.01),.3,1)-.35
    rnl=4.903e-9*((tmax+273.16)**4+(tmin+273.16)**4)/2*(.34-.14*np.sqrt(np.maximum(vapour,0)))*cloud
    rn=.77*rs-rnl
    result=(.408*delta*rn+gamma*(900/(t+273))*u2*np.maximum(es-vapour,0))/(delta+gamma*(1+.34*u2))
    return np.maximum(result,0)*DAYS[month]

def bucket(prec,et0,temp,storage_mm=100,spinup=12,snow_threshold=0,melt_factor=3):
    """Periodic monthly reference bucket with an analytically initialized soil store.
    Perennial snow accumulation is reported separately, not an endless spin-up.
    """
    p=np.asarray(prec,dtype=float);e=np.asarray(et0,dtype=float)
    t=np.asarray(temp,dtype=float);shape=p.shape
    snowfall=np.where(t<snow_threshold,p,0)
    meltcap=np.maximum(t-snow_threshold,0)*melt_factor*DAYS.reshape((12,)+(1,)*(p.ndim-1))
    change=snowfall-meltcap
    cumulative=np.cumsum(change,axis=0)
    annual=change.sum(axis=0)
    cyclic=np.maximum(0,np.max(np.cumsum(change[::-1],axis=0),axis=0))
    accumulating=np.maximum(0,-np.min(cumulative,axis=0))
    snow=np.where(annual>0,accumulating,cyclic)
    initial_snow=snow.copy();snow_end=[];water=[]
    for m in range(12):
        snow+=snowfall[m]
        melt=np.minimum(snow,meltcap[m]);snow-=melt
        water.append(p[m]-snowfall[m]+melt);snow_end.append(snow.copy())
    water=np.stack(water)
    # One annual map is clamp(x + annual_net, lower, upper). Its fixed point
    # is upper for positive net input and lower for negative net input.
    lower=np.zeros(shape[1:]);upper=np.full(shape[1:],storage_mm,dtype=float)
    for m in range(12):
        delta=water[m]-e[m]
        lower=np.clip(lower+delta,0,storage_mm);upper=np.clip(upper+delta,0,storage_mm)
    soil=np.where((water-e).sum(axis=0)>0,upper,lower);initial_soil=soil.copy()
    out={k:np.zeros(shape,dtype=np.float32) for k in ['eta','deficit','excess','soil','snow','residual']}
    previous_snow=initial_snow
    for m in range(12):
        before=soil+previous_snow
        available=soil+water[m];eta=np.minimum(e[m],available)
        after=available-eta;excess=np.maximum(after-storage_mm,0);soil=np.minimum(after,storage_mm)
        for k,v in [('eta',eta),('deficit',e[m]-eta),('excess',excess),('soil',soil),('snow',snow_end[m]),('residual',before+p[m]-eta-excess-soil-snow_end[m])]:out[k][m]=v
        previous_snow=snow_end[m]
    out['soil_cycle_error_mm']=float(np.max(np.abs(soil-initial_soil)))
    out['perennial_snow_accumulation']=annual>0
    return out

def topology(downstream):
    """Indices upstream-first; reject accidental cycles rather than allocating twice."""
    downstream=np.asarray(downstream,dtype=int)
    if np.any((downstream>=len(downstream))|(downstream< -1)):raise ValueError('Invalid downstream index')
    degree=np.bincount(downstream[downstream>=0],minlength=len(downstream))
    ready=deque(np.where(degree==0)[0]);order=[]
    while ready:
        i=ready.popleft();order.append(i);j=downstream[i]
        if j>=0:
            degree[j]-=1
            if degree[j]==0:ready.append(j)
    if len(order)!=len(downstream):raise ValueError('Catchment routing cycle')
    return np.array(order)

def route(local_runoff,demand,downstream,protected_fraction=.6,baseline=None,survival=None):
    """Route a monthly shared budget, with natural transmission losses.
    Existing allocations have priority; expansion cannot take their upstream water.
    """
    q=np.asarray(local_runoff,dtype=float);dem=np.asarray(demand,dtype=float)
    if q.shape!=dem.shape or np.any(q<0) or np.any(dem<0):raise ValueError('Invalid water inputs')
    order=topology(downstream)
    survival=np.ones(q.shape[1]) if survival is None else np.asarray(survival)
    if np.any((survival<0)|(survival>1)):raise ValueError('Invalid transmission fraction')
    def replay(allocations=None):
        flow=q*(1-protected_fraction);outflow=np.zeros_like(flow);allocated=np.zeros_like(flow);loss=np.zeros_like(flow)
        for i in order:
            loss[:,i]=flow[:,i]*(1-survival[i]);available=flow[:,i]*survival[i]
            take=np.minimum(available,dem[:,i]) if allocations is None else allocations[:,i]
            if np.any(take>available+1e-3):raise ValueError('Downstream allocation overdraws supply')
            allocated[:,i]=take;outflow[:,i]=np.maximum(available-take,0)
            j=downstream[i]
            if j>=0:flow[:,j]+=outflow[:,i]
        return allocated,outflow,loss
    if baseline is None:
        allocated,outflow,loss=replay()
    else:
        base=route(q,np.asarray(baseline),downstream,protected_fraction,survival=survival)
        allocated=base['allocated'].copy();spare=base['outflow'].copy()
        for i in order:
            chain=[];weights=[];j=int(i);weight=1.
            while j>=0:
                chain.append(j);weights.append(weight)
                j=int(downstream[j])
                if j>=0:weight*=survival[j]
            weights=np.asarray(weights)
            slack=np.min(np.divide(spare[:,chain],weights[None,:],out=np.full_like(spare[:,chain],np.inf),where=weights[None,:]>1e-15),axis=1)
            extra=np.minimum(np.maximum(dem[:,i]-allocated[:,i],0),np.maximum(slack,0))
            allocated[:,i]+=extra;spare[:,chain]-=extra[:,None]*weights[None,:]
        allocated,outflow,loss=replay(allocated)
    outlets=np.where(np.asarray(downstream)<0)[0]
    residual=q.sum(axis=1)*(1-protected_fraction)-allocated.sum(axis=1)-loss.sum(axis=1)-outflow[:,outlets].sum(axis=1)
    return {'allocated':allocated,'outflow':outflow,'residual':residual,'protected':q*protected_fraction,'transmission_loss':loss}
