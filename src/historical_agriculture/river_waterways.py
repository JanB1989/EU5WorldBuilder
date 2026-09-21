"""Named waterways drawn into the routed river raster as their own trees.

Canals (the Grand Canal south of the Yangtze, the Zhedong canal) and small rivers the discharge cut drops are real
water the engine rule "highest river level within a location's boundaries" should see, but neither the RiverATLAS
tree nor vanilla's bitmap carries them. ``configs/rivers.json`` ``export.waterways`` lists them by name as an ordered
chain of location tags and a level. Each waterway is drawn as one simple 4-connected path with one green source at
its first pixel: it starts at the deepest interior pixel of the first location, passes through the deepest interior
pixel of every middle location and stops as soon as it is one pixel inside the last one. The path stays inside the
listed locations, never enters blocked (water, unownable) pixels and keeps 8-neighbour clearance from every other
river pixel, so the drawn forest and its one-source-per-tree property survive untouched. A location already carrying
a higher level keeps it.
"""
from __future__ import annotations

from collections import deque

import numpy as np
from scipy import ndimage

OFFSETS4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
CROSS = ndimage.generate_binary_structure(2, 1)
SQUARE = ndimage.generate_binary_structure(2, 2)


def interior_seed(inside: np.ndarray) -> tuple[int, int] | None:
    """The pixel of ``inside`` farthest (taxicab) from its outside; None when ``inside`` is empty."""
    if not inside.any():
        return None
    dist = ndimage.distance_transform_cdt(np.pad(inside, 1), metric="taxicab")[1:-1, 1:-1]
    y, x = np.unravel_index(int(np.argmax(dist)), dist.shape)
    return int(x), int(y)


def _bfs(start, goal, free, forbidden):
    h, w = free.shape
    queue = deque([start])
    parents = {start: None}
    while queue:
        px, py = queue.popleft()
        for ox, oy in OFFSETS4:
            n = (px + ox, py + oy)
            if not (0 <= n[0] < w and 0 <= n[1] < h) or n in parents or forbidden[n[1], n[0]] or not free[n[1], n[0]]:
                continue
            parents[n] = (px, py)
            if goal[n[1], n[0]]:
                path = []
                while n != start:
                    path.append(n)
                    n = parents[n]
                return path[::-1]
            queue.append(n)
    return None


def _visible(path, inside):
    """A tree cut short by a river is grown to at least three pixels inside its own location so the level counts."""
    if len(path) >= 3:
        return path
    x0, y0 = path[-1]
    yy, xx = np.indices(inside.shape)
    goal = inside & (np.abs(xx - x0) + np.abs(yy - y0) >= 3 - (len(path) - 1))
    forbidden = np.zeros(inside.shape, bool)
    for x, y in path:
        forbidden[y, x] = True
    segment = _bfs(path[-1], goal, inside, forbidden)
    return path + segment if segment else path


def _route(z, ids, chain, free):
    """Simple paths from the deepest free pixel of the first location through every later location (any free pixel at
    least one pixel inside it; two for the last), never touching themselves (8-neighbourhood). Where a river lies
    between two consecutive locations (no free corridor), the waterway continues on the far side as a new tree from
    that location's deepest free pixel; the river it crosses is water anyway. Returns (trees, gaps, status)."""
    seed = interior_seed(free & (z == ids[0]))
    if seed is None:
        return [], [], f"no_free_interior:{chain[0]}"
    trees, gaps, path = [], [], [seed]
    for k in range(1, len(ids)):
        depth = 2 if k == len(ids) - 1 else 1
        goal = ndimage.binary_erosion(z == ids[k], CROSS, iterations=depth, border_value=0) & free
        if not goal.any():
            return [], [], f"no_free_interior:{chain[k]}"
        prev = np.zeros(z.shape, bool)
        for x, y in path[:-1]:
            prev[y, x] = True
        forbidden = ndimage.binary_dilation(prev, SQUARE)
        forbidden[path[-1][1], path[-1][0]] = True
        segment = _bfs(path[-1], goal, free, forbidden)
        if segment is None:
            gaps.append(f"{chain[k - 1]}->{chain[k]}")
            trees.append(_visible(path, free & (z == ids[k - 1])))
            seed = interior_seed(free & (z == ids[k]))
            if seed is None:
                return [], [], f"no_free_interior:{chain[k]}"
            path = [seed]
            continue
        path.extend(segment)
    trees.append(_visible(path, free & (z == ids[-1])))
    trees = [p for p in trees if len(p) >= 3]     # a one- or two-pixel stub is no river
    if not trees:
        return [], gaps, "no_path:" + ";".join(gaps)
    return trees, gaps, "drawn"


def draw(sizes, owner, markers, zones, inv, blocked, waterways, *, require_all=True):
    """Draw every configured waterway in place; returns the audit for the export manifest."""
    tags = {str(t): i + 1 for i, t in enumerate(inv.location_tag)}
    boxes = ndimage.find_objects(zones.astype(np.int32), max_label=len(inv))
    basin = int(owner.max()) + 1
    report = []
    for spec in waterways:
        name, level, chain = str(spec["name"]), int(spec["level"]), [str(t) for t in spec["locations"]]
        entry = {"name": name, "level": level, "locations": chain}
        missing = [t for t in chain if t not in tags or boxes[tags[t] - 1] is None]
        if missing or len(chain) < 2 or not 1 <= level <= 5:
            entry.update(status="invalid", missing=missing)
            report.append(entry)
            continue
        ids = [tags[t] for t in chain]
        sl = [boxes[i - 1] for i in ids]
        y0, y1 = max(min(s[0].start for s in sl) - 2, 0), min(max(s[0].stop for s in sl) + 2, sizes.shape[0])
        x0, x1 = max(min(s[1].start for s in sl) - 2, 0), min(max(s[1].stop for s in sl) + 2, sizes.shape[1])
        z = zones[y0:y1, x0:x1]
        river = sizes[y0:y1, x0:x1] > 0
        before = {t: int(sizes[y0:y1, x0:x1][z == i].max(initial=0)) for t, i in zip(chain, ids)}
        trees, gaps, status, clearance = [], [], "no_path", 8
        # 8-neighbour clearance from other rivers first; where a river hugs a border, 4-neighbour clearance (diagonal
        # contact, still a separate 4-connected tree, as the vanilla fallback pieces) is the fallback
        for clearance, structure in ((8, SQUARE), (4, CROSS)):
            free = np.isin(z, ids) & ~blocked[y0:y1, x0:x1] & ~ndimage.binary_dilation(river, structure)
            trees, gaps, status = _route(z, ids, chain, free)
            if trees and not gaps:
                break
        if not trees:
            entry.update(status=status)
            report.append(entry)
            continue
        for path in trees:
            for x, y in path:
                sizes[y0 + y, x0 + x] = level
                owner[y0 + y, x0 + x] = basin
            markers[y0 + path[0][1], x0 + path[0][0]] = 0
            basin += 1
        after = {t: int(sizes[y0:y1, x0:x1][z == i].max(initial=0)) for t, i in zip(chain, ids)}
        entry.update(status="drawn", pixels=sum(len(p) for p in trees), trees=len(trees), river_crossings=gaps, clearance=clearance, levels_before=before, levels_after=after,
                     locations_raised=[t for t in chain if after[t] > before[t]])
        report.append(entry)
    failed = [e["name"] for e in report if e["status"] != "drawn"]
    if failed and require_all:
        raise ValueError("waterways not drawn: " + "; ".join(f"{e['name']} ({e['status']})" for e in report if e["status"] != "drawn"))
    return {"configured": len(waterways), "drawn": len(report) - len(failed), "failed": failed, "entries": report}
