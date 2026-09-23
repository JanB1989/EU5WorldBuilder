"""Goods output rows from location attributes, constrained by an agronomic sign table.

Replaces the per-good least squares of ``goods_output_fit`` (method ``ols``) when the config sets
``method: constrained``. Differences, each fixing a measured inconsistency of the old rows:

- target: the V2 labor-output score on its own 0..1 log scale, centred on the good's median viable
  location (not rank-stretched per good, which turned small score differences into large rows);
- water: the rain-fed score, lifted towards the irrigated score only by the location's historical
  irrigated share (the fertility grade's weight). The canonical score takes the irrigated branch
  wherever it wins, so dry-land crops looked best in open desert;
- rows: climate rows are absolute (they carry the good's level, no separate intercept); every other
  attribute is relative to its reference class; fertility never falls with a better class; each row's
  sign is bounded by ``configs/goods_output_priors.json``; a ridge pulls thin classes towards zero
  instead of a hard relevance cut; rows under ``display_threshold`` are dropped and the rest refitted;
- every good is fitted from all its viable locations (RGO locations weighted), so goods with few
  vanilla RGOs (coffee, cloves) get rows too.

Output keeps the handover format: the climate reference class's absolute row is the ``reference``
intercept and every other climate row is written relative to it, so reference + climate row = the
absolute climate row (the constructor folds the intercept into the climate rows it writes).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear

ROOT = Path(__file__).resolve().parents[2]


# ----------------------------------------------------------------------------------------------- priors
def load_priors(path):
    return json.loads(Path(path).read_text())


def resolve_rules(priors, good):
    """(attribute.class or attribute) -> code for one good: defaults < group < good."""
    spec = priors["goods"][good]
    rules = dict(priors.get("defaults", {}))
    rules.update(priors.get("groups", {}).get(spec.get("group"), {}).get("rules", {}))
    rules.update(spec.get("rules", {}))
    return rules


def climate_code(priors, good, value):
    c = priors["goods"][good].get("climate", {})
    for code in ("core", "marginal", "unsuitable"):
        if value in c.get(code, []):
            return code
    return "possible"


def rule_for(rules, attribute, value):
    return rules.get(f"{attribute}.{value}", rules.get(attribute, "free"))


# ----------------------------------------------------------------------------------------------- target
def load_scores(directory, good, index):
    p = Path(directory) / f"{good}.csv"
    if not p.exists():
        return None
    t = pd.read_csv(p, keep_default_na=False).set_index("location_tag")
    return pd.to_numeric(t.score_0_1, errors="coerce").reindex(index).fillna(0.0).to_numpy()


def irrigation_weight(index, cfg):
    spec = cfg["irrigation_weight"]
    t = pd.read_csv(ROOT / spec["source"], keep_default_na=False).set_index("location_tag")
    share = pd.to_numeric(t["irrigated_share"], errors="coerce").reindex(index).fillna(0.0).to_numpy()
    return np.clip(share / float(spec["saturation"]), 0.0, 1.0)


def effective_score(rainfed, irrigated, weight):
    """Rain-fed score, lifted towards the irrigated score by the location's irrigated weight."""
    if rainfed is None:
        return irrigated
    return rainfed + weight * (irrigated - rainfed)


# ----------------------------------------------------------------------------------------------- design
class Design:
    """Parameters of one good's rows: each parameter has a design column, bounds, and a mapping to the
    displayed rows (row value = sum of parameter x coefficient)."""

    def __init__(self):
        self.cols, self.lo, self.hi, self.names = [], [], [], []
        self.rows = {}          # (attribute, value) -> list[(param index, coefficient)]
        self.fixed = {}         # (attribute, value) -> fixed value (no data, prior only)
        self.orders = []        # (i, j, gap): theta_i - theta_j >= gap

    def add(self, col, lo, hi, name):
        self.cols.append(col); self.lo.append(lo); self.hi.append(hi); self.names.append(name)
        return len(self.cols) - 1

    def matrix(self):
        return np.column_stack(self.cols) if self.cols else np.zeros((0, 0))

    def row_values(self, theta):
        out = {k: float(sum(theta[j] * c for j, c in terms)) for k, terms in self.rows.items()}
        out.update(self.fixed)
        return out


def build_design(d, good, priors, cfg, viable, is_rgo, features, reference):
    rules = resolve_rules(priors, good)
    spans = cfg["spans"]
    unsuitable_max = float(priors.get("unsuitable_max", -0.2))
    min_n = int(cfg["min_viable_per_class"])
    ordinal = priors.get("ordinal", {})
    des = Design()
    # climate: absolute rows, ordered home >= marginal >= unsuitable (possible climates are free); an
    # unsuitable climate sits at least unsuitable_gap under every home climate and under the typical RGO
    lo_c, hi_c = spans["climate"]
    params: dict[str, list[int]] = {"core": [], "marginal": [], "unsuitable": []}
    for value in sorted(d["climate"].unique()):
        member = (d["climate"] == value).to_numpy()
        code = climate_code(priors, good, value)
        lo, hi = (lo_c, unsuitable_max) if code == "unsuitable" else (lo_c, hi_c)
        if (member & viable).sum() >= min_n:     # thinner climates get their row from the prior (settle_fixed_climates)
            j = des.add(member.astype(float), lo, hi, ("climate", value))
            des.rows[("climate", value)] = [(j, 1.0)]
            if code in params:
                params[code].append(j)
    gap = float(priors.get("unsuitable_gap", 0.2))
    des.orders += [(c, m, 0.0) for c in params["core"] for m in params["marginal"]]
    des.orders += [(m, u, 0.0) for m in params["marginal"] for u in params["unsuitable"]]
    des.orders += [(c, u, gap) for c in params["core"] for u in params["unsuitable"]]
    # other attributes: relative to the reference class
    for f in features:
        if f == "climate":
            continue
        ref = str(reference[f])
        values = sorted(d[f].unique())
        attr_rule = rules.get(f, "free")
        if f in ordinal and attr_rule == "increasing":
            order = [v for v in ordinal[f] if v in values or v == ref]
            k = order.index(ref)
            lo_s, hi_s = spans[f]
            above, below = order[k + 1:], order[:k][::-1]      # outward from the reference
            for side, seq, sign in (("above", above, 1.0), ("below", below, -1.0)):
                for i, v in enumerate(seq):
                    outward = seq[i:]
                    col = np.zeros(len(d))
                    for w in outward:
                        col += (d[f] == w).to_numpy()
                    n = int(((d[f] == v).to_numpy() & viable).sum())
                    if n < min_n:
                        continue
                    j = des.add(sign * col, 0.0, hi_s if sign > 0 else -lo_s, (f, f"step_{v}"))
                    for w in outward:
                        des.rows.setdefault((f, w), []).append((j, sign))
            continue
        for v in values:
            if v == ref:
                continue
            code = rule_for(rules, f, v)
            if code == "0" or (attr_rule == "0" and f"{f}.{v}" not in rules):
                continue
            member = (d[f] == v).to_numpy()
            if (member & viable).sum() < min_n:
                continue
            lo_s, hi_s = spans[f]
            lo, hi = {"+": (0.0, hi_s), "-": (lo_s, 0.0), "free": (lo_s, hi_s), "increasing": (0.0, hi_s)}[code]
            j = des.add(member.astype(float), lo, hi, (f, v))
            des.rows[(f, v)] = [(j, 1.0)]
    return des


# ----------------------------------------------------------------------------------------------- solve
def solve(X, y, w, lo, hi, ridge, fixed_zero=(), orders=(), linear=()):
    """Weighted ridge least squares under bounds, pairwise orders (theta_i - theta_j >= gap) and general
    linear constraints (a @ theta >= gap)."""
    n = X.shape[1]
    cons = []
    for i, j, g in orders:
        a = np.zeros(n); a[i] += 1.0; a[j] -= 1.0
        cons.append((a, g))
    cons += [(np.asarray(a, float), float(g)) for a, g in linear]
    lo = np.array(lo, float); hi = np.array(hi, float)
    for j in fixed_zero:
        lo[j] = hi[j] = 0.0
    free = lo < hi
    theta = np.zeros(X.shape[1])
    theta[~free] = lo[~free]
    if not free.any():
        return theta
    sw = np.sqrt(w)
    A = np.vstack([X[:, free] * sw[:, None], np.sqrt(ridge) * np.eye(int(free.sum()))])
    b = np.concatenate([(y - X[:, ~free] @ theta[~free]) * sw, np.zeros(int(free.sum()))])
    start = lsq_linear(A, b, bounds=(lo[free], hi[free]), method="bvls", lsmr_tol="auto").x
    theta[free] = start
    if all(a @ theta >= g - 1e-9 for a, g in cons):
        return theta
    # quadratic programme on the free parameters: min |A t - b|^2 subject to bounds and constraints
    rows, rhs = [], []
    for a, g in cons:
        if a[free].any():
            rows.append(a[free]); rhs.append(g - a[~free] @ theta[~free])
    if not rows:
        return theta
    C = np.array(rows); c = np.array(rhs)
    scale = float(len(y)) or 1.0
    H = A.T @ A / scale; g = A.T @ b / scale
    from scipy.optimize import minimize
    res = minimize(lambda t: (t @ H @ t - 2 * g @ t, 2 * (H @ t - g)), start, jac=True, method="SLSQP",
                   bounds=list(zip(lo[free], hi[free])),
                   constraints=[{"type": "ineq", "fun": lambda t: C @ t - c, "jac": lambda t: C}],
                   options={"maxiter": 500, "ftol": 1e-12})
    t = np.clip(res.x, lo[free], hi[free])
    if (C @ t - c).min() < -1e-6:
        raise RuntimeError(f"constraints not met ({res.message})")
    theta[free] = t
    return theta


def prune(des, theta, threshold):
    """Parameters to fix at zero so that no displayed row is smaller than threshold (ordinal steps are
    pruned from the reference outwards, so a kept row never sits next to a dropped outer one)."""
    rows = des.row_values(theta)
    zero = set()
    for key, terms in des.rows.items():
        if abs(rows[key]) < threshold:
            for j, _ in terms:
                zero.add(j)
    return zero


def rgo_advantage(X, is_rgo, cfg):
    """The game's RGO placement is kept: the mean viable RGO location predicts at least rgo_advantage above
    the mean of the good's other viable land (rows of X are the viable locations of the fit)."""
    margin = cfg.get("rgo_advantage")
    if margin is None or is_rgo.sum() < int(cfg["min_rgo_for_centre"]) or (~is_rgo).sum() == 0:
        return []
    return [(X[is_rgo].mean(0) - X[~is_rgo].mean(0), float(margin))]


def fit_one(X, y, w, des, cfg, is_rgo=None):
    ridge = float(cfg["ridge_locations"]) * float(np.mean(w))
    linear = rgo_advantage(X, is_rgo, cfg) if is_rgo is not None else []
    theta = solve(X, y, w, des.lo, des.hi, ridge, orders=des.orders, linear=linear)
    zero = prune(des, theta, float(cfg["display_threshold"]))
    theta = solve(X, y, w, des.lo, des.hi, ridge, zero, des.orders, linear)
    return theta, zero


def r2(y, p, w=None):
    w = np.ones(len(y)) if w is None else w
    m = np.average(y, weights=w)
    ss = float((w * (y - m) ** 2).sum())
    return float(1 - (w * (y - p) ** 2).sum() / ss) if ss > 0 else float("nan")


# ----------------------------------------------------------------------------------------------- build
def build_good(d, good, priors, cfg, fit_cfg, folds, rgo, weight_irrigated):
    features = fit_cfg["features"]
    reference = {f: str(v) for f, v in fit_cfg["reference_classes"].items()}
    irrigated = load_scores(ROOT / cfg["irrigated_overrides_directory"], good, d.index)
    if irrigated is None:
        irrigated = load_scores(ROOT / cfg["tables_directory"], good, d.index)
    rainfed = load_scores(ROOT / cfg["rainfed_tables_directory"], good, d.index)
    s = effective_score(rainfed, irrigated, weight_irrigated)
    viable = s > 0
    is_rgo = (rgo == good).to_numpy()
    # centre on the good's median viable RGO location (the game's own placement keeps its level, so the
    # average RGO still gets about the raw-material bonus); goods with too few viable RGOs use all viable land
    rgo_viable = viable & is_rgo
    pool = s[rgo_viable] if rgo_viable.sum() >= int(cfg["min_rgo_for_centre"]) else s[viable]
    centre = float(np.median(pool)) if len(pool) else 0.0
    y = float(cfg["target_scale"]) * (s - centre)
    w = np.where(is_rgo, float(cfg["rgo_weight"]), 1.0)
    des = build_design(d, good, priors, cfg, viable, is_rgo, features, reference)
    X = des.matrix()
    m = viable
    theta, zero = fit_one(X[m], y[m], w[m], des, cfg, is_rgo[m])
    # unconstrained twin (same columns and ridge, no sign bounds): where did the priors overrule the data?
    wide = [-5.0] * len(des.lo), [5.0] * len(des.hi)
    free_theta = solve(X[m], y[m], w[m], wide[0], wide[1], float(cfg["ridge_locations"]) * float(np.mean(w[m])))
    rows = des.row_values(theta)
    level = calibrate_level(d, rows, features, reference, viable & is_rgo, cfg, priors, good)
    rows = {k: round(v, 2) for k, v in rows.items()}
    settle_fixed_climates(rows, des, good, priors, sorted(d["climate"].unique()), float(cfg["marginal_without_data"]))
    free_rows = {k: v + (level if k[0] == "climate" else 0.0) for k, v in des.row_values(free_theta).items()}
    pred = predict(d, rows, features, reference)
    # held-out by region (same bounds and pruning)
    ph = np.full(len(d), np.nan)
    for k in sorted(set(folds)):
        tr = m & (folds != k); te = m & (folds == k)
        if tr.sum() < 50 or te.sum() == 0:
            continue
        th, _ = fit_one(X[tr], y[tr], w[tr], des, cfg, is_rgo[tr])
        ph[te] = predict(d.loc[te], {kk: round(v, 2) for kk, v in des.row_values(th).items()}, features, reference)
    overruled = []
    for key, v in rows.items():
        fv = free_rows.get(key)
        if fv is None:
            continue
        flipped = fv * v < 0 and abs(fv) >= float(cfg["display_threshold"])
        if flipped or abs(fv - v) >= 0.1:
            overruled.append({"good": good, "attribute": key[0], "value": key[1], "data": round(fv, 3), "row": v})
    ev = m & np.isfinite(ph)
    rv = m & is_rgo & np.isfinite(ph)
    metrics = {
        "good": good, "viable_locations": int(m.sum()), "rgo_locations": int(is_rgo.sum()), "rgo_viable": int((is_rgo & m).sum()),
        "centre_score": round(centre, 4), "level_shift": round(level, 3), "irrigated_lifted": int(((weight_irrigated > 0) & (irrigated > (rainfed if rainfed is not None else irrigated))).sum()),
        "rows": int(sum(1 for k, v in rows.items() if abs(v) >= 0.005)),
        "r2_viable_insample": r2(y[m], pred[m], w[m]), "r2_viable_heldout": r2(y[ev], ph[ev]) if ev.sum() > 10 else float("nan"),
        "r2_rgo_heldout": r2(y[rv], ph[rv]) if rv.sum() > 10 else float("nan"),
        "mae_rgo_heldout": float(np.abs(y[rv] - ph[rv]).mean()) if rv.sum() else float("nan"),
        "predicted_rgo_median": float(np.median(pred[is_rgo])) if is_rgo.any() else float("nan"),
        "rgo_below_floor_share": float((pred[is_rgo] < float(cfg["rgo_floor"])).mean()) if is_rgo.any() else float("nan"),
        "rgo_nonviable_share": float((~viable[is_rgo]).mean()) if is_rgo.any() else float("nan"),
        "priors_overruled": len(overruled),
    }
    return rows, metrics, overruled, pred, y, viable, is_rgo


def calibrate_level(d, rows, features, reference, rgo_viable, cfg, priors, good):
    """Shift every climate row by one constant so the good's median viable RGO location predicts 0 (the
    game's own placement keeps the raw-material bonus level; the attributes cannot see what makes a
    particular RGO district special). A uniform shift keeps the climate order; unsuitable rows stay at or
    below unsuitable_max. Returns the shift."""
    if rgo_viable.sum() < int(cfg["min_rgo_for_centre"]):
        return 0.0
    # mean with the floor applied (what the RGOs actually get), solved by bisection: the good's average
    # viable RGO lands on the raw-material bonus
    p = predict(d.loc[rgo_viable], rows, features, reference)
    floor = float(cfg["rgo_floor"])
    lo_s, hi_s = -1.0, 1.0
    for _ in range(60):
        mid = (lo_s + hi_s) / 2
        if np.maximum(p + mid, floor).mean() > 0:
            hi_s = mid
        else:
            lo_s = mid
    shift = (lo_s + hi_s) / 2
    um = float(priors.get("unsuitable_max", -0.2))
    for key in [k for k in rows if k[0] == "climate"]:
        v = rows[key] + shift
        if climate_code(priors, good, key[1]) == "unsuitable":
            v = min(v, um)
        rows[key] = v
    return shift


def settle_fixed_climates(rows, des, good, priors, climates, marginal_without_data):
    """Climates without enough viable locations to fit get their row from the prior, keeping the climate
    order (a missing climate row would read as the typical RGO): a marginal one sits no higher than any
    home climate, an unsuitable one under every marginal climate and unsuitable_gap under every home
    climate. Possible climates without data keep no row."""
    um = float(priors.get("unsuitable_max", -0.2))
    gap = float(priors.get("unsuitable_gap", 0.2))
    fitted = {v: rows[("climate", v)] for (f, v) in des.rows if f == "climate"}
    missing = [v for v in climates if v not in fitted]
    core = [x for v, x in fitted.items() if climate_code(priors, good, v) == "core"]
    marginal = [x for v, x in fitted.items() if climate_code(priors, good, v) == "marginal"]
    for v in missing:
        if climate_code(priors, good, v) == "marginal":
            rows[("climate", v)] = round(min([marginal_without_data] + core), 2)
            marginal.append(rows[("climate", v)])
    for v in missing:
        code = climate_code(priors, good, v)
        if code == "unsuitable":
            rows[("climate", v)] = round(min([um] + marginal + [c - gap for c in core]), 2)
        elif code == "possible":
            rows.pop(("climate", v), None)


def predict(d, rows, features, reference):
    p = np.zeros(len(d))
    for f in features:
        vals = d[f].astype(str).to_numpy()
        for v in np.unique(vals):
            r = rows.get((f, v))
            if r:
                p[vals == v] += r
    return p


def absolute_to_handover(good, rows, climates, reference):
    """Absolute climate rows -> reference intercept + climate rows relative to it; other rows unchanged."""
    ref = str(reference["climate"])
    intercept = rows.get(("climate", ref), 0.0)
    out = [{"good": good, "attribute": "reference", "value": "intercept", "modifier": round(intercept, 2)}]
    for c in climates:
        if c == ref:
            continue
        rel = round(rows.get(("climate", c), 0.0) - intercept, 2)
        if abs(rel) >= 0.005:
            out.append({"good": good, "attribute": "climate", "value": c, "modifier": rel})
    for (f, v), val in sorted(rows.items()):
        if f != "climate" and abs(val) >= 0.005:
            out.append({"good": good, "attribute": f, "value": v, "modifier": round(val, 2)})
    return out


def check_rows(rows, good, priors, features, reference):
    """Every written row obeys the sign table and the ordinal order; returns violation strings."""
    bad = []
    rules = resolve_rules(priors, good)
    um = float(priors.get("unsuitable_max", -0.2))
    gap = float(priors.get("unsuitable_gap", 0.2))
    climate = {v: val for (f, v), val in rows.items() if f == "climate"}
    by_code = {code: {v: val for v, val in climate.items() if climate_code(priors, good, v) == code} for code in ("core", "marginal", "unsuitable")}
    for v, val in by_code["unsuitable"].items():
        if val > um + 1e-9:
            bad.append(f"{good}: climate {v} = {val:+.2f} breaks 'unsuitable' (<= {um})")
    for hi_code, lo_code, need in (("core", "marginal", 0.0), ("marginal", "unsuitable", 0.0), ("core", "unsuitable", gap)):
        for hv, h in by_code[hi_code].items():
            for lv, lval in by_code[lo_code].items():
                if h - lval < need - 0.011:   # rows are rounded to 0.01
                    bad.append(f"{good}: climate {hv} ({hi_code}) {h:+.2f} not {need:.2f} above {lv} ({lo_code}) {lval:+.2f}")
    for (f, v), val in rows.items():
        if abs(val) < 0.005 or f == "climate":
            continue
        code = rule_for(rules, f, v)
        if code == "0":
            bad.append(f"{good}: {f} {v} = {val:+.2f} should have no row")
        elif (code == "+" and val < 0) or (code == "-" and val > 0):
            bad.append(f"{good}: {f} {v} = {val:+.2f} breaks '{code}'")
    for f, order in priors.get("ordinal", {}).items():
        if f not in features:
            continue
        ref = str(reference[f])
        seq = [rows.get((f, v), 0.0) if v != ref else 0.0 for v in order]
        if any(b < a - 1e-9 for a, b in zip(seq, seq[1:])) and rules.get(f) == "increasing":
            bad.append(f"{good}: {f} rows {seq} fall with a better class")
    return bad


def build_all(cfg, fit_cfg, out, manifest):
    from .attribute_fit import region_folds
    from .attribute_fit_flat import load_attributes
    from .goods_output_fit import load_rgo, sha
    from .provenance import write_json

    priors_path = ROOT / cfg["priors"]
    priors = load_priors(priors_path)
    d = load_attributes(fit_cfg)
    features = cfg.get("features") or fit_cfg["features"]
    reference = {f: str(v) for f, v in fit_cfg["reference_classes"].items()}
    folds, _ = region_folds(d, fit_cfg.get("folds", 5), fit_cfg.get("seed", 1300))
    folds = np.asarray(folds)
    rgo = load_rgo(cfg, d.index)
    weight = irrigation_weight(d.index, cfg)
    floor = float(cfg["rgo_floor"])
    goods = sorted(priors["goods"])
    if cfg.get("goods"):
        goods = [g for g in goods if g in cfg["goods"]]
    climates = sorted(d["climate"].unique())
    coef_rows, metric_rows, pred_rows, floor_rows, overruled_all, violations = [], [], [], [], [], []
    for good in goods:
        rows, metrics, overruled, pred, y, viable, is_rgo = build_good(d, good, priors, cfg, fit_cfg, folds, rgo, weight)
        violations += check_rows(rows, good, priors, features, reference)
        coef = absolute_to_handover(good, rows, climates, reference)
        for c in coef:
            f, v = c["attribute"], c["value"]
            c["rgo_locations"] = int(is_rgo.sum()) if f == "reference" else int((is_rgo & (d[f].astype(str) == v).to_numpy()).sum())
        coef_rows += coef
        metric_rows.append(metrics)
        overruled_all += overruled
        for tag, tv, pv, vv in zip(d.index[is_rgo], y[is_rgo], pred[is_rgo], viable[is_rgo]):
            pred_rows.append({"location_tag": tag, "good": good, "target": tv if vv else np.nan, "predicted": pv, "viable": bool(vv)})
            if not vv:
                floor_rows.append({"location_tag": tag, "good": good, "predicted": pv, "target": np.nan, "reason": "not viable in the efficiency data"})
            elif pv < floor:
                floor_rows.append({"location_tag": tag, "good": good, "predicted": pv, "target": tv, "reason": f"predicted below floor {floor}"})
    if violations:
        raise ValueError("goods rows break the sign table:\n" + "\n".join(violations))
    coef = pd.DataFrame(coef_rows)
    metrics = pd.DataFrame(metric_rows)
    preds = pd.DataFrame(pred_rows)
    floors = pd.DataFrame(floor_rows)
    over = pd.DataFrame(overruled_all, columns=["good", "attribute", "value", "data", "row"])
    coef.to_csv(out / "coefficients.csv", index=False)
    metrics.to_csv(out / "metrics.csv", index=False, float_format="%.4f")
    preds.to_csv(out / "location_predictions.csv", index=False, float_format="%.4f")
    floors.to_csv(out / "rgo_floor.csv", index=False, float_format="%.4f")
    over.to_csv(out / "priors_overruled.csv", index=False)
    non_ref = coef[coef.attribute != "reference"]
    per_class = non_ref.groupby(["attribute", "value"]).size()
    summary = {
        "method": "constrained", "goods": len(goods), "goods_fitted": len(goods), "total_rows": int(len(non_ref)),
        "rows_per_class_value_mean": float(per_class.mean()) if len(per_class) else 0.0,
        "rows_per_class_value_max": int(per_class.max()) if len(per_class) else 0,
        "median_r2_viable_heldout": float(metrics.r2_viable_heldout.median()),
        "median_r2_rgo_heldout": float(metrics.r2_rgo_heldout.median()),
        "mean_mae_rgo_heldout": float(metrics.mae_rgo_heldout.mean()),
        "rgo_below_floor_share": float(metrics.rgo_below_floor_share.mean()),
        "rgo_nonviable_share": float(metrics.rgo_nonviable_share.mean()),
        "floor_list": int(len(floors)), "priors_overruled": int(len(over)), "sign_table_violations": 0,
    }
    inputs = {"tables": manifest.get("goods", {}), "rgo_source": sha(ROOT / cfg["rgo_source"]), "priors": sha(priors_path)}
    for key in ("rainfed_tables_directory", "irrigated_overrides_directory"):
        mp = ROOT / cfg[key] / "manifest.json"
        inputs[key] = json.loads(mp.read_text()) if mp.exists() else None
    write_json(out / "report.json", {
        "config": cfg, "summary": summary, "inputs": inputs, "reference_classes": fit_cfg["reference_classes"], "features": features,
        "scope": "Rows on displayed attributes only; climate rows absolute (reference row = the climate reference class); the game keeps its RGO; the constructor keeps its floor carve-out.",
    })
    s = summary
    lines = [
        "# Goods output modifiers from attributes (constrained)", "",
        f"{len(goods)} goods; target = V2 labor-output score (rain-fed, lifted to irrigated by the historical irrigated share, "
        f"saturating at {cfg['irrigation_weight']['saturation']:.0%}), centred on each good's median viable location, x{cfg['target_scale']}; "
        f"signs from `{cfg['priors']}`; ridge {cfg['ridge_locations']} location-equivalents; rows under {cfg['display_threshold']} dropped.", "",
        f"Rows: {s['total_rows']} total, {s['rows_per_class_value_mean']:.1f} per attribute value on average, max {s['rows_per_class_value_max']}. "
        f"Median held-out R² on viable locations {s['median_r2_viable_heldout']:.3f}, on RGO locations {s['median_r2_rgo_heldout']:.3f}. "
        f"Sign-table violations: 0. Rows where the priors moved the data by 0.1 or more or flipped its sign: {s['priors_overruled']} (priors_overruled.csv).", "",
        "| Good | Viable | RGO | Rows | R² held-out (viable) | R² held-out (RGO) | RGO median | Under floor | Non-viable RGO | Overruled |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in metrics.itertuples():
        lines.append(f"| {r.good} | {r.viable_locations:,} | {r.rgo_locations:,} | {r.rows} | {r.r2_viable_heldout:.3f} | {r.r2_rgo_heldout:.3f} | "
                     f"{r.predicted_rgo_median:+.2f} | {100 * r.rgo_below_floor_share:.1f}% | {100 * r.rgo_nonviable_share:.1f}% | {r.priors_overruled} |")
    lines += ["", "Files: coefficients.csv (good, attribute, value, modifier; the reference row is the climate reference class), metrics.csv, "
              "location_predictions.csv, rgo_floor.csv, priors_overruled.csv."]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    return {"summary": summary}
