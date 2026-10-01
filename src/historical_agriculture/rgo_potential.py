"""Conflict report: starting RGOs against the goods' vanilla ``location_potential`` under our geography.

EU5 1.4 gives 20 raw materials a ``location_potential`` (allowed climate, vegetation, topography, region or
area). The World Builder keeps vanilla's rules unchanged; this report lists every starting RGO (location x
raw_material) whose good's rule fails under the World Builder geography, with both error sides against the
same rule on vanilla's own 1.4 geography:

- introduced: passes on vanilla geography, fails on ours (our geography breaks a vanilla RGO);
- resolved:   fails on vanilla geography, passes on ours (vanilla's own 1.4 conflict our geography removes);
- both:       fails on both (vanilla's own conflict, kept);
- ok:         passes on both.

"Ours" is the rule as the geography export applies it: a vanilla key also matches the World Builder
subtypes that the compatibility layer maps to it (geography_compatibility.families, e.g. continental also
matches ha1300_climate_continental_monsoon). The starting-lumber whitelist the export adds to lumber's rule
is reported separately (``wb_whitelist``), not counted as a pass. Eligible land per good (every ownable
location the rule allows) is compared the same way: gained and lost against vanilla geography.

Outputs in artifacts/rgo_potential: conflicts.csv (every starting RGO of a good with a rule), goods.csv,
report.json, report.md.
"""
from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ATTRS = ("climate", "vegetation", "topography")


# --------------------------------------------------------------------------------------------- parsing
def tokens(text):
    text = re.sub(r"#[^\n]*", "", text)
    return re.findall(r'"[^"]*"|[{}=]|[^\s{}=]+', text)


def parse_block(tok, i):
    """tok[i] is just after '{'; returns ([(key, value)], next index); value is str or list."""
    out = []
    while i < len(tok):
        t = tok[i]
        if t == "}":
            return out, i + 1
        if i + 1 < len(tok) and tok[i + 1] == "=":
            key = t
            if tok[i + 2] == "{":
                val, i = parse_block(tok, i + 3)
            else:
                val, i = tok[i + 2], i + 3
            out.append((key, val))
        else:
            out.append((None, t)); i += 1
    return out, i


def goods_potentials(goods_dir: Path) -> dict[str, list]:
    """good -> parsed location_potential entries, for every top-level good that has one."""
    rules = {}
    for path in sorted(Path(goods_dir).glob("*.txt")):
        tok = tokens(path.read_text(encoding="utf-8-sig"))
        i = 0
        while i < len(tok):
            if i + 2 < len(tok) and tok[i + 1] == "=" and tok[i + 2] == "{":
                name = tok[i]
                body, i = parse_block(tok, i + 3)
                for key, val in body:
                    if key == "location_potential":
                        rules[name] = val
                continue
            i += 1
    return rules


def named_keys(entries, found=None):
    """{attribute: set of keys} named anywhere in a rule."""
    found = found if found is not None else {a: set() for a in ATTRS}
    for key, val in entries:
        if isinstance(val, list):
            named_keys(val, found)
        elif key in ATTRS:
            found[key].add(val)
    return found


def describe(key, val):
    if isinstance(val, list):
        inner = sorted({k for k, v in val if k in ATTRS + ("region", "area", "province", "this")} | {k for k, v in val if isinstance(v, list)})
        return f"{key}({'/'.join(inner)})"
    return f"{key}={val}"


# --------------------------------------------------------------------------------------------- evaluation
class Location:
    def __init__(self, tag, geo, region, area, province, families=None):
        self.tag, self.geo, self.region, self.area, self.province = tag, geo, region, area, province
        self.families = families or {}

    def match(self, attr, value):
        mine = self.geo.get(attr)
        if mine is None or mine == "":
            return False
        return mine == value or mine in self.families.get(attr, {}).get(value, ())


def evaluate(entries, loc, mode="and"):
    results = [clause(k, v, loc) for k, v in entries if k is not None]
    if mode == "and":
        return all(results)
    if mode == "or":
        return any(results)
    if mode == "nor":
        return not any(results)
    raise ValueError(mode)


def clause(key, val, loc):
    if key in ("AND",):
        return evaluate(val, loc, "and")
    if key == "OR":
        return evaluate(val, loc, "or")
    if key in ("NOR",):
        return evaluate(val, loc, "nor")
    if key == "NOT":
        return not evaluate(val, loc, "and")
    if key in ATTRS:
        return loc.match(key, val)
    if key == "region" and isinstance(val, str):
        return loc.region == val.split(":", 1)[-1]
    if key == "province" and isinstance(val, str):
        return loc.province == val.split(":", 1)[-1]
    if key == "area":
        if isinstance(val, str):
            return loc.area == val.split(":", 1)[-1]
        # area = { is_area_sea = no }: every RGO location is land
        for k, v in val:
            if k == "is_area_sea":
                return v == "no"
        raise ValueError(f"unsupported area scope {val}")
    if key == "this" and isinstance(val, str):
        return loc.tag == val.split(":", 1)[-1]
    raise ValueError(f"unsupported location_potential clause {key} = {val}")


def failing(entries, loc):
    return [describe(k, v) for k, v in entries if k is not None and not clause(k, v, loc)]


# --------------------------------------------------------------------------------------------- inputs
def vanilla_geography(templates: Path) -> pd.DataFrame:
    text = re.sub(r"#[^\n]*", "", templates.read_text(encoding="utf-8-sig"))
    rows = []
    for m in re.finditer(r"(?m)^([\w.-]+)\s*=\s*\{([^{}]*)\}", text):
        fields = dict(re.findall(r"(\w+)\s*=\s*([\w.]+)", m[2]))
        rows.append({"location_tag": m[1], **{a: fields.get(a, "") for a in ATTRS}, "raw_material": fields.get("raw_material", "")})
    return pd.DataFrame(rows).set_index("location_tag")


def our_geography() -> pd.DataFrame:
    cols = {}
    for attr in ATTRS:
        t = pd.read_csv(ROOT / f"artifacts/{attr}/locations.csv", keep_default_na=False).set_index("location_tag")
        cols[attr] = t[f"game_{attr}"]
    return pd.DataFrame(cols)


def build(output=None, local_config=None):
    from .geography_compatibility import families
    out = Path(output or ROOT / "artifacts/rgo_potential"); out.mkdir(parents=True, exist_ok=True)
    local = tomllib.loads(Path(local_config or ROOT / "geography_test.local.toml").read_text())
    game = Path(local["paths"]["game_root"]) / "game"
    rules = goods_potentials(game / "in_game/common/goods")
    vanilla = vanilla_geography(ROOT / "data/raw/location_inputs/game_templates.txt")
    ours = our_geography().reindex(vanilla.index)
    inv = pd.read_parquet(ROOT / "data/raw/location_inputs/inventory.parquet").set_index("location_tag")
    from .location_inventory import read_zone_inventory
    zones = read_zone_inventory(ROOT / "data/raw/location_inputs").set_index("location_tag")
    rgo = pd.read_csv(ROOT / "data/raw/vanilla/location_raw_material_1337.csv", keep_default_na=False).set_index("location_tag").raw_material
    fam = families()
    emitted = {a: set(ours[a].dropna()) | set(fam.get(a, {})) for a in ATTRS}
    lumber_whitelist = set(vanilla.index[vanilla.raw_material == "lumber"])

    def loc_pair(tag):
        region, area, province = (inv.at[tag, c] if tag in inv.index else "" for c in ("region", "area", "province"))
        v = Location(tag, {a: vanilla.at[tag, a] for a in ATTRS}, region, area, province)
        o = Location(tag, {a: ours.at[tag, a] for a in ATTRS}, region, area, province, fam)
        return v, o

    ownable = [t for t in vanilla.index if t in zones.index and bool(zones.at[t, "is_ownable"])]
    pairs = {t: loc_pair(t) for t in ownable}
    conflicts, goods = [], []
    unknown_keys = {}
    for good, rule in sorted(rules.items()):
        names = named_keys(rule)
        missing = {a: sorted(k for k in keys if k not in emitted[a]) for a, keys in names.items()}
        missing = {a: k for a, k in missing.items() if k}
        if missing:
            unknown_keys[good] = missing
        tags = [t for t in rgo.index[rgo == good] if t in pairs]
        counts = {"introduced": 0, "resolved": 0, "both": 0, "ok": 0}
        for tag in tags:
            v, o = pairs[tag]
            pv, po = evaluate(rule, v), evaluate(rule, o)
            status = "ok" if pv and po else "introduced" if pv else "resolved" if po else "both"
            counts[status] += 1
            conflicts.append({"location_tag": tag, "raw_material": good, "status": status,
                              "vanilla_pass": pv, "ours_pass": po,
                              "ours_failing": ";".join(failing(rule, o)), "vanilla_failing": ";".join(failing(rule, v)),
                              "wb_whitelist": good == "lumber" and tag in lumber_whitelist,
                              **{f"ours_{a}": ours.at[tag, a] for a in ATTRS}, **{f"vanilla_{a}": vanilla.at[tag, a] for a in ATTRS},
                              "region": inv.at[tag, "region"] if tag in inv.index else "", "macro_region": inv.at[tag, "macro_region"] if tag in inv.index else ""})
        ev = eo = gained = lost = 0
        for tag, (v, o) in pairs.items():
            pv, po = evaluate(rule, v), evaluate(rule, o)
            ev += pv; eo += po; gained += po and not pv; lost += pv and not po
        goods.append({"good": good, "rgo_locations": len(tags), "ours_fail": counts["introduced"] + counts["both"],
                      "vanilla_fail": counts["resolved"] + counts["both"], **counts,
                      "eligible_vanilla": ev, "eligible_ours": eo, "eligible_gained": gained, "eligible_lost": lost})
    c = pd.DataFrame(conflicts)
    g = pd.DataFrame(goods).sort_values(["ours_fail", "rgo_locations"], ascending=False)
    c.sort_values(["status", "raw_material", "location_tag"]).to_csv(out / "conflicts.csv", index=False)
    g.to_csv(out / "goods.csv", index=False)
    # where do the introduced conflicts come from: which clause attribute fails, which of our classes
    intro = c[c.status == "introduced"]
    by_clause = intro.ours_failing.str.split(";").explode().value_counts().to_dict() if len(intro) else {}
    worst = []
    for good, grp in intro.groupby("raw_material"):
        for attr in ATTRS:
            hit = grp[grp.ours_failing.str.contains(attr)]
            if len(hit):
                top = hit[f"ours_{attr}"].value_counts().head(4).to_dict()
                worst.append({"good": good, "attribute": attr, "locations": int(len(hit)), "our_classes": top})
    totals = {k: int(g[k].sum()) for k in ["rgo_locations", "ours_fail", "vanilla_fail", "introduced", "resolved", "both", "ok"]}
    report = {"goods_with_rules": len(rules), "totals": totals, "unknown_keys_in_rules": unknown_keys,
              "introduced_by_failing_clause": by_clause, "introduced_by_good_and_attribute": worst,
              "lumber_whitelist_rgos": int(c.wb_whitelist.sum()) if len(c) else 0,
              "evaluation": "ours = vanilla rule with World Builder subtypes matching their parent key (export compatibility); vanilla = same rule on the 1.4 templates' climate/vegetation/topography. Region/area from the location inventory; area = { is_area_sea = no } is true on land.",
              "rule_policy": "Vanilla 1.4 location_potential kept unchanged (Jan, 2026-10-01). Unknown keys would need a rename fix; none when unknown_keys_in_rules is empty."}
    (out / "report.json").write_text(json.dumps(report, indent=2, default=int) + "\n")
    lines = ["# Starting RGOs against vanilla 1.4 location_potential", "",
             f"{len(rules)} goods carry a vanilla `location_potential`; {totals['rgo_locations']:,} starting RGOs belong to them. "
             f"Under the World Builder geography {totals['ours_fail']:,} fail their good's rule, under vanilla's own 1.4 geography {totals['vanilla_fail']:,}.", "",
             f"- introduced (pass on vanilla, fail on ours): **{totals['introduced']:,}**",
             f"- resolved (fail on vanilla, pass on ours): **{totals['resolved']:,}**",
             f"- both fail (vanilla's own conflict, kept): **{totals['both']:,}**",
             f"- ok: {totals['ok']:,}", "",
             "Rules are kept as vanilla wrote them. Names in the rules our geography never emits: " + (json.dumps(unknown_keys) if unknown_keys else "none") + ".", "",
             "| Good | RGOs | Fail ours | Fail vanilla | Introduced | Resolved | Both | Eligible vanilla | Eligible ours | Gained | Lost |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in g.itertuples():
        lines.append(f"| {r.good} | {r.rgo_locations:,} | {r.ours_fail:,} | {r.vanilla_fail:,} | {r.introduced:,} | {r.resolved:,} | {r.both:,} | "
                     f"{r.eligible_vanilla:,} | {r.eligible_ours:,} | {r.eligible_gained:,} | {r.eligible_lost:,} |")
    lines += ["", "## Introduced conflicts by good and attribute", "", "| Good | Attribute | RGOs | Our classes (top) |", "|---|---|---:|---|"]
    for w in sorted(worst, key=lambda w: -w["locations"]):
        lines.append(f"| {w['good']} | {w['attribute']} | {w['locations']} | {', '.join(f'{k} {v}' for k, v in w['our_classes'].items())} |")
    lines += ["", "Lumber: the geography export whitelists the starting lumber RGOs in lumber's rule (`wb_whitelist`); the counts above evaluate the rule without it.",
              "", "Files: conflicts.csv (every starting RGO of a good with a rule: status, failing clauses on both geographies, both classes), goods.csv, report.json. "
              "Rebuild: `uv run worldbuilder rgo-potential`."]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    return report
