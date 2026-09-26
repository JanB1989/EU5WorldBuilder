"""Gameplay snapshot of the exported river/navigation geography, and a diff between two snapshots.

A river redraw is "visual only" when every land location keeps its river level, its coastal/port status, its
water-tile shore states and crossings, and the navigable network connects the same land locations with the same
number of tile steps. This script records exactly those per-location facts from an exported geography
(`in_game/map_data`) plus the navigation tables, and compares two such records.

    uv run python scripts/river_gameplay_snapshot.py snapshot <map_data> <navigation_dir> <out.json>
    uv run python scripts/river_gameplay_snapshot.py diff <before.json> <after.json>
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
ROOT = Path(__file__).resolve().parents[1]
LEVELS = np.array([0, 5, 5, 1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5] + [0] * 240, np.uint8)


def land_inventory():
    inv = pd.read_csv(ROOT / "artifacts/river_network/location_levels.csv",
                      usecols=["location_tag", "map_color_rgb", "is_ownable"])
    inv = inv[inv.is_ownable]
    return {int(c, 16): t for c, t in zip(inv.map_color_rgb, inv.location_tag)}


def location_levels(map_data, colors):
    rgb = np.asarray(Image.open(map_data / "locations.png").convert("RGB"))
    river = np.asarray(Image.open(map_data / "rivers.png"))
    code = (rgb[..., 0].astype(np.uint32) << 16) | (rgb[..., 1].astype(np.uint32) << 8) | rgb[..., 2]
    ys, xs = np.nonzero(river < 16)
    per = pd.DataFrame({"c": code[ys, xs], "lvl": LEVELS[river[ys, xs]]}).groupby("c").lvl.max()
    area = pd.Series(code.ravel()).value_counts()
    levels = {t: int(per.get(c, 0)) for c, t in colors.items()}
    areas = {t: int(area.get(c, 0)) for c, t in colors.items()}
    return levels, areas


def snapshot(map_data: Path, nav: Path, out: Path):
    colors = land_inventory()
    levels, areas = location_levels(map_data, colors)
    ports = pd.read_csv(map_data / "ports.csv", sep=";", usecols=[0, 1])
    ports.columns = ["land", "sea"]
    adj = pd.read_csv(map_data / "adjacencies.csv", sep=";", encoding="utf-8-sig", usecols=[0, 1, 2, 3])
    adj.columns = ["a", "b", "type", "through"]
    tiles = pd.read_csv(nav / "tiles.csv")
    edges = pd.read_csv(nav / "edges.csv")
    shores = pd.read_csv(nav / "shores.csv")
    effects = pd.read_csv(nav / "river_effect_changes.csv")
    tile_ids = set(tiles.location)
    # water graph over navigation tiles; land locations attach through shore edges
    graph = defaultdict(set)
    for a, b in zip(edges["from"], edges["to"]):
        if a in tile_ids and b in tile_ids:
            graph[a].add(b); graph[b].add(a)
    shore_tiles = defaultdict(set)
    for land, water in zip(shores.location_tag, shores.water_location):
        shore_tiles[land].add(water)
    # component of each tile, named by the sorted land locations it reaches
    comp, n = {}, 0
    for t in sorted(tile_ids):
        if t in comp: continue
        n += 1; comp[t] = n; q = deque([t])
        while q:
            u = q.popleft()
            for v in graph[u]:
                if v not in comp: comp[v] = n; q.append(v)
    comp_lands = defaultdict(set)
    for land, ws in shore_tiles.items():
        for w in ws:
            if w in comp: comp_lands[comp[w]].add(land)
    # tile steps between shore land locations of one component (multi-source BFS per land location)
    steps = {}
    for land, ws in shore_tiles.items():
        ws = [w for w in ws if w in comp]
        if not ws: continue
        dist = {w: 0 for w in ws}; q = deque(ws)
        while q:
            u = q.popleft()
            for v in graph[u]:
                if v not in dist: dist[v] = dist[u] + 1; q.append(v)
        reachable = set().union(*(comp_lands[comp[w]] for w in ws))
        for other in reachable:
            if other <= land: continue
            d = min((dist[w] for w in shore_tiles[other] if w in dist), default=None)
            if d is not None: steps[f"{land}|{other}"] = d
    state_by_tile = dict(zip(tiles.location, tiles.state))
    shore_states = defaultdict(set)
    for land, water in zip(shores.location_tag, shores.water_location):
        shore_states[land].add(state_by_tile.get(water, "sea"))
    nav_ports = sorted(set(ports.land[ports.sea.isin(tile_ids)]))
    record = {
        "river_level": levels,
        "land_pixels": areas,
        "coastal": {r.location_tag: bool(r.new_coastal) for r in effects.itertuples()},
        "shore_states": {k: sorted(v) for k, v in shore_states.items()},
        "river_port_locations": nav_ports,
        "all_port_locations": sorted(set(ports.land)),
        "crossings": sorted(f"{min(a, b)}|{max(a, b)}|{t}" for a, b, t in zip(adj.a, adj.b, adj.type)),
        "network_groups": sorted("|".join(sorted(s)) for s in comp_lands.values()),
        "tile_steps": steps,
        "tiles": len(tile_ids),
    }
    out.write_text(json.dumps(record))
    print(f"snapshot: {len(levels)} land locations, {len(tile_ids)} tiles, {len(steps)} connected pairs -> {out}")


def diff(before: Path, after: Path):
    a, b = json.loads(before.read_text()), json.loads(after.read_text())
    ok = True
    def report(name, changed, sample):
        nonlocal ok
        ok &= not changed
        print(f"{'OK ' if not changed else 'DIFF'} {name}: {changed} changed" + (f"  e.g. {sample[:8]}" if changed else ""))
    for key in ["river_level", "coastal", "shore_states"]:
        keys = set(a[key]) | set(b[key])
        ch = sorted(k for k in keys if a[key].get(k) != b[key].get(k))
        report(key, len(ch), [(k, a[key].get(k), b[key].get(k)) for k in ch])
    for key in ["river_port_locations", "all_port_locations", "crossings", "network_groups"]:
        x, y = set(a[key]), set(b[key])
        report(key, len(x ^ y), sorted(x - y)[:4] + ["->"] + sorted(y - x)[:4])
    sa, sb = a["tile_steps"], b["tile_steps"]
    keys = set(sa) | set(sb)
    missing = [k for k in keys if k not in sa or k not in sb]
    delta = np.array([sb[k] - sa[k] for k in keys if k in sa and k in sb])
    report("connected land pairs", len(missing), missing)
    print(f"     tile steps between connected land pairs: {len(delta)} pairs, identical {int((delta == 0).sum())}, "
          f"shorter {int((delta < 0).sum())}, longer {int((delta > 0).sum())}, mean change {delta.mean() if len(delta) else 0:+.3f}")
    ar = np.array([b["land_pixels"][k] - a["land_pixels"][k] for k in a["land_pixels"] if k in b["land_pixels"]])
    print(f"     land pixels per location: changed {int((ar != 0).sum())}, median |change| of those "
          f"{float(np.median(np.abs(ar[ar != 0]))) if (ar != 0).any() else 0}, max |change| {int(np.abs(ar).max())}")
    print(f"     tiles: {a['tiles']} -> {b['tiles']}")
    return ok


if __name__ == "__main__":
    if sys.argv[1] == "snapshot":
        snapshot(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
    else:
        sys.exit(0 if diff(Path(sys.argv[2]), Path(sys.argv[3])) else 1)
