import numpy as np
import pandas as pd
import pytest
from historical_agriculture.improvement_distribution import allocate, KINDS, FIELDS
from historical_agriculture.improvement_audit import reconcile_rounding


def frame(start=(60., 30., 10.), remaining=(20., 40., 40.)):
    d = pd.DataFrame({f'{s}_{k}_capacity': [v] for s, values in
                      [('starting', start), ('remaining', remaining)]
                      for k, v in zip(KINDS, values)})
    d['inert_capacity'] = 100.
    d['starting_improvement_capacity'] = sum(start)
    d['remaining_capacity'] = sum(remaining)
    d['starting_capacity'] = 100. + sum(start)
    d['maximum_capacity'] = 100. + sum(start) + sum(remaining)
    d['capacity_multiplier'] = 2.
    d['starting_improvement_effective_cropland'] = sum(start)/2
    d['remaining_improvement_effective_cropland'] = sum(remaining)/2
    d['maximum_improvement_effective_cropland'] = (sum(start)+sum(remaining))/2
    return reconcile_rounding(d)


def test_maximum_is_starting_plus_remaining_without_changing_inputs():
    d = frame(); result = allocate(d)
    pd.testing.assert_frame_equal(d, result[d.columns])
    assert result.starting_clearing_improvement_share.iloc[0] == pytest.approx(.6)
    assert result.maximum_clearing_improvement_share.iloc[0] == pytest.approx(.4)
    for k in KINDS:
        assert result[f'maximum_{k}_improvement_units'].iloc[0] >= result[f'starting_{k}_improvement_units'].iloc[0]
    for stage in ('starting', 'remaining', 'maximum'):
        assert sum(result[f'{stage}_{k}_improvement_share'].iloc[0] for k in KINDS) == pytest.approx(1)


def test_zero_budget_is_explicit_and_future_only_budget_is_allocated():
    result = allocate(frame((0., 0., 0.)))
    assert result.starting_distribution_status.iloc[0] == 'no_improvement_budget'
    assert all(result[f'starting_{k}_improvement_share'].iloc[0] == 0 for k in KINDS)
    assert result.maximum_irrigation_improvement_share.iloc[0] == pytest.approx(.4)
    result = allocate(frame((0., 0., 0.), (0., 0., 0.)))
    assert result.maximum_distribution_status.iloc[0] == 'no_improvement_budget'
    assert result[FIELDS].notna().all().all()


def test_signed_management_is_rejected_instead_of_creating_false_shares():
    with pytest.raises(ValueError, match='Signed improvement'):
        allocate(frame((60., -10., 10.)))


def test_float32_residue_is_reconciled_to_unchanged_budget():
    d = frame((60., -1e-6, 10.)); result = allocate(d)
    assert result.starting_management_improvement_share.iloc[0] == 0
    assert sum(result[f'starting_{k}_improvement_units'].iloc[0] for k in KINDS) == pytest.approx(d.starting_improvement_effective_cropland.iloc[0])


def test_area_scaling_leaves_shares_unchanged():
    d = frame(); scaled = d.copy()
    for c in scaled:
        if c != 'capacity_multiplier': scaled[c] *= 17
    a, b = allocate(d), allocate(scaled)
    for s in ('starting', 'remaining', 'maximum'):
        for k in KINDS:
            assert np.allclose(a[f'{s}_{k}_improvement_share'], b[f'{s}_{k}_improvement_share'])
