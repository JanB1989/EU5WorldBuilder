"""Named waterways on a tiny canvas: one simple tree per waterway, clearance from other rivers, levels raised."""
import numpy as np
import pandas as pd
import pytest

from historical_agriculture import river_waterways as rw
from historical_agriculture.river_completion import _degrees
from historical_agriculture.river_map import validate_native_rivers


def _canvas():
    h, w = 12, 24
    zones = np.ones((h, w), np.uint16)          # zone 1 on the left ...
    zones[:, 8:16] = 2                          # ... zone 2 in the middle ...
    zones[:, 16:] = 3                           # ... zone 3 on the right
    sizes = np.zeros((h, w), np.uint8)
    sizes[1, 16:24] = 4                         # a level-4 river along the top of zone 3
    owner = np.where(sizes > 0, 7, 0).astype(np.int32)
    markers = np.full((h, w), 255, np.uint8)
    markers[1, 16] = 0
    blocked = np.zeros((h, w), bool)
    blocked[:, 0] = True                        # a sea column on the far left
    inv = pd.DataFrame({"location_tag": ["one", "two", "three"], "is_ownable": [True, True, True]})
    return sizes, owner, markers, zones, inv, blocked


def _check_forest(sizes, markers):
    river = sizes > 0
    d = _degrees(river)
    assert d[river].max() <= 2
    pixels = np.where(river, 12, 255).astype(np.uint8)
    pixels[markers == 0] = 0
    validate_native_rivers(pixels)


def test_waterway_is_one_tree_through_every_listed_location_with_clearance():
    sizes, owner, markers, zones, inv, blocked = _canvas()
    report = rw.draw(sizes, owner, markers, zones, inv, blocked, [{"name": "canal", "level": 2, "locations": ["one", "two", "three"]}])
    entry = report["entries"][0]
    assert entry["status"] == "drawn" and report["failed"] == [] and entry["clearance"] == 8 and entry["trees"] == 1
    assert entry["levels_after"] == {"one": 2, "two": 2, "three": 4}      # zone 3 keeps its higher river
    assert entry["locations_raised"] == ["one", "two"]
    canal = sizes == 2
    assert canal[zones == 1].any() and canal[zones == 2].any() and canal[zones == 3].any()
    assert not canal[:, 0].any()                                           # never on blocked pixels
    # 8-neighbour clearance from the level-4 river and one green source at the canal's first pixel
    ys, xs = np.where(canal)
    assert all(not (sizes[max(y - 1, 0):y + 2, max(x - 1, 0):x + 2] == 4).any() for x, y in zip(xs, ys))
    assert int((markers[canal] == 0).sum()) == 1
    assert owner[canal].min() == owner[canal].max() == 8
    _check_forest(sizes, markers)


def test_a_river_between_two_locations_starts_a_new_tree_on_the_far_side():
    sizes, owner, markers, zones, inv, blocked = _canvas()
    sizes[:, 8] = 3                                                        # a river along the whole zone 1 / zone 2 border
    markers[0, 8] = 0
    report = rw.draw(sizes, owner, markers, zones, inv, blocked, [{"name": "canal", "level": 2, "locations": ["one", "two", "three"]}])
    entry = report["entries"][0]
    assert entry["status"] == "drawn" and entry["trees"] == 2 and entry["river_crossings"] == ["one->two"]
    assert entry["levels_after"] == {"one": 2, "two": 3, "three": 4}      # zone 2 keeps the level-3 river
    assert int((markers[sizes == 2] == 0).sum()) == 2                      # one green source per tree
    _check_forest(sizes, markers)


def test_unreachable_chain_is_reported_and_rejected():
    sizes, owner, markers, zones, inv, blocked = _canvas()
    blocked[:, 8:] = True                                                  # zone 2 and 3 are water: nowhere to draw
    with pytest.raises(ValueError, match="canal"):
        rw.draw(sizes, owner, markers, zones, inv, blocked, [{"name": "canal", "level": 2, "locations": ["one", "two"]}])
    report = rw.draw(sizes, owner, markers, zones, inv, blocked, [{"name": "canal", "level": 2, "locations": ["one", "two"]}], require_all=False)
    assert report["entries"][0]["status"].startswith("no_free_interior") and not (sizes == 2).any()


def test_unknown_location_is_invalid():
    sizes, owner, markers, zones, inv, blocked = _canvas()
    report = rw.draw(sizes, owner, markers, zones, inv, blocked, [{"name": "x", "level": 2, "locations": ["one", "nowhere"]}], require_all=False)
    assert report["entries"][0]["status"] == "invalid" and report["entries"][0]["missing"] == ["nowhere"]
