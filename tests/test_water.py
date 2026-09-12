import numpy as np
import pytest
from historical_agriculture.water_balance import bucket,route,topology,reference_et0,DAYS
from historical_agriculture.water import area_grid,SHAPE

def test_snow_and_soil_balance_conserve_every_month():
    p=np.full((12,2),40.);e=np.full((12,2),60.)
    t=np.tile(np.array([-5,-5,0,5,10,20,25,20,15,5,0,-5])[:,None],(1,2))
    b=bucket(p,e,t)
    assert np.max(abs(b['residual']))<1e-5
    assert np.allclose(b['eta']+b['deficit'],e)
    assert np.all((b['soil']>=0)&(b['soil']<=100))
    assert b['snow'][1,0]>b['snow'][0,0]
    assert b['deficit'][0,0]>0

def test_wet_and_dry_reference_limits():
    e=np.full((12,1),50.);t=e.copy()
    wet=bucket(e*3,e,t);dry=bucket(e*0,e,t)
    assert np.all(wet['deficit']==0)
    assert np.all(dry['deficit']==50)
    assert wet['soil_cycle_error_mm']==0

def test_monthly_water_not_carried_between_months():
    q=np.array([[10.,0],[0,0]])
    r=route(q,np.array([[0.,0],[0,20.]]),[1,-1],protected_fraction=0)
    assert r['allocated'].sum()==0
    assert r['outflow'][0,1]==10
    assert np.allclose(r['residual'],0)

def test_upstream_withdrawal_reduces_downstream_water():
    r=route(np.array([[100.,0,20]]),np.array([[30.,100,100]]),[1,2,-1],protected_fraction=.6)
    assert np.allclose(r['allocated'],[[30,10,8]])
    assert np.allclose(r['residual'],0)
    assert r['allocated'].sum()==48

def test_extension_preserves_downstream_existing_users():
    q=np.array([[100.,0,0]])
    base=route(q,np.array([[0.,0,30]]),[1,2,-1],protected_fraction=.6)
    r=route(q,np.array([[100.,100,30]]),[1,2,-1],protected_fraction=.6,baseline=base['allocated'])
    assert np.allclose(r['allocated'],[[10,0,30]])
    assert np.allclose(r['residual'],0)

def test_branching_river_global_water_accounting():
    rng=np.random.default_rng(92);q=rng.uniform(0,100,(12,4));d=rng.uniform(0,100,(12,4))
    down=[2,2,3,-1]
    r=route(q,d,down);x=route(q,d*3,down,baseline=r['allocated'])
    assert np.allclose(r['residual'],0,atol=1e-10)
    assert np.allclose(x['residual'],0,atol=1e-10)
    assert np.all(x['allocated']>=r['allocated']-1e-10)
    assert np.all(x['outflow']>=-1e-10)

def test_topology_rejects_cycles():
    with pytest.raises(ValueError,match='cycle'):topology([1,0])
    with pytest.raises(ValueError):topology([5,-1])

def test_reference_et0_units_and_water_demand_response():
    # Typical warm, sunny conditions: daily reference evaporation of a few mm,
    # not thousands from forgetting kJ -> MJ or multiplying days twice.
    t=np.array([15.,15.])
    result=reference_et0(t,t+10,np.array([20000.,20000.]),np.array([2.,2.]),np.array([1.2,2.]),np.array([100.,100.]),np.array([30.,30.]),5)
    assert np.all((result/DAYS[5]>2)&(result/DAYS[5]<8))
    assert result[0]>result[1]

def test_cell_area_is_only_geometric_and_additive():
    a=area_grid()
    assert a.shape==SHAPE
    assert np.isclose(a.sum(),4*np.pi*6371.0088**2)
    assert a[1080,0]>a[100,0]


def test_transmission_losses_and_priority_reconcile():
    q=np.array([[100.,0.,0.]])
    survival=np.array([1.,.5,1.])
    base=route(q,np.array([[0.,0.,15.]]),[1,2,-1],protected_fraction=.6,survival=survival)
    upper=route(q,np.array([[100.,100.,15.]]),[1,2,-1],protected_fraction=.6,survival=survival,baseline=base['allocated'])
    assert np.allclose(upper['allocated'],[[10,0,15]])
    assert np.allclose(upper['transmission_loss'],[[0,15,0]])
    assert np.allclose(upper['residual'],0)

def test_tiny_net_water_input_has_no_spinup_bias():
    e=np.full((12,1),40.)
    p=e.copy();p[0]=.1;p[1]=80.01
    b=bucket(p,e,e)
    assert b['soil_cycle_error_mm']<1e-8
    assert b['deficit'].sum()==0

def test_periodic_bucket_matches_long_explicit_run():
    rng=np.random.default_rng(7)
    p=rng.uniform(0,120,(12,30));e=rng.uniform(20,90,(12,30))
    b=bucket(p,e,np.full_like(e,20))
    soil=np.zeros(30)
    for year in range(500):
        expected=[]
        for m in range(12):
            eta=np.minimum(e[m],soil+p[m]);soil=np.clip(soil+p[m]-eta,0,100)
            expected.append(e[m]-eta)
    assert np.allclose(b['deficit'],expected,atol=1e-5)
    assert b['soil_cycle_error_mm']<1e-8
