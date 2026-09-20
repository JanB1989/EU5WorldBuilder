import numpy as np
import pandas as pd
from historical_agriculture.goods_output_fit import target_scale, fit_good


def test_target_scale_is_rank_uniform_over_viable_only():
    y, viable = target_scale([0., 0.2, 0.9, 0.5], -0.5, 0.5)
    assert viable.tolist() == [False, True, True, True] and np.isnan(y[0])
    assert y[1] == -0.5 and y[2] == 0.5 and abs(y[3]) < 1e-12


def test_fit_good_keeps_only_relevant_rows_and_prunes_small_ones():
    rng = np.random.default_rng(1); n = 400
    cls = rng.choice(['a', 'b', 'c'], n)                       # class a is the reference
    X = np.column_stack([np.ones(n), (cls == 'b').astype(float), (cls == 'c').astype(float)])
    member = X > 0.5; member[:, 0] = False
    y = 0.1 + 0.3 * (cls == 'b') + 0.02 * (cls == 'c') + rng.normal(0, 0.01, n)
    rgo = rng.random(n) < 0.5
    rgo[cls == 'c'] = False; rgo[np.where(cls == 'c')[0][:2]] = True   # c is RGO in only 2 locations
    folds = rng.integers(0, 5, n)
    cfg = {'min_rgo_locations_per_class': 5, 'prune_below': 0.1}
    beta, keep, ph = fit_good(X, [('reference', 'intercept'), ('k', 'b'), ('k', 'c')], member, y, rgo, rgo, folds, cfg)
    assert keep.tolist() == [True, True, False]                # c dropped by relevance
    assert abs(beta[1] - 0.3) < 0.03 and beta[2] == 0
    small = y - 0.3 * (cls == 'b') + 0.05 * (cls == 'b')      # b effect now 0.05 < prune threshold
    beta2, keep2, _ = fit_good(X, [('reference', 'intercept'), ('k', 'b'), ('k', 'c')], member, small, rgo, rgo, folds, cfg)
    assert keep2.tolist() == [True, False, False] and abs(beta2[0] - small[rgo].mean()) < 0.02
