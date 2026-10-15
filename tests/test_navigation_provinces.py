from historical_agriculture.navigation_map import river_provinces


def _chain(n, river, start=0, near='bank'):
    return [{'location': f't{start + i:03d}', 'river': river, 'near_location': near} for i in range(n)]


def test_one_river_per_province_cut_from_the_mouth_into_connected_stretches():
    # river A: a 20-tile chain from the sea; river B: 5 tiles joining A at t010 (a confluence, not the same river)
    rows = _chain(20, 'River A') + _chain(5, 'River B', start=100)
    nb = {}
    for i in range(19):
        nb.setdefault(f't{i:03d}', set()).add(f't{i + 1:03d}'); nb.setdefault(f't{i + 1:03d}', set()).add(f't{i:03d}')
    for i in range(100, 104):
        nb.setdefault(f't{i:03d}', set()).add(f't{i + 1:03d}'); nb.setdefault(f't{i + 1:03d}', set()).add(f't{i:03d}')
    nb['t100'].add('t010'); nb['t010'].add('t100')
    nb['t000'].add('sea')
    areas = river_provinces(rows, nb, {'sea'})
    assert set(areas) == {'pp_nav_river_a_area', 'pp_nav_river_b_area'}
    a = areas['pp_nav_river_a_area']
    assert [len(tags) for _, tags in a] == [8, 8, 4]
    assert a[0][1][0] == 't000'                                   # the first stretch starts at the mouth
    assert [len(tags) for _, tags in areas['pp_nav_river_b_area']] == [5]
    for row in rows:                                               # every tile annotated, never mixed rivers
        assert row['area'].startswith('pp_nav_river_' + row['river'][-1].lower())


def test_a_short_leftover_joins_a_touching_stretch_of_the_same_river():
    rows = _chain(9, 'Short')
    nb = {}
    for i in range(8):
        nb.setdefault(f't{i:03d}', set()).add(f't{i + 1:03d}'); nb.setdefault(f't{i + 1:03d}', set()).add(f't{i:03d}')
    nb['t000'].add('sea')
    areas = river_provinces(rows, nb, {'sea'})
    assert [len(tags) for _, tags in areas['pp_nav_short_area']] == [9]


def test_a_tile_no_bank_can_serve_joins_a_touching_tile_of_its_state():
    import numpy as np
    from historical_agriculture.navigation_map import merge_portless_tiles
    # one row: bank 5 | tile a | tile b | bank 5 again | tile c (improvable) | bank 7
    flat = np.array([5, 0, 0, 0, 0, 5, 0, 7], np.uint32)
    tiles = [{"state": 1, "cells": {1, 2}, "center": [1, 2]}, {"state": 1, "cells": {3, 4}, "center": [3, 4]},
             {"state": 2, "cells": {6}, "center": [6]}]
    out, merged = merge_portless_tiles(tiles, flat, 8, {5, 7})
    assert merged == 1   # a and b share the one bank location, so they become one tile; c has its own bank
    assert sorted(sorted(g["cells"]) for g in out) == [[1, 2, 3, 4], [6]]
    # a vanilla port its sea zone cannot spare is no bank: c then has none, but no same-state tile touches it
    out, merged = merge_portless_tiles(tiles, flat, 8, {5})
    assert merged == 1 and len(out) == 2
