"""Choose which river banks become ports and give them vanilla-style natural harbors.

The navigation raster makes every bank of a navigable river tile coastal and proposes a port for each
(``river_port_locations``). Vanilla gives almost every coastal location a port, but a port on every
river bank would turn inland Europe into a coastline. This step keeps a curated share:

1. Settlements: every vanilla town, city and megalopolis (``07_cities_and_buildings``) on a passable
   river tile gets a port.
2. Coverage: along the passable water graph, each tile of a large river (``coverage_min_river_level``)
   gets a port within ``coverage_hops`` tiles, taken from the best-scoring bank.
3. The total stays within ``max_share`` of the candidates; coverage ports are dropped first.

Score: settlement rank, starting population and the discharge of the adjacent passable water; ocean
connection and navigable (not merely improvable or difficult) water add to it.

Natural harbor suitability follows vanilla, where every port carries a value, most small ports have 0
and important river ports reach 0.25-0.5 (Bremen, Nantes, Seville): a tier by the largest adjacent
discharge (``harbor_tiers``) plus a settlement bonus (``harbor_rank_bonus``), capped at ``harbor_max``.
An existing higher value is kept.
Vanilla ports, including those the raster relocated onto a river, are never removed.
"""
from collections import defaultdict, deque
import math
import re

import pandas as pd

DEFAULTS = {
    'max_share': 0.33,
    'coverage_hops': 3,
    'coverage_min_river_level': 3,
    'rank_points': {'town': 3.0, 'city': 4.0, 'megalopolis': 5.0},
    'harbor_tiers': [[10000, 0.2], [3000, 0.1], [1000, 0.05]],
    'harbor_rank_bonus': {'town': 0.1, 'city': 0.25, 'megalopolis': 0.25},
    'harbor_max': 0.5,
    # Per-port floors for river ports whose trade outgrew their discharge (Frankfurt: the fair's Main port).
    'harbor_overrides': {},
}
MAP_DATA = 'in_game/map_data/'
DOCK = 'in_game/gfx/map/map_objects/generated_map_object_locators_dock.txt'


def settlement_ranks(game):
    text = (game/'main_menu/setup/start/07_cities_and_buildings.txt').read_text(encoding='utf-8-sig')
    return {m[1]: m[2] for m in re.finditer(r'(?m)^\s*(\w+)\s*=\s*\{\s*rank\s*=\s*(\w+)', text)}


def populations(game):
    text = (game/'main_menu/setup/start/06_pops.txt').read_text(encoding='utf-8-sig')
    sizes = defaultdict(float); current = None
    for line in text.splitlines():
        head = re.match(r'^(\w+)\s*=\s*\{\s*$', line)
        if head and head[1] != 'locations': current = head[1]
        for size in re.findall(r'size\s*=\s*([\d.]+)', line):
            if current: sizes[current] += float(size)
    return sizes


def port_names(text):
    return {row.split(';')[0] for row in text.splitlines()[1:] if ';' in row}


def select(out, manifest, game, settings=None):
    """Return the chosen river ports with their harbor values and a per-candidate table."""
    s = {**DEFAULTS, **(settings or {})}
    tiles = pd.read_csv(out/'tiles.csv').set_index('location')
    shores = pd.read_csv(out/'shores.csv')
    edges = pd.read_csv(out/'edges.csv')
    vanilla = port_names((game/MAP_DATA/'ports.csv').read_text(encoding='utf-8-sig'))
    ranks, pops = settlement_ranks(game), populations(game)
    passable = set(tiles.index[tiles.state != 'barrier'])
    shores = shores[shores.water_location.isin(passable)]
    candidates = sorted(set(manifest['river_port_locations']) - vanilla)
    banks = shores[shores.location_tag.isin(candidates)].groupby('location_tag').water_location.apply(list).to_dict()
    candidates = [c for c in candidates if c in banks]

    def score(name):
        water = tiles.loc[banks[name]]
        flow = float(water.mean_discharge_m3_s.max())
        points = s['rank_points'].get(ranks.get(name), 0.0) + math.log10(1 + pops.get(name, 0.0))
        points += math.log10(1 + max(flow, 0.0)) / 2
        points += 0.5 * bool(water.ocean_connected.any()) + 0.5 * bool((water.state == 'navigable').any())
        return points
    scores = {c: score(c) for c in candidates}
    chosen = {c: 'settlement' for c in candidates if ranks.get(c) in s['rank_points']}

    graph = defaultdict(set)
    water_edges = edges[(~edges.shore) & edges['from'].isin(passable) & edges['to'].isin(passable)]
    for a, b in zip(water_edges['from'], water_edges['to']):
        graph[a].add(b); graph[b].add(a)
    by_tile = defaultdict(list)
    for name, waters in banks.items():
        for w in waters: by_tile[w].append(name)

    def covered(tile):
        seen = {tile}; frontier = deque([(tile, 0)])
        while frontier:
            node, depth = frontier.popleft()
            if any(n in chosen for n in by_tile[node]): return True
            if depth < s['coverage_hops']:
                for nxt in graph[node] - seen:
                    seen.add(nxt); frontier.append((nxt, depth + 1))
        return False
    large = tiles[(tiles.index.isin(passable)) & (tiles.river_level >= s['coverage_min_river_level'])]
    for tile in large.sort_values('mean_discharge_m3_s', ascending=False).index:
        if by_tile[tile] and not covered(tile):
            chosen[max(by_tile[tile], key=lambda n: scores[n])] = 'coverage'

    cap = int(len(candidates) * s['max_share'])
    if len(chosen) > cap:
        order = sorted(chosen, key=lambda n: (chosen[n] == 'settlement', scores[n]), reverse=True)
        chosen = {n: chosen[n] for n in order[:cap]}

    def harbor(name):
        flow = float(tiles.loc[banks[name]].mean_discharge_m3_s.max())
        value = next((value for threshold, value in s['harbor_tiers'] if flow >= threshold), 0.0)
        value = min(s['harbor_max'], value + s['harbor_rank_bonus'].get(ranks.get(name), 0.0))
        return round(max(value, s['harbor_overrides'].get(name, 0.0)), 2)
    ports = {n: harbor(n) for n in chosen}
    table = pd.DataFrame([{'location_tag': c, 'rank': ranks.get(c, ''), 'population': round(pops.get(c, 0.0), 3),
                           'max_discharge_m3_s': float(tiles.loc[banks[c]].mean_discharge_m3_s.max()),
                           'water_tiles': ';'.join(banks[c]), 'score': round(scores[c], 3),
                           'port': c in chosen, 'reason': chosen.get(c, ''), 'natural_harbor_suitability': ports.get(c, '')}
                          for c in candidates])
    return ports, table


def prune(output, ports, game, candidates):
    """Drop the emitted river ports and dock locators that were not chosen; vanilla ports stay."""
    vanilla = port_names((game/MAP_DATA/'ports.csv').read_text(encoding='utf-8-sig'))
    path = output/MAP_DATA/'ports.csv'
    rows = path.read_text(encoding='utf-8-sig').splitlines()
    dropped = {r.split(';')[0] for r in rows[1:] if ';' in r} - vanilla - set(ports)
    path.write_text('\n'.join(r for r in rows if r.split(';')[0] not in dropped) + '\n', encoding='utf-8')
    dock = output/DOCK
    if dock.is_file():
        text = dock.read_text(encoding='utf-8-sig')
        pattern = re.compile(r'\n?[ \t]*\{\s*id\s*=\s*(\w+)\s+position\s*=\s*\{[^}]*\}\s*rotation\s*=\s*\{[^}]*\}\s*scale\s*=\s*\{[^}]*\}\s*\}')
        dock.write_text(pattern.sub(lambda m: '' if m[1] in dropped else m[0], text), encoding='utf-8-sig')
    return {'candidates': candidates, 'ports': len(ports), 'dropped': len(dropped),
            'harbor_values': {f'{k:.2f}': int(v) for k, v in sorted(pd.Series(list(ports.values())).value_counts().items())}}


def _rows(text):
    return {r.split(';')[0]: r.split(';') for r in text.splitlines()[1:] if ';' in r}


def _colors(*folders):
    colors = {}
    for folder in folders:
        for path in sorted(folder.glob('*.txt')) if folder.is_dir() else []:
            # vanilla drops leading zeros (`pagan = 296a`)
            for m in re.finditer(r'(?m)^\s*(\w+)\s*=\s*([0-9a-fA-F]{1,6})\b', path.read_text(encoding='utf-8-sig')):
                colors.setdefault(m[1], int(m[2], 16))
    return colors


def restore_lone_sea_ports(output, game, window=64):
    """Re-seat a vanilla port on its own sea zone when the raster moved it onto a river tile and that sea zone
    kept no port: the engine then logs the sea zone as "breaking any maritime and control propagation".

    The port goes to the sea pixel next to the location's land that lies closest to its vanilla coordinate;
    its dock locator follows. Returns the re-seated locations."""
    import numpy as np
    from PIL import Image

    vanilla = _rows((game/MAP_DATA/'ports.csv').read_text(encoding='utf-8-sig'))
    path = output/MAP_DATA/'ports.csv'
    lines = path.read_text(encoding='utf-8-sig').splitlines()
    current = _rows('\n'.join(lines))
    seas = {row[1] for row in current.values()}
    lone = sorted(name for name, row in vanilla.items() if row[1] not in seas and name in current)
    if not lone:
        return []
    Image.MAX_IMAGE_PIXELS = None
    image = np.asarray(Image.open(output/MAP_DATA/'locations.png').convert('RGB')).astype(np.uint32)
    codes = (image[..., 0] << 16) | (image[..., 1] << 8) | image[..., 2]
    height, width = codes.shape
    colors = _colors(output/MAP_DATA/'named_locations', game/MAP_DATA/'named_locations')
    moved = {}
    for name in lone:
        sea = vanilla[name][1]
        x0, y0 = int(vanilla[name][2]), height - int(vanilla[name][3])
        top, left = max(0, y0 - window), max(0, x0 - window)
        box = codes[top:y0 + window + 1, left:x0 + window + 1]
        land = box == colors[name]
        near = np.zeros_like(land)
        near[1:] |= land[:-1]; near[:-1] |= land[1:]; near[:, 1:] |= land[:, :-1]; near[:, :-1] |= land[:, 1:]
        ys, xs = np.nonzero((box == colors[sea]) & near)
        if not len(ys):
            continue
        i = int(np.argmin((ys + top - y0) ** 2 + (xs + left - x0) ** 2))
        moved[name] = (sea, int(xs[i] + left), int(ys[i] + top))
    if not moved:
        return []
    lines = [r for r in lines if r.split(';')[0] not in moved]
    lines += [f'{name};{sea};{x};{height - y};x' for name, (sea, x, y) in sorted(moved.items())]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    dock = output/DOCK
    if dock.is_file():
        text = dock.read_text(encoding='utf-8-sig')

        def seat(m):
            if m[1] not in moved:
                return m[0]
            _, x, y = moved[m[1]]
            return re.sub(r'position\s*=\s*\{\s*\S+\s+(\S+)\s+\S+\s*\}',
                          lambda p: f'position={{ {x + .5:.6f} {p[1]} {height - y - .5:.6f} }}', m[0], count=1)
        pattern = re.compile(r'\{\s*id\s*=\s*(\w+)\s+position\s*=\s*\{[^}]*\}\s*rotation\s*=\s*\{[^}]*\}\s*scale\s*=\s*\{[^}]*\}\s*\}')
        dock.write_text(pattern.sub(seat, text), encoding='utf-8-sig')
    return sorted(moved)


def portless_banks(out, game, ports):
    """Land locations next to a passable navigation tile (engine-coastal: the tile is `narrows`, not
    `ocean_wasteland`) that get neither a vanilla nor a chosen river port."""
    tiles = pd.read_csv(out/'tiles.csv').set_index('location')
    passable = set(tiles.index[tiles.state != 'barrier'])
    shores = pd.read_csv(out/'shores.csv')
    banks = set(shores.location_tag[shores.water_location.isin(passable)])
    vanilla = port_names((game/MAP_DATA/'ports.csv').read_text(encoding='utf-8-sig'))
    return banks - vanilla - set(ports)


def _border_pixels(codes, land_colors, water_colors):
    """(land color, water color) -> water-side pixels (x, row) that touch the land location."""
    import numpy as np

    land_set = np.array(sorted(land_colors), dtype=np.uint32)
    water_set = np.array(sorted(water_colors), dtype=np.uint32)
    pairs = {}
    for axis in (0, 1):
        a = codes[:-1, :] if axis == 0 else codes[:, :-1]
        b = codes[1:, :] if axis == 0 else codes[:, 1:]
        ys, xs = np.nonzero(a != b)
        va, vb = a[ys, xs], b[ys, xs]
        for land, water, dy, dx in ((va, vb, 1, 0), (vb, va, 0, 0)):
            keep = np.isin(land, land_set) & np.isin(water, water_set)
            wy = ys[keep] + (dy if axis == 0 else 0)
            wx = xs[keep] + (dy if axis == 1 else 0)
            for key, x, y in zip(zip(land[keep].tolist(), water[keep].tolist()), wx.tolist(), wy.tolist()):
                pairs.setdefault(key, []).append((x, y))
    return pairs


def assign_bank_ports(output, game, out):
    """Give every bank of a passable navigation tile a port, placed so that as many tiles as possible get one.

    The engine treats land next to a passable (`narrows`) tile as coastal and logs every coastal location without
    a port and every tile without one. Each location can hold one port, so banks are matched to tiles
    (augmenting paths over the bank-tile graph, starting from the emitted port tiles); banks left over keep their
    emitted tile. Vanilla ports stay where they are. Returns counts, including the tiles no bank can serve."""
    import numpy as np
    from PIL import Image

    tiles = pd.read_csv(out/'tiles.csv').set_index('location')
    passable = set(tiles.index[tiles.state != 'barrier'])
    shores = pd.read_csv(out/'shores.csv')
    shores = shores[shores.water_location.isin(passable)]
    vanilla = port_names((game/MAP_DATA/'ports.csv').read_text(encoding='utf-8-sig'))
    path = output/MAP_DATA/'ports.csv'
    lines = path.read_text(encoding='utf-8-sig').splitlines()
    rows = _rows('\n'.join(lines))
    fixed_seas = {row[1] for name, row in rows.items() if name in vanilla}
    banks = sorted(set(shores.location_tag) - vanilla)
    adjacent = shores[shores.location_tag.isin(banks)].groupby('location_tag').water_location.apply(list).to_dict()
    open_tiles = {w for ws in adjacent.values() for w in ws} - fixed_seas

    # Kuhn's matching, tiles -> banks, seeded with the emitted port tiles.
    bank_of, tile_of = {}, {}
    for bank in banks:
        tile = rows.get(bank, [None, None])[1]
        if tile in open_tiles and tile in adjacent.get(bank, []) and tile not in bank_of:
            bank_of[tile], tile_of[bank] = bank, tile
    by_tile = shores[shores.location_tag.isin(banks)].groupby('water_location').location_tag.apply(list).to_dict()

    def augment(tile, seen):
        for bank in by_tile.get(tile, []):
            if bank in seen:
                continue
            seen.add(bank)
            if bank not in tile_of or augment(tile_of[bank], seen):
                if bank in tile_of:
                    del bank_of[tile_of[bank]]
                bank_of[tile], tile_of[bank] = bank, tile
                return True
        return False

    import sys
    sys.setrecursionlimit(max(10000, sys.getrecursionlimit()))
    for tile in sorted(open_tiles - set(bank_of)):
        augment(tile, set())
    wanted = {}
    for bank in banks:
        tile = tile_of.get(bank)
        if tile is None:
            emitted = rows.get(bank, [None, None])[1]
            tile = emitted if emitted in adjacent.get(bank, []) else max(
                adjacent[bank], key=lambda w: int(shores[(shores.location_tag == bank) & (shores.water_location == w)].shore_pixels.sum()))
        wanted[bank] = tile

    # Coordinates: keep an emitted row that already sits on the wanted tile, else the border pixel nearest the
    # middle of the bank's shore on that tile.
    need = {bank: tile for bank, tile in wanted.items() if rows.get(bank, [None, None])[1] != tile}
    Image.MAX_IMAGE_PIXELS = None
    image = np.asarray(Image.open(output/MAP_DATA/'locations.png').convert('RGB')).astype(np.uint32)
    codes = (image[..., 0] << 16) | (image[..., 1] << 8) | image[..., 2]
    del image
    height = codes.shape[0]
    colors = _colors(output/MAP_DATA/'named_locations', game/MAP_DATA/'named_locations')
    border = _border_pixels(codes, {colors[b] for b in need}, {colors[t] for t in need.values()}) if need else {}
    placed = {}
    for bank, tile in need.items():
        points = border.get((colors[bank], colors[tile]))
        if not points:
            continue
        xy = np.array(points)
        x, y = map(int, xy[int(np.argmin(((xy - xy.mean(axis=0)) ** 2).sum(axis=1)))])
        placed[bank] = (tile, x, y)
    lines = [r for r in lines if r.split(';')[0] not in placed]
    lines += [f'{bank};{tile};{x};{height - y};x' for bank, (tile, x, y) in sorted(placed.items())]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    dock = output/DOCK
    if dock.is_file() and placed:
        text = dock.read_text(encoding='utf-8-sig')
        pattern = re.compile(r'\{\s*id\s*=\s*(\w+)\s+position\s*=\s*\{[^}]*\}\s*rotation\s*=\s*\{[^}]*\}\s*scale\s*=\s*\{[^}]*\}\s*\}')
        seen = set()

        def seat(m):
            if m[1] not in placed:
                return m[0]
            seen.add(m[1])
            _, x, y = placed[m[1]]
            return re.sub(r'position\s*=\s*\{[^}]*\}', f'position={{ {x + .5} 0 {height - y - .5} }}', m[0], count=1)
        text = pattern.sub(seat, text)
        added = ''.join(f'\n {{ id={n} position={{ {x + .5} 0 {height - y - .5} }} rotation={{ 0 0 0 1 }} scale={{ 1 1 1 }} }}'
                        for n, (_, x, y) in sorted(placed.items()) if n not in seen)
        close = text.rfind('}', 0, text.rfind('}'))
        dock.write_text(text[:close] + added + '\n' + text[close:], encoding='utf-8-sig')

    final = _rows('\n'.join(lines))
    served = {row[1] for row in final.values()}
    land_touching = set(shores.water_location)
    return {'bank_ports': len(banks), 'moved_or_added': len(placed), 'unplaced': sorted(set(need) - set(placed)),
            'tiles_without_port': len(land_touching - served)}
