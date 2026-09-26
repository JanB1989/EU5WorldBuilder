"""Vanilla snapping on a tiny canvas: stretches move onto vanilla's line only where no location level changes."""
import numpy as np

from historical_agriculture.river_snap import VanillaSnap, encode_widths, lattice_steps

CFG = {"max_distance_pixels": 3, "minimum_stretch_pixels": 5, "end_distance_pixels": 1, "junction_clearance_pixels": 1}


def _canvas(zone_split_row=None):
    h, w = 12, 30
    zones = np.ones((h, w), np.uint16)
    if zone_split_row is not None:
        zones[zone_split_row:, :] = 2
    native = np.full((h, w), 255, np.uint8)
    native[6, 2:28] = 4                       # vanilla's line one row below ours
    blocked = np.zeros((h, w), bool)
    sizes = np.zeros((h, w), np.uint8)
    return zones, native, blocked, sizes


def _level(pts):
    return np.ones(len(pts), np.uint8)


def test_lattice_steps_are_strictly_between():
    assert lattice_steps((0, 0), (2, 1)) == [(1, 0), (2, 0)]
    assert lattice_steps((3, 3), (3, 4)) == []


def test_parallel_stretch_moves_onto_vanilla():
    zones, native, blocked, sizes = _canvas()
    ref = np.array([0, 1], np.uint8)
    snap = VanillaSnap(native, blocked, zones, ref, np.zeros_like(blocked), CFG)
    path = [(x, 5) for x in range(0, 30)]
    out = snap.snap(path, ("b", 0), _level, sizes)
    on_vanilla = sum(native[y, x] < 16 for x, y in out)
    assert on_vanilla >= 20 and snap.counters["snapped_stretches"] == 1
    # still a simple four-connected path
    assert all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in zip(out, out[1:]))
    assert len(set(out)) == len(out)


def test_guard_refuses_a_location_without_a_routed_river():
    zones, native, blocked, sizes = _canvas(zone_split_row=6)   # vanilla's line lies in zone 2, ours in zone 1
    ref = np.array([0, 1, 0], np.uint8)                          # zone 2 has no routed river
    snap = VanillaSnap(native, blocked, zones, ref, np.zeros_like(blocked), CFG)
    path = [(x, 5) for x in range(0, 30)]
    assert snap.snap(path, ("b", 0), _level, sizes) == path
    assert snap.counters["level_guard"] == 1


def test_stretch_next_to_another_river_is_left_alone():
    zones, native, blocked, sizes = _canvas()
    sizes[7, 0:30] = 1                                           # another river right beside vanilla's line
    snap = VanillaSnap(native, blocked, zones, np.array([0, 1], np.uint8), np.zeros_like(blocked), CFG)
    path = [(x, 4) for x in range(0, 30)]
    assert snap.snap(path, ("b", 0), _level, sizes) == path


def test_denied_stretch_is_skipped():
    zones, native, blocked, sizes = _canvas()
    ref = np.array([0, 1], np.uint8)
    path = [(x, 5) for x in range(0, 30)]
    first = VanillaSnap(native, blocked, zones, ref, np.zeros_like(blocked), CFG)
    first.snap(path, ("b", 0), _level, sizes)
    key = first.log[0]["key"]
    again = VanillaSnap(native, blocked, zones, ref, np.zeros_like(blocked), CFG, deny={key})
    assert again.snap(path, ("b", 0), _level, sizes) == path


def test_widths_follow_vanilla_within_the_level_only():
    native = np.full((3, 6), 255, np.uint8)
    native[1, :] = [5, 5, 11, 11, 15, 255]
    sizes = np.zeros((3, 6), np.uint8)
    sizes[1, :] = [1, 2, 3, 1, 5, 4]
    out, report = encode_widths(sizes, native, 2)
    assert out[1].tolist() == [5, 6, 11, 5, 15, 12]
    levels = {3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 2, 9: 3, 10: 3, 11: 3, 12: 4, 13: 4, 14: 4, 15: 5}
    assert [levels[v] for v in out[1]] == sizes[1].tolist()
