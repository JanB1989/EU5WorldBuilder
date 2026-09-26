"""Researched navigation reaches: obstacle states, four-connected paths and a small traced river."""
import json

import numpy as np
import pandas as pd

from historical_agriculture import navigation_reaches as nr


def test_obstacle_states():
    assert nr.obstacle_state("falls") == "barrier"
    assert nr.obstacle_state("cataracts") == "barrier"
    assert nr.obstacle_state("rapids") == "improvable"
    assert nr.obstacle_state("gorge with rapids") == "improvable"
    assert nr.obstacle_state("weir") == "improvable"


def test_four_connected_inserts_corners():
    passable = np.ones((5, 5), bool)
    out = nr.four_connected([(0, 0), (1, 1), (2, 2)], passable)
    assert all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in zip(out, out[1:]))


def test_load_reaches_keeps_included_only(tmp_path):
    (tmp_path / "x.json").write_text(json.dumps([{"river": "A", "include": True}, {"river": "B", "include": False}]))
    rivers = nr.load_reaches(tmp_path)
    assert [r["river"] for r in rivers] == ["A"] and rivers[0]["region_file"] == "x"


def _world():
    h, w = 12, 30
    zones = np.full((h, w), 1, np.uint16)             # zone 1 land (town "up"), zone 2 land ("port"), zone 3 sea
    zones[:, 12:] = 2
    zones[:, 26:] = 3
    van = np.full((h, w), 255, np.uint8)
    van[6, 2:26] = 4                                   # one river from x=2 to the coast at x=25
    van[zones == 3] = 254
    drawn = np.full((h, w), 255, np.uint8)
    is_sea = np.array([False, False, False, True]); is_lake = np.zeros(4, bool)
    inv = pd.DataFrame({"centroid_x": [5, 18], "centroid_y": [6, 6], "bbox_min_x": [0, 12], "bbox_max_x": [11, 25],
                        "bbox_min_y": [0, 0], "bbox_max_y": [11, 11]}, index=["up", "port"])
    return nr.Tracer(van, drawn, zones, is_sea, is_lake, inv, {"up": 1, "port": 2})


def test_trace_splits_sea_and_river_reach_and_touches_the_sea():
    t = _world()
    river = {"river": "R", "include": True, "region_file": "t", "sea_head": {"tag": "port"}, "river_head": {"tag": "up"},
             "obstacles": [{"name": "rapids", "tag": "up", "kind": "rapids"}]}
    table, report = nr.trace([river], t)
    assert not report[0]["problems"]
    assert set(table.reach) == {"sea", "river"}
    assert table[table.reach == "sea"].x.min() >= table[table.reach == "river"].x.max() - 1
    assert (table[table.x < 12].state == "improvable").all() and (table[table.x >= 12].state == "navigable").all()
    assert table.x.max() == 25                         # the last pixel touches the sea at x=26
