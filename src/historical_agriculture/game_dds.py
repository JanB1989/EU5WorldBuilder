# Vendored copy of eu5-building-pipeline src/eu5_building_pipeline/dds.py (commit 84cc266), unchanged.
# The World Builder owns its export code (AGENTS.md: no sibling runtime), so the encoder is copied, not imported.
# Keep it identical to the source: the constructor converts interface DDS with the same encoder, and identical
# code gives identical bytes (tests/test_game_dds.py compares the two when the sibling checkout exists).
"""Game-format DDS files: block-compressed (DXT/BCn) with a full mip chain.

Vanilla EU5 interface textures (building icons, map mode icons, modifier icons, illustrations) are all DXT5 or DXT1
(some BC7) with ``floor(log2(max side)) + 1`` mip levels; building icons are 128 x 128 (a few 125 x 125). Pillow's
``Image.save(format="DDS")`` writes uncompressed RGBA without mips (4x-30x larger, no mips for the GUI scaler), so
everything that writes an interface DDS goes through :func:`encode_dds` / :func:`write_game_dds`. The block encoder
is numpy (principal-axis colour endpoints with a least-squares pass, alpha-weighted; exact-mode alpha blocks).
"""

from __future__ import annotations

from dataclasses import dataclass
import io
import math
from pathlib import Path
import struct

import numpy as np
from PIL import Image, ImageFilter

GAME_ICON_SIZE = 128

_DDSD_LINEARSIZE = 0x80000
_DDSD_PITCH = 0x8
_DDSD_MIPMAPCOUNT = 0x20000
_DDSCAPS_COMPLEX = 0x8
_DDSCAPS_MIPMAP = 0x400000
_DDPF_FOURCC = 0x4

_FOURCC_FORMATS = {
    b"DXT1": "DXT1", b"DXT2": "DXT3", b"DXT3": "DXT3", b"DXT4": "DXT5", b"DXT5": "DXT5",
    b"ATI1": "BC4", b"BC4U": "BC4", b"BC4S": "BC4", b"ATI2": "BC5", b"BC5U": "BC5", b"BC5S": "BC5",
}
# DXGI_FORMAT ranges of the block-compressed formats (BC1..BC5 = 70..84, BC6H/BC7 = 94..99)
_DXGI_BC = {**{n: "BC1" for n in (70, 71, 72)}, **{n: "BC2" for n in (73, 74, 75)}, **{n: "BC3" for n in (76, 77, 78)},
            **{n: "BC4" for n in (79, 80, 81)}, **{n: "BC5" for n in (82, 83, 84)},
            **{n: "BC6H" for n in (94, 95, 96)}, **{n: "BC7" for n in (97, 98, 99)}}
_EIGHT_BYTE_BLOCKS = {"DXT1", "BC1", "BC4"}
# formats this module encodes (Pillow only decodes here: its own BCn encoder loses alpha detail)
ENCODABLE = {"DXT1", "DXT5"}


@dataclass(frozen=True)
class DdsInfo:
    width: int
    height: int
    mip_count: int          # levels stored in the file (1 without a mip chain)
    format: str             # DXT1/DXT3/DXT5/BC4/BC5/BC1../BC7, or "raw<bits>" when uncompressed
    compressed: bool
    header_size: int        # 128, or 148 with the DX10 extension

    @property
    def full_mip_count(self) -> int:
        return full_mip_count(self.width, self.height)

    @property
    def has_full_mips(self) -> bool:
        return self.mip_count >= self.full_mip_count

    @property
    def top_level_size(self) -> int:
        """Bytes of the first (full size) level; only meaningful for compressed files."""
        block = 8 if self.format in _EIGHT_BYTE_BLOCKS else 16
        return max(1, (self.width + 3) // 4) * max(1, (self.height + 3) // 4) * block


def full_mip_count(width: int, height: int) -> int:
    return int(math.floor(math.log2(max(width, height, 1)))) + 1


def dds_info(source: Path | bytes) -> DdsInfo | None:
    """Header facts of a DDS file, or None when it is not a readable DDS."""
    if isinstance(source, Path):
        try:
            with source.open("rb") as handle:
                head = handle.read(148)
        except OSError:
            return None
    else:
        head = source[:148]
    if len(head) < 128 or head[:4] != b"DDS " or struct.unpack_from("<I", head, 4)[0] != 124:
        return None
    flags, height, width = struct.unpack_from("<III", head, 8)
    mips = struct.unpack_from("<I", head, 28)[0]
    mip_count = max(1, mips) if (flags & _DDSD_MIPMAPCOUNT or mips > 1) else 1
    pf_flags = struct.unpack_from("<I", head, 80)[0]
    fourcc = head[84:88]
    bits = struct.unpack_from("<I", head, 88)[0]
    header_size = 128
    if pf_flags & _DDPF_FOURCC and fourcc == b"DX10":
        if len(head) < 148:
            return None
        header_size = 148
        fmt = _DXGI_BC.get(struct.unpack_from("<I", head, 128)[0], f"dxgi{struct.unpack_from('<I', head, 128)[0]}")
        compressed = fmt.startswith("BC")
    elif pf_flags & _DDPF_FOURCC:
        fmt = _FOURCC_FORMATS.get(fourcc, fourcc.decode("latin1"))
        compressed = fourcc in _FOURCC_FORMATS
    else:
        fmt, compressed = f"raw{bits}", False
    return DdsInfo(width, height, mip_count, fmt, compressed, header_size)


def is_game_format(source: Path | bytes, *, size: tuple[int, int] | None = None, max_side: int | None = None) -> bool:
    """Block-compressed with a full mip chain (and the given size / no side above ``max_side``)."""
    info = dds_info(source)
    if info is None or not info.compressed or not info.has_full_mips:
        return False
    if size is not None and (info.width, info.height) != tuple(size):
        return False
    return max_side is None or max(info.width, info.height) <= max_side


def fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """``image`` at ``size``: Lanczos (Pillow premultiplies alpha) plus the light unsharp mask the icon kit gives its
    128 px icons, so a downscaled 512 px icon keeps vanilla-like edges."""
    if image.size == tuple(size):
        return image
    shrink = image.width > size[0] or image.height > size[1]
    resized = image.resize(size, Image.Resampling.LANCZOS)
    return resized.filter(ImageFilter.UnsharpMask(0.8, 70, 2)) if shrink else resized


def _blocks(plane: np.ndarray) -> np.ndarray:
    """(blocks, 16, ...) pixels of an (h, w, ...) array in 4x4 blocks, row-major; edges padded by repetition."""
    h, w = plane.shape[:2]
    pad = ((0, -h % 4), (0, -w % 4)) + ((0, 0),) * (plane.ndim - 2)
    a = np.pad(plane, pad, mode="edge")
    bh, bw = a.shape[0] // 4, a.shape[1] // 4
    return a.reshape(bh, 4, bw, 4, *a.shape[2:]).swapaxes(1, 2).reshape(bh * bw, 16, *a.shape[2:])


def _pack_indices(codes: np.ndarray, bits: int) -> np.ndarray:
    shifts = np.arange(16, dtype=np.uint64) * np.uint64(bits)
    return (codes.astype(np.uint64) << shifts).sum(axis=1, dtype=np.uint64)


def _alpha_blocks(alpha: np.ndarray) -> np.ndarray:
    """BC3 alpha blocks (8 bytes each) for an alpha plane; per block the better of the two modes: 8 values between
    max and min, or 6 between the inner values plus exact 0 and 255. (Pillow 12's own DXT5 alpha is far off: a block
    of 0/3/255 decodes 3 as 51, which shows as dark fringes on icon outlines.)"""
    values = _blocks(alpha).astype(np.int32)
    n = values.shape[0]
    hi, lo = values.max(axis=1), values.min(axis=1)
    s8 = np.arange(1, 7)
    pal8 = np.concatenate([hi[:, None], lo[:, None], ((7 - s8) * hi[:, None] + s8 * lo[:, None]) // 7], axis=1)
    inner = (values > 0) & (values < 255)
    in_lo = np.where(inner, values, 256).min(axis=1)
    in_hi = np.where(inner, values, -1).max(axis=1)
    none = in_lo == 256
    in_lo, in_hi = np.where(none, 0, in_lo), np.where(none, 0, in_hi)
    s6 = np.arange(1, 5)
    pal6 = np.concatenate([in_lo[:, None], in_hi[:, None], ((5 - s6) * in_lo[:, None] + s6 * in_hi[:, None]) // 5,
                           np.zeros((n, 1), np.int32), np.full((n, 1), 255, np.int32)], axis=1)

    def pick(palette: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        dist = np.abs(values[:, :, None] - palette[:, None, :])
        codes = dist.argmin(axis=2)
        return codes, (np.take_along_axis(dist, codes[:, :, None], axis=2)[:, :, 0] ** 2).sum(axis=1)

    codes8, err8 = pick(pal8)
    codes6, err6 = pick(pal6)
    use8 = (hi > lo) & (err8 < err6)
    bits = _pack_indices(np.where(use8[:, None], codes8, codes6), 3)
    out = np.zeros((n, 8), np.uint8)
    out[:, 0] = np.where(use8, hi, in_lo)
    out[:, 1] = np.where(use8, lo, in_hi)
    for byte in range(6):
        out[:, 2 + byte] = (bits >> np.uint64(8 * byte)) & np.uint64(0xFF)
    return out


def _to565(color: np.ndarray) -> np.ndarray:
    c = np.clip(np.rint(color * np.array([31 / 255, 63 / 255, 31 / 255])), 0, [31, 63, 31]).astype(np.uint32)
    return (c[..., 0] << 11) | (c[..., 1] << 5) | c[..., 2]


def _from565(value: np.ndarray) -> np.ndarray:
    r, g, b = (value >> 11) & 31, (value >> 5) & 63, value & 31
    return np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)], axis=-1).astype(np.float64)


def _color_blocks(rgb: np.ndarray, weight: np.ndarray) -> np.ndarray:
    """BC1 colour blocks (8 bytes each, always the 4-colour mode, which BC3 uses too): endpoints on the principal axis
    of the block's colours, refined by least squares; pixels weighted by alpha so invisible ones do not pull the
    colours of the visible ones (an outline next to transparent pixels keeps its colour)."""
    pixels = _blocks(rgb).astype(np.float64)
    w = _blocks(weight).astype(np.float64) + 1e-4
    n = pixels.shape[0]
    total = w.sum(axis=1, keepdims=True)
    mean = (pixels * w[..., None]).sum(axis=1) / total
    centred = pixels - mean[:, None, :]
    cov = np.einsum("nk,nki,nkj->nij", w, centred, centred)
    axis = np.ones((n, 3)) / np.sqrt(3)
    for _ in range(8):
        axis = np.einsum("nij,nj->ni", cov, axis)
        axis /= np.linalg.norm(axis, axis=1, keepdims=True) + 1e-12
    t = np.einsum("nki,ni->nk", centred, axis)
    seen = w > 0.05
    t_hi = np.where(seen, t, -np.inf).max(axis=1)
    t_lo = np.where(seen, t, np.inf).min(axis=1)
    t_hi, t_lo = np.where(np.isfinite(t_hi), t_hi, 0), np.where(np.isfinite(t_lo), t_lo, 0)
    e0 = mean + t_hi[:, None] * axis
    e1 = mean + t_lo[:, None] * axis
    share = np.array([1.0, 0.0, 2 / 3, 1 / 3])        # weight of e0 for codes 0..3
    for _ in range(2):
        palette = share[None, :, None] * e0[:, None, :] + (1 - share)[None, :, None] * e1[:, None, :]
        codes = ((pixels[:, :, None, :] - palette[:, None, :, :]) ** 2).sum(axis=3).argmin(axis=2)
        a = share[codes]
        b = 1 - a
        aa, bb, ab = (w * a * a).sum(1), (w * b * b).sum(1), (w * a * b).sum(1)
        ap, bp = (w[..., None] * a[..., None] * pixels).sum(1), (w[..., None] * b[..., None] * pixels).sum(1)
        det = aa * bb - ab * ab
        ok = np.abs(det) > 1e-9
        safe = np.where(ok, det, 1.0)[:, None]
        e0 = np.where(ok[:, None], (ap * bb[:, None] - bp * ab[:, None]) / safe, e0)
        e1 = np.where(ok[:, None], (bp * aa[:, None] - ap * ab[:, None]) / safe, e1)
    c0, c1 = _to565(np.clip(e0, 0, 255)), _to565(np.clip(e1, 0, 255))
    swap = c0 < c1
    c0, c1 = np.where(swap, c1, c0), np.where(swap, c0, c1)
    q0, q1 = _from565(c0), _from565(c1)
    palette = np.stack([q0, q1, (2 * q0 + q1) / 3, (q0 + 2 * q1) / 3], axis=1)
    codes = ((pixels[:, :, None, :] - palette[:, None, :, :]) ** 2).sum(axis=3).argmin(axis=2)
    codes = np.where((c0 == c1)[:, None], 0, codes)    # equal endpoints: one colour (and no 3-colour mode in BC1)
    bits = _pack_indices(codes, 2)
    out = np.zeros((n, 8), np.uint8)
    out[:, 0], out[:, 1] = c0 & 0xFF, c0 >> 8
    out[:, 2], out[:, 3] = c1 & 0xFF, c1 >> 8
    for byte in range(4):
        out[:, 4 + byte] = (bits >> np.uint64(8 * byte)) & np.uint64(0xFF)
    return out


def _encode_level(image: Image.Image, pixel_format: str) -> bytes:
    """One level's blocks (no header)."""
    rgba = np.asarray(image.convert("RGBA"))
    if pixel_format == "DXT1":
        return _color_blocks(rgba[..., :3], np.ones(rgba.shape[:2])).tobytes()
    colour = _color_blocks(rgba[..., :3], rgba[..., 3] / 255.0)
    return np.concatenate([_alpha_blocks(rgba[..., 3]), colour], axis=1).tobytes()


def _header(width: int, height: int, pixel_format: str, levels: int, top_level_size: int) -> bytes:
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | _DDSD_LINEARSIZE | _DDSD_MIPMAPCOUNT
    return (
        b"DDS " + struct.pack("<7I", 124, flags, height, width, top_level_size, 0, levels) + bytes(44)
        + struct.pack("<8I", 32, _DDPF_FOURCC, int.from_bytes(pixel_format.encode(), "little"), 0, 0, 0, 0, 0)
        + struct.pack("<5I", 0x1000 | _DDSCAPS_COMPLEX | _DDSCAPS_MIPMAP, 0, 0, 0, 0)
    )


def _patched_header(header: bytes, levels: int, top_level_size: int) -> bytes:
    patched = bytearray(header)
    flags = struct.unpack_from("<I", patched, 8)[0]
    struct.pack_into("<I", patched, 8, (flags & ~_DDSD_PITCH) | _DDSD_LINEARSIZE | _DDSD_MIPMAPCOUNT)
    struct.pack_into("<I", patched, 20, top_level_size)
    struct.pack_into("<I", patched, 28, levels)
    caps = struct.unpack_from("<I", patched, 108)[0]
    struct.pack_into("<I", patched, 108, caps | _DDSCAPS_COMPLEX | _DDSCAPS_MIPMAP)
    return bytes(patched)


def _mips(image: Image.Image, pixel_format: str, first: int) -> bytes:
    data = bytearray()
    for level in range(first, full_mip_count(*image.size)):
        width, height = max(1, image.width >> level), max(1, image.height >> level)
        data += _encode_level(image.resize((width, height), Image.Resampling.LANCZOS), pixel_format)
    return bytes(data)


def encode_dds(image: Image.Image, pixel_format: str = "DXT5") -> bytes:
    """``image`` as a DDS in ``pixel_format`` (DXT5, or DXT1 for opaque images) with a full mip chain, each level
    resampled from ``image`` itself (not from the previous level)."""
    if pixel_format not in ENCODABLE:
        raise ValueError(f"cannot encode {pixel_format}; use one of {sorted(ENCODABLE)}")
    image = image.convert("RGBA")
    top = _encode_level(image, pixel_format)
    return _header(image.width, image.height, pixel_format, full_mip_count(*image.size), len(top)) + top + _mips(
        image, pixel_format, 1
    )


def add_mips(data: bytes) -> bytes:
    """A DXT1/DXT5 DDS without (all of) its mips, with the full chain appended and the first level kept byte for byte
    (no second compression pass)."""
    info = dds_info(data)
    if info is None or not info.compressed or info.format not in ENCODABLE or info.header_size != 128:
        raise ValueError("add_mips needs a DXT1/DXT5 DDS")
    top_end = info.header_size + info.top_level_size
    with Image.open(io.BytesIO(data)) as source:
        image = source.convert("RGBA")
    return _patched_header(data[:128], info.full_mip_count, info.top_level_size) + data[128:top_end] + _mips(
        image, info.format, 1
    )


def write_game_dds(image: Image.Image, path: Path, *, size: tuple[int, int] | None = None,
                   pixel_format: str = "DXT5") -> bytes:
    """Write ``image`` (resized to ``size`` first when given) to ``path`` in the game format; returns the bytes."""
    image = image.convert("RGBA")
    if size is not None:
        image = fit(image, size)
    data = encode_dds(image, pixel_format)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data
