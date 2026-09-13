"""Fine-pixel slope screening, aggregated only after evaluating land access.

ETOPO 60s smooths real slopes: these are explicit screening priors, not measured
arable hectares. Slope class boundaries follow GAEZ; weights are model choices.
"""
import numpy as np
import rasterio
from rasterio.windows import Window
from .raster import write


def slope_percent(z, dx, dy):
    """Maximum one-sided cardinal gradients avoid cancelling ridges/valleys."""
    padded = np.pad(np.asarray(z, dtype=float), 1, mode='edge')
    x = np.maximum(abs(padded[1:-1, 2:]-z), abs(padded[1:-1, :-2]-z))/dx
    y = np.maximum(abs(padded[2:, 1:-1]-z), abs(padded[:-2, 1:-1]-z))/dy
    return 100*np.hypot(x, y)


def ratings(slopes, boundaries, weights):
    if len(weights) != len(boundaries)+1 or not np.all(np.diff(boundaries)>0):
        raise ValueError('Invalid slope classes')
    if np.any(np.asarray(weights)<0) or np.any(np.asarray(weights)>1):
        raise ValueError('Invalid terrain ratings')
    return np.asarray(weights)[np.searchsorted(boundaries, slopes, side='right')]


def aggregate(a, factor):
    h,w=a.shape
    if h%factor or w%factor:raise ValueError('Unaligned fine grid')
    return a.reshape(h//factor,factor,w//factor,factor).mean(axis=(1,3))


def calculate(dem, profile, cfg, out):
    if not np.isfinite(cfg.get('slope_multiplier',1)) or cfg.get('slope_multiplier',1)<=0:
        raise ValueError('Invalid slope sensitivity multiplier')
    shape=(profile['height'],profile['width'])
    base=np.zeros(shape,dtype='float32');potential=base.copy();missing=base.copy()
    with rasterio.open(dem) as ds:
        target_crs=rasterio.crs.CRS.from_user_input(profile['crs'])
        # ETOPO EPSG:9518 is WGS84 horizontally plus EGM2008 orthometric height.
        if ds.crs!=target_crs and not (ds.crs.to_epsg()==9518 and target_crs.to_epsg()==4326):
            raise ValueError('Terrain horizontal CRS mismatch')
        factor=round(profile['transform'].a/ds.transform.a)
        if factor<1 or (ds.height,ds.width)!=(shape[0]*factor,shape[1]*factor):
            raise ValueError('Terrain grid dimensions do not match')
        if not (ds.transform @ rasterio.Affine.scale(factor,factor)).almost_equals(profile['transform']):
            raise ValueError('Terrain grid registration mismatch')
        dy=abs(ds.transform.e)*111195
        for row in range(0,shape[0],48):
            h=min(48,shape[0]-row);start=row*factor;stop=(row+h)*factor
            top=max(0,start-1);bottom=min(ds.height,stop+1)
            z=ds.read(1,window=Window(0,top,ds.width,bottom-top),masked=True).filled(np.nan).astype(float)
            lat=ds.transform.f+(np.arange(top,bottom)+.5)*ds.transform.e
            dx=np.maximum(abs(ds.transform.a)*111195*np.cos(np.deg2rad(lat)),1)[:,None]
            slope=slope_percent(z,dx,dy)[start-top:stop-top]*cfg.get('slope_multiplier',1)
            z=z[start-top:stop-top]
            known=np.isfinite(slope)&np.isfinite(z)
            terrestrial=known&(z>=cfg['minimum_elevation_m'])
            for target,key in [(base,'baseline_weights'),(potential,'maximum_weights')]:
                fine=np.where(terrestrial,ratings(slope,cfg['slope_boundaries_percent'],cfg[key]),0)
                target[row:row+h]=aggregate(fine,factor)
            missing[row:row+h]=aggregate((~known).astype(float),factor)
    if np.any(base>potential+1e-7):raise ValueError('Terrain access exceeds improvement potential')
    for name,a in [('terrain_baseline_factor',base),('terrain_maximum_factor',potential),('terrain_missing_fraction',missing)]:
        write(out/(name+'.tif'),a,profile,'Fine-pixel slope screening fraction; not observed cultivated area')
    return base,potential,missing>0
