"""Evidence-led navigation selection on the existing World Builder river graph.

The physical source stays immutable. Modern discharge and coarse relief are
screening proxies, with explicit historical exceptions and retained uncertainty.
"""
from pathlib import Path
import json
import tomllib

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import rasterio
import shapely
from PIL import Image
from scipy.spatial import cKDTree

from .river_map import Projection
from .river_network import digest, save_json

ROOT = Path(__file__).resolve().parents[2]
STATES = {"native": 0, "navigable": 1, "improvable": 2, "barrier": 3}


def classify(mean, low, gradient, cfg):
    """Vectorized conservative screen. Missing evidence remains native river."""
    mean, low, gradient = np.broadcast_arrays(mean, low, gradient)
    ok = np.isfinite(mean) & np.isfinite(low) & np.isfinite(gradient)
    ok &= (mean >= cfg["minimum_mean_discharge_m3_s"]) & (low >= cfg["minimum_low_discharge_m3_s"])
    state = np.zeros(mean.shape, np.uint8)
    state[ok] = 3
    state[ok & (gradient <= cfg["improvable_gradient_m_per_km"])] = 2
    state[ok & (gradient <= cfg["open_gradient_m_per_km"])] = 1
    return state


def haversine(a, b):
    a, b = np.deg2rad(a), np.deg2rad(b)
    d = b-a
    v = np.sin(d[:, 1]/2)**2 + np.cos(a[:, 1])*np.cos(b[:, 1])*np.sin(d[:, 0]/2)**2
    return 12742.0176*np.arcsin(np.sqrt(np.clip(v, 0, 1)))


def prepare(config):
    cfg = config["selection"]
    raw = ROOT/config["raw_inputs"]
    output = ROOT/config["output"]; output.mkdir(parents=True, exist_ok=True)
    river_manifest = json.loads((ROOT/config["river_export"]/"export_manifest.json").read_text())
    river_path = ROOT/river_manifest["output_png"]
    Image.MAX_IMAGE_PIXELS = None
    river = np.asarray(Image.open(river_path))
    height, width = river.shape
    projection = Projection(json.loads((raw/"transform.json").read_text()), width, height)
    network = ROOT/config["network"]
    cache = output/"pixel_evidence.parquet"
    fingerprint = {"network": digest(network), "river": digest(river_path), "elevation": digest(ROOT/config["elevation"]),
                   "transform": digest(raw/"transform.json"), "prefilter": cfg["source_prefilter_m3_s"],
                   "evidence_algorithm": 1}
    stamp = output/"pixel_evidence.manifest.json"
    if cache.exists() and stamp.exists() and json.loads(stamp.read_text()) == fingerprint:
        print("Using verified navigation evidence cache", flush=True)
        return pd.read_parquet(cache), river, fingerprint
    print("Matching river pixels to source reaches and sampling relief", flush=True)
    columns = ["reach_id", "main_basin_id", "downstream_reach_id", "q_mean_m3_s", "q_min_m3_s", "distance_downstream_km", "geometry"]
    data = pq.read_table(network, columns=columns, filters=[("q_mean_m3_s", ">=", cfg["source_prefilter_m3_s"])])
    geoms = shapely.from_wkb(data["geometry"].to_pylist())
    coords, parent = shapely.get_coordinates(geoms, return_index=True)
    first = shapely.get_coordinates(shapely.get_point(geoms, 0))
    last = shapely.get_coordinates(shapely.get_point(geoms, -1))
    # Endpoint relief across a minimum baseline limits subpixel DEM noise.
    length = haversine(first, last)
    with rasterio.open(ROOT/config["elevation"]) as dem:
        z0 = np.array([v[0] for v in dem.sample(first)], dtype=float)
        z1 = np.array([v[0] for v in dem.sample(last)], dtype=float)
    gradient = np.maximum(0, z0-z1)/np.maximum(length, cfg["minimum_reach_length_for_gradient_km"])
    gradient[(z0 < -100) | (z1 < -100)] = np.nan
    pixels = projection.project(coords)
    valid = np.isfinite(pixels).all(axis=1)
    tree = cKDTree(pixels[valid])
    y, x = np.where(river < 16)
    distance, nearest = tree.query(np.column_stack((x, y)))
    ix = parent[valid][nearest]
    rows = pd.DataFrame({"x": x.astype(np.int32), "y": y.astype(np.int32), "match_distance_pixels": distance,
                         "gradient_m_per_km": gradient[ix]})
    for col in columns[:-1]:
        rows[col] = data[col].to_numpy()[ix]
    # Smooth the noisy relief proxy within the same mapped basin, never across
    # unrelated neighbouring rivers. Individual known falls override this later.
    k = min(int(cfg["gradient_smoothing_pixels"]), len(rows))
    _, neighbours = cKDTree(np.column_stack((x, y))).query(np.column_stack((x, y)), k=k)
    if k > 1:
        g = rows.gradient_m_per_km.to_numpy()[neighbours]
        same = rows.main_basin_id.to_numpy()[neighbours] == rows.main_basin_id.to_numpy()[:, None]
        rows["gradient_m_per_km"] = np.nanmedian(np.where(same, g, np.nan), axis=1)
    rows.to_parquet(cache, index=False)
    save_json(stamp, fingerprint)
    return rows, river, fingerprint


def build(config_path=None):
    config_path = Path(config_path or ROOT/"configs/river_navigation.json")
    config = json.loads(config_path.read_text())
    if config["schema_version"] != 1:
        raise ValueError("Unsupported navigation configuration")
    rows, river, fingerprint = prepare(config)
    output = ROOT/config["output"]
    rows["state"] = classify(rows.q_mean_m3_s, rows.q_min_m3_s, rows.gradient_m_per_km, config["selection"])
    unmatched = rows.match_distance_pixels > config["selection"]["maximum_match_distance_pixels"]
    rows.loc[unmatched, "state"] = 0
    rows["evidence"] = np.where(unmatched, "unmatched_native_river", "physical_screen")
    raw = ROOT/config["raw_inputs"]
    image = np.asarray(Image.open(raw/"locations.png").convert("RGB"))
    sampled = image[rows.y.to_numpy(), rows.x.to_numpy()].astype(np.uint32)
    enc = (sampled[:, 0] << 16) | (sampled[:, 1] << 8) | sampled[:, 2]
    inv = pd.read_parquet(raw/"inventory.parquet")
    names = dict(zip([int(c, 16) for c in inv.map_color_rgb], inv.location_tag))
    rows["land_location"] = [names.get(int(c), "") for c in enc]
    projection = Projection(json.loads((raw/"transform.json").read_text()), image.shape[1], image.shape[0])
    rows["longitude"] = projection.longitude(rows.x.to_numpy())
    rows["latitude"] = projection.lats[rows.y.to_numpy()]
    tropical=rows.latitude.abs() <= config['selection'].get('tropical_latitude',23.5)
    inadequate=(rows.q_mean_m3_s < config['selection'].get('tropical_minimum_mean_discharge_m3_s',2000)) | (rows.q_min_m3_s < config['selection'].get('tropical_minimum_low_discharge_m3_s',250))
    rows.loc[tropical & inadequate,'state']=0
    rows.loc[tropical & inadequate,'evidence']='tropical_small_or_seasonal_native'
    overrides = []
    for override in config["overrides"]:
        if "bounds" in override:
            x0, y0, x1, y1 = override["bounds"]
            match = rows.longitude.between(x0, x1) & rows.latitude.between(y0, y1)
        else:
            unknown = set(override["locations"])-set(inv.location_tag)
            if unknown: raise ValueError(f"Unknown override locations: {unknown}")
            match = rows.land_location.isin(override["locations"])
        if not override.get("allow_below_threshold", False):
            match &= rows.state != 0
        rows.loc[match, "state"] = STATES[override["state"]]
        rows.loc[match, "evidence"] = override["id"]
        overrides.append({"id": override["id"], "pixels": int(match.sum()), "source": override["source"]})
    from .navigation_cleanup import close_short_gaps
    gap_pixels=close_short_gaps(rows,image.shape[1],config['raster'].get('maximum_native_gap_pixels',6))
    print(f'Restored {gap_pixels} short native-channel gap pixels',flush=True)
    rows.to_parquet(output/"classified_pixels.parquet", index=False)
    from .navigation_map import export
    result = export(config, rows, river)
    result.update({"baseline_year": config["baseline_year"], "config": config,
                   "input_sha256": fingerprint, "config_sha256": digest(config_path), "overrides": overrides,
                   "screened_pixel_states": {n: int((rows.state == v).sum()) for n, v in STATES.items()},
                   "limits": ["Modern hydrology and coarse relief are proxies, not observations of medieval navigability.",
                              "All fleet classes can use converted sea zones.",
                              "Improvable routes are costly but passable until works are completed.",
                              "Short or unsafe conversions remain native rivers; omissions are explicit.",
                              "Map source registration and historical barrier envelopes are approximate."]})
    save_json(output/"manifest.json", result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("config", "input_sha256")}, indent=2), flush=True)
    return result
