"""Validate and import engine-exported river sizes; never fill missing exports."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .location_inventory import read_zone_inventory

LABELS = {0: "No river", 1: "Small river", 2: "Minor river", 3: "River", 4: "Major river", 5: "Great river"}
PREFIX = "river_exporter_"


def validate_rows(rows, inventory):
    d = pd.DataFrame(rows).rename(columns=lambda c: c.removeprefix(PREFIX))
    required = ["schema", "river_level", *[f"size_{i}" for i in range(1, 6)]]
    if not set(required).issubset(d):
        raise ValueError("Missing river exporter fields")
    if d.location_tag.duplicated().any() or set(d.location_tag) != set(inventory.location_tag):
        raise ValueError("River export does not match complete game inventory")
    if d[required].isna().any().any() or not np.isfinite(d[required].to_numpy()).all():
        raise ValueError("Missing or nonfinite river values")
    if not d.schema.eq(2).all():
        raise ValueError("River exporter schema 2 required")
    flags = d[[f"size_{i}" for i in range(1, 6)]]
    if not flags.isin([0, 1]).all().all():
        raise ValueError("Unexpected native river-size effect")
    largest = (flags.to_numpy() * np.arange(1, 6)).max(axis=1)
    if not np.array_equal(d.river_level, largest):
        raise ValueError("Exported river level differs from largest active size")
    # Presence flags are sparse by exporter design, but size and schema are mandatory.
    for f in ["has_river", "is_adjacent_to_lake"]:
        d[f] = d.get(f, pd.Series(0, index=d.index)).fillna(0)
        if not d[f].isin([0, 1]).all():
            raise ValueError("Invalid presence flag")
        d[f] = d[f].astype(bool)
    if not np.array_equal(d.has_river, d.river_level.gt(0)):
        raise ValueError("Native has_river and native size effects disagree")
    d[required] = d[required].astype(int)
    d["active_size_count"] = flags.sum(axis=1).astype(int)
    d["river_label"] = d.river_level.map(LABELS)
    return d.merge(inventory, on="location_tag", validate="one_to_one").sort_values("location_tag")


def build(source, raw, output):
    source, raw, output = Path(source), Path(raw), Path(output)
    payload = json.loads(source.read_text())
    d = validate_rows(payload["rows"], read_zone_inventory(raw))
    own = d[d.is_ownable]
    report = {
        "passed": True, "source": payload["source"],
        "source_json_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "all_locations": len(d), "ownable_locations": len(own), "missing_locations": 0,
        "all_level_counts": {str(i): int(d.river_level.eq(i).sum()) for i in LABELS},
        "ownable_level_counts": {str(i): int(own.river_level.eq(i).sum()) for i in LABELS},
        "multiple_active_sizes": int(d.active_size_count.gt(1).sum()),
        "presence_size_mismatches": 0,
        "meaning": "Largest active native river_flowing_through_N effect, not inferred from river bitmap colours.",
    }
    output.mkdir(parents=True, exist_ok=True)
    d.to_csv(output / "locations.csv", index=False)
    d.to_parquet(output / "locations.parquet", index=False)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
