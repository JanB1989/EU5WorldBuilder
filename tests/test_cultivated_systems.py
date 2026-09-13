from types import SimpleNamespace
import numpy as np
import pytest
from historical_agriculture import cultivated_systems as cs


def test_cereal_basket_substitutes_without_maximizing_or_double_harvest():
    original=np.array([1., 1., 3., 2.])
    alternatives=np.array([[2., 0., 1., np.nan], [4., 4., 2., 0.]])
    mixed,count=cs.cereal_mix(original,alternatives,.5)
    np.testing.assert_allclose(mixed,[2.,2.5,3.,2.])
    assert count.tolist()==[2,1,2,0]
    assert mixed[0] != .5*(original[0]+4.)
    with pytest.raises(ValueError):cs.cereal_mix(original,alternatives,1.1)


def test_only_dated_eligible_fields_receive_system_adjustment(monkeypatch,tmp_path):
    import json
    cfg={'food_directory':'food','input_directory':'raw','evidence_year':1300}
    c={'china':{'ecoregion_ids':[236],'minimum_cropland_fraction':.001,'maximum_elevation_m':1000,'management_position':.45,'active_rotation_fraction':.5,'harvests':1},
       'india':{'ecoregion_ids':[314],'minimum_cropland_fraction':.001,'maximum_rainfed_irrigated_ratio':.25,'summer_crops':['PML','SRG'],'summer_share':.5,'management_position':.6,'active_rotation_fraction':.75,'harvests':1}}
    cr={'kcal_kg':3500,'dry_fraction':1.,'recovery':1.,'seed_share':0.,'loss_share':0.}
    rc={'crop_order':['WHE','BRL','RCW','PML','SRG'],'crops':{x:cr for x in ['WHE','BRL','RCW','PML','SRG']}}
    (tmp_path/'configs').mkdir();(tmp_path/'configs/reconstruction.json').write_text(json.dumps(rc))
    eco=np.array([[236,236,236,314,314]])
    crop=np.array([[3,3,1,1,1]])
    extent=np.array([[.01,0.,.01,.01,0.]])
    class Time:
        units='years';calendar='standard'
        def __getitem__(self,key):return [1300]
    class Data:
        def __init__(self,*a):pass
        def __enter__(self):return {'time':Time(),'cropland':np.ma.array([extent])}
        def __exit__(self,*a):pass
    monkeypatch.setattr(cs,'Dataset',Data)
    monkeypatch.setattr(cs,'num2date',lambda *a:[SimpleNamespace(year=1300)])
    monkeypatch.setattr(cs,'configuration',lambda *a:c)
    monkeypatch.setattr(cs,'area_grid',lambda:np.ones_like(extent))
    monkeypatch.setattr(cs,'wc',lambda *a:np.full_like(extent,100))
    monkeypatch.setattr(cs,'read',lambda p:(eco if 'ecoregion' in str(p) else np.full_like(extent,2000.),{}))
    monkeypatch.setattr(cs,'write',lambda *a,**kw:None)
    monkeypatch.setattr(cs,'write_json',lambda *a,**kw:None)
    rf=np.ones_like(extent);ir=np.full_like(extent,10.)
    diagnostic={'rotation_fraction':np.full_like(extent,.23),'rainfed_headroom':np.full_like(extent,20.)}
    dry,wet,flags=cs.apply(tmp_path,cfg,np.ones_like(extent,dtype=bool),{},crop,rf,ir,diagnostic,tmp_path)
    assert flags.tolist()==[[1,0,0,2,0]]
    assert np.all(rf==1) and np.all(ir==10)
    assert dry[0,0]>1 and dry[0,3]>1
    np.testing.assert_allclose(dry[0,[1,2,4]],1)
    np.testing.assert_allclose(wet,10)
    assert crop.tolist()==[[3,3,1,1,1]]


def test_baseline_irrigation_is_not_displaced_by_management_on_other_fields():
    # All starting fields are baseline land. Changing another field-system
    # reference cannot reduce this existing irrigated capacity.
    b=.1;start=.1;served=.05;full=.3;maximum=.4;old_rf=1.;old_ir=5.;new_rf=3.;new_ir=5.;wild=.1
    current_fix,max_fix=cs.irrigation_corrections(b,served,full,old_rf,old_ir,new_rf,new_ir,wild)
    baseline=b*old_rf+(1-b)*wild
    old_start=baseline+(start-b)*(old_rf-wild)+served*(old_ir-old_rf)
    new_start=baseline+(start-b)*(new_rf-wild)+served*(new_ir-new_rf)+current_fix
    assert new_start==pytest.approx(old_start)
    old_max=baseline+(maximum-b)*(old_rf-wild)+full*(old_ir-old_rf)
    new_max=baseline+(maximum-b)*(new_rf-wild)+full*(new_ir-new_rf)+max_fix
    assert new_max>=old_max
