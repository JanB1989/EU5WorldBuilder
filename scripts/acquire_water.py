"""Acquire small, matched water inputs; existing scientific caches remain read-only."""
from pathlib import Path
import concurrent.futures, requests, hashlib, json
root=Path("data/raw/water");root.mkdir(parents=True,exist_ok=True)
jobs=[(f"wc2.1_5m_{v}.zip",f"https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_5m_{v}.zip") for v in ["prec","tmin","tmax","srad","wind","vapr","elev"]]
jobs += [(f"hybas_{r}_lev06_v1c.zip",f"https://data.hydrosheds.org/file/hydrobasins/standard/hybas_{r}_lev06_v1c.zip") for r in ["af","ar","as","au","eu","gr","na","sa","si"]]
def get(job):
 name,url=job;p=root/name
 if not p.exists():
  tmp=p.with_suffix(".partial")
  with requests.get(url,stream=True,timeout=(30,120)) as r:
   r.raise_for_status()
   with tmp.open("wb") as f:
    for b in r.iter_content(1024*1024):f.write(b)
  tmp.replace(p)
 h=hashlib.file_digest(p.open("rb"),"sha256").hexdigest()
 print(f"{name}: {p.stat().st_size:,} bytes",flush=True)
 return {"file":str(p),"url":url,"sha256":h,"bytes":p.stat().st_size}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: rows=list(pool.map(get,jobs))
(root/"download_manifest.json").write_text(json.dumps(rows,indent=2))
