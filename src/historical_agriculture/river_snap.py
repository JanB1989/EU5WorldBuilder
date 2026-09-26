"""Snap routed river stretches onto vanilla's own river pixels. Visual only.

The exporter traces rivers from the geographic network, so a river vanilla also draws usually runs one to five
pixels beside vanilla's line. Where a routed branch follows a vanilla river within ``max_distance_pixels`` for at
least ``minimum_stretch_pixels``, the stretch is redrawn on vanilla's pixels (a shortest path along vanilla's line
between the pixels nearest to the stretch ends), joined to the rest of the branch by at most a pixel or two.

The drawing is gameplay: a location's river level is the widest river pixel inside it, and a junction marker makes
it level 5. A stretch is therefore accepted only when

* every new pixel stays inside a location whose routed level (the same export without snapping) is at least the
  pixel's level, so no location gains a river or a level,
* every location whose routed level the old stretch provided still gets that level from the new pixels,
* it keeps clear of all drawn rivers (no pixel on or beside another river) and of every reference junction, so
  tributaries attach exactly where they did.

``river_map.export`` re-runs the export with snapping and compares every location's marker-aware level with the
unsnapped export; stretches touching a location that still differs (through the completion rules, which react to
the new drawing) are denied and the export repeats until nothing differs.
"""
from __future__ import annotations

from collections import Counter, deque

import numpy as np
from scipy.spatial import cKDTree

OFFSETS = ((-1, 0), (1, 0), (0, -1), (0, 1))
WIDTH_LEVEL = np.zeros(256, np.uint8)
for _index, _level in {3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 2, 9: 3, 10: 3, 11: 3, 12: 4, 13: 4, 14: 4, 15: 5}.items():
    WIDTH_LEVEL[_index] = _level
# vanilla's width for every level it draws (4, 11, 15); levels 2 and 4, which vanilla never draws, take the width
# closest to vanilla's look (6, 12). Used where no vanilla width of the same level lies nearby.
DEFAULT_WIDTH = np.array([0, 4, 6, 11, 12, 15], np.uint8)


def lattice_steps(a, b):
    """Four-connected pixels strictly between a and b (x first, then y)."""
    (x, y), (tx, ty) = a, b
    out = []
    while x != tx:
        x += 1 if tx > x else -1
        out.append((x, y))
    while y != ty:
        y += 1 if ty > y else -1
        out.append((x, y))
    return out[:-1] if out and out[-1] == (tx, ty) else out


class VanillaSnap:
    def __init__(self, native, blocked, zones, routed_ref, junctions, cfg, deny=(), protected=None):
        self.R = int(cfg.get("max_distance_pixels", 5))
        self.L = int(cfg.get("minimum_stretch_pixels", 12))
        self.end = int(cfg.get("end_distance_pixels", 1))
        self.clearance = int(cfg.get("junction_clearance_pixels", 2))
        self.vanilla = (native <= 15) & ~blocked
        ys, xs = np.nonzero(self.vanilla)
        self.vxy = np.column_stack((xs, ys))
        self.tree = cKDTree(self.vxy)
        self.blocked, self.zones, self.ref = blocked, zones, routed_ref
        jy, jx = np.nonzero(junctions)
        self.jtree = cKDTree(np.column_stack((jx, jy))) if len(jx) else None
        self.deny = set(deny)
        self.protected = protected if protected is not None else np.zeros(blocked.shape, bool)
        self.log = []
        self.counters = Counter()

    def _free(self, p, sizes):
        x, y = p
        h, w = sizes.shape
        if not (0 <= x < w and 0 <= y < h) or sizes[y, x] or self.blocked[y, x] or self.protected[y, x]:
            return False
        return not any(0 <= x + dx < w and 0 <= y + dy < h and sizes[y + dy, x + dx] for dx, dy in OFFSETS)

    def _vanilla_route(self, start, goal, stretch, sizes):
        """Shortest four-connected path along vanilla's pixels from start to goal, near the stretch, all free."""
        xs = [p[0] for p in stretch]; ys = [p[1] for p in stretch]
        pad = self.R + 2
        x0, x1, y0, y1 = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
        limit = int(1.6 * len(stretch)) + 10
        if not (self._free(start, sizes) and self._free(goal, sizes)):
            return None
        parents = {start: None}; depth = {start: 0}
        queue = deque([start])
        while queue:
            p = queue.popleft()
            if p == goal:
                path = []
                while p is not None:
                    path.append(p); p = parents[p]
                return path[::-1]
            if depth[p] >= limit:
                continue
            for dx, dy in OFFSETS:
                n = (p[0] + dx, p[1] + dy)
                if n in parents or not (x0 <= n[0] <= x1 and y0 <= n[1] <= y1):
                    continue
                if not self.vanilla[n[1], n[0]] or not self._free(n, sizes):
                    continue
                parents[n] = p; depth[n] = depth[p] + 1
                queue.append(n)
        return None

    def _guard(self, removed, added, level_of):
        if not added:
            return False
        ax = np.asarray(added)
        za = self.zones[ax[:, 1], ax[:, 0]]
        la = level_of(added)
        if np.any(la > self.ref[za]):
            return False
        if removed:
            rx = np.asarray(removed)
            zr = self.zones[rx[:, 1], rx[:, 0]]
            lr = level_of(removed)
            for z in np.unique(zr):
                top = lr[zr == z].max()
                if top == self.ref[z] and not np.any((za == z) & (la == top)):
                    return False
        return True

    def snap(self, path, key, level_of, sizes):
        """Return ``path`` with every acceptable stretch redrawn on vanilla's pixels."""
        from .river_map import erase_raster_loops
        n = len(path)
        if n < self.L:
            return path
        xy = np.asarray(path)
        d, idx = self.tree.query(xy, p=np.inf, distance_upper_bound=self.R + 0.5)
        ok = np.isfinite(d) & (sizes[xy[:, 1], xy[:, 0]] == 0) & ~self.protected[xy[:, 1], xy[:, 0]]
        if self.jtree is not None:
            jd, _ = self.jtree.query(xy, p=np.inf, distance_upper_bound=self.clearance + 0.5)
            ok &= ~np.isfinite(jd)
        stretches, k = [], 0
        while k < n:
            if not ok[k]:
                k += 1; continue
            s = k
            while k < n and ok[k]:
                k += 1
            a, b = s, k - 1
            while a <= b and d[a] > self.end:
                a += 1
            while b >= a and d[b] > self.end:
                b -= 1
            if b - a + 1 >= self.L:
                stretches.append((a, b))
        if not stretches:
            return path
        self.counters["candidate_stretches"] += len(stretches)
        out, last = [], 0
        for a, b in stretches:
            if (key, a) in self.deny:
                self.counters["denied"] += 1; continue
            va, vb = tuple(int(v) for v in self.vxy[idx[a]]), tuple(int(v) for v in self.vxy[idx[b]])
            route = self._vanilla_route(va, vb, path[a:b + 1], sizes)
            if route is None:
                self.counters["no_free_vanilla_route"] += 1; continue
            join_in = lattice_steps(path[a - 1], va) if a > 0 else []
            join_out = lattice_steps(vb, path[b + 1]) if b < n - 1 else []
            replacement = join_in + route + join_out
            if any(not self._free(p, sizes) for p in join_in + join_out):
                self.counters["blocked_join"] += 1; continue
            old = set(path[a:b + 1]); new = set(replacement)
            removed = sorted(old - new); added = sorted(new - old)
            if not added:
                continue
            if not self._guard(removed, added, level_of):
                self.counters["level_guard"] += 1; continue
            out.extend(path[last:a]); out.extend(replacement); last = b + 1
            pts = np.asarray(replacement + list(path[a:b + 1]))
            zs = set(np.unique(self.zones[pts[:, 1], pts[:, 0]]).tolist())
            self.log.append({"key": (key, a), "zones": zs, "bbox": (int(pts[:, 0].min()), int(pts[:, 1].min()),
                             int(pts[:, 0].max()), int(pts[:, 1].max())), "pixels": len(replacement)})
            self.counters["snapped_stretches"] += 1
            self.counters["snapped_pixels"] += len(route)
        if not last:
            return path
        out.extend(path[last:])
        return erase_raster_loops(out)


def encode_widths(sizes, native, radius):
    """Palette index per river pixel: vanilla's own width where vanilla draws the same level at the pixel or within
    ``radius``; otherwise the usual vanilla width of the level. The level (the gameplay) is never changed."""
    out = np.zeros(sizes.shape, np.uint8)
    ys, xs = np.nonzero(sizes)
    level = sizes[ys, xs]
    index = DEFAULT_WIDTH[level].copy()
    same_here = WIDTH_LEVEL[native[ys, xs]] == level
    index[same_here] = native[ys, xs][same_here]
    near_same = np.zeros(len(xs), bool)
    vanilla_level = WIDTH_LEVEL[native]
    for lvl in range(1, 6):
        vy, vx = np.nonzero(vanilla_level == lvl)
        todo = np.flatnonzero(~same_here & (level == lvl))
        if not len(vy) or not len(todo):
            continue
        dist, nearest = cKDTree(np.column_stack((vx, vy))).query(
            np.column_stack((xs[todo], ys[todo])), p=np.inf, distance_upper_bound=radius + 0.5)
        found = np.isfinite(dist)
        index[todo[found]] = native[vy[nearest[found]], vx[nearest[found]]]
        near_same[todo[found]] = True
    out[ys, xs] = index
    return out, {"vanilla_width_at_pixel": int(same_here.sum()), "vanilla_width_nearby": int(near_same.sum()),
                 "default_width_of_level": int((~same_here & ~near_same).sum())}
