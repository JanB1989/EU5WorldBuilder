"""Import the vanilla game-start state (RGOs, development, population, settlement rank) for the World Builder.

The game decides each location's RGO, starting development, population and settlement rank. This script
writes them into the ignored game-reference inputs the pipeline reads:

- data/raw/vanilla/location_raw_material_1337.csv  location_tag, raw_material   (vanilla location templates)
- data/raw/vanilla/start_development_1337.csv      location_tag, development    (vanilla start save)
- data/raw/location_inputs/starting_population_source.csv
      eu5_start_population, eu5_burghers, eu5_peasants, eu5_tribesmen, eu5_slaves and starting_location_rank
      replaced from the start save (people, not thousands); every other column is kept as diagnostic history.
- evidence/vanilla_start_manifest.json             save, game templates, hashes, counts, checks

The start save is read with the project's Rust/Polars save engine (eu5-game-parser), so run it from the
constructor environment, which has that engine installed (read-only use of the constructor):

    uv run --project ../ProsperOrPerishConstructor python scripts/import_vanilla_start.py --save <vanilla 1337.4.1 save>

The save must be a VANILLA game started on 1337.4.1 (no mods), so development, pops and ranks are the
game's own start values. Raw materials come from the game templates (the game keeps its RGOs); the save's
RGOs are compared as a check.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RANKS = {"rural_settlement": "rural_or_unranked", "town": "town", "city": "city", "megalopolis": "megalopolis"}
POPS = {"eu5_burghers": "population_burghers", "eu5_peasants": "population_peasants",
        "eu5_tribesmen": "population_tribesmen", "eu5_slaves": "population_slaves"}


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def template_raw_materials(path: Path) -> dict[str, str]:
    text = re.sub(r"#[^\n]*", "", path.read_text(encoding="utf-8-sig"))
    out = {}
    for m in re.finditer(r"(?m)^([\w.-]+)\s*=\s*\{([^{}]*)\}", text):
        hit = re.search(r"\braw_material\s*=\s*(\w+)", m[2])
        if hit:
            out[m[1]] = hit[1]
    return out


def save_locations(save: Path, constructor: Path):
    import polars as pl
    from eu5gameparser.savegame.exporter import load_savegame_tables

    t = load_savegame_tables(save_path=save, profile="constructor",
                             load_order_path=constructor / "constructor.load_order.toml")
    import pandas as pd

    loc = t.locations
    if not isinstance(loc, pl.DataFrame):
        loc = pl.DataFrame(loc)
    return pd.DataFrame(loc.to_dict(as_series=False))   # no pyarrow needed


def main() -> None:
    import pandas as pd

    a = argparse.ArgumentParser()
    a.add_argument("--save", type=Path, required=True, help="vanilla 1337.4.1 start save (.eu5)")
    a.add_argument("--constructor", type=Path, default=ROOT.parent / "ProsperOrPerishConstructor")
    a.add_argument("--templates", type=Path, default=ROOT / "data/raw/location_inputs/game_templates.txt")
    args = a.parse_args()
    raw = ROOT / "data/raw"
    loc = save_locations(args.save, args.constructor)
    meta = {"save": str(args.save), "save_bytes": args.save.stat().st_size}
    dates = loc["date"].dropna().unique().tolist() if "date" in loc else []
    meta["save_date"] = str(dates[0]) if dates else None
    loc = loc.set_index("slug")

    # RGOs: the game templates (the game keeps them); the save is the check.
    rgo = template_raw_materials(args.templates)
    rgo_table = pd.DataFrame({"location_tag": sorted(rgo), "raw_material": [rgo[k] for k in sorted(rgo)]})
    (raw / "vanilla").mkdir(parents=True, exist_ok=True)
    rgo_table.to_csv(raw / "vanilla/location_raw_material_1337.csv", index=False)
    in_save = loc["raw_material"].reindex(rgo_table.location_tag)
    differs = rgo_table[in_save.fillna("").to_numpy() != rgo_table.raw_material.to_numpy()]

    # Development, population and rank of every location that has an RGO (the settlement land).
    tags = rgo_table.location_tag
    dev = pd.to_numeric(loc["development"], errors="coerce").reindex(tags)
    pd.DataFrame({"location_tag": tags, "development": dev.fillna(0.0).round(3).to_numpy()}).to_csv(
        raw / "vanilla/start_development_1337.csv", index=False, float_format="%.3f")

    source = raw / "location_inputs/starting_population_source.csv"
    old = pd.read_csv(source, keep_default_na=False, dtype=str)
    new = old.copy()
    s = loc.reindex(old.location_tag)
    total = pd.to_numeric(s["total_population"], errors="coerce").fillna(0.0) * 1000.0
    new["eu5_start_population"] = total.round(1).to_numpy()
    for col, field in POPS.items():
        if col in new:
            new[col] = (pd.to_numeric(s[field], errors="coerce").fillna(0.0) * 1000.0).round(1).to_numpy()
    new["starting_location_rank"] = s["rank"].map(RANKS).fillna("rural_or_unranked").to_numpy()
    new.to_csv(source, index=False)

    # Receipt of the replaced starting population file.
    manifest_path = ROOT / "evidence/location_input_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for r in manifest["sources"]:
        if r["path"].endswith("starting_population_source.csv"):
            r.update(sha256=sha(source), bytes=source.stat().st_size, origin=str(args.save),
                     role="Vanilla game-start population and settlement rank from the start save (scripts/import_vanilla_start.py); contextual only. Other columns are kept diagnostics of the earlier constructor capacity map.")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    old_pop = pd.to_numeric(old.eu5_start_population, errors="coerce").fillna(0.0)
    old_rank = old.starting_location_rank
    report = {
        **meta,
        "game_templates": {"path": str(args.templates.relative_to(ROOT)), "sha256": sha(args.templates)},
        "outputs": {p: sha(ROOT / p) for p in ["data/raw/vanilla/location_raw_material_1337.csv",
                                               "data/raw/vanilla/start_development_1337.csv",
                                               "data/raw/location_inputs/starting_population_source.csv"]},
        "rgo_locations": int(len(rgo_table)),
        "rgo_counts": rgo_table.raw_material.value_counts().to_dict(),
        "rgo_save_differs_from_templates": differs.assign(in_save=in_save.reindex(differs.location_tag).to_numpy()).to_dict("records"),
        "development": {"locations": int(len(tags)), "missing_in_save_set_to_0": int(dev.isna().sum()),
                        "sum": float(dev.fillna(0).sum()), "median_positive": float(dev[dev > 0].median()), "max": float(dev.max())},
        "population": {"total_before": float(old_pop.sum()), "total_after": float(total.sum()),
                       "locations_changed_over_1000": int(((total.to_numpy() - old_pop.to_numpy()) ** 2 > 1e6).sum())},
        "rank_changes": {f"{a}->{b}": int(n) for (a, b), n in pd.crosstab(old_rank, new.starting_location_rank).stack().items() if n and a != b},
        "note": "Vanilla 1337.4.1 start: development, population and settlement rank from the save; RGOs from the game templates.",
    }
    (ROOT / "evidence/vanilla_start_manifest.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("rgo_counts", "outputs")}, indent=2, default=str))


if __name__ == "__main__":
    main()
