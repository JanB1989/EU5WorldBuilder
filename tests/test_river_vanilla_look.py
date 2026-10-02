"""Vanilla-look redraw on a tiny canvas: rivers move onto vanilla's lines and every location keeps its level."""
import numpy as np

from historical_agriculture.river_map import validate_native_rivers
from historical_agriculture.river_vanilla_look import WIDTH, redraw, zone_levels

H, W = 40, 80


def _maps():
    drawing = np.full((H, W), 255, np.uint8)
    drawing[:, 70:] = 254
    vanilla = drawing.copy()
    vanilla[20, 5] = 0
    vanilla[20, 6:70] = 4
    zones = np.ones((H, W), np.int32)
    zones[:, 35:70] = 2
    zones[:, 70:] = 3
    return drawing, vanilla, zones


def _main(drawing, row=22, start=5, zone2_width=11):
    drawing[row, start] = 0
    drawing[row, start + 1:35] = 4
    drawing[row, max(start + 1, 35):70] = zone2_width


def _run(drawing, vanilla, zones, ownable):
    out, report = redraw(drawing, vanilla, zones, np.asarray(ownable), np.zeros((H, W), bool), {})
    validate_native_rivers(out)
    count = int(zones.max()) + 1
    before, after = zone_levels(drawing, zones, count), zone_levels(out, zones, count)
    own = np.asarray(ownable)
    assert np.array_equal(before[own], after[own])
    return out, report


def test_parallel_river_moves_onto_vanilla_and_keeps_levels():
    drawing, vanilla, zones = _maps()
    _main(drawing)
    out, report = _run(drawing, vanilla, zones, [False, True, True, False])
    assert np.all(out[20, 6:70] < 16)
    # our line beside vanilla's is gone; zone 2 keeps level 3 through one invisible two-pixel carrier
    assert np.count_nonzero(out[22] < 16) <= 2
    assert report["counters"]["level_carriers"] == 1
    assert report["trees_reaching_water"] == 1


def test_own_tributary_joins_where_a_junction_is_allowed():
    drawing, vanilla, zones = _maps()
    _main(drawing)
    drawing[2:21, 50] = 4
    drawing[21, 50] = 1                        # our tributary joins our main river: zone 2 is level 5
    out, report = _run(drawing, vanilla, zones, [False, True, True, False])
    assert out[19, 50] == 1                    # joined to vanilla's line with a red marker
    assert np.all(out[3:19, 50] < 16)
    assert report["counters"]["bridges_joined"] == 1
    assert report["counters"].get("level_carriers", 0) == 0


def test_own_tributary_stops_short_where_a_junction_would_raise_the_level():
    drawing, vanilla, zones = _maps()
    zones[21:, 35:70] = 4                      # the junction location is south of vanilla's line
    _main(drawing)
    drawing[2:21, 50] = 4
    drawing[21, 50] = 1
    out, report = _run(drawing, vanilla, zones, [False, True, True, False, True])
    assert out[19, 50] == 255 and out[18, 50] < 16
    assert not np.any(out == 1)
    assert report["counters"]["bridges_one_pixel_short"] == 1


def test_vanilla_junction_in_a_low_level_location_is_detached():
    drawing, vanilla, zones = _maps()
    _main(drawing, zone2_width=4)
    vanilla[5:19, 50] = 4
    vanilla[19, 50] = 1
    out, report = _run(drawing, vanilla, zones, [False, True, True, False])
    assert not np.any(out == 1)
    assert out[19, 50] == 255 and np.all(out[6:19, 50] < 16)
    assert report["counters"]["tributaries_detached"] == 1


def test_location_without_a_river_cuts_vanilla_line():
    drawing, vanilla, zones = _maps()
    _main(drawing, start=40, zone2_width=4)    # our river only in zone 2; zone 1 has none
    out, _ = _run(drawing, vanilla, zones, [False, True, True, False])
    assert not np.any(WIDTH[out[:, :35]])
    assert np.all(out[20, 36:70] < 16)
