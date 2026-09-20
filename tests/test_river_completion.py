"""Bank detours and vanilla fallback pieces on a tiny canvas."""
import numpy as np
import pandas as pd

from historical_agriculture import river_completion as rc
from historical_agriculture.river_map import validate_native_rivers


def _canvas():
    h, w = 12, 16
    zones = np.ones((h, w), np.uint16)          # zone 1 everywhere ...
    zones[6:, :] = 2                            # ... zone 2 in the bottom half
    zones[:, 12:] = 3                           # zone 3 on the right
    sizes = np.zeros((h, w), np.uint8)
    sizes[5, 1:11] = 4                          # a level-4 mainstem along the zone 1 / zone 2 border, inside zone 1
    owner = np.where(sizes > 0, 7, 0).astype(np.int32)
    markers = np.full((h, w), 255, np.uint8)
    markers[5, 1] = 0                           # green source at the west end
    native = np.full((h, w), 255, np.uint8)
    native[5, 1:11] = 12                        # vanilla draws the same mainstem ...
    native[6, 3:9] = 4                          # ... but slightly lower, so zone 2 has a vanilla river too
    native[2, 13:16] = 4; native[2, 13] = 0     # a small vanilla river in zone 3 the network never carried
    blocked = np.zeros((h, w), bool)
    inv = pd.DataFrame({"location_tag": ["one", "two", "three"], "is_ownable": [True, True, True]})
    return native, sizes, owner, markers, zones, inv, blocked


def test_bank_detour_gives_the_other_bank_the_mainstem_level():
    native, sizes, owner, markers, zones, inv, blocked = _canvas()
    report = rc.complete(native, sizes, owner, markers, zones, inv, blocked, {"bank_detours": True, "fallback_pieces": False, "bfs_detours": False})
    assert report["bank_detours"] == 1
    assert (sizes[6] == 4).sum() == 3 and (sizes[5] == 4).sum() == 9      # one pixel moved down as a three-pixel wiggle
    # still a simple path: every river pixel has degree <= 2, no cycle
    river = sizes > 0
    d = rc._degrees(river)
    assert d[river].max() == 2 and int(d[river].sum()) // 2 == int(river.sum()) - 1
    pixels = np.where(river, 12, 255).astype(np.uint8); pixels[markers == 0] = 0
    validate_native_rivers(pixels)


def test_vanilla_piece_is_copied_as_its_own_tree_with_clearance():
    native, sizes, owner, markers, zones, inv, blocked = _canvas()
    report = rc.complete(native, sizes, owner, markers, zones, inv, blocked, {"bank_detours": False, "fallback_pieces": True, "minimum_piece_pixels": 3, "bfs_detours": False})
    assert report["fallback_pieces"]["pieces"] >= 1 and 3 in report.get("fallback_locations", 0) if False else report["fallback_locations"] >= 1
    assert sizes[2, 13:16].tolist() == [1, 1, 1] and markers[2, 13] == 0     # vanilla's small river and its green source
    # the vanilla pixels touching the drawn mainstem (row 6 under row 5) are not copied: one pixel of clearance
    assert not (sizes[6] > 0).any()
    pixels = np.where(sizes > 0, 4, 255).astype(np.uint8); pixels[sizes == 4] = 12; pixels[markers == 0] = 0
    validate_native_rivers(pixels)


def test_bfs_detour_handles_a_bend_next_to_the_target():
    native, sizes, owner, markers, zones, inv, blocked = _canvas()
    sizes[:] = 0; owner[:] = 0; markers[:] = 255
    # an L-shaped river in zone 1 hugging zone 2: no straight three-pixel run borders zone 2 at the corner
    sizes[3, 2:6] = 3; sizes[3:6, 5] = 3
    owner[sizes > 0] = 9
    markers[3, 2] = 0
    native[:] = 255; native[5, 5] = 9   # vanilla puts the corner one pixel further, inside zone 2? no: row 5 is zone 1; give zone 2 a vanilla river pixel
    native[6, 5] = 9
    report = rc.complete(native, sizes, owner, markers, zones, inv, blocked, {"bank_detours": True, "fallback_pieces": False, "bfs_detours": True})
    assert report["bank_detours"] + report["bfs_detours"] >= 1
    river = sizes > 0
    assert (river & (zones == 2)).any()
    d = rc._degrees(river)
    assert d[river].max() == 2 and int(d[river].sum()) // 2 == int(river.sum()) - 1

