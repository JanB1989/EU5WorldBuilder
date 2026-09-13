import numpy as np
import pytest
from historical_agriculture.terrain_access import slope_percent,ratings,aggregate


def test_slope_uses_distances_and_does_not_cancel_a_ridge():
    z=np.tile([0.,100.,0.],(3,1))
    s=slope_percent(z,1000.,1000.)
    assert np.allclose(s,10)
    assert np.allclose(slope_percent(np.ones((3,3)),1000,1000),0)


def test_mixed_valley_and_steep_pixels_are_evaluated_before_aggregation():
    slopes=np.array([[0,0,50,50],[0,0,50,50],[0,0,50,50],[0,0,50,50]])
    fraction=aggregate(ratings(slopes,[8,30],[1,.25,0]),4)
    assert fraction.item()==.5
    assert fraction.item()!=ratings(slopes.mean(),[8,30],[1,.25,0])


def test_missing_and_bad_parameters_are_not_silently_accepted():
    with pytest.raises(ValueError):ratings(np.array([1]),[8,2],[1,.25,0])
    with pytest.raises(ValueError):aggregate(np.ones((3,4)),2)


def test_native_dem_to_coarse_grid_and_missing_evidence(tmp_path):
    import rasterio
    from rasterio.transform import from_origin
    from historical_agriculture.terrain_access import calculate
    fine=dict(driver='GTiff',height=10,width=10,count=1,dtype='float32',
              crs='EPSG:9518',transform=from_origin(0,1,1/60,1/60),nodata=-9999)
    dem=tmp_path/'dem.tif'
    cfg=dict(slope_boundaries_percent=[8,30],baseline_weights=[1,.25,0],
             maximum_weights=[1,.5,0],minimum_elevation_m=-10)
    coarse={**fine,'crs':'EPSG:4326','height':2,'width':2,'transform':from_origin(0,1,5/60,5/60)}
    with rasterio.open(dem,'w',**fine) as ds:ds.write(np.full((10,10),100,dtype='float32'),1)
    b,m,unknown=calculate(dem,coarse,cfg,tmp_path)
    assert np.all(b==1) and np.all(m==1) and not unknown.any()
    with rasterio.open(dem,'w',**fine) as ds:ds.write(np.full((10,10),-9999,dtype='float32'),1)
    b,m,unknown=calculate(dem,coarse,cfg,tmp_path)
    assert np.all(b==0) and np.all(m==0) and unknown.all()
