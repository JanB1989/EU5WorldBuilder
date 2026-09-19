"""Empirically crosscheck the installed river bitmap against engine-exported levels.

This is an audit, not a replacement for engine exports. Untested palette entries
deliberately have no guessed level. Run with uv run python tools/audit_river_bitmap.py
--map-dir /path/to/game/in_game/map_data.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from scipy.ndimage import convolve, maximum_filter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map-dir", type=Path, required=True)
    parser.add_argument("--export", type=Path, default=Path("artifacts/rivers/locations.csv"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/rivers/bitmap_audit"))
    args = parser.parse_args()
    Image.MAX_IMAGE_PIXELS = None  # Trusted, installed 16384 x 8192 game maps.
    with Image.open(args.map_dir / "rivers.png") as im:
        if im.mode != "P":
            raise ValueError("Expected indexed river bitmap")
        palette = im.getpalette()
        rivers = np.asarray(im).copy()
    with Image.open(args.map_dir / "locations.png") as im:
        locations = np.asarray(im.convert("RGB"))
    if rivers.shape != locations.shape[:2]:
        raise ValueError("Game bitmaps do not align")
    observed = set(np.unique(rivers).tolist())
    expected = {0, 1, 2, 4, 5, 11, 15, 254, 255}
    if observed - expected:
        raise ValueError(f"Untested palette entries: {observed - expected}")
    frame = pd.read_csv(args.export, keep_default_na=False)
    frame["rgb"] = frame.map_color_rgb.map(lambda s: int(s, 16))
    frame = frame.sort_values("rgb").reset_index(drop=True)
    colors = frame.rgb.to_numpy()
    if len(np.unique(colors)) != len(colors):
        raise ValueError("Nonunique location colours")
    mask = rivers < 16
    pixels = locations[mask].astype(np.int32)
    rgb = (pixels[:, 0] << 16) | (pixels[:, 1] << 8) | pixels[:, 2]
    indices = np.searchsorted(colors, rgb)
    if np.any(indices >= len(colors)) or np.any(colors[indices] != rgb):
        raise ValueError("River pixels reference unknown location colours")
    river_pixels = rivers[mask]
    for value in [0, 1, 2, 4, 5, 11, 15]:
        counts = np.zeros(len(frame), dtype=np.int32)
        np.add.at(counts, indices[river_pixels == value], 1)
        frame[f"pixels_{value}"] = counts
    lookup = np.zeros(256, dtype=np.uint8)
    lookup[[4, 5, 11, 15]] = [1, 1, 3, 5]

    def aggregate(pixel_values):
        result = np.zeros(len(frame), dtype=np.uint8)
        np.maximum.at(result, indices, pixel_values)
        return result

    frame["width_only"] = aggregate(lookup[river_pixels])
    lookup[[1, 2]] = 5
    values = lookup[river_pixels]
    frame["width_and_junctions"] = aggregate(values)
    # Separate exploratory path-end filter, not an established engine rule.
    degree = convolve(mask.astype(np.uint8), np.array([[0, 1, 0], [1, 0, 1], [0, 1, 0]], dtype=np.uint8), mode="constant")
    near_water = maximum_filter((rivers == 254).astype(np.uint8), size=3) > 0
    ends = (degree[mask] <= 1) & ~near_water[mask] & (river_pixels >= 3)
    frame["inland_endpoint_hypothesis"] = aggregate(np.where(ends, 0, values))
    report = {
        "scope": "Empirical EU5 bitmap audit; does not establish unobserved palette thresholds or engine internals",
        "sources": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.map_dir / "rivers.png", args.map_dir / "locations.png", args.export]},
        "palette": {str(k): {"rgb": palette[k*3:k*3+3], "pixels": int((rivers == k).sum())} for k in sorted(observed)},
        "checks": {},
    }
    for name in ["width_only", "width_and_junctions", "inland_endpoint_hypothesis"]:
        wrong = frame[name] != frame.river_level
        report["checks"][name] = {"all_matches": int((~wrong).sum()), "all_locations": len(frame), "ownable_mismatches": int((wrong & frame.is_ownable).sum()), "exceptions": frame.loc[wrong, "location_tag"].tolist()}
    marker_promotion = (frame.width_only < 5) & (frame.pixels_1 + frame.pixels_2 > 0)
    report["junction_promotions_to_5"] = {"all": int(marker_promotion.sum()), "ownable": int((marker_promotion & frame.is_ownable).sum())}
    args.output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output / "locations.csv", index=False)
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"checks": {k: {x: y for x, y in v.items() if x != "exceptions"} for k, v in report["checks"].items()}, "junction_promotions_to_5": report["junction_promotions_to_5"]}, indent=2))


if __name__ == "__main__":
    main()
