"""Navigable river reaches from historical evidence (configs/navigation_reaches/*.json).

Every included river is traced along vanilla's river line from its head of navigation down to the open sea: the part
no farther from the sea (along the water) than the sea-going head is the sea reach, the rest the river reach. Branch
heads join the same way. Where vanilla has no river line, the drawn export river is followed and, if it stops short of
the coast, joined to it by a short straight line. Inland systems (sea_head null, "lower_end: <tag>" in period_note) join
their two ends; canals join their stops in a straight four-connected line.

Obstacle states: falls and cataracts are barriers (impassable tiles), every other obstacle (rapids, weirs, shoals,
gorges, silting) is improvable (passable at a cost, the site for lock works); everything else is navigable.
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from scipy import ndimage
from scipy.spatial import cKDTree

Image.MAX_IMAGE_PIXELS = None
STATES = {"navigable": 1, "improvable": 2, "barrier": 3}
STEPS = ((0, -1), (0, 1), (-1, 0), (1, 0), (-1, -1), (1, -1), (-1, 1), (1, 1))


def obstacle_state(kind):
    k = (kind or "").lower()
    return "barrier" if ("fall" in k or "cataract" in k) else "improvable"


def load_reaches(folder):
    rivers = []
    for f in sorted(Path(folder).glob("*.json")):
        for e in json.loads(f.read_text()):
            if e.get("include"):
                e = dict(e); e["region_file"] = f.stem
                rivers.append(e)
    return rivers


def _line(a, b):
    """Four-connected pixels from a to b inclusive (x first, then y, in unit steps along the longer axis)."""
    out = [a]; x, y = a
    n = max(abs(b[0] - a[0]), abs(b[1] - a[1]), 1)
    for t in range(1, n + 1):
        tx = round(a[0] + (b[0] - a[0]) * t / n); ty = round(a[1] + (b[1] - a[1]) * t / n)
        while (x, y) != (tx, ty):
            if x != tx: x += 1 if tx > x else -1
            else: y += 1 if ty > y else -1
            out.append((x, y))
    return out


class Tracer:
    def __init__(self, vanilla_rivers, drawn_rivers, zones, is_sea_zone, is_lake_zone, inventory, tag_ids):
        self.van = vanilla_rivers; self.zones = zones
        self.H, self.W = vanilla_rivers.shape
        self.sea = is_sea_zone[zones]; lake = is_lake_zone[zones]
        self.prefer = vanilla_rivers < 16
        self.river = self.prefer | (drawn_rivers < 16)
        self.passable = self.river | lake
        self.inv = inventory; self.tag_id = tag_ids
        # river-only distance first: a channel cannot be cut through a lake, so a route through a lagoon
        # (Vaccarès, Manzala) would end the channel at the lake; lakes only where no river reaches the sea
        river_only = self._distance(self.river)
        with_lakes = self._distance(self.passable)
        self.dist = np.where(river_only >= 0, river_only, with_lakes)
        self.walk = np.where(river_only >= 0, 1, 2).astype(np.int8)

    def _distance(self, passable):
        H, W = self.H, self.W
        seaside = ndimage.binary_dilation(self.sea, structure=np.ones((3, 3), bool), iterations=3) & passable
        dist = np.full(H * W, -1, np.int32); flat = passable.ravel()
        start = np.flatnonzero(seaside.ravel()); dist[start] = 0
        q = deque(start.tolist()); off = (-W, W, -1, 1, -W - 1, -W + 1, W - 1, W + 1)
        while q:
            p = q.popleft(); d = dist[p] + 1; x = p % W
            for o in off:
                n = p + o
                if 0 <= n < H * W and abs(n % W - x) <= 1 and flat[n] and dist[n] < 0:
                    dist[n] = d; q.append(n)
        return dist.reshape(H, W)

    def centroid(self, tag):
        r = self.inv.loc[tag]
        return int(r.centroid_x), int(r.centroid_y)

    def start_pixel(self, tag, need_dist=True):
        r = self.inv.loc[tag]; z = self.tag_id[tag]
        for pad in (0, 10, 25, 50):
            y0, y1 = max(int(r.bbox_min_y) - pad, 0), min(int(r.bbox_max_y) + pad + 1, self.H)
            x0, x1 = max(int(r.bbox_min_x) - pad, 0), min(int(r.bbox_max_x) + pad + 1, self.W)
            win = self.river[y0:y1, x0:x1].copy()
            if pad == 0: win &= self.zones[y0:y1, x0:x1] == z
            if need_dist: win &= self.dist[y0:y1, x0:x1] >= 0
            ys, xs = np.nonzero(win)
            if len(ys):
                w = np.where(self.prefer[y0:y1, x0:x1][ys, xs], self.van[y0:y1, x0:x1][ys, xs].astype(float) + 100, 0.0)
                dd = (xs + x0 - r.centroid_x) ** 2 + (ys + y0 - r.centroid_y) ** 2
                k = int(np.lexsort((dd, -w))[0])
                return (int(xs[k] + x0), int(ys[k] + y0)), pad
        return None, None

    def to_sea(self, p):
        x, y = p; path = [(x, y)]
        while self.dist[y, x] > 0:
            steps = [(x + dx, y + dy) for dx, dy in STEPS if 0 <= x + dx < self.W and 0 <= y + dy < self.H
                     and self.dist[y + dy, x + dx] == self.dist[y, x] - 1 and self.walk[y + dy, x + dx] == self.walk[y, x]]
            if not steps:
                steps = [(x + dx, y + dy) for dx, dy in STEPS if 0 <= x + dx < self.W and 0 <= y + dy < self.H
                         and 0 <= self.dist[y + dy, x + dx] < self.dist[y, x]]
            x, y = next((q for q in steps if self.prefer[q[1], q[0]]), steps[0]); path.append((x, y))
        return path

    def to_coast(self, start, reach=25, box=400):
        x0, y0 = max(start[0] - box, 0), max(start[1] - box, 0)
        x1, y1 = min(start[0] + box, self.W), min(start[1] + box, self.H)
        sy, sx = np.nonzero(self.sea[y0:y1, x0:x1])
        if not len(sy): return None, None
        tree = cKDTree(np.column_stack((sx + x0, sy + y0)))
        par = {start: None}; dq = deque([start]); best, best_d = start, float("inf")
        while dq:
            p = dq.popleft(); d, _ = tree.query(p)
            if d < best_d: best, best_d = p, d
            for dx, dy in STEPS:
                n = (p[0] + dx, p[1] + dy)
                if n not in par and x0 <= n[0] < x1 and y0 <= n[1] < y1 and self.river[n[1], n[0]]:
                    par[n] = p; dq.append(n)
        if best_d > reach: return None, None
        path = []; q = best
        while q: path.append(q); q = par[q]
        _, i = tree.query(best)
        return path[::-1] + _line(best, (int(sx[i] + x0), int(sy[i] + y0)))[1:], int(round(best_d))

    def between(self, a, b):
        par = {a: None}; dq = deque([a])
        while dq:
            p = dq.popleft()
            if p == b:
                out = []
                while p: out.append(p); p = par[p]
                return out[::-1]
            for dx, dy in STEPS:
                n = (p[0] + dx, p[1] + dy)
                if n not in par and 0 <= n[0] < self.W and 0 <= n[1] < self.H and self.passable[n[1], n[0]]:
                    par[n] = p; dq.append(n)
        return None


def four_connected(path, passable):
    """Insert a corner pixel into every diagonal step (the one on water or river if possible): the game joins
    locations four-connected, and a diagonal-only line falls apart into single-pixel pieces."""
    out = [path[0]]
    for (x, y) in path[1:]:
        px, py = out[-1]
        if abs(x - px) == 1 and abs(y - py) == 1:
            a, b = (x, py), (px, y)
            out.append(a if passable[a[1], a[0]] or not passable[b[1], b[0]] else b)
        out.append((x, y))
    return out


def reach_sea(path, tracer):
    """Extend a path from its last pixel to the nearest sea pixel, so the channel touches the sea."""
    x, y = path[-1]; t = tracer
    for r in range(0, 8):
        y0, y1, x0, x1 = max(y - r, 0), min(y + r + 1, t.H), max(x - r, 0), min(x + r + 1, t.W)
        ys, xs = np.nonzero(t.sea[y0:y1, x0:x1])
        if len(ys):
            k = int(np.argmin((xs + x0 - x) ** 2 + (ys + y0 - y) ** 2))
            tail = _line((x, y), (int(xs[k] + x0), int(ys[k] + y0)))
            return path + [q for q in tail[1:] if not t.sea[q[1], q[0]]]
    return path


def trace(rivers, tracer, obstacle_radius=15):
    """Pixel table (x, y, river, reach, state) and a per-river report."""
    t = tracer; rows = {}; report = []

    def put(x, y, river, reach, state):
        k = (x, y); old = rows.get(k)
        rank = {"sea": 2, "canal": 1, "river": 0}
        if old is None or STATES[state] > STATES[old[2]] or (state == old[2] and rank[reach] > rank[old[1]]):
            rows[k] = (river, reach, state)

    for e in rivers:
        name = e["river"]; problems = []; traced = []
        if e.get("kind") in ("canal", "unmapped_river"):
            # canals, and rivers neither map draws (the IJssel, a Rhine distributary): straight between the stops
            stops = [s for s in (e.get("stops") or []) if s in t.tag_id]
            pts = [t.centroid(s) for s in stops]
            if e.get("kind") == "canal":
                for a, b in zip(pts, pts[1:]):
                    traced.append(("canal", _line(a, b)))
            else:
                line = [q for a, b in zip(pts, pts[1:]) for q in _line(a, b)]
                line = reach_sea(list(dict.fromkeys(line)), t)
                sh = (e.get("sea_head") or {}).get("tag")
                for x, y in line:
                    put(x, y, name, "sea" if sh in t.tag_id and t.zones[y, x] == t.tag_id[sh] else "river", "navigable")
                traced.append(("unmapped", line))
        else:
            heads = [h["tag"] for h in [e.get("river_head") or e.get("sea_head")] if h]
            heads += [b["head"]["tag"] for b in e.get("branches") or [] if (b.get("head") or {}).get("tag")]
            inland = e.get("sea_head") is None
            lower = None
            if inland and "lower_end:" in (e.get("period_note") or ""):
                lower = e["period_note"].split("lower_end:")[1].strip().split()[0].strip(".,;)")
            sh = (e.get("sea_head") or {}).get("tag"); d_sh = None
            if not inland and sh in t.tag_id:
                s_px, _ = t.start_pixel(sh)
                if s_px is None: problems.append(f"sea head {sh}: no river reaching the sea")
                else:
                    d_sh = int(t.dist[s_px[1], s_px[0]]); traced.append(("sea_head", t.to_sea(s_px)))
            for tag in heads:
                if tag not in t.tag_id:
                    problems.append(f"unknown tag {tag}"); continue
                if inland:
                    a, _ = t.start_pixel(tag, need_dist=False); b, _ = t.start_pixel(lower, need_dist=False) if lower in t.tag_id else (None, None)
                    p = t.between(a, b) if a and b else None
                    if p is None: problems.append(f"{tag}: inland system not joined to {lower}"); continue
                else:
                    s0, pad0 = t.start_pixel(tag, need_dist=False)
                    if s0 is not None and pad0 == 0 and t.dist[s0[1], s0[0]] < 0:
                        p, join = t.to_coast(s0)
                        if p is None: problems.append(f"{tag}: river does not reach the sea"); continue
                        problems.append(f"{tag}: joined to the coast by a {join} px straight line")
                    else:
                        s, pad = t.start_pixel(tag)
                        if s is None: problems.append(f"{tag}: no river reaching the sea nearby"); continue
                        if pad: problems.append(f"{tag}: started {pad} px outside its location")
                        p = t.to_sea(s)
                        # the river must pass its sea-going head (IJssel via Kampen, not the Rhine): if the shortest
                        # way to the sea misses it, go head -> sea head along the water, then on to the sea
                        s_sh = t.start_pixel(sh)[0] if sh in t.tag_id else None
                        if s_sh and min((q[0]-s_sh[0])**2 + (q[1]-s_sh[1])**2 for q in p) > 25**2:
                            via = t.between(s, s_sh)
                            if via: p = via + t.to_sea(s_sh)[1:]
                traced.append((tag, p))
            traced = [(w, four_connected(reach_sea(p, t) if not inland else p, t.passable)) for w, p in traced]
            for which, p in traced:
                arr = np.asarray(p)
                d = t.dist[arr[:, 1], arr[:, 0]]
                sea = (d <= d_sh) & (d >= 0) if d_sh is not None else np.zeros(len(p), bool)
                for (x, y), s in zip(p, sea):
                    put(x, y, name, "sea" if s else "river", "navigable")
        for which, p in traced:
            if which == "canal":
                for x, y in p: put(x, y, name, "canal", "navigable")
        # obstacles: reach pixels inside the obstacle's location, else within a radius of its centre
        pts = {q for _, p in traced for q in p}
        for o in e.get("obstacles") or []:
            tag = o.get("tag")
            if tag not in t.tag_id: continue
            state = o.get("state") or obstacle_state(o.get("kind"))
            hit = [q for q in pts if t.zones[q[1], q[0]] == t.tag_id[tag]]
            if not hit:
                c = np.asarray(t.centroid(tag))
                hit = [q for q in pts if (q[0] - c[0]) ** 2 + (q[1] - c[1]) ** 2 <= obstacle_radius ** 2]
            if not hit: problems.append(f"obstacle {o.get('name')} ({tag}) is not on the traced reach")
            for x, y in hit: put(x, y, name, rows[(x, y)][1], state)
        report.append({"river": name, "region_file": e["region_file"], "paths": len(traced),
                       "pixels": len(pts), "problems": problems})
    table = pd.DataFrame([(x, y, r, reach, s) for (x, y), (r, reach, s) in rows.items()],
                         columns=["x", "y", "river", "reach", "state"])
    return table.sort_values(["y", "x"]).reset_index(drop=True), report
