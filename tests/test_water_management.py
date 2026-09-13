import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from historical_agriculture.water_management import (
    KINDS, RAW_COLUMNS, partition_settings, transfers, validate)
from historical_agriculture.improvement_distribution import allocate
from test_improvement_distribution import frame


def config():
    return json.loads((Path(__file__).resolve().parents[1]/'configs/water_management.json').read_text())


def supplied(start=(60.,30.,10.), remaining=(20.,40.,40.)):
    d=frame(start,remaining)
    settings=partition_settings(np.array([.4]),np.array([.3]),np.array([.5]),np.array([.8]))
    for stage, values in [('starting',start),('remaining',remaining)]:
        a,c,m=transfers(np.array([values[0]]),np.array([values[1]]),settings,config())
        for k,v in a.items(): d[f'{stage}_wm_{k}_capacity']=v
        d[f'{stage}_wm_clearing_transfer_capacity']=c
        d[f'{stage}_wm_management_transfer_capacity']=m
        for b,f in [('low',.5),('high',1.5)]:
            _,c,m=transfers(np.array([values[0]]),np.array([values[1]]),settings,config(),strength=f)
            d[f'{stage}_wm_{b}_capacity']=c+m
    return d


def test_overlapping_settings_partition_not_stack():
    a=partition_settings(np.ones(3),np.ones(3),np.ones(3),np.ones(3))
    np.testing.assert_array_equal(a['paddy_control'],1)
    np.testing.assert_array_equal(sum(a.values()),1)
    for k in ('polders','flood_bunds','field_drainage'):
        np.testing.assert_array_equal(a[k],0)
    with pytest.raises(ValueError): partition_settings(np.array([np.nan]),0,0,0)


def test_reclassification_preserves_base_totals_and_supply():
    d=supplied(); out=allocate(d)
    for k in ['starting_capacity','maximum_capacity','inert_capacity','capacity_multiplier']:
        pd.testing.assert_series_equal(d[k],out[k])
    assert out.starting_water_supply_improvement_capacity.iloc[0]==pytest.approx(10)
    assert out.starting_water_management_improvement_capacity.iloc[0]>10
    assert out.starting_clearing_improvement_capacity.iloc[0]<60
    assert out.starting_management_improvement_capacity.iloc[0]<30
    assert validate(out)
    for k in KINDS:
        assert out[f'maximum_{k}_improvement_capacity'].iloc[0]>=out[f'starting_{k}_improvement_capacity'].iloc[0]


def test_zero_and_future_only_improvements_have_complete_values():
    out=allocate(supplied((0.,0.,0.)))
    assert all(out[f'starting_{k}_improvement_capacity'].iloc[0]==0 for k in KINDS)
    assert out.maximum_water_management_improvement_capacity.iloc[0]>0
    out=allocate(supplied((0.,0.,0.),(0.,0.,0.)))
    assert validate(out)


def test_incomplete_native_ledger_cannot_silently_use_legacy():
    d=supplied().drop(columns=RAW_COLUMNS[-1])
    with pytest.raises(ValueError,match='Incomplete native'): allocate(d)
    d=supplied();d[RAW_COLUMNS[-1]]=np.nan
    with pytest.raises(ValueError,match='Missing native'): allocate(d)


def test_sensitivity_changes_attribution_not_available_support():
    out=allocate(supplied())
    for stage in ('starting','remaining','maximum'):
        assert out[f'{stage}_water_management_capacity_low'].iloc[0]<out[f'{stage}_water_management_improvement_capacity'].iloc[0]<out[f'{stage}_water_management_capacity_high'].iloc[0]
    bad=out.copy();bad['starting_paddy_control_improvement_capacity']+=100
    with pytest.raises(AssertionError):validate(bad)


def test_area_conversion_scales_each_transfer_once():
    from historical_agriculture.location_area import equal_area
    d=supplied()
    d['base_effective_cropland']=50.
    d['modelled_land']=True;d['is_ownable']=True
    d['physical_location_ha']=100.;d['eu5_start_population']=0.
    d['uncalibrated_base_capacity']=100.
    a=allocate(d)
    equal,_=equal_area(d,reference_area=500.,base_land_floor=1000.)
    b=allocate(equal)
    for stage in ('starting','remaining','maximum'):
        for kind in KINDS:
            key=f'{stage}_{kind}_improvement_capacity'
            np.testing.assert_allclose(b[key],a[key]*5)
    # A game base floor cannot leak into water attribution or its bounds.
    np.testing.assert_allclose(b.starting_water_management_capacity_low,a.starting_water_management_capacity_low*5)


def test_all_chosen_types_have_paired_viewer_maps():
    from historical_agriculture.location_reporting import WATER_METRICS,HTML
    assert len(WATER_METRICS)==10
    for stage in ('starting','maximum'):
        for kind in KINDS:
            assert any(m[0]==f'{stage}_{kind}_improvement_capacity' for m in WATER_METRICS)
    assert 'tabWater' in HTML
    assert 'units × location multiplier' in HTML


def test_nonsettlement_csv_blank_coverage_is_explicit_but_ownable_gap_fails():
    d=supplied();d['wm_inferred_fraction']='';d['is_ownable']=False
    out=allocate(d)
    assert out.wm_inferred_fraction.iloc[0]==0
    d['is_ownable']=True
    with pytest.raises(ValueError,match='Missing ownable water-evidence coverage'):
        allocate(d)


def test_native_fractional_resampling_keeps_small_wet_shares_and_missing():
    from historical_agriculture.water_management_inputs import mean_blocks
    a=np.array([[0,1,255,255],[0,0,255,255],[100,255,0,0],[255,255,0,0]],dtype=np.uint8)
    out=mean_blocks(a,2,255)
    assert out[0,0]==pytest.approx(.25)
    assert out.mask[0,1]
    assert out[1,0]==100
    assert out[1,1]==0
    assert not out.mask[1,1]
