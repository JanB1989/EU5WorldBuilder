"""Explicit chart-only crop proxies; never rewrite the Seshat observation."""
import json
import numpy as np
import rasterio
from .accounting import annual_food


def assumed_range(root,config,out,region,observation,coefficient,daily,days):
    path=root/'configs/benchmark_proxies.json'
    if not path.exists():return None
    rule=json.loads(path.read_text())['proxies'].get(region)
    if rule is None:return None
    x,y=float(observation.longitude),float(observation.latitude)
    points=[(x+dx,y+dy) for dy in np.linspace(-.5,.5,11) for dx in np.linspace(-.5,.5,11)]
    values=[]
    for scenario in ['lower','upper']:
        with rasterio.open(out/'crops'/f"{rule['crop']}_{scenario}.tif") as ds:
            values.append(np.ma.stack(list(ds.sample(points,masked=True))).astype(float).filled(np.nan)[:,0])
    lo,hi=values
    use=np.isfinite(lo)&np.isfinite(hi)&(lo>=0)&(hi>lo)
    if not use.any():raise ValueError(f'No valid proxy range for {region}')
    result={}
    for name,values in [('lower',lo),('upper',hi)]:
        _,_,net=annual_food(values[use],config['crops'][rule['crop']],max(1,coefficient),min(1,coefficient))
        result[name]=float(np.median(net)/(daily*days))
    result.update(range_crop=rule['crop'],proxy_cells=int(use.sum()),proxy_source=rule['source'],proxy_reason=rule['reason'])
    return result
