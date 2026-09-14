import numpy as np
import pandas as pd
import pytest
from historical_agriculture.rural_balance import apply, validate

SETTINGS={'maximum_starting_fill':1.5}


def fixture():
    n=6
    return pd.DataFrame({
        'is_ownable':[True,True,True,True,True,False],
        'settlement_context':['rural_or_unranked']*4+['urban','rural_or_unranked'],
        'eu5_start_population':[300,150,149,0,30000,np.nan],
        'capacity_multiplier':[2.]*n,'base_effective_cropland':[10.]*n,
        'inert_capacity':[20.]*n,'starting_capacity':[100.]*n,'maximum_capacity':[200.]*n,
        'starting_improvement_effective_cropland':[40.]*n,
        'maximum_improvement_effective_cropland':[90.]*n,
        'remaining_improvement_effective_cropland':[50.]*n,'remaining_capacity':[100.]*n,
        'pre_water_base_capacity':[25.]*n,'base_water_transferred_capacity':[5.]*n,
        'physical_location_ha':[250.]*n,'starting_crop_ha':[8.]*n,
        'starting_served_ha':[2.]*n,'starting_capacity_low':[75.]*n,
        'starting_capacity_high':[125.]*n})


def test_allowance_boundary_scope_and_full_accounting():
    d=fixture();saved=d.copy(deep=True);e=apply(d,SETTINGS)
    assert e.rural_balance_added_capacity.tolist()==[100,0,0,0,0,0]
    assert e.rural_balance_added_units.tolist()==[50,0,0,0,0,0]
    assert e.starting_capacity.iloc[0]==200
    assert e.maximum_capacity.iloc[0]==300
    assert e.base_effective_cropland.iloc[0]==60
    for stage in ['starting','maximum']:
        np.testing.assert_allclose(e[f'{stage}_capacity'],
            (e.base_effective_cropland+e[f'{stage}_improvement_effective_cropland'])*e.capacity_multiplier)
    for col in ['capacity_multiplier','remaining_capacity','remaining_improvement_effective_cropland',
                'starting_improvement_effective_cropland','maximum_improvement_effective_cropland',
                'physical_location_ha','starting_crop_ha','starting_served_ha']:
        pd.testing.assert_series_equal(e[col],d[col])
    np.testing.assert_allclose(e.pre_water_base_capacity-e.inert_capacity,e.base_water_transferred_capacity)
    assert e.starting_capacity_low.iloc[0]==175
    assert e.starting_capacity_high.iloc[0]==225
    pd.testing.assert_frame_equal(d,saved)
    assert validate(e,SETTINGS)['affected_locations']==1


def test_invalid_population_and_repeat_application_fail_loudly():
    d=fixture();d.loc[0,'eu5_start_population']=np.nan
    with pytest.raises(ValueError,match='population'):apply(d,SETTINGS)
    with pytest.raises(ValueError,match='already applied'):apply(apply(fixture(),SETTINGS),SETTINGS)
    with pytest.raises(ValueError,match='fill limit'):apply(fixture(),{'maximum_starting_fill':0})


def test_tampered_allowance_fails_validation():
    e=apply(fixture(),SETTINGS);e.loc[4,'rural_balance_added_capacity']=100
    with pytest.raises(AssertionError):validate(e,SETTINGS)


def test_export_precision_preserves_ceiling(tmp_path):
    d=fixture();d.loc[0,'eu5_start_population']=341520;d.loc[0,'capacity_multiplier']=1.319802
    # Reconcile the synthetic input's units to the changed multiplier.
    d['base_effective_cropland']=d.inert_capacity/d.capacity_multiplier
    d['starting_improvement_effective_cropland']=(d.starting_capacity-d.inert_capacity)/d.capacity_multiplier
    d['maximum_improvement_effective_cropland']=(d.maximum_capacity-d.inert_capacity)/d.capacity_multiplier
    e=apply(d,SETTINGS);p=tmp_path/'values.csv';e.to_csv(p,index=False,float_format='%.15g')
    assert validate(pd.read_csv(p),SETTINGS)['passed']
