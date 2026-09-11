import argparse, hashlib, json, shutil
from pathlib import Path
import numpy as np
import rasterio
import requests
from .model import scale_yield

BASE="https://storage.googleapis.com/fao-gismgr-gaez-v5-data/DATA/GAEZ-V5/MAPSET/RES05-YXX/"

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def main():
    a=argparse.ArgumentParser()
    sub=a.add_subparsers(dest="command",required=True)
    f=sub.add_parser("fetch")
    f.add_argument("--cache",type=Path,required=True)
    f.add_argument("--output",type=Path,default=Path("data/raw/gaez"))
    f.add_argument("--crops",nargs="+",default=["WHE","MZE","RCW","RCD"])
    s=sub.add_parser("scale")
    s.add_argument("--config",type=Path,default=Path("configs/scaling.json"))
    s.add_argument("--inputs",type=Path,default=Path("data/raw/gaez"))
    s.add_argument("--output",type=Path,default=Path("artifacts/scaled"))
    args=a.parse_args()
    if args.command=="fetch":
        args.output.mkdir(parents=True,exist_ok=True)
        manifest=[]
        for crop in args.crops:
            if not crop.isalnum(): raise ValueError("Invalid crop code")
            for scenario in ["LRLM","HILM"]:
                name=f"GAEZ-V5.RES05-YXX.HP0120.AGERA5.HIST.{crop}.{scenario}.tif"
                dst=args.output/name; source=args.cache/name
                url=BASE+name
                if not dst.exists():
                    temp=dst.with_suffix(".partial")
                    if source.exists(): shutil.copyfile(source,temp)
                    else:
                        with requests.get(url,stream=True,timeout=120) as r:
                            r.raise_for_status()
                            with temp.open("wb") as f:
                                for chunk in r.iter_content(1024*1024): f.write(chunk)
                    with rasterio.open(temp) as ds:
                        if ds.count!=1 or ds.crs.to_epsg()!=4326: raise ValueError("Unexpected raster contract")
                    temp.replace(dst)
                with rasterio.open(dst) as ds:
                    manifest.append(dict(crop=crop,scenario=scenario,url=url,sha256=sha(dst),shape=ds.shape,transform=list(ds.transform),nodata=ds.nodata,product="YXX",climate="HP0120",license_status="consult FAO dataset terms; not relicensed by this project"))
                print(crop,scenario,"ready",flush=True)
        (args.output/"manifest.json").write_text(json.dumps(manifest,indent=2))
        return
    config=json.loads(args.config.read_text())
    args.output.mkdir(parents=True,exist_ok=True)
    results=[]
    for crop,settings in config["crops"].items():
        if settings.get("status")=="unresolved": continue
        outputs=[]; expected=None
        for scenario in ["LRLM","HILM"]:
            src=args.inputs/f"GAEZ-V5.RES05-YXX.HP0120.AGERA5.HIST.{crop}.{scenario}.tif"
            with rasterio.open(src) as ds:
                contract=(ds.shape,ds.transform,ds.crs)
                if expected is not None and expected!=contract: raise ValueError("Grid mismatch")
                expected=contract
                raw=ds.read(1,masked=True).astype(float).filled(np.nan)
                spec=settings[scenario]
                out=scale_yield(raw,spec["factor"],spec.get("exponent",1.))
                profile=ds.profile.copy();profile.update(dtype="float32",nodata=-9999,compress="deflate")
                dest=args.output/f"{crop}_{scenario}_1300_diagnostic.tif"
                with rasterio.open(dest,"w",**profile) as writer:
                    writer.write(np.where(np.isfinite(out),out,-9999).astype("float32"),1)
                    writer.update_tags(status="diagnostic_not_accepted",units="scaled source kg/ha; annual/fallow conversion not yet certified",config_sha256=sha(args.config))
                outputs.append(out)
                valid=out[np.isfinite(out)]
                results.append(dict(crop=crop,scenario=scenario,source_sha256=sha(src),output_sha256=sha(dest),status=settings["status"],valid_cells=int(valid.size),positive_cells=int((valid>0).sum()),quantiles=np.quantile(valid,[0,.5,.9,.99,1]).tolist()))
        valid=np.isfinite(outputs[0])&np.isfinite(outputs[1])
        results.append(dict(crop=crop,inverted_endpoint_cells=int(((outputs[0]>outputs[1])&valid).sum()),both_valid_cells=int(valid.sum())))
    report=dict(status="diagnostic_not_accepted",config_sha256=sha(args.config),model_sha256=sha(Path(__file__).with_name("model.py")),results=results)
    (args.output/"report.json").write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=="__main__":main()
