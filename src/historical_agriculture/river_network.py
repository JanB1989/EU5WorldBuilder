"""Geographic river network. This module deliberately knows nothing about EU5."""
from pathlib import Path
import hashlib
import json

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import shapely

FIELDS = ["reach_id", "downstream_reach_id", "main_basin_id", "river_source_id",
          "q_mean_m3_s", "q_min_m3_s", "q_max_m3_s", "catchment_km2",
          "distance_downstream_km", "endorheic", "geometry_wkb", "continent_code",
          "source_id", "source_sha256"]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n")


def manifest_path(network):
    return Path(network).with_suffix(".manifest.json")


def downstream_indices(ids, downstream):
    """Resolve source IDs, rejecting dangling links instead of inventing outlets."""
    order = np.argsort(ids)
    ordered = ids[order]
    if np.any(ordered[1:] == ordered[:-1]):
        raise ValueError("Duplicate river reach IDs")
    pos = np.searchsorted(ordered, downstream)
    valid = (downstream != 0) & (pos < len(ids))
    valid &= ordered[np.minimum(pos, len(ids) - 1)] == downstream
    if np.any((downstream != 0) & ~valid):
        raise ValueError("Downstream links refer to missing source reaches")
    return np.where(valid, order[np.minimum(pos, len(ids) - 1)], -1)


def check_acyclic(down):
    incoming = np.bincount(down[down >= 0], minlength=len(down))
    front = np.flatnonzero(incoming == 0)
    seen = 0
    while len(front):
        seen += len(front)
        targets = down[front]
        targets = targets[targets >= 0]
        np.add.at(incoming, targets, -1)
        front = np.unique(targets[incoming[targets] == 0])
    if seen != len(down):
        raise ValueError(f"River network contains a directed cycle ({len(down)-seen} reaches)")


def build(source, network):
    source, network = Path(source), Path(network)
    fingerprint = {"source_sha256": digest(source), "code_sha256": digest(__file__)}
    mp = manifest_path(network)
    if network.exists() and mp.exists():
        old = json.loads(mp.read_text())
        if old.get("fingerprint") == fingerprint and old.get("network_sha256") == digest(network):
            return old
    network.parent.mkdir(parents=True, exist_ok=True)
    temporary = network.with_suffix(".partial.parquet")
    ids, downstream, starts, ends = [], [], [], []
    counts, sources = {}, set()
    n = 0
    writer = None
    try:
        for batch in pq.ParquetFile(source).iter_batches(batch_size=100_000, columns=FIELDS):
            t = pa.Table.from_batches([batch])
            rid = pc.cast(t["reach_id"], pa.int64()).to_numpy()
            dst = pc.fill_null(pc.cast(t["downstream_reach_id"], pa.int64()), 0).to_numpy()
            geometry = shapely.from_wkb(t["geometry_wkb"].to_pylist())
            if not np.all(shapely.is_valid(geometry)) or np.any(shapely.get_type_id(geometry) != 1):
                raise ValueError("Invalid or non-LineString source geometry")
            xy = shapely.get_coordinates(geometry)
            if not np.isfinite(xy).all() or np.any(np.abs(xy[:, 0]) > 180) or np.any(np.abs(xy[:, 1]) > 90):
                raise ValueError("Source is not finite longitude/latitude geometry")
            q = t["q_mean_m3_s"].to_numpy()
            if not np.isfinite(q).all() or np.any(q < 0):
                raise ValueError("Missing or negative discharge requires explicit source handling")
            ids.append(rid); downstream.append(dst)
            starts.append(shapely.get_coordinates(shapely.get_point(geometry, 0)))
            ends.append(shapely.get_coordinates(shapely.get_point(geometry, -1)))
            for value, count in zip(*np.unique(t["continent_code"].to_numpy(), return_counts=True)):
                counts[str(value)] = counts.get(str(value), 0) + int(count)
            sources.update(zip(t["source_id"].to_pylist(), t["source_sha256"].to_pylist()))
            t = t.set_column(t.schema.get_field_index("reach_id"), "reach_id", pa.array(rid))
            t = t.set_column(t.schema.get_field_index("downstream_reach_id"), "downstream_reach_id", pa.array(dst, mask=dst == 0))
            t = t.rename_columns(["geometry" if c == "geometry_wkb" else c for c in t.column_names])
            # GeoParquet's omitted CRS means OGC:CRS84, longitude then latitude.
            meta = {b"geo": json.dumps({"version": "1.0.0", "primary_column": "geometry",
                "columns": {"geometry": {"encoding": "WKB", "geometry_types": ["LineString"]}}}).encode()}
            t = t.replace_schema_metadata(meta)
            if writer is None:
                writer = pq.ParquetWriter(temporary, t.schema, compression="zstd")
            writer.write_table(t)
            n += len(t)
        writer.close(); writer = None
        ids, dst = np.concatenate(ids), np.concatenate(downstream)
        down = downstream_indices(ids, dst)
        check_acyclic(down)
        starts, ends = np.concatenate(starts), np.concatenate(ends)
        linked = down >= 0
        gaps = np.max(np.abs(ends[linked] - starts[down[linked]]), axis=1)
        if np.any(gaps > 1e-5):
            raise ValueError(f"{int((gaps > 1e-5).sum())} links do not meet geographically")
        temporary.replace(network)
    finally:
        if writer is not None:
            writer.close()
    report = {"fingerprint": fingerprint, "network_sha256": digest(network),
        "source": str(source), "network": str(network), "reaches": n,
        "continents": counts, "linked_reaches": int(linked.sum()),
        "terminal_reaches": int((~linked).sum()), "maximum_endpoint_gap_degrees": float(gaps.max()),
        "engineering_checks": "Unique IDs, finite nonnegative mean discharge, valid geographic lines, complete downstream links, acyclic graph, matching directed endpoints",
        "crs": "OGC:CRS84", "geometry_direction": "upstream first, downstream last",
        "source_product": "HydroATLAS / RiverATLAS 1.0",
        "source_url": "https://www.hydrosheds.org/hydroatlas", "license": "CC BY 4.0",
        "upstream_source_files": [{"source_id": a, "sha256": b} for a, b in sorted(sources)],
        "transformations": ["IDs normalized to integers; null downstream ID means terminal",
            "WKB renamed geometry and GeoParquet metadata added; no geometries or physical values changed",
            "Game-alignment fields omitted; no size classes, discharge cutoff or game coordinates applied"],
        "historical_limit": "Modern hydrographic reconstruction, not observed rivers in 1300. Historical channel shifts, reservoirs, diversions and seasonal navigability are not reconstructed."}
    save_json(mp, report)
    return report


def verify(network):
    """Refuse stale exports; the independent stage must be rebuilt explicitly."""
    report = json.loads(manifest_path(network).read_text())
    if digest(network) != report["network_sha256"]:
        raise ValueError("Geographic network changed; rebuild the network stage")
    if digest(report["source"]) != report["fingerprint"]["source_sha256"]:
        raise ValueError("Raw river source changed; rebuild the network stage")
    if digest(__file__) != report["fingerprint"]["code_sha256"]:
        raise ValueError("Network builder changed; rebuild the network stage")
    return report
