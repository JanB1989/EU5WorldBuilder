from historical_agriculture.rgo_potential import Location, evaluate, failing, goods_potentials, named_keys


def _rules(tmp_path):
    (tmp_path / 'goods.txt').write_text(
        'horses = {\n method = farming\n location_potential = {\n  NOR = { vegetation = jungle vegetation = forest }\n'
        '  OR = { topography = flatland topography = hills }\n  OR = { climate = arid climate = continental }\n }\n demand_add = { nobles = 0.25 }\n}\n'
        'cocoa = {\n location_potential = {\n  area = { is_area_sea = no }\n  NOR = { region = region:bengal_region area = area:konkan_area }\n  climate = tropical\n }\n}\n'
        'iron = { method = mining }\n', encoding='utf-8-sig')
    return goods_potentials(tmp_path)


def test_rules_parse_per_good_and_name_their_keys(tmp_path):
    rules = _rules(tmp_path)
    assert set(rules) == {'horses', 'cocoa'}
    keys = named_keys(rules['horses'])
    assert keys['climate'] == {'arid', 'continental'} and keys['vegetation'] == {'jungle', 'forest'}


def test_vanilla_literal_and_ours_with_subtype_families(tmp_path):
    rules = _rules(tmp_path)
    geo = {'climate': 'ha1300_climate_continental_monsoon', 'vegetation': 'ha1300_veg_mixed_forest', 'topography': 'ha1300_topo_rolling'}
    literal = Location('x', geo, 'r', 'a', 'p')
    assert not evaluate(rules['horses'], literal)
    fam = {'climate': {'continental': ['ha1300_climate_continental_monsoon']}, 'vegetation': {'forest': ['ha1300_veg_mixed_forest']},
           'topography': {'flatland': ['ha1300_topo_rolling']}}
    ours = Location('x', geo, 'r', 'a', 'p', fam)
    # climate and topography now match their parents, but the mixed forest is a forest: NOR fails
    assert failing(rules['horses'], ours) == ['NOR(vegetation)']
    ok = Location('x', {**geo, 'vegetation': 'grasslands'}, 'r', 'a', 'p', fam)
    assert evaluate(rules['horses'], ok)


def test_region_area_scopes(tmp_path):
    rules = _rules(tmp_path)
    geo = {'climate': 'tropical', 'vegetation': 'jungle', 'topography': 'flatland'}
    assert evaluate(rules['cocoa'], Location('x', geo, 'java_region', 'java_area', 'p'))
    assert not evaluate(rules['cocoa'], Location('x', geo, 'bengal_region', 'dhaka_area', 'p'))
    assert not evaluate(rules['cocoa'], Location('x', geo, 'deccan_region', 'konkan_area', 'p'))
