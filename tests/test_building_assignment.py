import numpy as np
import pandas as pd
from historical_agriculture.building_assignment import choose_unit, gate, development_band, assign


def test_unit_choice_recovers_exact_multiples_and_gate_rules():
    unit, info = choose_unit(np.array([3000., 6000., 9000., 12000., 0.]), 20, [0.3, 0.5, 0.7])
    assert abs(unit - 3000) < 1e-6 or abs(info['captured_within_25_share'] - 1) < 1e-9
    d = pd.DataFrame({'climate': ['tropical', 'arctic'], 'topography': ['flatland', 'flatland'], 'is_coastal': ['True', 'False']})
    assert gate(d, [{'climate': ['tropical'], 'topography': ['flatland']}]).tolist() == [True, False]
    assert gate(d, [{'climate': ['arctic']}, {'is_coastal': ['True']}]).tolist() == [True, True]
    assert gate(d, []).tolist() == [True, True]
    assert development_band([0, 19.9, 20, 79, 100]).tolist() == ['d00_20', 'd00_20', 'd20_40', 'd60_80', 'd80_100']


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
           'unit_quantiles': [0.5, 0.7, 0.9], 'gates': {'clearing': [{'vegetation': ['forest']}], 'water_supply': [{'river_level': ['3']}], 'management': []}}
    out, buildings, caps = assign(d, ledger, dev, cfg)
    b = buildings.set_index('building')
    assert b.loc['clearing', 'ungated_ledger_share'] == 0 and b.loc['water_supply', 'ungated_ledger_share'] == 0
    assert (out.clearing_levels_start <= out.clearing_cap).all() and (out.water_supply_levels_start <= out.water_supply_cap).all()
    assert (out.loc[d.vegetation.eq('grasslands'), 'clearing_cap'] == 0).all()
    assert set(caps.columns) == {'building', 'attribute', 'value', 'levels'}
    assert caps.levels.dtype.kind in 'iu'
    assert (out.clearing_cap_at_development_100 >= 0).all()
