"""Geographic overview independent of all game rendering choices."""
from pathlib import Path
import json

import numpy as np
import pyarrow.parquet as pq
import shapely

from .river_network import digest, save_json


def build(network, output, minimum=10):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fingerprint = {"network_sha256": digest(network), "display_minimum_mean_discharge_m3_s": minimum,
                   "code_sha256": digest(__file__)}
    manifest = output.with_suffix(".manifest.json")
    if output.exists() and manifest.exists():
        previous = json.loads(manifest.read_text())
        if previous.get("fingerprint") == fingerprint and previous.get("png_sha256") == digest(output):
            return previous
    table = pq.read_table(network, columns=["geometry", "q_mean_m3_s"],
                          filters=[("q_mean_m3_s", ">=", minimum)])
    q = table["q_mean_m3_s"].to_numpy()
    geometries = shapely.from_wkb(table["geometry"].to_pylist())
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.colors import LogNorm, LinearSegmentedColormap
    fig, ax = plt.subplots(figsize=(20, 10), facecolor="#0c1825")
    ax.set_facecolor("#0c1825")
    colours = LinearSegmentedColormap.from_list("river_discharge",
        ["#5993b3", "#58c4d4", "#7bd6ad", "#dedb6b", "#fff0b0"])
    lc = LineCollection([np.asarray(g.coords) for g in geometries], cmap=colours,
        norm=LogNorm(vmin=max(.1, minimum), vmax=float(q.max())), linewidths=.35)
    lc.set_array(q); ax.add_collection(lc)
    ax.set(xlim=(-180, 180), ylim=(-60, 85), aspect="equal")
    ax.tick_params(colors="white")
    ax.set_title(f"Geographic rivers · modern HydroATLAS · mean discharge ≥ {minimum:g} m³/s shown", color="white")
    cb = fig.colorbar(lc, ax=ax, orientation="horizontal", fraction=.025, pad=.04)
    cb.ax.tick_params(colors="white")
    cb.set_label("Mean discharge (m³/s); continuous physical values, no game classes", color="white")
    fig.savefig(output, dpi=150, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    result = {"fingerprint": fingerprint, "png_sha256": digest(output), "displayed_reaches": len(table),
              "note": "Display filter only. All source reaches remain in the geographic network."}
    save_json(manifest, result)
    return result
