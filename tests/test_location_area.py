import numpy as np
import pandas as pd
import pytest
from historical_agriculture.location_area import equal_area

def fixture():
    return pd.DataFrame({
        "modelled_land":[True,True,False], "physical_location_ha":[100,200,np.nan],
        "eu5_start_population":[5,50,np.nan], "base_effective_cropland":[10,20,0],
        "starting_improvement_effective_cropland":[20,40,0],
        "maximum_improvement_effective_cropland":[40,80,0],
        "capacity_multiplier":[2,2,1], "starting_capacity":[60,120,0],
        "maximum_capacity":[100,200,0], "inert_capacity":[20,40,0],
        "starting_improvement_capacity":[40,80,0],
        "remaining_improvement_effective_cropland":[20,40,0],
        "remaining_capacity":[40,80,0]})

def test_equal_systems_ignore_size_and_preserve_total_and_ratios():
    d=fixture();e,m=equal_area(d)
    assert m["reference_area_ha"]==pytest.approx(150)
    assert e.starting_capacity.tolist()==pytest.approx([90,90,0])
    assert e.maximum_capacity.tolist()==pytest.approx([150,150,0])
    assert e.starting_capacity.sum()==pytest.approx(d.starting_capacity.sum())
    np.testing.assert_allclose(e.capacity_multiplier,d.capacity_multiplier)
    np.testing.assert_allclose(e.physical_location_ha,d.physical_location_ha)
    for col in ["starting","maximum"]:
        np.testing.assert_allclose(e[col+"_capacity"],
            (e.base_effective_cropland+e[col+"_improvement_effective_cropland"])*e.capacity_multiplier)
    assert e.starting_fill.iloc[0]==pytest.approx(5/90)
    assert e.starting_capacity.iloc[2]==0

def test_population_cannot_affect_equal_area_parameters():
    d=fixture();a,_=equal_area(d);d.eu5_start_population=1000000;b,_=equal_area(d)
    np.testing.assert_allclose(a.starting_capacity,b.starting_capacity)
    np.testing.assert_allclose(a.area_comparison_factor,b.area_comparison_factor)

def test_missing_modelled_area_is_rejected():
    d=fixture();d.loc[0,"physical_location_ha"]=0
    with pytest.raises(ValueError,match="physical area"):equal_area(d)


def test_base_land_floor_is_effective_units_and_adds_capacity_without_improvements():
    d=fixture();d['is_ownable']=[True,True,False]
    unfloored,_=equal_area(d,150)
    e,m=equal_area(d,150,1000)
    assert e.base_effective_cropland.tolist()==[1000,1000,0]
    assert e.base_land_floor_added_units.tolist()==[985,985,0]
    np.testing.assert_allclose(e.starting_capacity-unfloored.starting_capacity,[1970,1970,0])
    np.testing.assert_allclose(e.maximum_capacity-unfloored.maximum_capacity,[1970,1970,0])
    for col in ['starting_improvement_effective_cropland','maximum_improvement_effective_cropland','remaining_capacity','capacity_multiplier']:
        np.testing.assert_allclose(e[col],unfloored[col])
    assert m['base_land_floor_locations']==2
    assert e.starting_fill.iloc[0]==pytest.approx(5/2060)
    assert e.maximum_starting_ratio.iloc[0]==pytest.approx(2120/2060)
    d.loc[0,'base_effective_cropland']=2000
    e,_=equal_area(d,150,1000)
    assert e.base_effective_cropland.iloc[0]==3000
    with pytest.raises(ValueError,match='floor'):equal_area(d,150,-1)
