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


def test_a_navigable_lake_moves_from_the_lakes_to_the_sea_zones_and_into_its_rivers_area():
    import numpy as np
    import pandas as pd
    import pytest
    from historical_agriculture.navigation_map import (lake_provinces, navigable_lake_tags, remove_from_list,
                                                       remove_token, river_slug, shore_counts)
    text = 'sea_zones = {\n\tbaltic\n}\nlakes = {\n\tlake_ladoga lake_ladoga_small lake_onega\n}\n'
    out = remove_from_list(text, 'lakes', ['lake_ladoga'])
    assert 'lake_ladoga_small lake_onega' in out and ' lake_ladoga ' not in out.replace('\t', ' ')
    with pytest.raises(ValueError):
        remove_from_list(out, 'lakes', ['lake_ladoga'])
    defs = 'korela_province = { korela salmi lake_ladoga }\nother = { lake_ladoga_small }\n'
    assert remove_token(defs, 'lake_ladoga') == 'korela_province = { korela salmi  }\nother = { lake_ladoga_small }\n'
    inv = pd.DataFrame({'location_tag': ['lake_ladoga', 'baltic'], 'game_zone_class': ['lakes', 'sea_zones']})
    assert navigable_lake_tags({'navigable_lakes': ['lake_ladoga']}, inv) == ['lake_ladoga']
    with pytest.raises(ValueError):
        navigable_lake_tags({'navigable_lakes': ['baltic']}, inv)
    # 4x5 map: lake 9 in the middle, banks 1 (left) and 2 (right), channel 7 below
    after = np.array([[1, 9, 9, 2, 2], [1, 9, 9, 2, 2], [1, 7, 7, 2, 2], [1, 1, 1, 1, 1]], np.uint32)
    assert shore_counts(after, 9, {9}) == {1: 2, 2: 2, 7: 2}
    meta = [{'location': 'pp_nav_1', 'area': 'pp_nav_volkhov_area'}]
    adjacent = {7: {9, 1}}
    names = {7: 'pp_nav_1', 9: 'lake_ladoga'}
    assert lake_provinces([('lake_ladoga', 9)], meta, adjacent, names, river_slug) == \
        [('pp_nav_volkhov_area', 'pp_nav_lake_ladoga_province', 'lake_ladoga')]
    assert lake_provinces([('lake_ladoga', 9)], meta, {}, names, river_slug) == \
        [('pp_nav_lake_ladoga_area', 'pp_nav_lake_ladoga_province', 'lake_ladoga')]


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
