"""Native wetland fractions and dated vegetation inputs, before EU5 aggregation."""
import json
from pathlib import Path
from zipfile import ZipFile
import numpy as np
import rasterio
from .soil_types import sha
from .water_management_inputs import mean_blocks

ROOT=Path(__file__).resolve().parents[2]
GROUPS={
 "swamp":[8,10,12,14,16,18,22,24,26],
 "marsh":[9,11,13,15,17,19,23,25,27],
 "mangroves":[28], "saltmarsh":[29],
}
def prepare_wetlands():
 raw=ROOT/'data/raw/water_management'
 out=ROOT/'data/processed/vegetation';out.mkdir(parents=True,exist_ok=True)
 archive=raw/'GLWD_v2_0_area_by_class_pct_tif.zip'
 key={"source_sha256":sha(archive),"groups":GROUPS,"code_sha256":sha(Path(__file__))}
 cache=out/'wetland_types.npz';meta=out/'wetland_types.json'
 if cache.exists() and meta.exists() and json.loads(meta.read_text()).get('inputs')==key:
  return cache
 result={};covered=None
 with ZipFile(archive) as z:
  for group,codes in GROUPS.items():
   total=np.zeros((2160,4320),np.float32)
   for code in codes:
    name=next(n for n in z.namelist() if n.endswith(f'class_{code:02d}_pct.tif'))
    with rasterio.open('/vsizip/'+str(archive)+'/'+name,OVERVIEW_LEVEL='NONE') as ds:
     if ds.shape!=(33600,86400) or ds.crs.to_epsg()!=4326 or not np.allclose(tuple(ds.bounds),(-180,-56,180,84)):
      raise ValueError('Unexpected GLWD native registration')
     cov=np.zeros((2160,4320),bool)
     for row in range(0,1680,20):
      n=min(20,1680-row)
      block=ds.read(1,window=rasterio.windows.Window(0,row*20,86400,n*20))
      reduced=mean_blocks(block,20,ds.nodata)
      total[72+row:72+row+n]+=reduced.filled(0)/100
      cov[72+row:72+row+n]=~np.ma.getmaskarray(reduced)
     if covered is None:covered=cov
    print('Vegetation wetland fractions:',group,code,flush=True)
   result[group]=total
 result['covered']=covered
 np.savez_compressed(cache,**result)
 meta.write_text(json.dumps({"inputs":key,"output_sha256":sha(cache),
  "date":"GLWD 1990-2020; historical correction is separate",
  "method":"Native 15-arcsecond percentages averaged in exact20x20 blocks; missing separate from zero; no source overviews."},indent=2))
 return cache
if __name__=='__main__':print(prepare_wetlands())
