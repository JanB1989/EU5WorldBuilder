import numpy as np
from historical_agriculture.crop_water_response import requirements, seasonal_response


def test_crop_stages_reduce_initial_demand_and_preserve_winter_wrap():
    active=np.zeros((12,1),bool);active[[10,11,0,1],0]=True
    et=np.full((12,1),100.)
    result=requirements(active,et,et,np.array([1]),{'1':[.35,.75,1.15,.45]},0,0)
    np.testing.assert_allclose(result[[10,11,0,1],0],[35,75,115,45])
    assert result.sum()==270


def test_rain_and_irrigation_never_double_count_and_paddy_is_separate():
    active=np.ones((12,2),bool);et=np.full((12,2),100.)
    result=requirements(active,et,np.zeros_like(et),np.array([1,7]),{'1':[.5]*4,'7':[1]*4},0,60)
    assert result[:,0].sum()==0
    assert result[:,1].sum()==720


def test_seasonal_supply_is_not_destroyed_by_one_dry_month_or_invented():
    r=seasonal_response(np.array([300.,0.,400.]),np.full(3,400.),np.array([0.,0.,1.]),.25)
    np.testing.assert_allclose(r,[.5625,0,1])
    assert np.all(r<=np.array([.75,0,1]))
    strict=seasonal_response(np.array([300.]),np.array([400.]),np.array([0.]),1)
    assert strict[0]==0
