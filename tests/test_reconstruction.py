import json
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin

from historical_agriculture.provenance import fingerprint
from historical_agriculture.reconstruction import assign
from historical_agriculture.raster import write, read

def test_historical_preference_beats_maximum_yield_and_preserves_missing(tmp_path):
    root=tmp_path;out=root/'artifacts';out.mkdir()
    (root/'configs').mkdir();(root/'data/raw').mkdir(parents=True)
    profile={'driver':'GTiff','height':1,'width':6,'count':1,'dtype':'float32','crs':'EPSG:4326','transform':from_origin(0,1,1,1)}
    from historical_agriculture.acquisition import filename
    config={'inputs':'data/raw','crop_order':['WHE','MZE']}
    write(root/'data/raw'/filename('WHE','LRLM'),np.array([[1,1,1,np.nan,0,0]]),profile,'kg')
    for crop,values in [('WHE',[100,0,100,np.nan,0,0]),('MZE',[1000,1000,1000,np.nan,0,np.nan])]:
        for scenario in ['lower','upper']:
            write(out/'crops'/f'{crop}_{scenario}.tif',np.array([values]),profile,'kg')
    (root/'configs/regions.json').write_text(json.dumps({'regions':[
        {'id':1,'name':'historic wheat preference','bbox':[0,0,2,1],'crops':['WHE','MZE'],'confidence':'low'},
        {'id':2,'name':'non-crop society','bbox':[2,0,4,1],'crops':[],'confidence':'low'}]}))
    result=assign(root,config,out)
    crops,_=read(out/'crop.tif');states,_=read(out/'state.tif')
    assert crops[0,0]==1  # Wheat despite maize's larger yield.
    assert crops[0,1]==2  # Environmental infeasibility permits the recorded alternative.
    assert crops[0,2]==0 and states[0,2]==1
    assert np.isnan(crops[0,3])
    assert states[0,4]==5  # Known unsuitable cell is not missing historical evidence.
    assert states[0,5]==6  # Missing crop scenarios do not become unsuitable zero.
    assert result['domain_cells']==5

def test_configuration_and_raw_evidence_invalidate_fingerprint(tmp_path):
    (tmp_path/'configs').mkdir();(tmp_path/'data/raw/documentation').mkdir(parents=True)
    config=tmp_path/'configs/reconstruction.json';config.write_text('{}')
    raw=tmp_path/'data/raw';a,_=fingerprint(config,raw)
    config.write_text('{"changed":true}');b,_=fingerprint(config,raw)
    assert a!=b
    (raw/'documentation/evidence.txt').write_text('changed evidence')
    c,_=fingerprint(config,raw)
    assert b!=c
