"""No improvement starts above its cap (2026-10-24, Jan: everything by the book, no exceptions)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def test_config_clamps_starting_levels_to_the_cap() -> None:
    cfg = json.loads((ROOT / "configs/building_assignment.json").read_text(encoding="utf-8"))
    assert cfg["clamp_start_to_cap"] is True


def test_handover_starting_levels_never_exceed_the_cap() -> None:
    path = ROOT / "artifacts/handover/latest/location_buildings.csv"
    if not path.is_file():   # no handover in this checkout yet
        return
    rows = pd.read_csv(path, keep_default_na=False)
    over = rows[rows.starting_levels > rows.cap_at_start]
    assert over.empty, over.head(10).to_string()
    types = pd.read_csv(ROOT / "artifacts/handover/latest/building_types.csv", keep_default_na=False)
    groups = dict(zip(types.building, types.cap_group))
    rows["group"] = [groups.get(b) or b for b in rows.building]
    shared = rows.groupby(["location_tag", "group"]).agg(start=("starting_levels", "sum"), cap=("cap_at_start", "max"))
    assert (shared.start <= shared.cap).all(), shared[shared.start > shared.cap].head(10).to_string()
