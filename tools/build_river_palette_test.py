"""Build a one-launch experiment testing every supported river-width palette index.

Only width indices change. River paths, palette RGB values, sources, connection
markers and backgrounds are preserved. Each location gets one assigned colour;
marker-free locations provide repeated, uncontaminated level measurements.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/rivers/palette_test"))
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    mod = output / "River Palette Test"
    shutil.copytree("tools/river_exporter", mod, dirs_exist_ok=True)
    metadata = mod / ".metadata/metadata.json"
    meta = json.loads(metadata.read_text(encoding="utf-8-sig"))
    meta.update(name="River Palette Test", id="ha1300_river_palette_test", version="1.0.0", short_description="Diagnostic: all 13 river width indices in one export.")
    metadata.write_text(json.dumps(meta, indent=2))
    action = mod / "in_game/common/on_action/river_exporter_game_start.txt"
    action.write_text(action.read_text(encoding="utf-8-sig").replace(
        "set_variable = { name = river_exporter_schema value = 2 }",
        "set_variable = { name = river_exporter_schema value = 2 }\n\t\t\tset_variable = { name = river_exporter_palette_experiment value = 1 }"), encoding="utf-8-sig")
    Image.MAX_IMAGE_PIXELS = None
    original = Image.open(args.map_dir / "rivers.png")
    if original.mode != "P":
        raise ValueError("River map must use indexed colours")
    palette = original.getpalette()
    rivers = np.array(original)
    locations = np.asarray(Image.open(args.map_dir / "locations.png").convert("RGB"))
    if rivers.shape != locations.shape[:2]:
        raise ValueError("Mismatched map geometry")
    frame = pd.read_csv("artifacts/rivers/locations.csv", keep_default_na=False).sort_values("location_tag")
    frame["assigned_index"] = np.arange(len(frame)) % 13 + 3
    frame["rgb"] = frame.map_color_rgb.map(lambda v: int(v, 16))
    frame = frame.sort_values("rgb").reset_index(drop=True)
    mask = rivers < 16
    px = locations[mask].astype(np.int32)
    codes = (px[:, 0] << 16) | (px[:, 1] << 8) | px[:, 2]
    colors = frame.rgb.to_numpy()
    ids = np.searchsorted(colors, codes)
    if np.any(ids >= len(colors)) or np.any(colors[ids] != codes):
        raise ValueError("Unmapped river pixels")
    values = rivers[mask]
    for key, keep in [("width_pixels", values >= 3), ("connection_pixels", (values == 1) | (values == 2)), ("source_pixels", values == 0)]:
        counts = np.zeros(len(frame), np.int32)
        np.add.at(counts, ids[keep], 1)
        frame[key] = counts
    widths = values >= 3
    changed = values.copy()
    changed[widths] = frame.assigned_index.to_numpy()[ids[widths]]
    rivers[mask] = changed
    result = Image.fromarray(rivers)
    result.putpalette(palette)
    map_path = mod / "in_game/map_data/rivers.png"
    map_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(map_path, optimize=False)
    reloaded = Image.open(map_path)
    assert reloaded.mode == "P" and reloaded.getpalette() == palette
    assert np.array_equal(np.asarray(original) < 16, np.asarray(reloaded) < 16)
    assert np.array_equal(np.asarray(original)[~mask], np.asarray(reloaded)[~mask])
    assert np.array_equal(values[~widths], changed[~widths])
    frame["clean_case"] = (frame.width_pixels >= 3) & (frame.connection_pixels == 0) & (frame.river_level > 0)
    frame.to_csv(output / "assignments.csv", index=False)
    files = [args.map_dir / "rivers.png", args.map_dir / "locations.png", map_path, output / "assignments.csv"]
    report = {"design": "Each location is assigned a width index 3..15. Source and junction pixels unchanged. Repeated clean cases have >=3 width pixels, no junctions and a positive baseline native level.",
              "source_version": "EU5 1.3.11", "sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
              "palette": {str(i): palette[3*i:3*i+3] for i in range(3, 16)},
              "clean_cases_per_index": frame[frame.clean_case].groupby("assigned_index").size().to_dict()}
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["clean_cases_per_index"], indent=2))


if __name__ == "__main__":
    main()
