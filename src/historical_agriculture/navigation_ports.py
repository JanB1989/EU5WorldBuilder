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
        return round(min(s['harbor_max'], value + s['harbor_rank_bonus'].get(ranks.get(name), 0.0)), 2)
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
