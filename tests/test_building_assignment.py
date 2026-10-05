import numpy as np
import pandas as pd
from historical_agriculture.building_assignment import choose_unit, gate, assign


def test_unit_choice_recovers_exact_multiples_and_gate_rules():
    unit, info = choose_unit(np.array([3000., 6000., 9000., 12000., 0.]), 20, [0.3, 0.5, 0.7])
    assert abs(unit - 3000) < 1e-6 or abs(info['captured_within_25_share'] - 1) < 1e-9
    d = pd.DataFrame({'climate': ['tropical', 'arctic'], 'topography': ['flatland', 'flatland'], 'is_coastal': ['True', 'False']})
    assert gate(d, [{'climate': ['tropical'], 'topography': ['flatland']}]).tolist() == [True, False]
    assert gate(d, [{'climate': ['arctic']}, {'is_coastal': ['True']}]).tolist() == [True, True]
    assert gate(d, []).tolist() == [True, True]


def test_assignment_uses_ledger_levels_below_caps_and_fits_no_per_location_term():
    rng = np.random.default_rng(0); n = 120
    d = pd.DataFrame({'climate': rng.choice(['tropical', 'continental'], n), 'topography': ['flatland'] * n, 'vegetation': rng.choice(['forest', 'grasslands'], n),
                      'fertility': rng.choice(['moderate', 'high'], n), 'river_level': rng.choice(['0', '3'], n), 'is_coastal': ['False'] * n, 'is_adjacent_to_lake': ['False'] * n},
                     index=[f'l{i}' for i in range(n)])
    ledger = pd.DataFrame({'location_tag': d.index})
    for kind in ['clearing', 'management', 'water_supply', 'paddy_control', 'flood_bunds', 'field_drainage', 'polders']:
        base = np.where(d.vegetation.eq('forest'), 4000., 0.) if kind == 'clearing' else np.where(d.river_level.eq('3'), 2000., 0.) if kind == 'water_supply' else 1000. * (kind == 'management')
        ledger[f'starting_{kind}_capacity'] = base * rng.integers(0, 3, n)
        ledger[f'maximum_{kind}_capacity'] = ledger[f'starting_{kind}_capacity'] + base * rng.integers(0, 4, n)
    dev = pd.Series(rng.uniform(0, 100, n), index=d.index)
    cfg = {'cap_features': ['climate', 'vegetation', 'fertility', 'river_level'], 'reference_classes': {'climate': 'continental', 'vegetation': 'grasslands', 'fertility': 'moderate', 'river_level': '0'},
           'ordinal': {'fertility': ['moderate', 'high'], 'river_level': ['0', '3']}, 'signed_cap_features': ['climate', 'vegetation', 'fertility'], 'level_limit': 20, 'envelope_quantile': 0.9, 'capacity_percent_per_point': 0.01,
           'unit_quantiles': [0.5, 0.7, 0.9], 'max_levels_per_development_point': 0.2, 'gates': {'clearing': [{'vegetation': ['forest']}], 'water_supply': [{'river_level': ['3']}], 'management': []}}
    out, buildings, caps = assign(d, ledger, dev, cfg)
    b = buildings.set_index('building')
    assert b.loc['clearing', 'ungated_ledger_share'] == 0 and b.loc['water_supply', 'ungated_ledger_share'] == 0
    assert (out.clearing_levels_start <= out.clearing_cap).all() and (out.water_supply_levels_start <= out.water_supply_cap).all()
    assert (out.loc[d.vegetation.eq('grasslands'), 'clearing_cap'] == 0).all()
    assert set(caps.columns) == {'building', 'attribute', 'value', 'levels'}
    dev_terms = caps[caps.attribute == 'development']
    assert len(dev_terms) == int(buildings.unit_people_per_level.notna().sum()) and (dev_terms.levels >= 0).all() and (dev_terms.levels <= 0.2).all()
    assert (caps[caps.attribute != 'development'].levels % 1 == 0).all()
    assert (out.clearing_cap_at_reference >= 0).all()


def test_fixed_unit_split_kinds_and_cap_groups_keep_starting_works():
    rng = np.random.default_rng(1); n = 150
    d = pd.DataFrame({'climate': rng.choice(['tropical', 'continental'], n), 'vegetation': rng.choice(['forest', 'grasslands'], n),
                      'river_level': rng.choice(['0', '3'], n), 'is_coastal': rng.choice(['True', 'False'], n)}, index=[f'l{i}' for i in range(n)])
    ledger = pd.DataFrame({'location_tag': d.index})
    for kind in ['clearing', 'management', 'water_supply', 'paddy_control', 'flood_bunds', 'field_drainage', 'polders']:
        ledger[f'starting_{kind}_capacity'] = rng.integers(0, 30, n) * 1000.
        ledger[f'maximum_{kind}_capacity'] = ledger[f'starting_{kind}_capacity'] + rng.integers(0, 40, n) * 1000.
    ledger.loc[0, 'starting_management_capacity'] = 200_000.   # far above any cap: kept in full
    dev = pd.Series(rng.uniform(0, 60, n), index=d.index)
    cfg = {'cap_features': ['climate', 'vegetation', 'river_level'], 'reference_classes': {'climate': 'continental', 'vegetation': 'grasslands', 'river_level': '0'},
           'ordinal': {'river_level': ['0', '3']}, 'signed_cap_features': ['climate', 'vegetation'], 'level_limit': 15, 'envelope_quantile': 0.5,
           'capacity_percent_per_point': 0.0, 'unit_quantiles': [0.5], 'max_levels_per_development_point': 0.1, 'unit_people_per_level': 5000,
           'clamp_start_to_cap': False, 'split_kinds': {'paddy_control': {'paddy_fields': 0.5, 'paddy_water_control': 0.5}},
           'cap_groups': {'water_control': ['water_supply', 'flood_bunds', 'field_drainage', 'polders']},
           'gates': {'water_supply': [{'river_level': ['3']}], 'polders': [{'is_coastal': ['True']}], 'flood_bunds': [{'river_level': ['3']}], 'field_drainage': [{'vegetation': ['forest']}]}}
    out, buildings, caps = assign(d, ledger, dev, cfg)
    b = buildings.set_index('building')
    assert set(b.index) >= {'paddy_fields', 'paddy_water_control', 'water_supply', 'polders'} and 'paddy_control' not in b.index
    assert (b.unit_people_per_level == 5000).all()
    assert (out.paddy_fields_cap == out.paddy_water_control_cap).all()
    members = ['water_supply', 'flood_bunds', 'field_drainage', 'polders']
    assert set(b.loc[members, 'cap_group']) == {'water_control'}
    group_cap = out[[f'{m}_cap' for m in members]].max(axis=1)
    # every member shows the group's one cap where its own gate holds, nothing where it fails
    assert (out.loc[d.is_coastal.eq('False'), 'polders_cap'] == 0).all()
    assert ((out.polders_cap == 0) | (out.polders_cap == group_cap)).all()
    # the group's starting levels are split over the members whose gate holds
    assert (out.loc[d.is_coastal.eq('False'), 'polders_levels_start'] == 0).all()
    led = ledger.set_index('location_tag')
    gated = d.river_level.eq('3') | d.is_coastal.eq('True') | d.vegetation.eq('forest')
    total = sum(led[f'starting_{m}_capacity'] for m in members)[gated]
    assert (out.loc[gated, [f'{m}_levels_start' for m in members]].sum(axis=1) <= np.round(total / 5000)).all()
    # 1337 works above the cap are kept, not clamped
    assert out.loc['l0', 'management_levels_start'] == 40 and out.loc['l0', 'management_cap'] <= 15
    assert (out[[c for c in out.columns if c.endswith('_cap')]] <= 15).all().all()
