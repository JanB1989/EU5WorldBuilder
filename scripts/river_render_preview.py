"""Approximate map look of one or more rivers.png bitmaps, side by side, for visual review outside the game.

Water (sea, lakes and navigable channels) is index 254 in an exported rivers.png; river pixels (< 16) are drawn as
connected strokes whose width follows the palette index (the engine's width), junction/source markers at the width
of the river they sit on. Faint location borders come from each map's locations.png. The widths are an
approximation of the in-game renderer, not a capture.

    uv run python scripts/river_render_preview.py OUT_DIR NAME=MAP_DATA_DIR [NAME=MAP_DATA_DIR ...] \
        --region rhine=7800,1700,450,380 [--region ...] [--scale 4]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

Image.MAX_IMAGE_PIXELS = None
LAND, BORDER, SEA, RIVER = (164, 168, 132), (138, 142, 108), (52, 86, 124), (58, 112, 170)


def stroke(index):
    # palette index 3..15 -> stroke width in map pixels; markers (0..2) take their neighbours' width
    return 0.45 + 0.11 * index


def render(map_data: Path, box, scale):
    x0, y0, w, h = box
    river = np.asarray(Image.open(map_data / "rivers.png").crop((x0, y0, x0 + w, y0 + h)))
    loc = np.asarray(Image.open(map_data / "locations.png").convert("RGB").crop((x0, y0, x0 + w, y0 + h)))
    code = (loc[..., 0].astype(np.int32) << 16) | (loc[..., 1].astype(np.int32) << 8) | loc[..., 2]
    img = np.empty((h, w, 3), np.uint8); img[:] = LAND
    border = np.zeros((h, w), bool)
    border[:, 1:] |= code[:, 1:] != code[:, :-1]; border[1:, :] |= code[1:, :] != code[:-1, :]
    img[border] = BORDER
    img[river == 254] = SEA
    big = Image.fromarray(img).resize((w * scale, h * scale), Image.NEAREST)
    draw = ImageDraw.Draw(big)
    width = np.where(river < 16, river, 0).astype(float)
    ys, xs = np.nonzero(river < 16)
    # markers borrow the widest neighbouring width
    for y, x in zip(ys, xs):
        if river[y, x] < 3:
            ns = [river[y + dy, x + dx] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                  if 0 <= y + dy < h and 0 <= x + dx < w and 3 <= river[y + dy, x + dx] < 16]
            width[y, x] = max(ns) if ns else 4
    c = lambda v: v * scale + scale / 2
    for y, x in zip(ys, xs):
        wpx = stroke(width[y, x]) * scale
        for dx, dy in ((1, 0), (0, 1)):
            nx, ny = x + dx, y + dy
            if nx < w and ny < h and river[ny, nx] < 16:
                lw = max(1, round(min(wpx, stroke(width[ny, nx]) * scale)))
                draw.line([(c(x), c(y)), (c(nx), c(ny))], fill=RIVER, width=lw)
        r = wpx / 2
        draw.ellipse([c(x) - r, c(y) - r, c(x) + r, c(y) + r], fill=RIVER)
    return big


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("maps", nargs="+", help="NAME=MAP_DATA_DIR")
    ap.add_argument("--region", action="append", required=True, help="name=x,y,w,h in map pixels")
    ap.add_argument("--scale", type=int, default=4)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    maps = [m.split("=", 1) for m in a.maps]
    for region in a.region:
        name, spec = region.split("=")
        box = tuple(int(v) for v in spec.split(","))
        for label, path in maps:
            render(Path(path), box, a.scale).save(a.out / f"{name}_{label}.png", optimize=True)
        print(name, "done")


if __name__ == "__main__":
    main()
