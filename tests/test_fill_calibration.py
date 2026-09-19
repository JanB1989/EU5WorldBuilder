import numpy as np
import pandas as pd
from scipy import sparse
from historical_agriculture.fill_calibration import capacity_proxy
from historical_agriculture.agricultural_game_calibration import convert
from historical_agriculture.fill_report import evaluate, rural_balance_diagnostic


def test_capacity_proxy_matches_converted_overlap_aggregation_and_scales_linearly():
    support = np.array([[0., .001], [.5, 2.]])
    reference = np.ones((2, 2))
    weights = sparse.csr_matrix(np.array([[1., 1., 0., 0.], [0., 0., .5, .5]]))  # km2 overlaps, row-major cells
    area_factor = np.array([2., .5])
    expected = np.asarray(weights @ convert(support, reference, 1 / 3).ravel()).ravel() * 100 * area_factor
    np.testing.assert_allclose(capacity_proxy(weights, support, reference, 1., 1 / 3, area_factor), expected)
    np.testing.assert_allclose(capacity_proxy(weights, support, reference, .25, 1 / 3, area_factor), .25 * expected)
    # exponent 1 is the identity conversion: plain area-weighted support
    np.testing.assert_allclose(capacity_proxy(weights, support, reference, 1., 1., area_factor),
                               np.asarray(weights @ support.ravel()).ravel() * 100 * area_factor)


def frame():
    return pd.DataFrame({'location_tag': list('abcdef'), 'is_ownable': [True] * 5 + [False],
        'province': ['p'] * 6, 'region': ['r'] * 6, 'macro_region': ['western_europe'] * 3 + ['north_asia'] * 3,
        'settlement_context': ['rural_or_unranked', 'rural_or_unranked', 'urban', 'rural_or_unranked', 'rural_or_unranked', 'rural_or_unranked'],
        'eu5_start_population': [75., 150., 900., 10., 0., np.nan], 'starting_capacity': [100., 100., 100., 100., 100., 0.],
        'maximum_capacity': [200.] * 5 + [0.], 'physical_location_ha': [1000.] * 6, 'source_starting_crop_ha': [100., 100., 100., 1., 1., 0.]})


def test_fill_evaluation_is_informational_and_population_free_in_targets():
    ev, table = evaluate(frame(), {'settled_median_fill': .75, 'rural_over_capacity_share': .05})
    s = ev['summary']
    assert s['global']['locations'] == 5 and s['urban']['over_capacity_locations'] == 1
    assert s['rural']['over_capacity_locations'] == 1 and s['settled_old_world_rural']['locations'] == 2
    assert s['settled_old_world_rural']['median_location_fill'] == 1.125
    assert ev['checks']['settled_median_fill']['passed'] is False and ev['informational']
    assert ev['population_is_formula_input'] is False
    assert table.settled_old_world.tolist() == [True, True, True, False, False]
    would = rural_balance_diagnostic(frame(), {'maximum_starting_fill': 1.5})
    assert would.location_tag.tolist() == [] or would.would_add_capacity.min() > 0
