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
