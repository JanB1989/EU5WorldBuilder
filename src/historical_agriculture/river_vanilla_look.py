"""Redraw the final rivers on vanilla's own river network. Visual only.

EU5 1.4 draws rivers in many map modes (paper style, with dark banks) and animates their flow in the river map
mode, so the shape of the drawing shows. Vanilla's rivers are about 700 continuous systems that nearly all reach
the sea; the drawing traced from the geographic network (``river_map.export`` plus the navigation cleanup) had about
5,300 pieces, most of them ending on land, many shorter than the engine's source fade-in, and some running one or two
pixels beside a copied vanilla piece. This pass redraws the final rivers after the navigation cut its channels:

1. Skeleton: vanilla's river pixels on land, except in ownable locations without a river in the gameplay table and
   along a channel (a line beside a channel goes, a tributary mouth crossing the corridor stays and touches the
   channel). Vanilla's distributary splits (yellow) are detached: the branch starts one pixel off the main river.
2. Own rivers: the drawing's pixels farther than ``cover_pixels`` from the skeleton, i.e. rivers vanilla does not
   draw. A piece that leaves a vanilla line and comes back to it (the same river drawn a little apart) is dropped; a
   piece that flows into a vanilla river is joined to it by a short bridge; pieces below ``minimum_piece_pixels``
   are dropped.
3. Encoding: every connected river becomes one tree in the engine's strict encoding (one green source at the head of
   the mainstem, a red marker on the first pixel of each tributary; ``river_map.validate_native_rivers``). A red
   marker makes its location level 5, so a tributary joins only inside a location the gameplay table gives level 5
   (or on unownable land); elsewhere it ends one pixel short of the receiving river.
4. Levels: the gameplay table (every ownable location's engine level in the input drawing: widest pixel, a junction
   marker = 5) is kept exactly. A pixel wider than its location's level takes the widest width of that level. The
   widths stay vanilla's otherwise: vanilla draws nearly every river at 4 or 5, so widening each location's line to
   its level (3, 4, 5) would pinch and bulge the rivers at every location border (about 6,000 abrupt width changes
   in a trial, and the wrong river widened where the level came from a river vanilla draws elsewhere). Only level 2
   is widened (width 6 looks like vanilla's 5, ``widen_up_to_level``). A location still below its level gets a
   two-pixel carrier (source plus one width pixel): the engine does not draw the first ``FADE_IN_DISTANCE *
   FADE_IN_INVISIBLE_DISTANCE_THRESHOLD`` (5) pixels after a source, so a carrier is not visible; the input drawing
   already held about a thousand such pieces.
"""
from __future__ import annotations

from collections import Counter, deque

import numpy as np
from scipy import ndimage, sparse
from scipy.sparse import csgraph
from scipy.spatial import cKDTree

LEVELS = np.array([0, 5, 5, 1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5] + [0] * 240, np.uint8)
WIDTH = np.zeros(256, bool)
WIDTH[3:16] = True
# widest palette index of each level (a capped pixel keeps as much of its width as the level allows)
CAP_INDEX = np.array([0, 5, 8, 11, 14, 15], np.uint8)
# carrier width per level (vanilla's widths for 1, 3, 5)
CARRIER_INDEX = np.array([0, 4, 6, 11, 12, 15], np.uint8)
# width a visible river takes when widened to its location's level (the export's default width of the level)
DEFAULT_INDEX = np.array([0, 4, 6, 11, 12, 15], np.uint8)
FOUR = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool)
EIGHT = np.ones((3, 3), bool)
OFFSETS = ((-1, 0), (1, 0), (0, -1), (0, 1))


def zone_levels(pixels, zones, count):
    """Engine river level per zone id: the widest pixel, a junction marker counts as 5, a source as nothing."""
    ys, xs = np.nonzero(pixels < 16)
    out = np.zeros(count, np.uint8)
    np.maximum.at(out, zones[ys, xs], LEVELS[pixels[ys, xs]])
    return out


def width_jumps(pixels):
    """Neighbouring width pixels along a river whose levels differ by two or more (a visible pinch or bulge)."""
    level = np.where(WIDTH[pixels], LEVELS[pixels], 0).astype(np.int16)
    out = 0
    for a, b in ((level[:, :-1], level[:, 1:]), (level[:-1], level[1:])):
        out += int(((a > 0) & (b > 0) & (np.abs(a - b) >= 2)).sum())
    return out


def _fill_widths(pixels, mask):
    """Palette width per river pixel; marker pixels take their widest neighbour's width (4 if none)."""
    h, w = mask.shape
    out = np.where(mask & WIDTH[pixels], pixels, 0).astype(np.uint8)
    ys, xs = np.nonzero(mask & (out == 0))
    if len(ys):
        best = np.zeros(len(ys), np.uint8)
        for dy, dx in OFFSETS:
            yy, xx = np.clip(ys + dy, 0, h - 1), np.clip(xs + dx, 0, w - 1)
            best = np.maximum(best, out[yy, xx])
        best[best == 0] = 4
        out[ys, xs] = best
    return out


class Graph:
    """Four-connected graph over the pixels of a mask (node = rank of the flat index)."""

    def __init__(self, mask):
        self.h, self.w = mask.shape
        self.flat = np.flatnonzero(mask.ravel())
        self.n = n = len(self.flat)
        x = self.flat % self.w
        right = np.where(x < self.w - 1, self.lookup(self.flat + 1), -1)
        down = self.lookup(self.flat + self.w)
        a = np.r_[np.flatnonzero(right >= 0), np.flatnonzero(down >= 0)]
        b = np.r_[right[right >= 0], down[down >= 0]]
        g = sparse.coo_matrix((np.ones(len(a), np.int8), (a, b)), shape=(n, n)).tocsr()
        self.g = (g + g.T).tocsr()
        self.degree = np.diff(self.g.indptr)

    def lookup(self, q):
        q = np.asarray(q)
        if not self.n:
            return np.full(q.shape, -1)
        pos = np.minimum(np.searchsorted(self.flat, q), self.n - 1)
        return np.where(self.flat[pos] == q, pos, -1)

    def neighbours(self, i):
        return self.g.indices[self.g.indptr[i]:self.g.indptr[i + 1]]

    def yx(self, i):
        return divmod(int(self.flat[i]), self.w)


def flow_distance(pixels):
    """Steps to the mouth for every river pixel of a native drawing (-1 elsewhere). The mouth of a tree is the far
    end of the segment that carries its green source; tributaries (and split branches) flow towards their marker."""
    river = pixels < 16
    graph = Graph(river)
    value = pixels.ravel()[graph.flat]
    plain = ~np.isin(value, (1, 2))
    seg = Graph(river & ~np.isin(pixels, (1, 2)))
    _, seg_label = csgraph.connected_components(seg.g, directed=False)
    seg_of = np.full(graph.n, -1)
    seg_of[plain] = seg_label[seg.lookup(graph.flat[plain])]
    green = np.flatnonzero(value == 0)
    root = set(seg_of[green].tolist())
    ends = np.flatnonzero(plain & (value != 0))
    seg_degree = np.zeros(graph.n, np.int64)
    seg_degree[plain] = seg.degree[seg.lookup(graph.flat[plain])]
    mouths = [i for i in ends[seg_degree[ends] <= 1] if seg_of[i] in root]
    if not mouths:
        mouths = green.tolist()
    dist = csgraph.dijkstra(graph.g, unweighted=True, indices=np.asarray(mouths), min_only=True)
    out = np.full(river.shape, -1, np.int64)
    finite = np.isfinite(dist)
    out.ravel()[graph.flat[finite]] = dist[finite].astype(np.int64)
    return out


def encode(mask, widths, zones, water, allowed_zone, prefer_red, hint, keep, counters, max_passes=40):
    """Encode the river pixels of ``mask`` as native trees; returns the palette pixels of the rivers (255 elsewhere).

    widths: palette width (3..15) per pixel. allowed_zone: per zone id, may a red marker sit there. prefer_red:
    pixels vanilla marks as a tributary head. hint: flow distance hint (smaller = further downstream, -1 unknown).
    keep: removal priority (a cycle loses its lowest pixel). Pixels are only ever removed (cycles, tributary heads
    that cannot be marked, lone pixels); the loop ends when every tree has a valid marker assignment."""
    mask = mask.copy()
    h, w = mask.shape
    for _ in range(max_passes):
        graph = Graph(mask)
        n, flat, deg = graph.n, graph.flat, graph.degree
        ncomp, comp = csgraph.connected_components(graph.g, directed=False)
        removals = flat[deg == 0].tolist()
        counters["lone_pixels_removed"] += len(removals)
        edges = np.bincount(comp, weights=deg, minlength=ncomp) / 2
        verts = np.bincount(comp, minlength=ncomp)
        # sink: an endpoint on water first, then the one furthest downstream by the hint, then the widest
        fy, fx = flat // w, flat % w
        wet = np.zeros(n, bool)
        for dy, dx in OFFSETS:
            yy, xx = np.clip(fy + dy, 0, h - 1), np.clip(fx + dx, 0, w - 1)
            wet |= water[yy, xx]
        node_hint = hint.ravel()[flat].astype(np.float64)
        node_hint[node_hint < 0] = 1e9
        node_width = widths.ravel()[flat].astype(np.int64)
        candidates = np.flatnonzero(deg == 1)
        order = np.lexsort((-node_width[candidates], node_hint[candidates], ~wet[candidates]))
        sinks = np.full(ncomp, -1, np.int64)
        for i in candidates[order]:
            if sinks[comp[i]] < 0:
                sinks[comp[i]] = i
        for c in np.flatnonzero((sinks < 0) & (verts > 1)):
            sinks[c] = np.flatnonzero(comp == c)[0]
        valid_sinks = sinks[sinks >= 0]
        if not len(valid_sinks):
            break
        dist, pred, _ = csgraph.dijkstra(graph.g, unweighted=True, indices=valid_sinks, min_only=True,
                                         return_predecessors=True)
        node_keep = keep.ravel()[flat]
        # cycles: drop the weaker end of every edge outside the breadth-first tree
        cyclic = np.flatnonzero(edges > verts - 1)
        if len(cyclic):
            in_cycle = np.isin(comp, cyclic)
            coo = graph.g.tocoo()
            sel = (coo.row < coo.col) & in_cycle[coo.row]
            a, b = coo.row[sel], coo.col[sel]
            off = (pred[a] != b) & (pred[b] != a)
            for i, j in zip(a[off], b[off]):
                weaker = i if (node_keep[i], node_width[i]) < (node_keep[j], node_width[j]) else j
                removals.append(int(flat[weaker]))
            counters["cycle_pixels_removed"] += int(off.sum())
        if removals:
            mask.ravel()[np.asarray(removals, np.int64)] = False
            continue
        parent = pred.astype(np.int64)
        parent[parent < 0] = -1
        children = np.bincount(parent[parent >= 0], minlength=n)
        # subtree size and widest pixel, accumulated from the leaves
        order = np.argsort(-dist, kind="stable")
        size = np.ones(n, np.int64)
        top = node_width.copy()
        par_list, size_l, top_l = parent.tolist(), size.tolist(), top.tolist()
        for i in order.tolist():
            p = par_list[i]
            if p >= 0:
                size_l[p] += size_l[i]
                if top_l[i] > top_l[p]:
                    top_l[p] = top_l[i]
        size, top = np.asarray(size_l), np.asarray(top_l)
        kids_of = {}
        junctions = np.flatnonzero(children >= 2)
        if len(junctions):
            members = np.flatnonzero(np.isin(parent, junctions))
            for k in members.tolist():
                kids_of.setdefault(par_list[k], []).append(k)
        node_zone = zones.ravel()[flat]
        node_pref = prefer_red.ravel()[flat]
        only_child = {}
        single = np.flatnonzero(children == 1)
        if len(single):
            holders = np.flatnonzero(np.isin(parent, single))
            for k in holders.tolist():
                only_child[par_list[k]] = k

        def markable(r):
            t = only_child.get(r)
            return (t is not None and children[t] == 1 and bool(allowed_zone[node_zone[r]]))

        red, main_of = [], {}
        for q, kids in kids_of.items():
            kids.sort(key=lambda k: (not node_pref[k], top[k], size[k], node_keep[k]))
            main = kids[-1]
            tribs = kids[:-1]
            if len(kids) == 2 and not markable(tribs[0]) and markable(main) and not node_pref[main]:
                main, tribs = tribs[0], [main]
                counters["junctions_swapped"] += 1
            main_of[q] = main
            for r in tribs:
                if markable(r):
                    red.append(r)
                else:
                    removals.append(int(flat[r]))
                    counters["tributaries_detached"] += 1
        if removals:
            mask.ravel()[np.asarray(removals, np.int64)] = False
            continue
        out = np.full(mask.shape, 255, np.uint8)
        out.ravel()[flat] = node_width.astype(np.uint8)
        if red:
            out.ravel()[flat[np.asarray(red, np.int64)]] = 1
        # green source at the head of every mainstem; an extra pixel beyond the head where one fits, so the head
        # keeps its width
        for s in valid_sinks.tolist():
            i = s
            while True:
                nxt = main_of.get(i)
                if nxt is None:
                    nxt = only_child.get(i)
                if nxt is None:
                    break
                i = nxt
            y, x = divmod(int(flat[i]), w)
            placed = False
            for dy, dx in OFFSETS:
                py, px = y + dy, x + dx
                if not (0 <= py < h and 0 <= px < w) or out[py, px] < 254 or water[py, px] or zones[py, px] == 0:
                    continue
                if any(0 <= py + ey < h and 0 <= px + ex < w and out[py + ey, px + ex] < 16 and (py + ey, px + ex) != (y, x)
                       for ey, ex in OFFSETS):
                    continue
                out[py, px] = 0
                placed = True
                counters["sources_added_beyond_head"] += 1
                break
            if not placed:
                out[y, x] = 0
                counters["sources_on_head"] += 1
        counters["trees"] += int(len(valid_sinks))
        counters["tributary_markers"] += len(red)
        return out
    raise RuntimeError("River encoding did not converge")


def _bounded_path_length(mask, a, b, limit):
    """Four-connected path length from a to b inside mask, or None beyond ``limit`` steps."""
    h, w = mask.shape
    seen = {a: 0}
    queue = deque([a])
    while queue:
        p = queue.popleft()
        if p == b:
            return seen[p]
        if seen[p] >= limit:
            continue
        for dy, dx in OFFSETS:
            q = (p[0] + dy, p[1] + dx)
            if 0 <= q[0] < h and 0 <= q[1] < w and q not in seen and mask[q]:
                seen[q] = seen[p] + 1
                queue.append(q)
    return None


def redraw(drawing, vanilla, zones, ownable, converted, cfg=None):
    """Return (pixels, report). ``drawing``: the final rivers (palette indices, 254 water); ``vanilla``: vanilla's
    rivers.png; ``zones``: zone id per pixel (0 = none); ``ownable``: bool per zone id; ``converted``: land turned
    into channel water. Every ownable zone keeps the engine river level it has in ``drawing``."""
    cfg = cfg or {}
    R = int(cfg.get("cover_pixels", 5))
    min_piece = int(cfg.get("minimum_piece_pixels", 12))
    bridge_max = int(cfg.get("bridge_max_pixels", R + 4))
    corridor = int(cfg.get("channel_corridor_pixels", 3))
    band = int(cfg.get("channel_parallel_pixels", 8))
    band_min = int(cfg.get("channel_parallel_minimum_pixels", 12))
    mouth_max = int(cfg.get("channel_mouth_maximum_pixels", 4))
    duplicate_share = float(cfg.get("duplicate_share", 0.8))
    h, w = drawing.shape
    counters = Counter()
    water = drawing == 254
    count = int(zones.max()) + 1
    ownable = np.asarray(ownable, bool)
    target = zone_levels(drawing, zones, count)
    target[~ownable] = 0
    land_zone = np.bincount(zones[~water].ravel(), minlength=count)[:count] > 0
    land_zone[0] = False
    usable_zone = land_zone & (~ownable | (target > 0))
    allowed_red = land_zone & ((~ownable) | (target == 5))

    # 1. skeleton
    skeleton = (vanilla < 16) & ~water & usable_zone[zones]
    yellow = skeleton & (vanilla == 2)
    counters["vanilla_splits_detached"] = int(yellow.sum())
    skeleton &= ~yellow
    if converted.any():
        near = ndimage.binary_dilation(converted, iterations=corridor) & ~converted & skeleton
        lab, n = ndimage.label(near, EIGHT)
        if n:
            sizes = np.bincount(lab.ravel(), minlength=n + 1)
            wet_piece = np.zeros(n + 1, bool)
            touch = ndimage.binary_dilation(converted, FOUR) & near
            wet_piece[np.unique(lab[touch])] = True
            mouth = (sizes <= mouth_max) & wet_piece
            mouth[0] = False
            drop = near & ~mouth[lab]
            counters["vanilla_channel_corridor_pixels_dropped"] = int(drop.sum())
            skeleton &= ~drop
        beside = ndimage.binary_dilation(converted, iterations=band) & ~converted & skeleton
        lab, n = ndimage.label(beside, EIGHT)
        if n:
            sizes = np.bincount(lab.ravel(), minlength=n + 1)
            sizes[0] = 0
            drop = sizes[lab] > band_min
            counters["vanilla_channel_parallel_pixels_dropped"] = int(drop.sum())
            skeleton &= ~drop
    skeleton_width = _fill_widths(vanilla, skeleton)
    prefer_red = skeleton & (vanilla == 1)
    vanilla_flow = flow_distance(vanilla)

    # 2. own rivers
    river = drawing < 16
    own_width = _fill_widths(drawing, river)
    flow = flow_distance(drawing)
    distance = ndimage.distance_transform_cdt(~skeleton, metric="chessboard")
    covered = river & (distance <= R)
    own = river & (distance > R)
    alongside = distance <= int(cfg.get("duplicate_pixels", 12))
    del distance
    contact = own & ndimage.binary_dilation(covered, FOUR)
    lab, n_own = ndimage.label(own, FOUR)
    objects = ndimage.find_objects(lab)
    sk_graph = Graph(skeleton)
    _, sk_comp = csgraph.connected_components(sk_graph.g, directed=False)
    sk_tree = cKDTree(np.column_stack((sk_graph.flat // w, sk_graph.flat % w)))
    kept = np.zeros((h, w), bool)
    bridges_wanted = []
    for k, sl in enumerate(objects, 1):
        if sl is None:
            continue
        piece = lab[sl] == k
        size = int(piece.sum())
        if size < min_piece:
            counters["own_pieces_dropped_small"] += 1
            counters["own_pixels_dropped_small"] += size
            continue
        oy, ox = sl[0].start, sl[1].start
        # the same river as a vanilla one, drawn a few pixels beside it
        if np.count_nonzero(piece & alongside[sl]) >= duplicate_share * size:
            counters["own_pieces_dropped_alongside"] += 1
            counters["own_pixels_dropped_alongside"] += size
            continue
        cys, cxs = np.nonzero(piece & contact[sl])
        if not len(cys):
            kept[sl] |= piece
            counters["own_pieces_standalone"] += 1
            continue
        pys, pxs = np.nonzero(piece)
        pflow = flow[sl][piece]
        known = pflow >= 0
        down = int(np.argmin(np.where(known, pflow, 1 << 40))) if known.any() else 0
        dy_, dx_ = int(pys[down]), int(pxs[down])
        # contact groups (eight-connected clusters of contact pixels)
        cmask = np.zeros(piece.shape, bool)
        cmask[cys, cxs] = True
        clab, ncl = ndimage.label(cmask, EIGHT)
        groups = []
        for g in range(1, ncl + 1):
            gy, gx = np.nonzero(clab == g)
            gflow = flow[sl][gy, gx]
            groups.append((gy, gx, gflow))
        down_group = None
        for gi, (gy, gx, gflow) in enumerate(groups):
            if np.any((np.abs(gy - dy_) <= 1) & (np.abs(gx - dx_) <= 1)):
                down_group = gi
        if len(groups) >= 2:
            # excursion: both ends near the same vanilla river, vanilla's own path between them about as long
            ends = sorted(range(len(groups)), key=lambda gi: float(np.max(groups[gi][2])) if len(groups[gi][2]) else 0)
            first, last = groups[ends[0]], groups[ends[-1]]
            pa = (int(first[0][0]) + oy, int(first[1][0]) + ox)
            pb = (int(last[0][0]) + oy, int(last[1][0]) + ox)
            _, ia = sk_tree.query(pa, p=np.inf)
            _, ib = sk_tree.query(pb, p=np.inf)
            if sk_comp[ia] == sk_comp[ib]:
                sa, sb = sk_graph.yx(ia), sk_graph.yx(ib)
                length = _bounded_path_length(skeleton, sa, sb, int(1.5 * size) + 2 * R)
                if length is not None:
                    counters["own_pieces_dropped_excursion"] += 1
                    counters["own_pixels_dropped_excursion"] += size
                    continue
        kept[sl] |= piece
        counters["own_pieces_joined" if down_group is not None else "own_pieces_kept_upstream_contact"] += 1
        if down_group is not None:
            bridges_wanted.append((dy_ + oy, dx_ + ox))
    del lab, contact, alongside

    # bridges from the downstream end of a kept piece to the skeleton
    drawn = skeleton | kept
    width_map = np.where(skeleton, skeleton_width, np.where(kept, own_width, 0)).astype(np.uint8)
    sk_degree = np.zeros((h, w), np.uint8)
    sk_degree.ravel()[sk_graph.flat] = sk_graph.degree.astype(np.uint8)
    # flow hint for the encoder (smaller = further downstream); a bridge continues its piece downstream
    hint = np.where(skeleton, vanilla_flow + 1.0, np.where(kept, flow + 1.0, -1.0))
    hint[(skeleton & (vanilla_flow < 0)) | (kept & (flow < 0))] = -1.0
    for e in bridges_wanted:
        if water[max(e[0] - 1, 0):e[0] + 2, max(e[1] - 1, 0):e[1] + 2].any():
            continue
        path, kind = _bridge(e, drawn, skeleton, sk_degree, water, zones, usable_zone, allowed_red, bridge_max)
        if path is None:
            counters["bridges_not_found"] += 1
            continue
        base = max(float(hint[e]), 1.0)
        for k, p in enumerate(path):
            drawn[p] = True
            width_map[p] = width_map[e]
            hint[p] = base - (k + 1) / (len(path) + 1)
        counters["bridges_" + kind] += 1
        counters["bridge_pixels"] += len(path)

    # 3. encoding
    keep = np.where(skeleton, 3, np.where(kept, 2, 1)).astype(np.int8)
    pixels = encode(drawn, width_map, zones, water, allowed_red, prefer_red, hint, keep, counters)
    pixels[water] = 254

    # 4. levels: cap, then carriers
    river_now = WIDTH[pixels]
    zone_of = zones
    lvl = LEVELS[pixels]
    tz = target[zone_of]
    over = river_now & ownable[zone_of] & (lvl > tz)
    if np.any(over & (tz == 0)):
        raise AssertionError("River width pixel in a location without a river")
    counters["pixels_capped"] = int(over.sum())
    pixels[over] = CAP_INDEX[tz[over]]
    # A location whose visible river is narrower than its level shows the level, up to ``widen_up_to_level``: its
    # widest visible river takes the level's width. A level 5 is never widened where it came from a junction marker
    # (it stays as narrow as before, with a carrier below).
    lab, ncomp = ndimage.label(pixels < 16, FOUR)
    comp_size = np.bincount(lab.ravel(), minlength=ncomp + 1)
    visible = WIDTH[pixels] & (comp_size[lab] > int(cfg.get("invisible_tree_pixels", 5)))
    del lab
    seen = zone_levels(np.where(visible, pixels, 255).astype(np.uint8), zones, count)
    wide5 = zone_levels(np.where(drawing == 15, drawing, 255).astype(np.uint8), zones, count) == 5
    widen_zone = ownable & (seen > 0) & (seen < target) & ((target < 5) | wide5)
    widen_zone &= target <= int(cfg.get("widen_up_to_level", 2))
    vz = zones
    pick = visible & widen_zone[vz] & (LEVELS[pixels] == seen[vz])
    counters["locations_widened"] = int(widen_zone.sum())
    counters["pixels_widened"] = int(pick.sum())
    pixels[pick] = DEFAULT_INDEX[target[vz[pick]]]
    del pick, visible
    now = zone_levels(pixels, zones, count)
    deficit = np.flatnonzero(ownable & (now < target))
    if len(deficit):
        boxes = ndimage.find_objects(zones)
        occupied = ndimage.binary_dilation(pixels < 16, EIGHT)
        for z in deficit.tolist():
            sl = boxes[z - 1]
            y0, y1 = max(sl[0].start - 1, 0), min(sl[0].stop + 1, h)
            x0, x1 = max(sl[1].start - 1, 0), min(sl[1].stop + 1, w)
            inside = (zones[y0:y1, x0:x1] == z) & ~water[y0:y1, x0:x1]
            free = inside & ~occupied[y0:y1, x0:x1]
            pair = free.copy()
            pair[:, :-1] &= free[:, 1:]
            ys, xs = np.nonzero(pair)
            level = int(target[z])
            if not len(ys):
                # no room for a carrier: widen a pixel of the location's own river instead
                ry, rx = np.nonzero(inside & WIDTH[pixels[y0:y1, x0:x1]])
                if not len(ry):
                    raise AssertionError(f"No room to keep the river level of zone {z}")
                pixels[ry[0] + y0, rx[0] + x0] = CAP_INDEX[level]
                counters["levels_kept_by_widening"] += 1
                continue
            # nearest to where the input drawing had the location's level
            oy, ox = np.nonzero((zones[y0:y1, x0:x1] == z) & (LEVELS[drawing[y0:y1, x0:x1]] == level) & (drawing[y0:y1, x0:x1] < 16))
            if len(oy):
                d, _ = cKDTree(np.column_stack((oy, ox))).query(np.column_stack((ys, xs)))
                k = int(np.argmin(d))
            else:
                k = len(ys) // 2
            cy, cx = int(ys[k]) + y0, int(xs[k]) + x0
            pixels[cy, cx] = CARRIER_INDEX[level]
            pixels[cy, cx + 1] = 0
            occupied[max(cy - 1, 0):cy + 2, max(cx - 1, 0):cx + 3] = True
            counters["level_carriers"] += 1
    final = zone_levels(pixels, zones, count)
    bad = np.flatnonzero(ownable & (final != target))
    if len(bad):
        raise AssertionError(f"{len(bad)} locations changed their river level")
    if np.any((pixels < 16) & water):
        raise AssertionError("River pixel on water")
    from .river_map import validate_native_rivers
    checks = validate_native_rivers(pixels)
    river_out = pixels < 16
    lab, comps = ndimage.label(river_out, FOUR)
    sizes = np.bincount(lab.ravel(), minlength=comps + 1)[1:]
    wet = ndimage.binary_dilation(water, FOUR) & river_out
    wet_comps = len(np.unique(lab[wet]))
    vr = (vanilla < 16) & ~water
    own_out = river_out & ~vr
    report = {
        "own_pixels_by_level": {int(k): int(v) for k, v in zip(*np.unique(LEVELS[pixels[own_out & WIDTH[pixels]]], return_counts=True))},
        "width_jumps": {"output": width_jumps(pixels), "input": width_jumps(drawing), "vanilla": width_jumps(vanilla)},
        "counters": dict(sorted(counters.items())),
        "trees": int(comps), "trees_reaching_water": int(wet_comps),
        "trees_below_6_pixels": int((sizes <= 5).sum()), "trees_6_to_15_pixels": int(((sizes > 5) & (sizes < 16)).sum()),
        "river_pixels": int(river_out.sum()),
        "river_pixels_on_vanilla": int((river_out & vr).sum()),
        "vanilla_pixels_drawn": int((river_out & vr).sum()),
        "vanilla_land_pixels": int(vr.sum()),
        "checks": checks,
        "locations_with_level_kept": int((ownable & (target > 0)).sum()),
    }
    return pixels, report


def _bridge(e, drawn, skeleton, sk_degree, water, zones, usable_zone, allowed_red, limit):
    """Shortest free four-connected path from the own pixel ``e`` to a pixel touching exactly one skeleton pixel:
    a skeleton end (the rivers join end to end) or, where a red marker may sit, a skeleton interior pixel (the piece
    joins as a tributary). The path touches no other river pixel. Returns the path without ``e`` or None."""
    h, w = drawn.shape

    def touching(p):
        return [(p[0] + dy, p[1] + dx) for dy, dx in OFFSETS
                if 0 <= p[0] + dy < h and 0 <= p[1] + dx < w and drawn[p[0] + dy, p[1] + dx]]

    def trace(q):
        path = []
        while q != e:
            path.append(q)
            q = parents[q]
        return path[::-1]

    parents = {e: None}
    depth = {e: 0}
    queue = deque([e])
    near = gap = None
    while queue:
        p = queue.popleft()
        if depth[p] >= limit:
            continue
        for dy, dx in OFFSETS:
            q = (p[0] + dy, p[1] + dx)
            if not (0 <= q[0] < h and 0 <= q[1] < w) or q in parents or drawn[q] or water[q]:
                continue
            if not usable_zone[zones[q]]:
                continue
            others = [t for t in touching(q) if t != p]
            if p != e and e in others:
                continue
            parents[q] = p
            depth[q] = depth[p] + 1
            if not others:
                queue.append(q)
                if near is None and skeleton[max(q[0] - 1, 0):q[0] + 2, max(q[1] - 1, 0):q[1] + 2].any():
                    near = q
                elif gap is None and skeleton[max(q[0] - 2, 0):q[0] + 3, max(q[1] - 2, 0):q[1] + 3].any():
                    gap = q
                continue
            if len(others) != 1 or not skeleton[others[0]]:
                continue
            s = others[0]
            end_to_end = sk_degree[s] == 1 and not water[max(s[0] - 1, 0):s[0] + 2, max(s[1] - 1, 0):s[1] + 2].any()
            if end_to_end or (sk_degree[s] == 2 and allowed_red[zones[q]]):
                return trace(q), "joined"
    # no join allowed: end diagonally against the receiving river (not connected, drawn as touching), else one
    # pixel short of it
    if near is not None:
        return trace(near), "touching"
    if gap is not None:
        return trace(gap), "one_pixel_short"
    return None, None
