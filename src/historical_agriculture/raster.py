from pathlib import Path
import numpy as np
import rasterio

def read(path):
    with rasterio.open(path) as d:
        a=d.read(1,masked=True).astype("float32").filled(np.nan)
        return a,d.profile

def write(path,a,profile,unit,tags=None):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    profile=profile.copy();profile.update(dtype="float32",count=1,nodata=-9999.,compress="deflate",predictor=3)
    with rasterio.open(path,"w",**profile) as d:
        d.write(np.where(np.isfinite(a),a,-9999).astype("float32"),1)
        d.update_tags(units=unit,status="research_candidate_not_historically_validated",**(tags or {}))

def grid(path):
    with rasterio.open(path) as d:return d.shape,tuple(d.transform),str(d.crs)

def coordinates(profile):
    t=profile["transform"]
    return t.c+(np.arange(profile["width"])+.5)*t.a,t.f+(np.arange(profile["height"])+.5)*t.e
