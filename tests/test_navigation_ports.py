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
