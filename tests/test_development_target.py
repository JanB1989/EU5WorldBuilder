import numpy as np
import pandas as pd
import pytest
from historical_agriculture.development_target import development, checks, hash_map, saturate, components, used_land


def cfg():
    return {'weights': {'land_use_share': .4, 'feasible_utilisation': .2, 'improvement_share': .2, 'management_intensity': .2},
            'land_use_reference': .3, 'utilisation_saturation': 3.0, 'management_intensity_quantile': .9, 'management_intensity_reference': None,
            'grazing_equivalence': {'default': .15, 'by_climate': {'oceanic': .5}}, 'management_intensity_kinds': ['management', 'field_drainage', 'polders'],
            'capacity_percent_per_point': .01,
            'checks': {'p90_band': [25, 90], 'maximum': 100, 'expected_ordering': [['east_asia'], ['north_asia']], 'frontier_macro_regions': ['north_asia'],
                       'frontier_median_below': 25, 'spot_checks': {'a': [30, 100], 'zz': [0, 1]}}}


def frames():
    frame = pd.DataFrame({'location_tag': ['a', 'b', 'c'], 'province': ['p'] * 3, 'region': ['r'] * 3, 'macro_region': ['east_asia', 'north_asia', 'north_asia'],
                          'is_ownable': [True, True, False], 'settlement_context': ['urban', 'rural_or_unranked', 'rural_or_unranked'],
                          'climate': ['oceanic', 'arid', 'oceanic'],
                          'source_starting_crop_ha': [60., 5., 0.], 'maximum_crop_ha': [100., 100., 0.], 'grazing_area_ha': [0., 50., 0.], 'physical_location_ha': [100., 100., 100.]})
    ledger = pd.DataFrame({'location_tag': ['a', 'b', 'c'], 'natural_capacity': [100., 100., 0.], 'starting_ledger_total': [100., 5., 0.],
                           'starting_management_capacity': [80., 1., 0.], 'starting_field_drainage_capacity': [10., 0., 0.], 'starting_polders_capacity': [0., 2., 0.]})
    return frame, ledger


def test_used_land_applies_climate_equivalence_to_grazing():
    frame, _ = frames()
    used, g = used_land(frame, cfg())
    assert list(g) == [.5, .15, .5]
    assert used[1] == pytest.approx(5 + .15 * 50)
    humid = frame.copy(); humid.loc[1, 'climate'] = 'oceanic'
    assert used_land(humid, cfg())[0][1] == pytest.approx(5 + .5 * 50)
    no_grazing = frame.drop(columns='grazing_area_ha')
    assert np.array_equal(used_land(no_grazing, cfg())[0], [60., 5., 0.])


def test_components_and_development_formula():
    frame, ledger = frames()
    parts = components(frame, ledger, cfg())
    assert parts.loc[0, 'land_use_share'] == pytest.approx(-np.expm1(-0.6 / 0.3))
    assert parts.loc[1, 'land_use_share'] == pytest.approx(-np.expm1(-0.125 / 0.3))
    assert parts.loc[0, 'feasible_utilisation'] == pytest.approx(-np.expm1(-1.8))
    assert parts.loc[0, 'improvement_share'] == pytest.approx(0.5)
    # works per used hectare: a = 90 / 60, b = 3 / 12.5; the p90 reference is the larger, so a saturates further
    assert parts.attrs['management_intensity_kinds'] == ['management', 'field_drainage', 'polders']
    assert parts.loc[0, 'management_intensity'] > parts.loc[1, 'management_intensity'] > 0
    d = development(frame, ledger, cfg())
    a = d.set_index('location_tag')
    expected = 100 * min(1, .4 * parts.loc[0, 'land_use_share'] + .2 * parts.loc[0, 'feasible_utilisation'] + .2 * .5 + .2 * parts.loc[0, 'management_intensity'])
    assert a.loc['a', 'development'] == pytest.approx(expected)
    assert a.loc['c', 'development'] == 0  # non-ownable
    assert d.development.between(0, 100).all()
    assert list(d.grazing_equivalence) == [.5, .15, .5] and a.loc['b', 'used_land_ha'] == pytest.approx(12.5)
    assert np.array_equal(saturate([0., 1.], 0.), [0., 0.])
    with pytest.raises(ValueError, match='sum to one'):development(frame, ledger, {**cfg(), 'weights': {'land_use_share': 1, 'improvement_share': 1}})


def test_grazing_lifts_a_pasture_economy_without_touching_arable_locations():
    frame, ledger = frames()
    fixed = {**cfg(), 'management_intensity_reference': 1.0}  # pin the global p90 so only the grazing input differs
    with_grazing = development(frame, ledger, fixed).set_index('location_tag').development
    dry = development(frame.assign(grazing_area_ha=0.), ledger, fixed).set_index('location_tag').development
    assert with_grazing['b'] > dry['b'] and with_grazing['a'] == pytest.approx(dry['a'])


def test_checks_detect_ordering_frontier_and_spot_violations_and_hash_is_stable():
    frame, ledger = frames()
    d = development(frame, ledger, cfg())
    r = checks(d, cfg())
    assert r['regional_ordering']['passed'] and r['frontier_median']['passed'] and r['spot_checks']['locations']['a']['passed']
    assert r['spot_checks']['locations']['zz']['passed'] is None
    swapped = d.copy(); swapped.loc[swapped.location_tag == 'b', 'development'] = 99.
    r2 = checks(swapped, cfg())
    assert not r2['regional_ordering']['passed'] and not r2['frontier_median']['passed'] and not r2['all_passed']
    assert hash_map(d) == hash_map(d.copy()) and hash_map(d) != hash_map(swapped)
