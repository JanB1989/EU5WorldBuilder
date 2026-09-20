"""Irrigated-share layer (HID 1900) and the flat development term."""
import json

import numpy as np

from historical_agriculture import irrigation


def test_cell_area_matches_the_sphere():
    area = irrigation.cell_area_ha()
    assert area.shape == (2160, 4320)
    # the whole grid is the sphere: 4 pi R^2 in hectares
    assert abs(area.sum() / (4 * np.pi * irrigation.EARTH_RADIUS_M ** 2 / 1e4) - 1) < 1e-9
    assert area[0, 0] < area[1080, 0]   # polar cells are smaller than equatorial ones


def test_read_ascii_grid_and_nodata(tmp_path):
    p = tmp_path / "g.asc"
    p.write_text("ncols 3\nnrows 2\nxllcorner -180\nyllcorner -90\ncellsize 0.0833333\nNODATA_value -9999\n1 2 -9999\n0 5 6\n")
    values, header = irrigation.read_ascii_grid(p)
    assert values.shape == (2, 3) and header["nodata_value"] == -9999 and values[0, 2] == -9999 and values[1, 1] == 5


def test_development_flat_term_is_configured_and_read():
    from historical_agriculture.development_target import capacity_people_per_point

    cfg = json.loads((irrigation.ROOT / "configs/development.json").read_text())
    assert cfg["capacity_people_per_point"] == capacity_people_per_point() == 1000.0
