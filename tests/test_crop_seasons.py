import numpy as np
import pytest
from historical_agriculture.crop_seasons import select,demand

WHEAT={'months':5,'minimum_temperature_c':5,'maximum_temperature_c':32,'preferred_temperature_c':[12,22]}

def test_hot_winter_cereal_season_and_hemisphere():
    t=np.array([14,16,20,25,30,34,36,35,31,26,20,15.])[:,None]
    a,s,f=select(t,np.zeros_like(t),np.full_like(t,100),WHEAT)
    assert s.item()==10  # November through March; not the hot summer.
    assert a[:,0].tolist()==[True,True,True,False,False,False,False,False,False,False,True,True]
    south,ss,_=select(np.roll(t,6,axis=0),np.zeros_like(t),np.full_like(t,100),WHEAT)
    assert ss.item()==4 and np.array_equal(south,np.roll(a,6,axis=0))
    assert not f.item()

def test_warm_crop_follows_rains_when_thermal_conditions_equal():
    t=np.full((12,1),25.);p=np.zeros_like(t);p[5:9]=150
    spec={'months':4,'minimum_temperature_c':15,'maximum_temperature_c':40,'preferred_temperature_c':[20,30]}
    a,s,f=select(t,p,np.full_like(t,100),spec)
    assert s.item()==5 and a.sum()==4 and not f.item()

def test_unknown_and_incompatible_calendars_are_flagged():
    t=np.full((12,2),-10.);t[0,1]=np.nan
    a,_,f=select(t,np.zeros_like(t),np.ones_like(t),WHEAT)
    assert f.all() and np.all(a.sum(axis=0)==5)

def test_water_floor_paddy_and_inactive_months():
    a=np.zeros((12,2),bool);a[2:7]=True
    d=demand(a,np.zeros_like(a,float),np.array([1,7]),100,60)
    assert np.allclose(d.sum(axis=0),[100,400])
    assert not d[~a].any()
    with pytest.raises(ValueError):demand(a,np.full_like(a,-1,float),np.array([1,7]),100,60)

def test_perennial_and_no_crop():
    spec={**WHEAT,'months':12}
    a,_,_=select(np.full((12,1),18.),np.zeros((12,1)),np.ones((12,1)),spec)
    assert a.all()
    assert demand(np.zeros((12,1),bool),np.zeros((12,1)),np.array([0]),100,60).sum()==0
