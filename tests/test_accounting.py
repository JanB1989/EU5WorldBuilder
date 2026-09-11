import numpy as np
import pytest
from historical_agriculture.accounting import annual_food, labour_days, upper_system, historical_position

def test_irrigation_failure_keeps_rainfed_upper():
    upper,system=upper_system([1200,0,200],[0,800,300])
    np.testing.assert_array_equal(upper,[1200,800,300])
    np.testing.assert_array_equal(system,[1,2,2])

def test_missing_scenario_is_not_certified_as_best():
    upper,system=upper_system([np.nan,0],[10,0])
    assert np.isnan(upper[0]) and system[0]==255
    assert upper[1]==0 and system[1]==0

def test_dry_paddy_to_annual_food_has_one_rotation_factor():
    crop={'dry_fraction':.87,'recovery':.65,'kcal_kg':3600,'seed_share':.02,'loss_share':.1}
    mass,gross,net=annual_food(870,crop,2,.25)
    assert mass==500
    assert gross==1170000
    assert net==pytest.approx(1031940)
    assert labour_days(150,2,.25,10)==85

def test_zero_fallow_output_retains_maintenance_work():
    crop={'dry_fraction':1,'recovery':1,'kcal_kg':1000,'seed_share':0,'loss_share':0}
    assert annual_food(100,crop,1,0)[2]==0
    assert labour_days(100,1,0,5)==5
    np.testing.assert_allclose(labour_days(100,np.array([1,2]),np.array([1,.5]),np.array([0,5])),[100,105])

def test_invalid_conversion_cannot_create_food():
    crop={'dry_fraction':0,'recovery':1,'kcal_kg':1000,'seed_share':0,'loss_share':0}
    with pytest.raises(ValueError):annual_food(1,crop,1,1)

def test_outside_benchmarks_remain_outside():
    np.testing.assert_allclose(historical_position([0,200,400],100,300),[-.5,.5,1.5])
    assert np.isnan(historical_position(100,100,100))
    assert np.isnan(historical_position(100,200,100))
