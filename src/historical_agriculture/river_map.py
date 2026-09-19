"""Configurable export of a geographic river network to EU5's indexed bitmap.

No game class is written back into the geographic network. Raster routing builds
an induced, four-connected forest: accidental touches are stopped, not silently
turned into hydrological links. The resulting omissions are reported explicitly.
"""
from collections import Counter, deque
from pathlib import Path
import heapq
import json
import tomllib

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from PIL import Image
import shapely

from .river_network import digest, save_json, verify, downstream_indices
from .location_inventory import read_zone_inventory

Image.MAX_IMAGE_PIXELS = None
OFFSETS = ((-1, 0), (1, 0), (0, -1), (0, 1))


def select_with_closure(q, down, minimum):
    selected = q >= minimum
    front = np.flatnonzero(selected)
    initial = int(selected.sum())
    while len(front):
        targets = down[front]
        targets = np.unique(targets[targets >= 0])
        front = targets[~selected[targets]]
        selected[front] = True
    return selected, int(selected.sum()) - initial


def levels(q, bounds):
    if len(bounds) != 5 or any(b <= a for a, b in zip(bounds, bounds[1:])):
        raise ValueError("Exactly five increasing discharge lower bounds are required")
    # Below-cutoff downstream closure segments still have the smallest river size.
    return np.clip(np.searchsorted(bounds, q, side="right"), 1, 5).astype(np.uint8)


class Projection:
    def __init__(self, transform, width, height):
        self.t, self.width, self.height = transform, width, height
        yy = np.arange(height, dtype=float)
        self.lats = np.polynomial.polynomial.polyval(
            (yy-transform["y_mean"])/transform["y_scale"], transform["lat_coefficients"])
        if not np.all(np.diff(self.lats) < 0):
            raise ValueError("Expected monotonic latitude registration")
        self.lon0 = self.longitude(0)

    def longitude(self, x):
        t = self.t
        return t["lon_coefficients"][0]+(x-t["x_mean"])/t["x_scale"]*t["lon_coefficients"][1]

    def project(self, coords):
        t = self.t
        lon = (coords[:, 0]-self.lon0) % 360 + self.lon0
        x = (lon-t["lon_coefficients"][0])/t["lon_coefficients"][1]*t["x_scale"]+t["x_mean"]
        y = np.interp(coords[:, 1], self.lats[::-1], np.arange(self.height)[::-1], left=np.nan, right=np.nan)
        return np.column_stack((x, y))


def lattice_path(points, width, height):
    """Four-connected lines; split outside the map and at its longitude seam."""
    run = []
    for a, b in zip(points[:-1], points[1:]):
        if not np.isfinite([*a, *b]).all() or abs(a[0]-b[0]) > width/2:
            if run:
                yield run
                run = []
            continue
        x, y = np.rint(a).astype(int); tx, ty = np.rint(b).astype(int)
        dx, dy = abs(tx-x), abs(ty-y)
        sx, sy = (1 if tx > x else -1), (1 if ty > y else -1)
        ix = iy = 0
        while True:
            if 0 <= x < width and 0 <= y < height:
                if not run or run[-1] != (x, y):
                    run.append((x, y))
            elif run:
                yield run; run = []
            if ix == dx and iy == dy:
                break
            if ix < dx and (iy == dy or (ix+.5)*dy <= (iy+.5)*dx):
                x += sx; ix += 1
            else:
                y += sy; iy += 1
    if run:
        yield run


def erase_raster_loops(path):
    """Shortcut self-touches at pixel resolution, retaining an induced path."""
    clean, positions = [], {}
    for p in path:
        x, y = p
        contacts = [positions[z] for z in [(x+dx, y+dy) for dx, dy in OFFSETS] if z in positions]
        if p in positions:
            keep = positions[p]+1
            for removed in clean[keep:]: positions.pop(removed)
            del clean[keep:]
            continue
        if contacts:
            keep = min(contacts)+1
            for removed in clean[keep:]: positions.pop(removed)
            del clean[keep:]
        positions[p] = len(clean)
        clean.append(p)
    return clean


def valid_attachment(point, sizes):
    """Join an ordinary interior pixel, with room for a tributary marker.

    EU5's red marker belongs BEFORE the branch point, never on it. Excluding
    adjacent branch points also prevents a later tributary from branching off
    an existing marker. Headwaters/outlets remain endpoints.
    """
    h, w = sizes.shape
    def neighbours(p):
        x, y = p
        return [(x+dx, y+dy) for dx, dy in OFFSETS
                if 0 <= x+dx < w and 0 <= y+dy < h and sizes[y+dy, x+dx]]
    ns = neighbours(point)
    nearby = {n for p in [point, *ns] for n in neighbours(p)}
    return len(ns) == 2 and all(len(neighbours(n)) <= 2 for n in nearby)


def validate_native_rivers(pixels):
    """Audit the strict tree subset emitted here, not arbitrary split rivers.

    Remove red tributary endpoints: each remaining segment must be a simple
    path. A red marker connects the end of its tributary to the INTERIOR of
    its receiving segment. This catches the engine's clumped-affluent failure
    that a generic acyclic-graph test misses.
    """
    from scipy.ndimage import label
    river = pixels < 16
    def degrees(mask):
        d = np.zeros(mask.shape, np.uint8)
        d[1:] += mask[:-1]; d[:-1] += mask[1:]
        d[:, 1:] += mask[:, :-1]; d[:, :-1] += mask[:, 1:]
        return d
    if np.any(pixels == 2):
        raise ValueError('Distributary markers are not supported by this tree exporter')
    degree = degrees(river)
    red = pixels == 1
    green = pixels == 0
    if np.any(degree[red] != 2): raise ValueError('Red tributary marker must have degree two, before the junction')
    if np.any(degree[green] != 1): raise ValueError('Green source must be an endpoint')
    segments = river & ~red
    sd = degrees(segments)
    if np.any(sd[segments] > 2): raise ValueError('Unmarked branch/clumped affluent in river segment')
    labels, count = label(river)
    sources = np.bincount(labels[green], minlength=count+1)[1:]
    if np.any(sources != 1): raise ValueError('Each river tree must have exactly one green source')
    vertices = int(river.sum())
    if int(degree[river].astype(np.int64).sum())//2 != vertices-count:
        raise ValueError('River graph contains a cycle')
    del labels
    sl, nseg = label(segments)
    parent = np.zeros(nseg+1, np.int32)
    for y, x in np.argwhere(red):
        ns = [(x+dx, y+dy) for dx, dy in OFFSETS if
              0 <= x+dx < pixels.shape[1] and 0 <= y+dy < pixels.shape[0] and river[y+dy, x+dx]]
        if any(red[ny, nx] for nx, ny in ns): raise ValueError('Adjacent tributary markers')
        if sorted(int(sd[ny, nx]) for nx, ny in ns) != [1, 2]:
            raise ValueError(f'Tributary at {(int(x),int(y))} must attach its endpoint to a receiving segment interior: {[int(sd[ny,nx]) for nx,ny in ns]}')
        if sl[ns[0][1], ns[0][0]] == sl[ns[1][1], ns[1][0]]:
            raise ValueError('Tributary reconnects to its own segment')
        incoming = next((nx,ny) for nx,ny in ns if sd[ny,nx] == 1)
        receiving = next((nx,ny) for nx,ny in ns if sd[ny,nx] == 2)
        child = sl[incoming[1],incoming[0]]
        if parent[child]: raise ValueError('Tributary has multiple receiving segments')
        parent[child] = sl[receiving[1],receiving[0]]
    root_segments = set(np.flatnonzero(parent[1:] == 0)+1)
    source_segments = set(sl[green].tolist())
    if root_segments != source_segments:
        raise ValueError('Green sources must start receiving mainstems, not tributaries')
    return {'components': int(count), 'segments': int(nseg), 'river_pixels': vertices,
            'tributary_markers': int(red.sum()), 'sources': int(green.sum()),
            'native_tributary_encoding': True, 'directed_segment_coverage': True}


def route_run(path, sizes, owner, basin, level, allow_root, min_pixels):
    """Extend downstream-first. Only actual network siblings may share pixels.

    Stops on a second contact, so an accidental crossing never creates a loop
    or a new basin connection. The caller reports truncated and omitted runs.
    """
    h, w = sizes.shape
    added = []
    attached = False
    last = None
    reason = "complete"
    consumed = 0
    for x, y in path:
        consumed += 1
        neighbours = [(x+dx, y+dy) for dx, dy in OFFSETS
                      if 0 <= x+dx < w and 0 <= y+dy < h and sizes[y+dy, x+dx]]
        if sizes[y, x]:
            if added or owner[y, x] != basin:
                reason = "collision"; break
            attached = True
            last = (x, y)
            continue
        if added:
            if neighbours != [last] and (len(neighbours) != 1 or neighbours[0] != last):
                reason = "collision"; break
        elif neighbours:
            if len(neighbours) != 1 or owner[neighbours[0][1], neighbours[0][0]] != basin:
                reason = "collision"; break
            if not valid_attachment(neighbours[0], sizes):
                reason = "collision"; break
            attached = True
        elif not allow_root:
            reason = "missing_parent"; break
        sizes[y, x] = level
        owner[y, x] = basin
        added.append((x, y)); last = (x, y)
    if len(added) < min_pixels:
        for x, y in added:
            sizes[y, x] = 0; owner[y, x] = 0
        return [], attached, "subpixel_or_short" if reason == "complete" else reason, consumed
    return added, attached, reason, consumed


def snap_junction(path, sizes, owner, water, basin, radius):
    """Find a single-contact confluence near the geographic join, within one basin.

    A raster stair-step can put the first tributary pixel against two mainstem
    pixels. Route around that tiny corner rather than discarding the tributary.
    The search cannot pass water, other rivers, or move the join beyond radius.
    """
    if len(path) < 3 or radius <= 0:
        return path, False
    h, w = sizes.shape
    origin = path[0]
    anchor_index = 0
    for i, (px, py) in enumerate(path[1:], 1):
        # Start the approach outside the confluence's contact zone, so its tail
        # cannot immediately re-touch a parallel mainstem pixel after snapping.
        if max(abs(px-origin[0]), abs(py-origin[1])) > radius+2:
            break
        anchor_index = i
    if not anchor_index:
        return path, False
    start = path[anchor_index]
    if sizes[start[1], start[0]]:
        return path, False
    queue, parents = deque([start]), {start: None}
    while queue:
        x, y = p = queue.popleft()
        contacts = [(x+dx, y+dy) for dx, dy in OFFSETS if
            0 <= x+dx < w and 0 <= y+dy < h and sizes[y+dy, x+dx]]
        if contacts:
            if (len(contacts) == 1 and owner[contacts[0][1], contacts[0][0]] == basin
                and valid_attachment(contacts[0], sizes)
                and max(abs(contacts[0][0]-origin[0]), abs(contacts[0][1]-origin[1])) <= radius):
                prefix = [contacts[0], p]
                while parents[p] is not None:
                    p = parents[p]; prefix.append(p)
                replacement = erase_raster_loops(prefix + path[anchor_index+1:])
                return replacement, replacement != path
            continue
        for dx, dy in OFFSETS:
            nx, ny = n = (x+dx, y+dy)
            if not (0 <= nx < w and 0 <= ny < h) or n in parents:
                continue
            if max(abs(nx-origin[0]), abs(ny-origin[1])) > radius+4:
                continue
            if water[ny, nx] or sizes[ny, nx]:
                continue
            parents[n] = (x, y); queue.append(n)
    return path, False


def route_branch(path, sizes, owner, water, basin, allow_root, min_pixels, radius):
    """Keep the original confluence whenever it works; snap only on failure."""
    original = route_run(path, sizes, owner, basin, 1, allow_root, min_pixels)
    if allow_root or original[2] not in ("collision", "missing_parent"):
        return (*original, False)
    best_path, best_length, best_snapped = path, len(original[0]), False
    for x, y in original[0]: sizes[y, x] = 0; owner[y, x] = 0
    for attempt in sorted({min(3, radius), min(6, radius), radius}):
        candidate, snapped = snap_junction(path, sizes, owner, water, basin, attempt)
        if not snapped: continue
        result = route_run(candidate, sizes, owner, basin, 1, False, min_pixels)
        if result[2] == "complete":
            return (*result, True)
        if len(result[0]) > best_length:
            best_path, best_length, best_snapped = candidate, len(result[0]), True
        for x, y in result[0]: sizes[y, x] = 0; owner[y, x] = 0
    return (*route_run(best_path, sizes, owner, basin, 1, False, min_pixels), best_snapped)


def prepare_surface(raw, width, height):
    inv = read_zone_inventory(raw)
    lookup = np.zeros(1 << 24, dtype=np.uint16)
    for i, row in enumerate(inv.itertuples()):
        lookup[int(row.map_color_rgb, 16)] = i+1
    source = Image.open(raw/"locations.png").convert("RGB")
    if source.size != (width, height):
        raise ValueError("Location and river map dimensions differ")
    zone_ids = np.zeros((height, width), np.uint16)
    for y in range(0, height, 128):
        rgb = np.asarray(source.crop((0, y, width, min(y+128, height))), dtype=np.uint32)
        zone_ids[y:y+128] = lookup[(rgb[:, :, 0] << 16)+(rgb[:, :, 1] << 8)+rgb[:, :, 2]]
    water_zone = np.r_[True, inv.game_zone_class.str.contains("sea_zones|lakes").to_numpy()]
    water = water_zone[zone_ids]
    return inv, zone_ids, water


def routing_mask(inv, zones, water, ownable_only):
    """Exclude game-ineligible zones without reclassifying land as ocean."""
    if not ownable_only: return water.copy()
    ownable = np.r_[False, inv.is_ownable.to_numpy(dtype=bool)]
    return water | ~ownable[zones]


def split_visible_runs(path, blocked):
    """Clip before routing so each surviving piece can receive valid markers."""
    runs, run = [], []
    for x, y in path:
        if blocked[y, x]:
            if run: runs.append(run); run = []
        else:
            run.append((x, y))
    if run: runs.append(run)
    return runs


def location_audit(inv, zones, sizes, markers, output):
    intended = np.zeros(len(inv)+1, np.uint8)
    native = intended.copy()
    junctions = np.zeros(len(inv)+1, np.int64)
    for y in range(0, zones.shape[0], 128):
        z, s, m = zones[y:y+128].ravel(), sizes[y:y+128].ravel(), markers[y:y+128].ravel()
        np.maximum.at(intended, z, s)
        np.maximum.at(native, z, np.where(m == 1, 5, s))
        np.add.at(junctions, z[m == 1], 1)
    result = inv.copy()
    result["intended_river_level"] = intended[1:]
    result["marker_aware_predicted_level"] = native[1:]
    result["junction_pixels"] = junctions[1:]
    result["junction_promotes_to_level_5"] = (native[1:] > intended[1:])
    result.to_csv(output/"location_levels.csv", index=False)
    return {"locations": len(inv), "locations_with_river": int((intended[1:] > 0).sum()),
            "junction_promoted_locations": int((native[1:] > intended[1:]).sum()),
            "level_counts_intended": {str(i): int((intended[1:] == i).sum()) for i in range(6)},
            "note": "Marker-aware prediction, not a new engine export. Source pixels retain their intended size here; rare endpoint cases can differ in the engine."}


def preview(sizes, water, markers, output):
    # Max pooling preserves thin rivers in the full-world preview.
    h, w = sizes.shape
    step = 4
    hh, ww = h//step, w//step
    sm = sizes[:hh*step, :ww*step].reshape(hh, step, ww, step).max(axis=(1, 3))
    wet = water[:hh*step, :ww*step].reshape(hh, step, ww, step).mean(axis=(1, 3)) > .5
    palette = np.array([[29, 39, 44], [139, 207, 228], [79, 174, 212], [48, 133, 214], [114, 104, 235], [232, 193, 84]], np.uint8)
    rgb = palette[sm]; rgb[(sm == 0) & wet] = [12, 24, 37]
    Image.fromarray(rgb).save(output/"eu5_preview.png")
    promoted = (markers[:hh*step, :ww*step] == 1).reshape(hh, step, ww, step).max(axis=(1, 3))
    rgb[promoted] = [255, 91, 73]
    Image.fromarray(rgb).save(output/"junction_preview.png")


def export(config):
    network, output, raw = Path(config["network"]), Path(config["output"]), Path(config["raw_map_inputs"])
    output.mkdir(parents=True, exist_ok=True)
    code_fingerprints = {str(p): digest(p) for p in [Path(__file__),
        Path(__file__).with_name("river_network.py"), Path(__file__).with_name("river_preview.py")]}
    upstream = verify(network)
    cfg = config["export"]
    if cfg["junction_policy"] != "native_markers_with_promotion_audit":
        raise ValueError("Only the audited native-junction policy is implemented; suppressing markers breaks connectivity")
    palette_indices = cfg["level_palette_indices"]
    known = {3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 2, 9: 3, 10: 3, 11: 3, 12: 4, 13: 4, 14: 4, 15: 5}
    if len(palette_indices) != 5 or any(known.get(v) != i+1 for i, v in enumerate(palette_indices)):
        raise ValueError("Palette indices do not represent the five verified engine levels")
    paths = tomllib.loads(Path(config["local_config"]).read_text())["paths"]
    native_path = Path(paths["game_root"])/"game/in_game/map_data/rivers.png"
    native = Image.open(native_path)
    if native.mode != "P":
        raise ValueError("Expected indexed native rivers bitmap")
    width, height = native.size
    palette = native.getpalette()
    transform = json.loads((raw/"transform.json").read_text())
    project = Projection(transform, width, height)
    print("Loading geographic network and selecting downstream-complete reaches", flush=True)
    a = pq.read_table(network, columns=["reach_id", "downstream_reach_id", "q_mean_m3_s"])
    ids = a["reach_id"].to_numpy()
    import pyarrow.compute as pc
    dst = pc.fill_null(a["downstream_reach_id"], 0).to_numpy()
    q = a["q_mean_m3_s"].to_numpy()
    down = downstream_indices(ids, dst)
    selected, closure = select_with_closure(q, down, cfg["minimum_mean_discharge_m3_s"])
    selection = np.flatnonzero(selected)
    remap = np.full(len(ids), -1, np.int32); remap[selection] = np.arange(len(selection))
    ds = np.where(down[selection] >= 0, remap[np.maximum(down[selection], 0)], -1)
    ids, q = ids[selection], q[selection]
    del a, dst, down, remap
    # Row-order-preserving batch selection avoids a huge Python ID filter list.
    tables, offset = [], 0
    for batch in pq.ParquetFile(network).iter_batches(batch_size=100_000, columns=["geometry", "continent_code"]):
        t = pa.Table.from_batches([batch])
        tables.append(t.filter(pa.array(selected[offset:offset+len(t)])))
        offset += len(t)
    g = pa.concat_tables(tables)
    geometries = shapely.from_wkb(g["geometry"].to_pylist())
    continents = g["continent_code"].to_numpy()
    del tables, g, selected, selection
    from .river_preview import build as source_preview
    source_preview(network, output/"geographic_preview.png",
        config["geographic_preview_minimum_mean_discharge_m3_s"])
    print(f"Projecting {len(ids):,} reaches into a {width} × {height} bitmap", flush=True)
    inv, zones, water = prepare_surface(raw, width, height)
    blocked = routing_mask(inv, zones, water, cfg.get("ownable_locations_only", False))
    sizes = np.zeros((height, width), np.uint8)
    owner = np.zeros((height, width), np.int32)
    markers = np.full((height, width), 255, np.uint8)
    reach_levels = levels(q, cfg["level_lower_bounds_m3_s"])
    children = [[] for _ in ids]
    for i, d in enumerate(ds):
        if d >= 0: children[d].append(i)
    main = np.full(len(ids), -1, np.int32)
    for i, c in enumerate(children):
        if c: main[i] = max(c, key=lambda j: (q[j], -int(ids[j])))
    roots = np.flatnonzero(ds < 0)
    heap = [(-float(q[r]), int(r), int(r)+1, True) for r in roots]
    heapq.heapify(heap)
    ledger = []
    root_sources = []
    root_outlets = []
    counters = Counter()
    visited = np.zeros(len(ids), bool)
    reach_branch = np.zeros(len(ids), np.int64)
    while heap:
        _, first, basin, is_root = heapq.heappop(heap)
        chain, coordinates, vertex_levels = [], [], []
        i = first
        while i >= 0:
            chain.append(i); visited[i] = True
            reach_branch[i] = ids[first]
            xy = np.asarray(geometries[i].coords)[::-1]
            coordinates.extend(xy)
            vertex_levels.extend([int(reach_levels[i])] * len(xy))
            for child in children[i]:
                if child != main[i]:
                    heapq.heappush(heap, (-float(q[child]), child, basin, False))
            i = int(main[i])
        projected = project.project(np.asarray(coordinates))
        # Rasterize each constant-class run separately, retaining mainstem class
        # changes. Pixel levels are then sampled from projected source vertices.
        from scipy.spatial import cKDTree
        finite = np.isfinite(projected).all(axis=1)
        tree = cKDTree(projected[finite]) if finite.any() else None
        vertex_levels = np.asarray(vertex_levels, np.uint8)[finite]
        added_total = visible = clipped_water = clipped_unownable = 0
        reasons = Counter()
        for path in lattice_path(projected, width, height):
            clean = erase_raster_loops(path)
            counters["self_touch_pixels_generalized"] += len(path)-len(clean)
            # Clip excluded zones before routing, never erase an encoded PNG:
            # each surviving fragment needs its own valid source/join structure.
            runs = split_visible_runs(clean, blocked)
            for x, y in clean:
                clipped_water += int(water[y, x])
                clipped_unownable += int(blocked[y, x] and not water[y, x])
            for j, run in enumerate(runs):
                visible += len(run)
                root_allowed = is_root or j > 0 or run[0] != clean[0]
                added, attached, reason, consumed, snapped = route_branch(run, sizes, owner, blocked, basin,
                    root_allowed, cfg["minimum_visible_branch_pixels"], cfg["junction_snap_radius_pixels"])
                counters["snapped_junctions"] += int(snapped)
                if added:
                    xy = np.asarray(added)
                    _, nearest = tree.query(xy)
                    sizes[xy[:, 1], xy[:, 0]] = vertex_levels[nearest]
                    if attached:
                        mx, my = added[0]
                        markers[my, mx] = 1
                    if not attached:
                        root_sources.append(added[-1]); root_outlets.append(added[0])
                added_total += len(added)
                reasons[reason] += 1
                if reason == "collision": counters["collision_omitted_pixels"] += len(run)-len(added)
        counters.update(reasons)
        ledger.append({"branch_id": int(ids[first]), "basin_terminal_reach_id": int(ids[basin-1]),
            "continent": str(continents[first]), "source_reaches": len(chain),
            "source_mean_discharge_m3_s": float(q[first]), "source_is_terminal_branch": is_root,
            "projected_land_pixels": visible, "drawn_pixels": added_total,
            "projected_water_pixels": clipped_water, "projected_unownable_land_pixels": clipped_unownable, "outcome": "drawn" if added_total else "not_drawn",
            "routing_notes": ";".join(sorted(reasons)) or "outside_projection"})
        if len(ledger) % 5000 == 0:
            print(f"  {len(ledger):,} branches routed", flush=True)
    if not visited.all(): raise AssertionError("Selected reaches missing from the export ledger")
    del owner
    # Keep junction centres ordinary width pixels. Tributary endpoints were
    # marked during routing, one pixel before each receiving mainstem.
    degree = np.zeros_like(sizes)
    degree[1:] += sizes[:-1] > 0; degree[:-1] += sizes[1:] > 0
    degree[:, 1:] += sizes[:, :-1] > 0; degree[:, :-1] += sizes[:, 1:] > 0
    junction = (sizes > 0) & (degree >= 3)
    from scipy.ndimage import label
    # Count components and confirm one green source per tree. Large temporary
    # labels are released before encoding the bitmap.
    labels, components = label(sizes > 0)
    endpoint_y, endpoint_x = np.where((sizes > 0) & (degree == 1))
    endpoint_components = labels[endpoint_y, endpoint_x]
    # Snapping can extend a mainstem's former headwater pixel. Move its green
    # marker to a remaining upstream leaf; never put a source at the outlet.
    # Component outlets were recorded while drawing downstream-first.
    for (x, y), outlet in zip(root_sources, root_outlets):
        component = labels[y, x]
        candidates = np.flatnonzero(endpoint_components == component)
        candidates = [i for i in candidates if (endpoint_x[i], endpoint_y[i]) != outlet]
        if not candidates: raise ValueError("River component has no non-outlet endpoint")
        i = min(candidates, key=lambda i: (endpoint_x[i]-x)**2+(endpoint_y[i]-y)**2)
        nx, ny = int(endpoint_x[i]), int(endpoint_y[i])
        markers[ny, nx] = 0
        counters["source_pixels_relocated_after_snapping"] += int((nx, ny) != (x, y))
    green_counts = np.bincount(labels[markers == 0], minlength=components+1)[1:]
    vertices = int((sizes > 0).sum())
    edges = int(degree[sizes > 0].astype(np.int64).sum()//2)
    forest_ok = edges == vertices-components
    sources_ok = bool(np.all(green_counts == 1))
    del labels, degree
    if not forest_ok or not sources_ok:
        raise ValueError(f"Native topology gate failed: forest={forest_ok}, one source/component={sources_ok}")
    native_pixels = np.where(water, 254, 255).astype(np.uint8)
    for i, entry in enumerate(palette_indices, 1): native_pixels[sizes == i] = entry
    native_pixels[markers == 0] = 0
    native_pixels[markers == 1] = 1
    excluded_river_pixels = int(np.count_nonzero((native_pixels < 16) & blocked))
    if excluded_river_pixels: raise ValueError("River pixels escaped the routing eligibility mask")
    native_checks = validate_native_rivers(native_pixels)
    native_checks["excluded_zone_river_pixels"] = excluded_river_pixels
    image = Image.frombytes("P", (width, height), native_pixels.tobytes())
    image.putpalette(palette)
    target = output/"mod"/"EU5 World Builder - Rivers"/"in_game"/"map_data"
    target.mkdir(parents=True, exist_ok=True)
    image.save(target/"rivers.png", optimize=False)
    metadata = target.parent.parent/".metadata"/"metadata.json"
    save_json(metadata, {"name": "EU5 World Builder - Rivers", "id": "river_network_prototype",
        "version": "0.1.0", "supported_game_version": "1.3.*",
        "short_description": "Independent hydrographic network mapped to EU5; junction promotions audited."})
    # Re-open to ensure saving preserved exact indices, dimensions and palette.
    reopened = Image.open(target/"rivers.png")
    if reopened.mode != "P" or reopened.getpalette() != palette or not np.array_equal(np.asarray(reopened), native_pixels):
        raise AssertionError("Indexed river PNG did not round-trip")
    del native_pixels
    loc = location_audit(inv, zones, sizes, markers, output)
    preview(sizes, water, markers, output)
    ledger = pd.DataFrame(ledger)
    ledger.to_csv(output/"export_branches.csv", index=False)
    pd.DataFrame({"reach_id": ids, "branch_id": reach_branch,
        "downstream_reach_id": np.where(ds >= 0, ids[np.maximum(ds, 0)], 0),
        "mean_discharge_m3_s": q, "intended_size_class": reach_levels,
        "source_tile": continents}).to_parquet(output/"export_reaches.parquet", index=False)
    continent = ledger.groupby("continent").agg(branches=("branch_id", "size"),
        source_reaches=("source_reaches", "sum"), drawn_pixels=("drawn_pixels", "sum"),
        branches_drawn=("drawn_pixels", lambda x: int((x > 0).sum())))
    continent.to_csv(output/"coverage_by_continent.csv")
    inputs = {str(p): digest(p) for p in [network, raw/"transform.json", raw/"locations.png",
        raw/"game_default.map", raw/"game_templates.txt", raw/"game_named_locations.txt", native_path]}
    report = {"source_reaches": upstream["reaches"], "selected_reaches": len(ids),
        "downstream_closure_reaches": closure, "branches": len(ledger),
        "branches_with_visible_pixels": int((ledger.drawn_pixels > 0).sum()),
        "branches_without_visible_pixels": int((ledger.drawn_pixels == 0).sum()),
        "projection_bounds": {"longitude": [project.lon0, project.longitude(width-1)],
            "latitude": [float(project.lats[-1]), float(project.lats[0])]},
        "river_pixels": vertices, "components": int(components), "junction_pixels": int((markers == 1).sum()),
        "native_encoding_audit": native_checks,
        "routing": dict(counters), "location_audit": loc,
        "engineering_checks": {"every_selected_reach_accounted_for": bool(visited.all()),
            "acyclic_four_connected_raster": forest_ok, "one_source_per_component": sources_ok,
            "indexed_png_roundtrip": True, "native_tributary_encoding": True},
        "config": config, "input_sha256": inputs,
        "code_sha256": code_fingerprints,
        "output_png": str(target/"rivers.png"), "output_sha256": digest(target/"rivers.png"),
        "status": "Global prototype exported; not yet verified by loading this new bitmap in EU5",
        "limits": ["No discharge classification has been calibrated as historical navigability",
            "Modern source hydrography is an approximation to 1300, especially for changing deltas and altered channels",
            "Separable game-map registration is approximate. Water clipping and raster collision omissions are recorded per branch",
            "Geographic source extends beyond the game map's latitude coverage",
            "Native red junction markers force level 5 in affected locations; intended sizes remain separate",
            "Unownable land is clipped only in the game export; rivers crossing it become disconnected visible components",
            "RiverATLAS is a downstream tree; distributaries and their yellow markers are not invented"]}
    save_json(output/"export_manifest.json", report)
    write_html(output, report)
    return report


def write_html(output, report):
    n = report["location_audit"]["junction_promoted_locations"]
    output.joinpath("index.html").write_text('''<!doctype html><meta charset="utf-8">
<title>River network — source and EU5 export</title><style>
body{background:#0c1825;color:#e0eaf3;font:16px system-ui;margin:24px auto;max-width:1500px}a{color:#87d3ff}
button{padding:10px;background:#20394b;color:white;border:1px solid #678;margin-right:8px;cursor:pointer}
#view{height:70vh;overflow:auto;border:1px solid #456;margin-top:15px}img{width:100%;display:block}small{color:#b5c5d1}
</style><h1>One geographic network, separate game mapping</h1>
<p>The source preserves actual downstream links and discharge. The EU5 exporter chooses detail, levels and connections.</p>
<button onclick="show('geographic_preview.png')">Geographic source</button>
<button onclick="show('eu5_preview.png')">EU5 intended sizes</button>
<button onclick="show('junction_preview.png')">EU5 junctions in red</button>
<button onclick="zoom()">Toggle full resolution</button><div id="view"><img id="map" src="geographic_preview.png"></div>
<p>EU5 sizes: 1 pale blue · 2 cyan · 3 blue · 4 violet · 5 gold. Geographic source uses continuous mean discharge.</p>
<p>''' + f'{report["source_reaches"]:,} source reaches · {report["selected_reaches"]:,} selected for export · {n:,} locations promoted to level 5 by junction markers.' + '''</p>
<p><b>Prototype:</b> modern hydrography and approximate game-map registration. This bitmap has not yet been loaded and exported from EU5.</p>
<p><a href="export_manifest.json">Export audit</a> · <a href="export_branches.csv">Every selected branch</a> ·
<a href="location_levels.csv">Intended vs marker-aware location levels</a> · <a href="coverage_by_continent.csv">Coverage</a> ·
<a href="mod/EU5%20World%20Builder%20-%20Rivers/in_game/map_data/rivers.png">Indexed EU5 PNG</a></p>
<script>function show(p){document.getElementById('map').src=p}function zoom(){let m=document.getElementById('map');m.style.width=m.style.width==='auto'?'100%':'auto'}</script>''')
