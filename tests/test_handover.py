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


def test_attribute_rows_merge_capacity_and_goods_columns(monkeypatch):
    monkeypatch.setattr('historical_agriculture.handover.game_keys', lambda: {('climate', 'arid'): 'arid'})
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


def test_location_buildings_ledger_follows_split_and_extension_kinds():
    from historical_agriculture.handover import location_buildings
    from historical_agriculture.building_assignment import building_ledger
    d = pd.DataFrame({'climate': ['arid', 'tropical'], 'river_level': ['0', '2'], 'is_adjacent_to_lake': ['False', 'False'],
                      'natural_capacity': [100., 200.]}, index=pd.Index(['a', 'b'], name='location_tag'))
    raw = pd.DataFrame({'location_tag': ['a', 'b'], 'natural_capacity': [100., 200.], 'maximum_capacity': [400., 1200.]})
    for k, (s, m) in {'water_supply': ([10., 0.], [300., 0.]), 'paddy_control': ([0., 50.], [0., 1000.])}.items():
        raw[f'starting_{k}_capacity'] = s; raw[f'maximum_{k}_capacity'] = m
    cfg = {'split_kinds': {'paddy_control': {'paddy_fields': 0.5, 'paddy_water_control': 0.5}},
           'extensions': {'oasis_irrigation': {'enabled': True, 'gate': [{'climate': ['arid'], 'river_level': ['0']}]}}}
    led = building_ledger(d, raw, cfg)
    kinds = ['water_supply', 'oasis_irrigation', 'paddy_fields', 'paddy_water_control']
    assign = pd.DataFrame(index=d.index)
    for k in kinds:
        assign[f'{k}_levels_start'] = 0; assign[f'{k}_cap'] = 1; assign[f'{k}_cap_at_reference'] = 1
    lb = location_buildings(assign, led, kinds).set_index(['location_tag', 'building']).maximum_ledger_people
    assert lb[('b', 'paddy_fields')] == 500 and lb[('b', 'paddy_water_control')] == 500
    assert lb[('a', 'oasis_irrigation')] == 300 and lb[('a', 'water_supply')] == 0
    # identity: natural + every building's maximum ledger = the location's maximum, for every type
    total = lb.groupby(level=0).sum()
    np.testing.assert_allclose((raw.set_index('location_tag').natural_capacity + total).to_numpy(), raw.maximum_capacity.to_numpy())


def test_published_handover_ledger_identity():
    """Every location of the published handover: natural + summed maximum ledger people = maximum target,
    and every improvement type carries its own ledger total (paddy split, oasis carve-out)."""
    from pathlib import Path
    d = Path(__file__).resolve().parents[1] / 'artifacts/handover/latest'
    if not (d / 'location_buildings.csv').exists():
        pytest.skip('no published handover')
    # the location tag 'nan' (Nan, Indochina) must stay a string
    lb = pd.read_csv(d / 'location_buildings.csv', keep_default_na=False); lt = pd.read_csv(d / 'location_targets.csv', keep_default_na=False).set_index('location_tag')
    bt = pd.read_csv(d / 'building_types.csv').set_index('building')
    led = lb.groupby('location_tag').maximum_ledger_people.sum().reindex(lt.index).fillna(0.)
    rows = lb.groupby('location_tag').size().reindex(lt.index).fillna(0.)
    gap = (lt.maximum_target_people - lt.natural_target_people - led).abs()
    # each CSV value is rounded to 0.1 people
    assert (gap <= 0.1 * (rows + 2) + 1e-6).all(), gap[gap > 0.1 * (rows + 2)].head()
    per_type = lb.groupby('building').maximum_ledger_people.sum()
    for b in bt.index:
        assert np.isfinite(bt.loc[b, 'maximum_ledger_people']), b
        assert per_type.get(b, 0.) == pytest.approx(bt.loc[b, 'maximum_ledger_people'], rel=1e-6, abs=1e3), b
    assert per_type.get('paddy_fields', 0.) > 0 and per_type.get('paddy_water_control', 0.) > 0
