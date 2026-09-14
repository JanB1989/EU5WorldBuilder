import numpy as np
import pytest
from historical_agriculture.water_boundary import requests,apply,REQUESTS,APPLIED
from historical_agriculture.water_management import KINDS,partition_settings
from historical_agriculture.improvement_distribution import allocate
from historical_agriculture.improvement_audit import reconcile_rounding
from historical_agriculture.location_area import equal_area
from test_water_management import supplied,config


def test_base_transfer_requires_cultivation_crop_gain_and_water_dependency():
    base=np.full(4,100.)
    settings=partition_settings(np.ones(4),np.zeros(4),np.zeros(4),np.zeros(4))
    out=requests(base,np.array([.8,0,.8,.8]),np.full(4,.1),np.array([.1,.1,0,.025]),settings,config())
    np.testing.assert_allclose(out['paddy_control'],[52,0,0,13])
    assert all(np.all(v==0) for k,v in out.items() if k!='paddy_control')


def test_natural_floodplain_is_not_automatically_infrastructure():
    settings=partition_settings(np.zeros(1),np.zeros(1),np.ones(1),np.ones(1))
    out=requests(np.array([100.]),np.ones(1),np.ones(1),np.ones(1),settings,config())
    assert sum(v.sum() for v in out.values())==0


def model_frame():
    d=supplied();d['physical_location_ha']=100.
    d['base_effective_cropland']=50.
    d['uncalibrated_base_capacity']=20.
    d['modelled_land']=True;d['is_ownable']=True;d['eu5_start_population']=0.
    for k in REQUESTS:d[k]=0.
    return d


CFG={'equal_reference_area_ha':500.,'equal_area_base_land_floor':1000.}


def test_transfer_conserves_totals_remaining_and_both_water_ledgers():
    before=model_frame();before[REQUESTS[1]]=40.
    after=apply(before,CFG);after=reconcile_rounding(after)
    for k in ('starting_capacity','maximum_capacity','remaining_capacity','capacity_multiplier'):
        np.testing.assert_array_equal(before[k],after[k])
    assert after.inert_capacity.iloc[0]==60
    assert after.starting_improvement_effective_cropland.iloc[0]==70
    assert after.maximum_improvement_effective_cropland.iloc[0]==120
    a,b=allocate(before),allocate(after)
    assert b.starting_paddy_control_improvement_capacity.iloc[0]==pytest.approx(a.starting_paddy_control_improvement_capacity.iloc[0]+40)
    assert b.starting_management_improvement_capacity.iloc[0]==pytest.approx(a.starting_management_improvement_capacity.iloc[0])
    for stage in ('starting','maximum'):
        assert b[f'{stage}_water_management_improvement_capacity'].iloc[0]==pytest.approx(a[f'{stage}_water_management_improvement_capacity'].iloc[0]+40)


def test_equal_area_floor_caps_transfer_without_creating_capacity():
    before=model_frame();before[REQUESTS[1]]=100.
    after=apply(before,CFG)
    assert after.base_water_transferred_capacity.iloc[0]==pytest.approx(80)
    a,_=equal_area(before,500.,1000.)
    b,_=equal_area(after,500.,1000.)
    assert b.base_effective_cropland.iloc[0]==pytest.approx(1000)
    for k in ('starting_capacity','maximum_capacity','base_land_floor_added_capacity'):
        np.testing.assert_allclose(a[k],b[k])
    assert b.base_water_transferred_capacity.iloc[0]==400
    np.testing.assert_allclose(b.pre_water_base_capacity,b.inert_capacity+b.base_water_transferred_capacity)


def test_invalid_requests_fail_and_total_ceiling_is_not_relaxed():
    d=model_frame();d[REQUESTS[0]]=10
    with pytest.raises(ValueError,match='Natural flooding'):apply(d,CFG)
    d=model_frame();d[REQUESTS[1]]=101
    with pytest.raises(ValueError,match='exceeds original base'):apply(d,CFG)


def test_comparison_preserves_location_ids_that_look_like_missing_values(tmp_path):
    import pandas as pd
    from historical_agriculture.water_boundary import report
    before=model_frame();before['location_tag']='NA';before['region']='test'
    after=apply(before,CFG)
    before,_=equal_area(before,500.,1000.);before=allocate(before)
    after,_=equal_area(after,500.,1000.);after=allocate(after)
    (tmp_path/'data/processed').mkdir(parents=True)
    before.to_csv(tmp_path/'data/processed/water_boundary_before.csv',index=False)
    result=report(tmp_path,tmp_path,after,'test')
    assert result['totals_conserved']
    assert result['base_floor_pass']
    assert pd.read_csv(tmp_path/'water_boundary_comparison.csv',keep_default_na=False).location_tag.iloc[0]=='NA'
