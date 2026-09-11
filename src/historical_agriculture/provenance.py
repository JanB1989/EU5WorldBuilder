import hashlib,json
from pathlib import Path

def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1048576),b""):h.update(chunk)
    return h.hexdigest()

def clean(x):
    import numpy as np
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [clean(v) for v in x]
    if isinstance(x,np.ndarray):return clean(x.tolist())
    if isinstance(x,np.generic):return clean(x.item())
    if isinstance(x,float) and not np.isfinite(x):return None
    return x

def write_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(clean(data),indent=2,allow_nan=False)+"\n")

def fingerprint(config_path,raw_root):
    root=Path(config_path).resolve().parents[1]
    files=[Path(config_path)]+sorted((root/"configs").glob("*.json"))+sorted((root/"evidence").glob("*.csv"))+sorted((root/"evidence").glob("*.json"))+sorted(Path(__file__).parent.glob("*.py"))
    files+=sorted(Path(raw_root).glob("*.tif"))
    files+=sorted(Path(raw_root).glob("*.json"))
    files+=sorted((root/"data/raw/ecoregions").glob("*.zip"))
    food_config=root/'configs/food_systems.json'
    if food_config.exists():
        food=json.loads(food_config.read_text())
        files += [root/food[key]['path'] for key in ['forge','climate_transfer'] if key in food]

    files += [root/'pyproject.toml',root/'uv.lock',root/'reports/food_system_method.md']
    files+=sorted((root/"data/raw/documentation").glob("*"))
    if (root/"data/raw/seshat.zip").exists(): files.append(root/"data/raw/seshat.zip")
    # Prepared benchmark tables are stage outputs, not independent source evidence.
    files=[p for p in files if p.name not in {'benchmarks_1300.csv','benchmark_manifest.json'}]
    details={str(p.resolve().relative_to(root)) if p.resolve().is_relative_to(root) else p.name:digest(p) for p in sorted(set(files),key=str) if p.is_file()}
    return hashlib.sha256(json.dumps(details,sort_keys=True).encode()).hexdigest(),details
