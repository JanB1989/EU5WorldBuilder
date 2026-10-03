import re
import tomllib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from historical_agriculture import navigation_terrain as nt

ROOT = Path(__file__).resolve().parents[1]


def game_root():
    local = ROOT/"geography_test.local.toml"
    if not local.is_file():
        return None
    game = Path(tomllib.loads(local.read_text())["paths"]["game_root"])/"game"
    return game if (game/nt.TERRAIN/"decals").is_dir() else None


@pytest.mark.parametrize("name", ["suez_canal", "panama_canal"])
def test_pages_match_vanilla_decal_layout(name):
    """Our page writer gives vanilla's own mip 0 pages (borders and edge padding included) from the source PNG."""
    game = game_root()
    if game is None:
        pytest.skip("game install not configured")
    folder = game/nt.TERRAIN/"decals"/name
    info = (folder/f"{name}_height.info").read_text()
    vanilla = nt.decode_pages(info, (folder/f"{name}_height.bin").read_bytes())
    source = np.asarray(Image.open(folder/f"{name}_height.png"))[::-1]
    ours = nt.pages(source)
    assert len(vanilla) == len([p for m in nt.mip_chain(source) for p in nt.pages(m)])
    for v, o in zip(vanilla, ours):
        assert np.array_equal(v, o)


def test_encode_round_trip_and_tile_count():
    rng = np.random.default_rng(1)
    image = rng.integers(0, 65535, (384, 640), dtype=np.uint16)
    info, blob = nt.encode(image)
    assert re.search(r"source_resolution=\{ 640 384 \}", info)
    # 5x3 + 3x2 (rounded up) + 2x1 + 1 pages
    assert info.count("offset=") == 15+6+2+1
    assert np.array_equal(nt.assemble(info, blob), image)
    mips = nt.mip_chain(image)
    lowest = np.sort(image.reshape(192, 2, 320, 2).transpose(0, 2, 1, 3).reshape(192, 320, 4), axis=2).astype(int)
    assert np.array_equal(mips[1], (lowest[..., 0]+lowest[..., 1]+1)//2)


CFG = {"shore_smoothing": 1.5, "inside": {"slope": 0.010, "curve": 0.002}, "outside": {"slope": 0.003, "curve": 0.0003},
       "bed_level": 0.04}


def test_carve_lowers_only_the_channels():
    water = 0.0834
    mask = np.zeros((96, 96), bool)
    mask[40:44, :] = True                            # a straight 2-pixel channel (4 texels)
    h = nt.carve(mask, water, CFG)
    assert (h[mask] < water).all() and (h[~mask] > water).all()
    assert h.max() == 1.0 and h.min() >= 0.04
    assert (np.diff(h[44:, 0]) >= 0).all()          # banks only rise away from the water


def test_smoothed_shore_keeps_a_diagonal_channel_open():
    """A 4-connected diagonal staircase two location pixels wide stays water along its whole length."""
    loc = np.zeros((40, 40), bool)
    for i in range(40):
        loc[i, max(0, i-1):i+1] = True
    mask = np.repeat(np.repeat(loc, 2, axis=0), 2, axis=1)
    h = nt.carve(mask, 0.0834, CFG)
    centre = [h[2*i:2*i+2, 2*i-2:2*i+2].min() for i in range(2, 38)]
    assert max(centre) < 0.0834
