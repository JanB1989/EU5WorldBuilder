"""Build an isolated, directed five-level river showcase along the Seine basin.

Run from the research repository. The generated mod overrides only rivers.png.
It retains one source-to-sea path from the vanilla network, removes that
network's tributaries, and assigns five increasing downstream width stages.
"""
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
from PIL import Image
from scipy.ndimage import convolve, label, maximum_filter


NAME = "River Levels and Flow Showcase"
BBOX = (7500, 1700, 8100, 2300)
SOURCE_XY = (7925, 2058)
STAGES = [(0, 1, 4, "langres"), (87, 2, 7, "troyes"),
          (175, 3, 11, "paris"), (300, 4, 13, "mantes"),
          (415, 5, 15, "rouen")]
CROSS = np.array([[0, 1, 0], [1, 0, 1], [0, 1, 0]])


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/rivers/showcase"))
    parser.add_argument("--deploy-dir", type=Path, help="Explicit live mod parent directory")
    args = parser.parse_args()
    Image.MAX_IMAGE_PIXELS = None
    image = Image.open(args.map_dir / "rivers.png")
    assert image.mode == "P"
    palette = image.getpalette()
    original = np.array(image)
    rivers = original.copy()
    locations = np.asarray(Image.open(args.map_dir / "locations.png").convert("RGB"))
    assert locations.shape[:2] == rivers.shape
    frame = pd.read_csv("artifacts/rivers/locations.csv", keep_default_na=False)
    by_rgb = {int(r.map_color_rgb, 16): r for r in frame.itertuples()}
    x0, y0, x1, y1 = BBOX
    region = rivers[y0:y1, x0:x1]
    components, _ = label(region < 16)
    source = (SOURCE_XY[1] - y0, SOURCE_XY[0] - x0)
    assert region[source] == 0, "Expected vanilla source moved"
    component = components == components[source]
    assert not (component[0].any() or component[-1].any() or component[:, 0].any() or component[:, -1].any())
    assert np.count_nonzero(component & (region == 0)) == 1
    degree = convolve(component.astype(int), CROSS, mode="constant")
    near_sea = maximum_filter((region == 254).astype(int), size=3) > 0
    mouths = np.argwhere(component & near_sea & (degree == 1))
    assert len(mouths) == 1, "Expected one unambiguous sea mouth"
    mouth = tuple(mouths[0])
    parents = {source: None}
    queue = deque([source])
    while queue:
        y, x = queue.popleft()
        for p in ((y-1, x), (y+1, x), (y, x-1), (y, x+1)):
            if component[p] and p not in parents:
                parents[p] = (y, x)
                queue.append(p)
    path = []
    current = mouth
    while current is not None:
        path.append(current)
        current = parents[current]
    path.reverse()
    assert len(path) > STAGES[-1][0] + 20

    # Remove the entire original connected network, including its red/yellow
    # branch markers. Preserve land/water background under removed tributaries.
    for y, x in np.argwhere(component):
        rgb = locations[y+y0, x+x0].astype(int)
        row = by_rgb[(rgb[0] << 16) | (rgb[1] << 8) | rgb[2]]
        region[y, x] = 254 if row.game_zone_class in ("sea_zones", "lakes", "sea_zones+impassable_mountains") else 255
    path_rows = []
    for i, (y, x) in enumerate(path):
        _, level, index, _ = max(s for s in STAGES if s[0] <= i)
        region[y, x] = 0 if i == 0 else index
        rgb = locations[y+y0, x+x0].astype(int)
        tag = by_rgb[(rgb[0] << 16) | (rgb[1] << 8) | rgb[2]].location_tag
        path_rows.append(dict(step=i, x=int(x+x0), y=int(y+y0), level=level,
                              palette_index=int(region[y, x]), location_tag=tag))
    path_frame = pd.DataFrame(path_rows)
    new_mask = region < 16
    new_component = np.zeros_like(component)
    for p in path:
        new_component[p] = True
    assert np.array_equal(new_mask & component, new_component)
    path_degree = convolve(new_component.astype(int), CROSS, mode="constant")
    assert np.count_nonzero(path_degree[new_component] == 1) == 2
    assert np.all(path_degree[new_component] <= 2), "Path contains a branch or self-touch"
    assert region[source] == 0 and region[mouth] == 15
    assert not np.isin(region[new_component], [1, 2]).any()
    assert np.all(np.diff(path_frame.level) >= 0)
    assert np.array_equal(region[~component], original[y0:y1, x0:x1][~component])

    # Evaluate the whole polygon for each inspection location, including rivers
    # outside the edited network, so another channel cannot mask a test level.
    lookup = np.zeros(256, dtype=np.uint8)
    for i in range(3, 16):
        lookup[i] = min(5, (i-3)//3 + 1)
    lookup[[1, 2]] = 5
    water_pixels = rivers < 16
    rgb = locations[water_pixels].astype(np.int32)
    packed = (rgb[:, 0] << 16) | (rgb[:, 1] << 8) | rgb[:, 2]
    inspection = []
    for start, level, index, tag in STAGES:
        code = int(frame.set_index("location_tag").loc[tag, "map_color_rgb"], 16)
        got = int(lookup[rivers[water_pixels][packed == code]].max())
        assert got == level, f"{tag}: expected {level}, bitmap predicts {got}"
        count = int((path_frame.location_tag == tag).sum())
        assert count >= 10
        inspection.append(dict(location_tag=tag, expected_level=level,
                               palette_index=index, rgb=palette[3*index:3*index+3], path_pixels=count))

    output = args.output
    mod = output / NAME
    map_path = mod / "in_game/map_data/rivers.png"
    map_path.parent.mkdir(parents=True, exist_ok=True)
    result = Image.fromarray(rivers)
    result.putpalette(palette)
    result.save(map_path, optimize=False)
    check = Image.open(map_path)
    assert check.mode == "P" and check.getpalette() == palette
    assert np.array_equal(np.asarray(check), rivers)
    metadata = mod / ".metadata/metadata.json"
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(json.dumps(dict(name=NAME, id="ha1300_river_flow_showcase", version="1.0.0",
        supported_game_version="1.3.11", short_description="Five river levels along a single directed Seine test channel. Start a new game; inspect Langres, Troyes, Paris, Mantes and Rouen.",
        tags=["Utilities"], relationships=[], game_custom_data={}), indent=2)+"\n")
    path_frame.to_csv(output / "route.csv", index=False)
    report = dict(game_version="1.3.11", direction="Langres headwaters -> Troyes -> Paris -> Mantes -> Rouen -> Seine Bay / English Channel",
        source_xy=list(SOURCE_XY), mouth_xy=[int(mouth[1]+x0), int(mouth[0]+y0)],
        path_pixels=len(path), removed_branch_pixels=int(component.sum()-len(path)),
        inspection=inspection, checks="Single connected four-neighbour path; two endpoints; one source; sea-connected mouth; no junction markers; monotone levels; exact indexed palette; outside network unchanged; full-polygon predicted sample levels",
        verification="Static topology and previously engine-verified palette rules; this showcase has not been launched in EU5.",
        sha256={str(p):sha(p) for p in [args.map_dir / "rivers.png", args.map_dir / "locations.png", map_path]})
    (output / "manifest.json").write_text(json.dumps(report, indent=2)+"\n")
    guide = """# River Levels and Flow Showcase

Enable this mod by itself and start a NEW game (observer is fine).
Search for Paris, then inspect the river from inland Langres towards the Channel.
Use the native Rivers map mode and location river tooltip.

| Inspect location | Expected native river level |
| --- | ---: |
| Langres | 1 - Small |
| Troyes | 2 - Minor |
| Paris | 3 - River |
| Mantes | 4 - Major |
| Rouen | 5 - Great |

Flow: Langres headwaters -> Troyes -> Paris -> Mantes -> Rouen -> Seine Bay.
One green source marker defines the inland start; the other endpoint reaches
the original sea background. Width increases downstream. There are no red or
yellow connection markers to cause unwanted level-5 promotions.

This is an artificial diagnostic channel on the existing Seine-basin geometry,
not a historical or geographical correction. Tributaries in this connected
network were removed for the demonstration. All other river networks are intact.
Only rivers.png is overridden: no static bonuses, location assignments, or
transport defines are modified. Use without other map/river mods.

Static topology, palette and full-polygon expected levels were checked. Confirm
the rendered current direction in-game; it has not been separately exported.
"""
    (mod / "README.md").write_text(guide)
    (output / "README.md").write_text(guide)
    if args.deploy_dir:
        target = args.deploy_dir / NAME
        shutil.copytree(mod, target, dirs_exist_ok=True)
        for p in mod.rglob("*"):
            if p.is_file():
                assert sha(p) == sha(target / p.relative_to(mod))
        print(f"Deployed and verified: {target}")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
