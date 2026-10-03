"""3D terrain for the navigable channels: carve decals that let the sea-level water show along every channel.

EU5 draws all water as one plane at the sea level (NJominiMap water_level_percentage of the world height) and the
terrain hides it wherever it is higher. The channels are sea tiles on the location map, but the terrain under them
is still land, so on the 3D terrain (higher graphics settings) they were invisible; the flat map colours them by tile.

EU5 1.4 composes the terrain heightmap at load from decals (in_game/gfx/terrain2: decals/decal_definitions.txt and
terrain_cache/ingame_decals.json), blended in order by the clausewitz compute shader terrain2_streamed_decals.shader.
Blend mode min with strength 1 and ground level 0 gives final = min(terrain, decal). We add one such decal per vanilla
heightmap tile that holds a channel, placed exactly over that tile and applied after every vanilla decal: 1.0 (no
effect) away from the channels, below the water level inside them, and banks rising from the water line, so the
terrain is only ever lowered and only next to a channel. Vanilla carves the Suez and Panama cuts the same way.

Decal textures are streamed virtual textures: <name>_height.info (resolution, tile table) + <name>_height.bin, pages of
128 x 128 texels with a 2-texel border (the neighbouring texels, clamped at the image edge), stored row by row from the
south-west, mip 0 first, every mip until the image fits one page, each page LZAV-compressed (format 3); verified against
the vanilla decals (tests/test_navigation_terrain.py). The shore line is smoothed (the channel tiles are location
pixel staircases) and the mips keep narrow channels carved when the terrain is drawn from a coarse mip (far zoom).
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import tomllib

import numpy as np
from PIL import Image
from scipy import ndimage

from . import lzav_codec
from .river_network import digest

ROOT = Path(__file__).resolve().parents[2]
PAGE = 128
BORDER = 2
TERRAIN = "in_game/gfx/terrain2"
DEFINITIONS = f"{TERRAIN}/decals/decal_definitions.txt"
PLACEMENTS = f"{TERRAIN}/terrain_cache/ingame_decals.json"
HEIGHTMAP_TILE = re.compile(r"heightmap_(\d+)_16$")


def mip_chain(image):
    """Mip levels as the game stores them (halve until the image fits one page). A texel is the mean of the two lowest
    of its 2 x 2 block: a channel narrower than a texel stays carved at a distance (a plain mean loses 2/3 of the
    channel water from mip 3 on), and the water spills onto the banks half as much as with the block minimum."""
    mips = [image]
    while mips[-1].shape[0] > PAGE or mips[-1].shape[1] > PAGE:
        a = mips[-1]
        a = np.pad(a, ((0, a.shape[0] % 2), (0, a.shape[1] % 2)), mode="edge")
        h, w = a.shape[0]//2, a.shape[1]//2
        block = np.sort(a.reshape(h, 2, w, 2).transpose(0, 2, 1, 3).reshape(h, w, 4), axis=2)
        mips.append(((block[..., 0].astype(np.uint32)+block[..., 1]+1)//2).astype(a.dtype))
    return mips


def pages(image):
    """Pages of one mip (rows from the south), row by row, each with its 2-texel border; edges clamped."""
    h, w = image.shape; nx, ny = -(-w//PAGE), -(-h//PAGE)
    padded = np.pad(image, ((BORDER, ny*PAGE-h+BORDER), (BORDER, nx*PAGE-w+BORDER)), mode="edge")
    side = PAGE+2*BORDER
    return [padded[ty*PAGE:ty*PAGE+side, tx*PAGE:tx*PAGE+side] for ty in range(ny) for tx in range(nx)]


def encode(image, empty_value=0):
    """(info text, bin bytes) of a single-channel streamed texture; image rows run from the south."""
    blobs = [lzav_codec.compress(np.ascontiguousarray(p).tobytes()) for m in mip_chain(image) for p in pages(m)]
    rows, offset = [], 0
    for blob in blobs:
        rows.append(f"\t\toffset={offset}\n\t\tsize={len(blob)}\n"); offset += len(blob)
    h, w = image.shape
    info = (f"source_resolution={{ {w} {h} }}\nnum_channels=1\nbytes_per_channel={image.dtype.itemsize}\n"
            f"empty_value={{ {empty_value} 0 0 0 }}\nlzav=yes\ntile_infos={{ {{\n" + "\t} {\n".join(rows) + "\t} }\n")
    return info, b"".join(blobs)


def decode_pages(info, blob, dtype=np.uint16):
    side = PAGE+2*BORDER; size = side*side*np.dtype(dtype).itemsize
    tiles = [(int(a), int(b)) for a, b in re.findall(r"offset=(\d+)\s+size=(\d+)", info)]
    return [np.frombuffer(lzav_codec.decompress(blob[o:o+s], size), dtype).reshape(side, side) for o, s in tiles]


def assemble(info, blob, dtype=np.uint16):
    """Mip 0 rebuilt from the pages (rows from the south)."""
    w, h = map(int, re.search(r"source_resolution=\{\s*(\d+)\s+(\d+)", info).groups())
    nx, ny = -(-w//PAGE), -(-h//PAGE)
    out = np.zeros((ny*PAGE, nx*PAGE), dtype)
    for k, p in enumerate(decode_pages(info, blob, dtype)[:nx*ny]):
        ty, tx = divmod(k, nx); out[ty*PAGE:(ty+1)*PAGE, tx*PAGE:(tx+1)*PAGE] = p[BORDER:BORDER+PAGE, BORDER:BORDER+PAGE]
    return out[:h, :w]


def shore_distance(mask, sigma):
    """Signed distance (texels, negative in the water) to a smoothed shore line.

    The channel tiles are staircases of location pixels; the shore is the 0.5 line of the mask blurred by sigma (thin
    diagonal reaches keep ~90 % of their width). Next to the shore the distance is the blurred mask's offset over its
    gradient (sub-texel, so the water line is smooth under the shader's bilinear sampling), further away the exact
    distance to the blurred shore's texels."""
    if not sigma:
        return np.where(mask, 0.5-ndimage.distance_transform_edt(mask), ndimage.distance_transform_edt(~mask)-0.5)
    soft = ndimage.gaussian_filter(mask.astype(np.float32), sigma)
    water = soft > 0.5
    far = np.where(water, 0.5-ndimage.distance_transform_edt(water), ndimage.distance_transform_edt(~water)-0.5)
    gy, gx = np.gradient(soft)
    near = np.clip((0.5-soft)/np.maximum(np.hypot(gx, gy), 1e-6), -2, 2)
    blend = np.clip(np.abs(far)-1.0, 0, 1)
    return (1-blend)*near+blend*far


def carve(mask, water, cfg):
    """Carve height (0..1) on the decal grid: the water level at the shore, the bed falling steeply inside (opaque
    water), the bank rising gently outside (a valley, not a cut; steep walls stretch the land's border colour)."""
    d = shore_distance(mask, cfg["shore_smoothing"])
    a = np.abs(d); inside, outside = cfg["inside"], cfg["outside"]
    return np.clip(np.where(d < 0, water-(inside["slope"]*a+inside["curve"]*a*a), water+(outside["slope"]*a+outside["curve"]*a*a)),
                   cfg["bed_level"], 1.0)


def water_level(game):
    text = (game/"loading_screen/common/defines/00_defines.txt").read_text(encoding="utf-8-sig")
    return float(re.search(r"@water_level_percentage\s*=\s*([\d.]+)", text).group(1))


def channel_mask(mod):
    """Channel tiles (every converted water tile) on the location map, rows from the north."""
    md = mod/"in_game/map_data"
    colors = [int(line.split("=")[1], 16) for line in (md/"named_locations/pp_navigation.txt").read_text(encoding="utf-8-sig").splitlines() if "=" in line]
    Image.MAX_IMAGE_PIXELS = None
    rgb = np.asarray(Image.open(md/"locations.png").convert("RGB"))
    code = (rgb[..., 0].astype(np.uint32) << 16) | (rgb[..., 1].astype(np.uint32) << 8) | rgb[..., 2]
    del rgb
    return np.isin(code, np.array(sorted(colors), np.uint32))


def instance_id(name):
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    n = int(hashlib.sha256(name.encode()).hexdigest(), 16)
    return "".join(alphabet[(n >> (6*i)) % 62] for i in range(11))


def placement(name, entry, priority):
    t = entry["decal_transform"]; s = entry["decal_size"]
    return (f'\t\t"decal_name":\t"{name}",\n\t\t"decal_tags":\t[],\n\t\t"decal_transform":\t{{\n\t\t\t"position":\t{{\n'
            f'\t\t\t\t"x":\t{t["position"]["x"]},\n\t\t\t\t"y":\t{t["position"]["y"]}\n\t\t\t}},\n\t\t\t"rotation":\t0,\n'
            f'\t\t\t"scale":\t{{\n\t\t\t\t"x":\t{t["scale"]["x"]},\n\t\t\t\t"y":\t{t["scale"]["y"]}\n\t\t\t}}\n\t\t}},\n'
            f'\t\t"decal_params":\t{{\n\t\t\t"strength":\t1,\n\t\t\t"fade_margin":\t0,\n\t\t\t"heightblendmode":\t"min",\n'
            f'\t\t\t"materialblendmode":\t"min",\n\t\t\t"curvatureblendmode":\t"addsub",\n\t\t\t"curvature_strength":\t1,\n'
            f'\t\t\t"depth_priority":\t{priority},\n\t\t\t"groundlevel":\t0\n\t\t}},\n\t\t"decal_size":\t{{\n'
            f'\t\t\t"x":\t{s["x"]},\n\t\t\t"y":\t{s["y"]}\n\t\t}}\n')


def build(out, game, cfg):
    """Write the carve decals into out/mod; returns (report, written relative paths)."""
    mod = out/"mod"; prefix = cfg["decal_prefix"]
    for old in (mod/TERRAIN/"decals").glob(prefix+"_*"):
        shutil.rmtree(old)
    for rel in (DEFINITIONS, PLACEMENTS):
        (mod/rel).unlink(missing_ok=True)
    if not cfg.get("enabled"):
        return {"enabled": False}, []
    vanilla_placements = (game/PLACEMENTS).read_text(encoding="utf-8-sig")
    entries = json.loads(vanilla_placements)
    tiles = {int(HEIGHTMAP_TILE.match(e["decal_name"]).group(1)): e for e in entries if HEIGHTMAP_TILE.match(e["decal_name"])}
    resolution = json.loads((game/TERRAIN/"terrain_properties.json").read_text(encoding="utf-8-sig"))["terrain_properties"]["resolution"]
    water = water_level(game)
    mask = channel_mask(mod)
    height, width = mask.shape
    units = resolution["x"]/width
    if resolution["y"]/height != units: raise ValueError("Terrain and location map aspect differ")
    margin = int(cfg["margin_location_pixels"])
    written, decals, report_tiles = [], [], {}
    for k, entry in sorted(tiles.items()):
        t = entry["decal_transform"]; size = entry["decal_size"]; scale = t["scale"]["x"]
        per_pixel = scale/units  # location pixels per decal texel
        if t["rotation"] or t["scale"]["y"] != scale or per_pixel != 0.5: raise ValueError(f"Unexpected heightmap tile placement: {entry}")
        x0 = round((t["position"]["x"]-size["x"]*scale/2)/units); y0 = round((t["position"]["y"]-size["y"]*scale/2)/units)
        cols = round(size["x"]*per_pixel); rows = round(size["y"]*per_pixel)
        top = height-(y0+rows)
        # The region plus a margin: columns wrap round the world, rows beyond the poles stay dry.
        xs = np.arange(x0-margin, x0+cols+margin) % width
        ys = np.arange(top-margin, top+rows+margin)
        region = np.zeros((len(ys), len(xs)), bool)
        inside = (ys >= 0) & (ys < height)
        region[inside] = mask[ys[inside]][:, xs]
        core = region[margin:margin+rows, margin:margin+cols]
        if not core.any():
            continue
        fine = np.repeat(np.repeat(region, 2, axis=0), 2, axis=1)
        heights = carve(fine, water, cfg)[2*margin:2*(margin+rows), 2*margin:2*(margin+cols)]
        image = np.round(heights[::-1]*65535).astype(np.uint16)
        name = f"{prefix}_{k}_16"
        info, blob = encode(image)
        if not np.array_equal(assemble(info, blob), image): raise ValueError(f"{name}: page round trip failed")
        folder = f"{TERRAIN}/decals/{name}"
        files = {f"{folder}/{name}_height.info": info.encode(), f"{folder}/{name}_height.bin": blob,
                 f"{folder}/presets.json": (game/TERRAIN/"decals"/f"heightmap_{k}_16"/"presets.json").read_bytes()}
        instance = {"layer_id": cfg["layer_id"], "tags": [], "strength": 1, "ground_level": 0, "height_blend_mode": 3,
                    "materialblendmode": "min", "curvatureblendmode": "addsub", "rotation": 0, "fade_margin": 0,
                    "position.x": t["position"]["x"], "position.y": t["position"]["y"], "scale.x": scale, "scale.y": scale,
                    "depth_priority": 1, "locked": True, "disabled": False}
        files[f"{folder}/instances/{instance_id(name)}.json"] = ("﻿"+json.dumps(instance, indent="\t").replace('": ', '":\t')).encode()
        for rel, data in files.items():
            p = mod/rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data); written.append(rel)
        decals.append((name, entry))
        below = image < round(water*65535)
        report_tiles[name] = {"channel_location_pixels": int(core.sum()), "carved_texels": int((image < 65535).sum()),
                              "texels_below_water": int(below.sum()), "bin_bytes": len(blob), "pages": info.count("offset=")}
    # Definitions and placements: vanilla plus ours, applied after every vanilla decal.
    definitions = (game/DEFINITIONS).read_text(encoding="utf-8-sig").rstrip()
    definitions += "".join(f'\n{{\n    name = {n}\n    layer_textures = {{\n        heightmap = "{n}_height.info"\n    }}\n'
                           f'    additional_textures = {{\n    }}\n}}' for n, _ in decals)
    first = max(e["decal_params"]["depth_priority"] for e in entries)+1
    body = vanilla_placements.rstrip()
    if not body.endswith("}]"): raise ValueError("Unexpected ingame_decals.json layout")
    body = body[:-1]+"".join(", {\n"+placement(n, e, first+i)+"\t}" for i, (n, e) in enumerate(decals))+"]"
    if len(json.loads(body)) != len(entries)+len(decals): raise ValueError("ingame_decals.json merge failed")
    for rel, text, bom in ((DEFINITIONS, definitions, ""), (PLACEMENTS, body, "﻿")):
        p = mod/rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes((bom+text).encode()); written.append(rel)
    report = {"enabled": True, "water_level": water, "decals": report_tiles,
              "channel_location_pixels": int(mask.sum()),
              "covered_channel_location_pixels": sum(r["channel_location_pixels"] for r in report_tiles.values()),
              "bytes": sum((mod/rel).stat().st_size for rel in written),
              "vanilla_inputs": {rel: digest(game/rel) for rel in (DEFINITIONS, PLACEMENTS, f"{TERRAIN}/terrain_properties.json")}}
    if report["covered_channel_location_pixels"] != report["channel_location_pixels"]:
        raise ValueError("Channel pixels outside the heightmap tiles")
    return report, written


def check_vanilla(manifest, game):
    """The decal list and definitions are vanilla's plus ours: after a game update they must be rebuilt."""
    stamp = manifest.get("terrain") or {}
    if not stamp.get("enabled"):
        return
    stale = [rel for rel, d in stamp["vanilla_inputs"].items() if digest(Path(game)/rel) != d]
    if stale:
        raise ValueError("Vanilla terrain files changed (game update?): run worldbuilder navigation-terrain: "+", ".join(stale))


def apply(manifest, out, game, config_path=None):
    """Rebuild the carve decals of a navigation export and record them in its manifest (files, terrain report)."""
    config_path = Path(config_path or ROOT/"configs/navigation_terrain.json")
    cfg = json.loads(config_path.read_text())
    if cfg["schema_version"] != 1: raise ValueError("Unsupported navigation terrain configuration")
    files = {rel: d for rel, d in manifest["files"].items() if not rel.startswith(TERRAIN+"/")}
    report, written = build(Path(out), Path(game), cfg)
    files.update({rel: digest(Path(out)/"mod"/rel) for rel in written})
    manifest["files"] = files
    manifest["terrain"] = {**report, "config_sha256": digest(config_path), "code_sha256": digest(Path(__file__)),
                           "codec_sha256": digest(Path(__file__).with_name("lzav_codec.py"))}
    return manifest


def run(config_path=None):
    """CLI: carve decals for the existing navigation export (no full navigation rerun)."""
    nav = json.loads((ROOT/"configs/river_navigation.json").read_text())
    out = ROOT/nav["output"]
    game = Path(tomllib.loads((ROOT/nav["local_config"]).read_text())["paths"]["game_root"])/"game"
    manifest = json.loads((out/"manifest.json").read_text())
    apply(manifest, out, game, config_path)
    from .river_network import save_json
    save_json(out/"manifest.json", manifest)
    return manifest["terrain"]
