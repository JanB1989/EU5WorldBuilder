import numpy as np
import pandas as pd

from historical_agriculture import goods_output_constrained as gc

PRIORS = {
    "unsuitable_max": -0.2,
    "ordinal": {"fertility": ["very_low", "low", "moderate", "high", "very_high"]},
    "defaults": {"fertility": "increasing", "soil_type.peat": "-"},
    "groups": {"field": {"rules": {"vegetation.forest": "-"}}},
    "goods": {"crop": {"group": "field", "climate": {"core": ["warm"], "marginal": [], "unsuitable": ["cold"]}, "rules": {"soil_type.peat": "0"}}},
}
CFG = {"spans": {"climate": [-0.6, 0.5], "fertility": [-0.3, 0.3], "vegetation": [-0.3, 0.3], "soil_type": [-0.2, 0.2]},
       "min_viable_per_class": 5, "marginal_without_data": -0.1, "ridge_locations": 0.0, "display_threshold": 0.05}
FEATURES = ["climate", "fertility", "vegetation", "soil_type"]
REFERENCE = {"climate": "warm", "fertility": "moderate", "vegetation": "grass", "soil_type": "loam"}


def _frame(n=600, seed=3):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "climate": rng.choice(["warm", "mild", "cold"], n), "fertility": rng.choice(PRIORS["ordinal"]["fertility"], n),
        "vegetation": rng.choice(["grass", "forest"], n), "soil_type": rng.choice(["loam", "peat"], n),
    }, index=[f"l{i}" for i in range(n)])


def _fit(d, y):
    viable = np.ones(len(d), bool); is_rgo = np.zeros(len(d), bool)
    des = gc.build_design(d, "crop", PRIORS, CFG, viable, is_rgo, FEATURES, REFERENCE)
    theta, _ = gc.fit_one(des.matrix(), y, np.ones(len(d)), des, CFG)
    return {k: round(v, 3) for k, v in des.row_values(theta).items()}


def test_rules_resolve_defaults_then_group_then_good():
    rules = gc.resolve_rules(PRIORS, "crop")
    assert rules["vegetation.forest"] == "-" and rules["soil_type.peat"] == "0" and rules["fertility"] == "increasing"
    assert gc.climate_code(PRIORS, "crop", "cold") == "unsuitable" and gc.climate_code(PRIORS, "crop", "mild") == "possible"


def test_fertility_never_falls_and_signs_hold_even_when_the_data_says_otherwise():
    d = _frame()
    fert = {"very_low": -0.3, "low": -0.1, "moderate": 0.0, "high": 0.2, "very_high": 0.1}   # data dips at very_high
    y = (d.climate.map({"warm": 0.1, "mild": 0.0, "cold": 0.1}) + d.fertility.map(fert)
         + 0.2 * (d.vegetation == "forest") + 0.1 * (d.soil_type == "peat")).to_numpy(float)
    rows = _fit(d, y)
    seq = [rows.get(("fertility", v), 0.0) for v in ["very_low", "low"]] + [0.0] + [rows.get(("fertility", v), 0.0) for v in ["high", "very_high"]]
    assert all(b >= a - 1e-9 for a, b in zip(seq, seq[1:]))          # monotone
    assert rows.get(("vegetation", "forest"), 0.0) <= 0               # '-' holds against +0.2 data
    assert ("soil_type", "peat") not in rows                          # '0': no row at all
    assert rows[("climate", "cold")] <= -0.2                          # unsuitable
    assert rows[("climate", "warm")] >= 0                             # core


def test_small_rows_are_dropped_and_ordinal_pruning_keeps_the_order():
    d = _frame()
    y = (d.climate.map({"warm": 0.1, "mild": 0.0, "cold": -0.3})
         + d.fertility.map({"very_low": -0.3, "low": -0.02, "moderate": 0.0, "high": 0.02, "very_high": 0.25})).to_numpy(float)
    rows = _fit(d, y)
    assert abs(rows.get(("fertility", "high"), 0.0)) < 1e-9 and abs(rows.get(("fertility", "low"), 0.0)) < 1e-9
    assert rows[("fertility", "very_high")] > 0.2 and rows[("fertility", "very_low")] < -0.25


def test_absolute_climate_rows_become_intercept_plus_relative_rows():
    rows = {("climate", "warm"): 0.3, ("climate", "mild"): 0.1, ("fertility", "high"): 0.1}
    out = gc.absolute_to_handover("crop", rows, ["cold", "mild", "warm"], REFERENCE)
    got = {(r["attribute"], r["value"]): r["modifier"] for r in out}
    assert got[("reference", "intercept")] == 0.3
    assert got[("climate", "mild")] == -0.2 and got[("climate", "cold")] == -0.3      # absent climate = 0 absolute
    assert got[("fertility", "high")] == 0.1 and ("climate", "warm") not in got


def test_check_rows_reports_every_kind_of_break():
    bad = gc.check_rows({("climate", "warm"): -0.1, ("climate", "cold"): 0.0, ("vegetation", "forest"): 0.1, ("soil_type", "peat"): 0.1,
                         ("fertility", "high"): 0.2, ("fertility", "very_high"): 0.1}, "crop", PRIORS, FEATURES, REFERENCE)
    text = "\n".join(bad)
    assert "climate warm" in text and "vegetation forest" in text and "soil_type peat" in text and "fertility rows" in text


def test_the_priors_file_names_real_classes_and_lists_each_climate_once():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    priors = gc.load_priors(root / "configs/goods_output_priors.json")
    climates = set(json.loads((root / "configs/climate.json").read_text())["types"])
    codes = {"+", "-", "0", "free", "increasing"}
    assert len(priors["goods"]) == 25
    for good, spec in priors["goods"].items():
        listed = [c for k in ("core", "marginal", "unsuitable") for c in spec["climate"][k]]
        assert len(listed) == len(set(listed)), good
        assert set(listed) <= climates, (good, set(listed) - climates)
        assert spec["climate"]["core"] or good == "medicaments", good
        assert spec.get("evidence") and spec.get("group") in priors["groups"], good
        rules = gc.resolve_rules(priors, good)
        assert set(rules.values()) <= codes, (good, set(rules.values()) - codes)


def test_effective_score_lifts_towards_irrigated_only_by_the_weight():
    r = np.array([0.2, 0.0, 0.5]); i = np.array([0.8, 0.6, 0.5]); w = np.array([0.5, 0.0, 1.0])
    assert np.allclose(gc.effective_score(r, i, w), [0.5, 0.0, 0.5])
