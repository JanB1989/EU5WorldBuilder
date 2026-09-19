import numpy as np
import pandas as pd
import pytest
from historical_agriculture.capacity_targets import derive, validate_targets, validate_ledger, LEDGER_KINDS


def allocated_frame():
    n = 3
    d = pd.DataFrame({
        'location_tag': ['a', 'b', 'c'], 'location_id': [1, 2, 3], 'province': ['p'] * n, 'region': ['r'] * n,
        'super_region': ['s'] * n, 'macro_region': ['m'] * n, 'is_ownable': [True, True, False], 'modelled_land': [True, True, False],
        'physical_location_ha': [100., 200., np.nan], 'inert_capacity': [20., 40., 0.], 'starting_capacity': [60., 120., 0.],
        'maximum_capacity': [100., 200., 0.], 'unbounded_reference_multiplier': [1.5, 0.2, 1.], 'capacity_multiplier': [1.5, .25, 1.],
        'base_effective_cropland': [1., 2., 0.], 'evidence_status': ['x'] * n, 'source_rule': ['y'] * n,
        'eu5_start_population': [5., 50., np.nan], 'starting_wm_low_capacity': [1., 1., 0.]})
    starting = {'clearing': [10., 20., 0.], 'management': [20., 40., 0.], 'water_supply': [4., 8., 0.], 'paddy_control': [3., 6., 0.],
                'flood_bunds': [1., 2., 0.], 'field_drainage': [1., 2., 0.], 'polders': [1., 2., 0.]}
    remaining = {'clearing': [10., 20., 0.], 'management': [10., 20., 0.], 'water_supply': [5., 10., 0.], 'paddy_control': [5., 10., 0.],
                 'flood_bunds': [4., 8., 0.], 'field_drainage': [3., 6., 0.], 'polders': [3., 6., 0.]}
    for kind in LEDGER_KINDS:
        d[f'starting_{kind}_improvement_capacity'] = starting[kind]
        d[f'maximum_{kind}_improvement_capacity'] = np.add(starting[kind], remaining[kind])
        d[f'starting_{kind}_improvement_units'] = np.divide(starting[kind], d.capacity_multiplier)
    return d


def test_targets_are_people_without_population_and_ledger_is_disjoint_and_exact():
    targets, ledger, diagnostics = derive(allocated_frame())
    assert 'eu5_start_population' not in targets and 'eu5_start_population' not in ledger
    assert targets.natural_capacity.tolist() == [20., 40., 0.]
    assert targets.starting_improvement_capacity.tolist() == [40., 80., 0.]
    assert targets.remaining_capacity.tolist() == [40., 80., 0.]
    checks = validate_ledger(ledger)
    assert checks['disjoint_and_exact']
    assert ledger.starting_ledger_total.tolist() == [40., 80., 0.]
    assert np.allclose(ledger.starting_residual, 0) and np.allclose(ledger.maximum_residual, 0)
    assert checks['starting']['by_kind']['management'] == 60.
    assert 'capacity_multiplier' in diagnostics and 'starting_wm_low_capacity' in diagnostics
    assert 'starting_clearing_improvement_units' in diagnostics
    inv = pd.DataFrame({'location_tag': ['a', 'b', 'c']})
    assert validate_targets(targets, inv)['ownable_locations'] == 2


def test_ordering_violations_and_ledger_gaps_are_rejected():
    targets, ledger, _ = derive(allocated_frame())
    bad = targets.copy(); bad.loc[0, 'starting_capacity'] = 10.
    with pytest.raises(ValueError, match='natural <= starting <= maximum'):validate_targets(bad)
    bad = targets.copy(); bad['eu5_start_population'] = 1.
    with pytest.raises(ValueError, match='Population'):validate_targets(bad)
    gap = ledger.copy(); gap.loc[0, 'starting_clearing_capacity'] = 0.
    with pytest.raises(ValueError, match='does not sum'):validate_ledger(gap)
    neg = ledger.copy(); neg.loc[0, 'maximum_polders_capacity'] = 0.; neg.loc[0, 'maximum_clearing_capacity'] += 4.
    with pytest.raises(ValueError, match='Maximum ledger below starting'):validate_ledger(neg)
    with pytest.raises(ValueError, match='allocated location columns'):derive(allocated_frame().drop(columns=['starting_polders_improvement_capacity']))
