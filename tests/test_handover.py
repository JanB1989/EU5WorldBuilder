import json
import numpy as np
import pandas as pd
import pytest
from historical_agriculture.handover import check, attribute_rows, building_types


def test_check_recomputes_model_from_levels_and_units():
    targets = pd.DataFrame({'attribute_flat_people': [1000., 2000.], 'starting_target_people': [1500., 2600.], 'maximum_target_people': [3000., 5000.]}, index=['a', 'b'])
    levels = pd.DataFrame({'location_tag': ['a', 'b', 'b'], 'building': ['x', 'x', 'y'], 'starting_levels': [1, 2, 1], 'cap_at_start': [4, 6, 2]})
    r = check(levels, {'x': 500., 'y': 300.}, targets)
    assert r['starting']['total_model'] == pytest.approx(1000 + 500 + 2000 + 1000 + 300)
    assert r['maximum']['total_model'] == pytest.approx(1000 + 2000 + 2000 + 3000 + 600)
    # inverse scaling leaves the model unchanged
    scaled = levels.assign(starting_levels=levels.starting_levels * 2, cap_at_start=levels.cap_at_start * 2)
    r2 = check(scaled, {'x': 250., 'y': 150.}, targets)
    assert r2['starting']['total_model'] == pytest.approx(r['starting']['total_model'])
    with pytest.raises(ValueError, match='Missing unit'):
        check(levels, {'x': 500.}, targets)


def test_attribute_rows_merge_capacity_and_goods_columns():
    coef = pd.DataFrame({'target': ['natural_capacity'] * 3 + ['maximum_capacity'] * 3, 'attribute': ['reference', 'climate', 'climate'] * 2,
                         'value': ['intercept', 'arid', 'oceanic'] * 2, 'people': [1000, -200, 100, 3000, -600, 300], 'share_of_reference': [1, -.2, .1, 3, -.6, .3], 'locations': [10, 4, 6] * 2})
    goods = pd.DataFrame({'good': ['wheat', 'wheat', 'incense'], 'attribute': ['reference', 'climate', 'climate'], 'value': ['intercept', 'oceanic', 'arid'], 'modifier': [0.05, 0.2, 0.4]})
    rows = attribute_rows(coef, goods, ['climate'])
    r = rows.set_index(['attribute', 'value'])
    assert r.loc[('climate', 'oceanic'), 'capacity_people'] == 100 and r.loc[('climate', 'oceanic'), 'output_wheat'] == 0.2
    assert np.isnan(r.loc[('climate', 'oceanic'), 'output_incense']) and r.loc[('climate', 'arid'), 'output_incense'] == 0.4
    assert bool(r.loc[('reference', 'intercept'), 'is_reference'])


def test_building_types_serialise_cap_equations():
    buildings = pd.DataFrame({'building': ['clearing'], 'unit_people_per_level': [5200.], 'eligible_locations': [100], 'users_at_start': [40], 'gate': ['[{"vegetation": ["forest"]}]'], 'level_limit': [20]})
    caps = pd.DataFrame({'building': ['clearing'] * 4, 'attribute': ['base', 'climate', 'climate', 'development'], 'value': ['reference', 'tropical', 'arid', 'per_point'], 'levels': [2, 3, 0, 0.03]})
    ledger = pd.DataFrame({'starting_clearing_capacity': [1000., 2000.], 'maximum_clearing_capacity': [4000., 6000.]})
    bt = building_types(buildings, caps, ledger)
    eq = json.loads(bt.cap_equation_json.iloc[0])
    assert eq['base_levels'] == 2 and eq['levels_per_development_point'] == 0.03 and eq['class_terms'] == [{'attribute': 'climate', 'value': 'tropical', 'levels': 3.0}]
    assert bt.starting_ledger_people.iloc[0] == 3000 and bt.maximum_ledger_people.iloc[0] == 10000
