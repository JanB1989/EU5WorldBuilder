import numpy as np
import pandas as pd
import pytest
from historical_agriculture.attribute_fit_flat import design_reference, fit_quantile, sensibility

CFG = {'tau': 0.3, 'ordinal': {'fertility': ['low', 'moderate', 'high']}, 'sign_expectations': {'negative': [['climate', 'cold']], 'positive': [['fertility', 'high']]}}


def frame(n=300, seed=1):
    rng = np.random.default_rng(seed)
    d = pd.DataFrame({'climate': rng.choice(['warm', 'cold', 'mild'], n), 'fertility': rng.choice(['low', 'moderate', 'high'], n)})
    truth = {('climate', 'cold'): -40., ('climate', 'mild'): 5., ('fertility', 'low'): -20., ('fertility', 'high'): 30.}
    y = 100. + sum(v * (d[f] == c).to_numpy(float) for (f, c), v in truth.items())
    return d, y, truth


def setup(d):
    return design_reference(d, ['climate', 'fertility'], {'climate': 'warm', 'fertility': 'moderate'})


def test_exact_additive_signal_is_recovered_with_reference_intercept():
    d, y, truth = frame()
    X, names, groups = setup(d)
    spans = {'climate': (-90, 80), 'fertility': (-50, 60)}
    beta, info = fit_quantile(X, y, names, groups, CFG, spans, (20, 300), 400, CFG['ordinal'])
    assert beta[0] == pytest.approx(100, abs=1e-6)
    for (f, c), v in truth.items():
        assert beta[groups[f]['columns'][c]] == pytest.approx(v, abs=1e-6)
    assert info['possible_minimum'] == pytest.approx(40, abs=1e-6)


def test_quantile_objective_leaves_about_tau_overshooting_and_spans_and_ordering_bind():
    d, y, truth = frame(n=600)
    rng = np.random.default_rng(2)
    noisy = y * np.exp(rng.normal(0, .4, len(y)))
    X, names, groups = setup(d)
    spans = {'climate': (-90, 80), 'fertility': (-50, 60)}
    beta, info = fit_quantile(X, noisy, names, groups, CFG, spans, (20, 300), 1e6, CFG['ordinal'])
    assert abs(info['overshoot_share'] - 0.3) < 0.08
    tight = {'climate': (-10, 10), 'fertility': (-10, 10)}
    b2, _ = fit_quantile(X, y, names, groups, CFG, tight, (20, 300), 400, CFG['ordinal'])
    assert b2[groups['climate']['columns']['cold']] == pytest.approx(-10, abs=1e-6)
    checks = sensibility(b2, names, groups, tight, (20, 300), CFG, 100.)
    assert checks['inside_spans'] and len(checks['pinned']) >= 1 and checks['ordinal']
    # ordering: force fertility low above high by inverting the signal; the constraint must hold anyway
    inverted = y - 60 * (d.fertility == 'high').to_numpy(float) + 60 * (d.fertility == 'low').to_numpy(float)
    b3, _ = fit_quantile(X, inverted, names, groups, CFG, spans, (20, 300), 400, CFG['ordinal'])
    low, high = b3[groups['fertility']['columns']['low']], b3[groups['fertility']['columns']['high']]
    assert low <= 0 + 1e-6 <= high + 1e-6 and low <= high + 1e-6


def test_zero_floor_holds_for_unseen_combinations():
    d, y, _ = frame(n=200)
    d = d[~((d.climate == 'cold') & (d.fertility == 'low'))].reset_index(drop=True); y = y[:len(d)]
    X, names, groups = setup(d)
    y = np.where((d.climate == 'cold').to_numpy(), 5., y)  # cold pushes the model far down
    beta, info = fit_quantile(X, y, names, groups, CFG, {'climate': (-200, 80), 'fertility': (-200, 60)}, (0, 300), 400, CFG['ordinal'])
    assert info['possible_minimum'] >= -1e-6
