from pathlib import Path
import json
import numpy as np
import rasterio
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
root=Path(__file__).resolve().parents[1]
fig,axes=plt.subplots(4,2,figsize=(14,12),layout="constrained")
for row,crop in enumerate(["WHE","MZE","RCW","RCD"]):
    arrays=[]
    for scenario in ["LRLM","HILM"]:
        with rasterio.open(root/f"artifacts/scaled/{crop}_{scenario}_1300_diagnostic.tif") as ds:
            arrays.append(ds.read(1,out_shape=(540,1080),masked=True)/1000)
    upper=max(float(np.ma.max(a)) for a in arrays)
    for col,(scenario,a) in enumerate(zip(["low input / rainfed","high input / irrigated"],arrays)):
        ax=axes[row,col]
        im=ax.imshow(a,extent=(-180,180,-90,90),vmin=0,vmax=upper,cmap="YlGn",interpolation="nearest")
        ax.set_ylim(-60,85);ax.set_title(f"{crop}: {scenario}");ax.set_xticks([]);ax.set_yticks([])
    fig.colorbar(im,ax=list(axes[row]),shrink=.65,label="Scaled source tonnes / ha")
fig.suptitle("DIAGNOSTIC ONLY: Seshat selection ratios applied to GAEZ\nModern management remains; not an accepted 1300 yield map",fontsize=15)
fig.savefig(root/"artifacts/scaled/selection_only_diagnostic.png",dpi=130)
plt.close(fig)
