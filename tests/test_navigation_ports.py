import pandas as pd

from historical_agriculture.navigation_ports import select, prune


def _game(tmp_path):
    start = tmp_path/'game/main_menu/setup/start'; start.mkdir(parents=True)
    (start/'07_cities_and_buildings.txt').write_text('\tbigtown = { rank = city town_setup = x }\n')
    (start/'06_pops.txt').write_text('locations={\nbigtown = {\n\tdefine_pop = { type = peasants size = 10.0 }\n}\nhamlet = {\n\tdefine_pop = { type = peasants size = 1.0 }\n}\n}\n')
    md = tmp_path/'game/in_game/map_data'; md.mkdir(parents=True)
    (md/'ports.csv').write_text('LandProvince;SeaZone;x;y;\nseaport;ocean;1;1;x\n')
    return tmp_path/'game'


def _out(tmp_path):
    out = tmp_path/'nav'; out.mkdir()
    pd.DataFrame([
        {'location': 'w1', 'state': 'navigable', 'mean_discharge_m3_s': 12000, 'river_level': 5, 'ocean_connected': True},
        {'location': 'w2', 'state': 'navigable', 'mean_discharge_m3_s': 500, 'river_level': 3, 'ocean_connected': True},
        {'location': 'w3', 'state': 'barrier', 'mean_discharge_m3_s': 500, 'river_level': 3, 'ocean_connected': False},
    ]).to_csv(out/'tiles.csv', index=False)
    pd.DataFrame([
        {'location_tag': 'bigtown', 'water_location': 'w1', 'state': 'navigable', 'shore_pixels': 9},
        {'location_tag': 'hamlet', 'water_location': 'w2', 'state': 'navigable', 'shore_pixels': 9},
        {'location_tag': 'farm', 'water_location': 'w2', 'state': 'navigable', 'shore_pixels': 3},
        {'location_tag': 'cliff', 'water_location': 'w3', 'state': 'barrier', 'shore_pixels': 3},
        {'location_tag': 'seaport', 'water_location': 'w1', 'state': 'navigable', 'shore_pixels': 3},
    ]).to_csv(out/'shores.csv', index=False)
    pd.DataFrame([{'from': 'w1', 'to': 'w2', 'state': 'navigable', 'cost_profile': 'navigable', 'shore': False}]).to_csv(out/'edges.csv', index=False)
    return out


def test_settlements_and_coverage_get_ports_with_vanilla_style_harbors(tmp_path):
    game, out = _game(tmp_path), _out(tmp_path)
    manifest = {'river_port_locations': ['bigtown', 'hamlet', 'farm', 'cliff', 'seaport']}
    ports, table = select(out, manifest, game, {'coverage_hops': 0, 'max_share': 1.0})
    # the city is a settlement port; w2 needs coverage and takes its better bank; barrier banks and vanilla ports are not candidates
    assert ports == {'bigtown': 0.45, 'hamlet': 0.0}
    assert set(table.location_tag) == {'bigtown', 'hamlet', 'farm'}
    capped, _ = select(out, manifest, game, {'coverage_hops': 0, 'max_share': 0.34})
    assert capped == {'bigtown': 0.45}


def test_prune_keeps_vanilla_and_chosen_ports(tmp_path):
    game = _game(tmp_path)
    md = tmp_path/'mod/in_game/map_data'; md.mkdir(parents=True)
    (md/'ports.csv').write_text('LandProvince;SeaZone;x;y;\nseaport;ocean;1;1;x\nbigtown;w1;2;2;x\nfarm;w2;3;3;x\n')
    stats = prune(tmp_path/'mod', {'bigtown': 0.45}, game, 3)
    assert (md/'ports.csv').read_text().splitlines()[1:] == ['seaport;ocean;1;1;x', 'bigtown;w1;2;2;x']
    assert stats['dropped'] == 1


def test_a_sea_zone_left_without_its_only_vanilla_port_gets_it_back(tmp_path):
    import numpy as np
    from PIL import Image

    from historical_agriculture.navigation_ports import restore_lone_sea_ports, DOCK

    game = tmp_path/'game'; (game/'in_game/map_data/named_locations').mkdir(parents=True)
    out = tmp_path/'out'; (out/'in_game/map_data/named_locations').mkdir(parents=True)
    (game/'in_game/map_data/named_locations/00.txt').write_text('town = 0000ff\nbay = 00ff00\nother = 0000aa\nsound = 00aa00\n')
    (out/'in_game/map_data/named_locations/pp.txt').write_text('pp_nav_1 = ff0000\n')
    # 6x6 map: town in the middle columns, the bay on the right, the river tile painted over the old port pixel
    grid = np.full((6, 6, 3), 0, np.uint8); grid[:, :] = (0, 0, 0xaa)
    grid[:, 2:4] = (0, 0, 0xff); grid[:, 4:] = (0, 0xff, 0); grid[1:3, 4] = (0xff, 0, 0)
    Image.fromarray(grid).save(out/'in_game/map_data/locations.png')
    (game/'in_game/map_data/ports.csv').write_text('LandProvince;SeaZone;x;y;\ntown;bay;4;4;x\nother;sound;0;0;x\n')
    (out/'in_game/map_data/ports.csv').write_text('LandProvince;SeaZone;x;y;\nother;sound;0;0;x\ntown;pp_nav_1;4;4;x\n')
    (out/DOCK).parent.mkdir(parents=True)
    (out/DOCK).write_text('instances={\n\t{\n\t\tid=town\n\t\tposition={ 4.5 1.2 3.5 }\n\t\trotation={ 0 0 0 1 }\n\t\tscale={ 1 1 1 }\n\t}\n}\n')

    assert restore_lone_sea_ports(out, game) == ['town']
    rows = (out/'in_game/map_data/ports.csv').read_text().splitlines()
    assert rows[1:] == ['other;sound;0;0;x', 'town;bay;4;3;x']   # nearest bay pixel next to the town, bottom-up y
    assert 'position={ 4.500000 1.2 2.500000 }' in (out/DOCK).read_text(encoding='utf-8-sig')
    assert restore_lone_sea_ports(out, game) == []


def test_portless_banks_of_passable_tiles_are_listed_for_a_zero_harbor(tmp_path):
    from historical_agriculture.navigation_ports import portless_banks

    game, out = _game(tmp_path), _out(tmp_path)
    # seaport keeps its vanilla port, bigtown gets a river port, cliff only borders a barrier (not coastal)
    assert portless_banks(out, game, {'bigtown': 0.45}) == {'hamlet', 'farm'}


def test_every_bank_gets_a_port_and_the_tiles_are_covered_as_far_as_possible(tmp_path):
    import numpy as np
    from PIL import Image

    from historical_agriculture.navigation_ports import assign_bank_ports, DOCK

    game = tmp_path/'game'; (game/'in_game/map_data/named_locations').mkdir(parents=True)
    (game/'in_game/map_data/named_locations/00.txt').write_text('a = 0000a0\nb = 0000b0\n')
    (game/'in_game/map_data/ports.csv').write_text('LandProvince;SeaZone;x;y;\n')
    output = tmp_path/'out'; (output/'in_game/map_data/named_locations').mkdir(parents=True)
    (output/'in_game/map_data/named_locations/pp.txt').write_text('t1 = 00ff01\nt2 = 00ff02\n')
    # row 0: a a t1 b / row 1: a t2 t1 b  -> a touches t1 and t2, b only t1
    a, b, t1, t2 = (0, 0, 0xa0), (0, 0, 0xb0), (0, 0xff, 1), (0, 0xff, 2)
    Image.fromarray(np.array([[a, a, t1, b], [a, t2, t1, b]], np.uint8)).save(output/'in_game/map_data/locations.png')
    # both banks were emitted onto t1
    (output/'in_game/map_data/ports.csv').write_text('LandProvince;SeaZone;x;y;\na;t1;2;2;x\nb;t1;2;1;x\n')
    (output/DOCK).parent.mkdir(parents=True)
    (output/DOCK).write_text('game_object_locator={\n\tinstances={\n\t\t{ id=a position={ 2.5 0 1.5 } rotation={ 0 0 0 1 } scale={ 1 1 1 } }\n\t}\n}\n')
    nav = tmp_path/'nav'; nav.mkdir()
    pd.DataFrame([{'location': 't1', 'state': 'navigable'}, {'location': 't2', 'state': 'improvable'}]).to_csv(nav/'tiles.csv', index=False)
    pd.DataFrame([{'location_tag': 'a', 'water_location': 't1', 'shore_pixels': 1}, {'location_tag': 'a', 'water_location': 't2', 'shore_pixels': 2},
                  {'location_tag': 'b', 'water_location': 't1', 'shore_pixels': 2}]).to_csv(nav/'shores.csv', index=False)

    stats = assign_bank_ports(output, game, nav)

    rows = (output/'in_game/map_data/ports.csv').read_text().splitlines()[1:]
    assert sorted(rows) == ['a;t2;1;1;x', 'b;t1;2;1;x']   # a moves to t2 so both tiles get a port
    assert stats['tiles_without_port'] == 0 and stats['unplaced'] == []
    assert 'id=a position={ 1.5 0 0.5 }' in (output/DOCK).read_text(encoding='utf-8-sig')
