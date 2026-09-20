"""Complete the drawn river network where vanilla gives a location a river and the network drawing does not.

Two global rules, applied to the routed raster before the marker and topology gates of ``river_map.export``:

1. Bank detours. A mainstem often runs exactly along the border between two locations and is rasterised on one
   side only, so the other bank gets no river although the engine's rule ("highest level within the boundaries")
   and vanilla both give it one (Cairo on the Nile). Where a straight three-pixel run of a river borders such a
   location, the middle pixel is replaced by a one-pixel-deep wiggle into that location. The river stays one simple
   path (no junction, no marker), the location gets the mainstem's level.

2. Vanilla fallback pieces. Where vanilla draws a river the network does not carry at all (small rivers below the
   discharge cut, delta distributaries the downstream tree cannot represent), vanilla's own pixels are copied as
   separate trees: the parts of vanilla's rivers that keep one pixel of clearance from the drawn network, reduced to
   a simple path with one source when vanilla's markers no longer form a valid tree. Only pieces that give at
   least one still-uncovered vanilla-river location its river are kept; widths are vanilla's.

The engine rule "highest recognised level within a location's boundaries wins" is what both rules serve.
"""
from __future__ import annotations

from collections import deque

import numpy as np
from scipy import ndimage

OFFSETS = ((1, 0), (-1, 0), (0, 1), (0, -1))
WIDTH_LEVEL = {3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 2, 9: 3, 10: 3, 11: 3, 12: 4, 13: 4, 14: 4, 15: 5}


def location_presence(zones, mask, count):
    present = np.zeros(count, bool)
    present[np.unique(zones[mask])] = True
    return present


def _degrees(mask):
    d = np.zeros(mask.shape, np.uint8)
    d[1:] += mask[:-1]; d[:-1] += mask[1:]
    d[:, 1:] += mask[:, :-1]; d[:, :-1] += mask[:, 1:]
    return d


def bank_detours(sizes, owner, markers, zones, targets, blocked):
    """Rule 1. ``targets`` is a boolean array over zone ids (index 0 unused). Returns the zone ids served."""
    h, w = sizes.shape
    river = sizes > 0
    served = []
    for zone in np.flatnonzero(targets):
        inside = zones == zone
        if not inside.any():
            continue
        ys, xs = np.where(inside)
        y0, y1, x0, x1 = max(ys.min() - 2, 0), min(ys.max() + 3, h), max(xs.min() - 2, 0), min(xs.max() + 3, w)
        done = False
        # river pixels touching the location
        for y in range(y0, y1):
            if done:
                break
            for x in range(x0, x1):
                if not river[y, x] or markers[y, x] != 255:
                    continue
                for dx, dy in OFFSETS:
                    qx, qy = x + dx, y + dy
                    if not (0 <= qx < w and 0 <= qy < h) or zones[qy, qx] != zone:
                        continue
                    # straight run a-p-b perpendicular to the offset into the location
                    ax, ay, bx, by = (x - dy, y - dx, x + dy, y + dx) if True else None
                    if not (0 <= ax < w and 0 <= ay < h and 0 <= bx < w and 0 <= by < h):
                        continue
                    if not (river[ay, ax] and river[by, bx]):
                        continue
                    if markers[ay, ax] != 255 or markers[by, bx] != 255:
                        continue
                    # p must be an interior pixel with exactly these two river neighbours
                    ns = [(x + ox, y + oy) for ox, oy in OFFSETS if 0 <= x + ox < w and 0 <= y + oy < h and river[y + oy, x + ox]]
                    if sorted(ns) != sorted([(ax, ay), (bx, by)]):
                        continue
                    trio = [(ax + dx, ay + dy), (qx, qy), (bx + dx, by + dy)]
                    if any(not (0 <= tx < w and 0 <= ty < h) or river[ty, tx] or blocked[ty, tx] for tx, ty in trio):
                        continue
                    # the wiggle must touch no river pixel other than a, b (and itself)
                    allowed = {(ax, ay), (bx, by), *trio}
                    clash = False
                    for tx, ty in trio:
                        for ox, oy in OFFSETS:
                            nx, ny = tx + ox, ty + oy
                            if 0 <= nx < w and 0 <= ny < h and river[ny, nx] and (nx, ny) not in allowed and (nx, ny) != (x, y):
                                clash = True
                        if any(markers[ty + oy, tx + ox] != 255 for ox, oy in OFFSETS if 0 <= tx + ox < w and 0 <= ty + oy < h):
                            clash = True
                    if clash:
                        continue
                    level, basin = int(sizes[y, x]), int(owner[y, x])
                    sizes[y, x] = 0; owner[y, x] = 0; river[y, x] = False
                    for tx, ty in trio:
                        sizes[ty, tx] = level; owner[ty, tx] = basin; river[ty, tx] = True
                    served.append(int(zone)); done = True
                    break
                if done:
                    break
    return served


def _bfs(start, goal, free, forbidden, x0, y0, x1, y1):
    """Shortest 4-path from ``start`` to any pixel with goal(pixel) True over free(pixel) pixels, never entering
    ``forbidden``; returns the path excluding ``start`` (last element satisfies goal) or None."""
    queue = deque([start]); parents = {start: None}
    while queue:
        px, py = queue.popleft()
        for ox, oy in OFFSETS:
            n = (px + ox, py + oy)
            if not (x0 <= n[0] < x1 and y0 <= n[1] < y1) or n in parents or n in forbidden or not free(n):
                continue
            parents[n] = (px, py)
            if goal(n):
                path = []
                while n != start:
                    path.append(n); n = parents[n]
                return path[::-1]
            queue.append(n)
    return None


def _neighbourhood(pixels):
    out = set()
    for x, y in pixels:
        out.add((x, y))
        for ox, oy in OFFSETS:
            out.add((x + ox, y + oy))
    return out


def bfs_detours(sizes, owner, markers, zones, targets, blocked, max_length=12, reach=4):
    """Rule 3. For a target location near a river (within ``reach`` px), replace one interior river pixel p (neighbours
    a, b) by a simple free 4-path from a to b that passes through the location and touches no other river pixel:
    a leg from a into the location, a leg from b into the location, joined inside. Generalises the straight-run
    detour to bends and to rivers a few pixels away from the border."""
    h, w = sizes.shape
    river = sizes > 0
    served = []
    for zone in np.flatnonzero(targets):
        inside = zones == zone
        if not inside.any():
            continue
        ys, xs = np.where(inside)
        y0, y1, x0, x1 = max(ys.min() - reach - 2, 0), min(ys.max() + reach + 3, h), max(xs.min() - reach - 2, 0), min(xs.max() + reach + 3, w)
        win = np.zeros((y1 - y0, x1 - x0), bool); win[ys - y0, xs - x0] = True
        near = ndimage.binary_dilation(win, iterations=reach)
        candidates = np.argwhere(near & river[y0:y1, x0:x1])
        done = False
        for cy, cx in candidates:
            if done:
                break
            x, y = int(cx + x0), int(cy + y0)
            if markers[y, x] != 255:
                continue
            ns = [(x + ox, y + oy) for ox, oy in OFFSETS if 0 <= x + ox < w and 0 <= y + oy < h and river[y + oy, x + ox]]
            if len(ns) != 2:
                continue
            a, b = ns
            if markers[a[1], a[0]] != 255 or markers[b[1], b[0]] != 255:
                continue
            allowed_contacts = {a, b, (x, y)}

            def free(n, allowed=allowed_contacts):
                nx, ny = n
                if river[ny, nx] or blocked[ny, nx]:
                    return False
                for qx, qy in OFFSETS:
                    cx2, cy2 = nx + qx, ny + qy
                    if 0 <= cx2 < w and 0 <= cy2 < h:
                        if river[cy2, cx2] and (cx2, cy2) not in allowed:
                            return False
                        if markers[cy2, cx2] != 255:
                            return False
                return True

            goal = lambda n: bool(inside[n[1], n[0]])
            # each leg keeps clear of the other end's neighbourhood, so a and b keep degree two after the swap
            leg_a = _bfs(a, goal, free, (_neighbourhood([b]) | {(x, y)}) - {a}, x0, y0, x1, y1)
            if leg_a is None:
                continue
            forbidden_b = (_neighbourhood(leg_a[:-1]) | _neighbourhood([a]) | {(x, y)}) - {leg_a[-1], b}
            leg_b = _bfs(b, goal, free, forbidden_b, x0, y0, x1, y1)
            if leg_b is None:
                continue
            e, f = leg_a[-1], leg_b[-1]
            if e == f:
                path = leg_a + leg_b[-2::-1]
            elif abs(e[0] - f[0]) + abs(e[1] - f[1]) == 1:
                path = leg_a + leg_b[::-1]
            else:
                forbidden_c = (_neighbourhood(leg_a[:-1]) | _neighbourhood(leg_b[:-1]) | _neighbourhood([a, b]) | {(x, y)}) - {e, f}
                join = _bfs(e, lambda n: n == f, free, forbidden_c, x0, y0, x1, y1)
                if join is None:
                    continue
                path = leg_a + join[:-1] + leg_b[::-1]
            if len(path) > max_length:
                continue
            # a simple path: each pixel touches only its path neighbours (and a / b at the ends)
            pset = set(path)
            ok = len(pset) == len(path)
            for i, (qx, qy) in enumerate(path):
                if not ok:
                    break
                adj = {(qx + ox, qy + oy) for ox, oy in OFFSETS} & pset
                expected = {path[j] for j in (i - 1, i + 1) if 0 <= j < len(path)}
                if adj != expected:
                    ok = False
                touches = {(qx + ox, qy + oy) for ox, oy in OFFSETS} & {a, b}
                if (i == 0 and touches != {a}) or (i == len(path) - 1 and touches != {b}) or (0 < i < len(path) - 1 and touches):
                    ok = False
            if not ok:
                continue
            level, basin = int(sizes[y, x]), int(owner[y, x])
            sizes[y, x] = 0; owner[y, x] = 0; river[y, x] = False
            for qx, qy in path:
                sizes[qy, qx] = level; owner[qy, qx] = basin; river[qy, qx] = True
            served.append(int(zone)); done = True
    return served


def _simple_path(mask):
    """Longest-ish simple 4-path of a connected mask: BFS from an endpoint, then from the farthest pixel."""
    ys, xs = np.where(mask)
    if not len(ys):
        return []
    pts = set(zip(xs.tolist(), ys.tolist()))

    def bfs(start):
        parents = {start: None}
        queue = deque([start]); last = start
        while queue:
            x, y = p = queue.popleft(); last = p
            for dx, dy in OFFSETS:
                n = (x + dx, y + dy)
                if n in pts and n not in parents:
                    parents[n] = p; queue.append(n)
        return last, parents

    far, _ = bfs(next(iter(pts)))
    end, parents = bfs(far)
    path = []
    p = end
    while p is not None:
        path.append(p); p = parents[p]
    return path


def vanilla_pieces(native, sizes, owner, markers, zones, targets, blocked, min_pixels=4):
    """Rule 2. Copies vanilla river pieces (with clearance from the drawn network) that serve a target location."""
    h, w = sizes.shape
    river = sizes > 0
    clearance = ndimage.binary_dilation(river, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool))
    vanilla = (native <= 15) & ~clearance & ~blocked
    labels, count = ndimage.label(vanilla, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool))
    served, pieces, simplified, skipped = [], 0, 0, 0
    width_level = np.zeros(256, np.uint8)
    for k, v in WIDTH_LEVEL.items():
        width_level[k] = v
    objects = ndimage.find_objects(labels)
    for index, sl in enumerate(objects, 1):
        if sl is None:
            continue
        window = labels[sl] == index
        if window.sum() < min_pixels:
            continue
        zone_window = zones[sl]
        hit = np.unique(zone_window[window])
        hit = hit[targets[hit]]
        if not len(hit):
            continue
        native_window = native[sl]
        piece_sizes = np.where(window, width_level[native_window], 0).astype(np.uint8)
        # vanilla pixels with a marker but no width: give them the level of a neighbour
        nowidth = window & (piece_sizes == 0)
        if nowidth.any():
            dil = ndimage.grey_dilation(piece_sizes, size=(3, 3))
            piece_sizes[nowidth] = np.maximum(dil[nowidth], 1)
        piece_markers = np.full(window.shape, 255, np.uint8)
        green = window & (native_window == 0)
        trib = window & ((native_window == 1) | (native_window == 2))
        ok = _valid_tree(window, green, trib)
        if not ok:
            path = _simple_path(window)
            if len(path) < min_pixels:
                skipped += 1
                continue
            keep = np.zeros(window.shape, bool)
            for x, y in path:
                keep[y, x] = True
            window = keep; green = np.zeros_like(keep); trib = np.zeros_like(keep)
            gx, gy = path[-1]
            green[gy, gx] = True
            simplified += 1
            zone_hit = zone_window[window]
            hit = np.unique(zone_hit); hit = hit[targets[hit]]
            if not len(hit):
                skipped += 1
                continue
        piece_markers[green] = 0
        piece_markers[trib] = 1
        # write back
        ys, xs = np.where(window)
        oy, ox = sl[0].start, sl[1].start
        sizes[ys + oy, xs + ox] = piece_sizes[ys, xs]
        owner[ys + oy, xs + ox] = 0
        markers[ys + oy, xs + ox] = piece_markers[ys, xs]
        river[ys + oy, xs + ox] = True
        pieces += 1
        served.extend(int(z) for z in hit)
        targets[hit] = False
    return {"pieces": pieces, "simplified_to_path": simplified, "skipped": skipped, "served": sorted(set(served))}


def _valid_tree(mask, green, trib):
    """Vanilla piece keeps its markers only if they still form the exporter's tree encoding."""
    if green.sum() != 1:
        return False
    d = _degrees(mask)
    if d[green][0] != 1:
        return False
    if np.any(d[trib] != 2):
        return False
    segments = mask & ~trib
    sd = _degrees(segments)
    if np.any(sd[segments] > 2):
        return False
    labels, count = ndimage.label(mask, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool))
    if count != 1:
        return False
    vertices = int(mask.sum())
    if int(d[mask].astype(np.int64).sum()) // 2 != vertices - 1:
        return False
    for y, x in np.argwhere(trib):
        ns = [(x + dx, y + dy) for dx, dy in OFFSETS if 0 <= x + dx < mask.shape[1] and 0 <= y + dy < mask.shape[0] and mask[y + dy, x + dx]]
        if any(trib[ny, nx] for nx, ny in ns):
            return False
        if sorted(int(sd[ny, nx]) for nx, ny in ns) != [1, 2]:
            return False
    return True


def complete(native, sizes, owner, markers, zones, inv, blocked, cfg):
    """Apply both rules in place; returns the audit for the export manifest."""
    count = len(inv) + 1
    ownable = np.r_[False, inv.is_ownable.to_numpy(bool)]
    vanilla_present = location_presence(zones, native <= 15, count)
    drawn = location_presence(zones, sizes > 0, count)
    targets = ownable & vanilla_present & ~drawn
    before = int(targets.sum())
    report = {"vanilla_river_locations_without_drawn_river": before}
    if cfg.get("bank_detours", True):
        served = bank_detours(sizes, owner, markers, zones, targets, blocked)
        targets[served] = False
        report["bank_detours"] = len(served)
    if cfg.get("fallback_pieces", True):
        pieces = vanilla_pieces(native, sizes, owner, markers, zones, targets, blocked, int(cfg.get("minimum_piece_pixels", 4)))
        report["fallback_pieces"] = {k: v for k, v in pieces.items() if k != "served"}
        report["fallback_locations"] = len(pieces["served"])
    if cfg.get("bfs_detours", True):
        served = bfs_detours(sizes, owner, markers, zones, targets, blocked, int(cfg.get("detour_max_length", 12)), int(cfg.get("detour_reach", 4)))
        targets[served] = False
        report["bfs_detours"] = len(served)
        # what is still left gets vanilla's smallest pieces too
        pieces = vanilla_pieces(native, sizes, owner, markers, zones, targets, blocked, 2)
        report["small_pieces"] = {k: v for k, v in pieces.items() if k != "served"}
        report["small_piece_locations"] = len(pieces["served"])
    drawn = location_presence(zones, sizes > 0, count)
    report["remaining"] = int((ownable & vanilla_present & ~drawn).sum())
    return report
