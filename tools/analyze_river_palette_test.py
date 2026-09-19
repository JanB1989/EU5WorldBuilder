"""Compare a palette-test native save export with the assigned pixel indices."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--experiment", type=Path, default=Path("artifacts/rivers/palette_test"))
    args = parser.parse_args()
    payload = json.loads(args.export.read_text())
    exported = pd.DataFrame(payload["rows"]).rename(columns=lambda x: x.removeprefix("river_exporter_"))
    assigned = pd.read_csv(args.experiment / "assignments.csv", keep_default_na=False)
    assert not exported.location_tag.duplicated().any()
    assert set(exported.location_tag) == set(assigned.location_tag)
    assert exported.palette_experiment.eq(1).all(), "Wrong mod/save: missing experiment marker"
    assert exported.schema.eq(2).all()
    flags = exported[[f"size_{i}" for i in range(1, 6)]]
    assert flags.isin([0, 1]).all().all()
    assert np.array_equal(exported.river_level, (flags.to_numpy() * np.arange(1, 6)).max(axis=1))
    assigned = assigned.rename(columns={"river_level": "baseline_level"})
    frame = assigned.merge(exported[["location_tag", "river_level", "palette_experiment"]], on="location_tag", validate="one_to_one")
    clean = frame[frame.clean_case]
    matrix = pd.crosstab(clean.assigned_index, clean.river_level).reindex(columns=range(6), fill_value=0)
    matrix.to_csv(args.experiment / "palette_level_counts.csv")
    frame.to_csv(args.experiment / "results.csv", index=False)
    manifest = json.loads((args.experiment / "manifest.json").read_text())
    report = {"source": payload["source"], "export_sha256": hashlib.sha256(args.export.read_bytes()).hexdigest(),
              "all_locations": len(frame), "clean_cases": len(clean), "multiple_active_flags": int(flags.sum(axis=1).gt(1).sum()), "results": []}
    for index, counts in matrix.iterrows():
        nonzero = {int(level): int(n) for level, n in counts.items() if n}
        modal = int(counts.idxmax())
        report["results"].append({"palette_index": int(index), "rgb": manifest["palette"][str(index)], "level_counts": nonzero,
                                  "modal_level": modal, "unanimous": len(nonzero) == 1,
                                  "examples": clean[(clean.assigned_index == index) & (clean.river_level == modal)].location_tag.head(5).tolist()})
    (args.experiment / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(matrix.to_string())
    print(f"Clean cases: {len(clean)}; complete native exports: {len(frame)}; stacked flags: {report['multiple_active_flags']}")
    print(json.dumps(report["results"], indent=2))


if __name__ == "__main__":
    main()
