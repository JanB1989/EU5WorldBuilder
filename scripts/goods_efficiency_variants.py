"""Build the two V2 efficiency variants the constrained goods fit reads, without touching the V2 repository.

- ``data/raw/goods_efficiency_rainfed/<good>.csv``: every good scored rain-fed only (the irrigated LILM
  branches removed), on the canonical per-good anchors, so dry-land scores are not irrigated potential;
- ``data/raw/goods_efficiency_overrides/sugar.csv``: sugar with its canonical regimes but sugarcane only
  (sugar beet removed: not a sugar crop before the 19th century).

Both runs happen in sandboxes under ``~/.cache/eu5-goods-efficiency-variants``: a copy of the V2 code and
configuration, the V2 input data linked read-only, fresh output folders. The sandbox configs keep only
the components the canonical run computed (it never had inputs for the later-added millet, sugar and tea
proxies), accept the canonical anchors from the published manifests, and read the location baseline
from the constructor (the labeling pipeline that used to provide it is retired). A sandbox that
reproduces the canonical run exactly (checked on cotton) is the basis of both variants.

    uv run python scripts/goods_efficiency_variants.py setup
    uv run python scripts/goods_efficiency_variants.py run        # ~40 min, rain-fed all 25 goods + sugar
    uv run python scripts/goods_efficiency_variants.py import
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT.parent
V2_CODE = DEV / "ProsperOrPerishStaticModifiersV2-crop-location-modifiers"
V2_DATA = DEV / "ProsperOrPerishStaticModifiersV2" / "data"
BASELINE = DEV / "ProsperOrPerishConstructor" / "data" / "vanilla" / "locations_with_raw_material.parquet"
CACHE = Path(os.environ.get("EU5_GOODS_VARIANTS_CACHE", Path.home() / ".cache" / "eu5-goods-efficiency-variants"))
SANDBOXES = {"rainfed": CACHE / "rainfed", "sugar_cane": CACHE / "sugar_cane"}
NEVER_COMPUTED = {  # declared in the V2 configs after the canonical run; no inputs exist
    "millet": ["proso_millet_grain", "barnyard_millet_grain", "kodo_little_millet_grain", "quinoa_grain", "grain_amaranth_grain"],
    "sugar": ["date_palm_sweetener_proxy", "palm_sap_sweetener_proxy", "maple_sugar_proxy"],
    "tea": ["mate_leaf_proxy", "yaupon_leaf_proxy", "guayusa_leaf_proxy"],
}
HISTORICAL_DROP = {"sugar": ["sugar_beet"]}
LINKED_OUTPUTS = ["eu5_map", "hyde_3_5", "people_fed_yearly"]
LINKED_TRADE_GOODS = ["animals", "deposits", "fao_pilots", "manufactured", "other"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def drop_keys(node, key):
    if isinstance(node, dict):
        node.pop(key, None)
        for v in node.values():
            drop_keys(v, key)
    elif isinstance(node, list):
        for v in node:
            drop_keys(v, key)


def edit_good(path: Path, drop_components=(), drop_regime=None):
    data = yaml.safe_load(path.read_text())
    comps = []
    for comp in data.get("components") or []:
        if comp["id"] in drop_components:
            continue
        if drop_regime:
            comp["regimes"] = [r for r in comp.get("regimes") or [] if r != drop_regime]
            if "management_branches" in comp:
                comp["management_branches"] = [b for b in comp["management_branches"] if b.get("regime") != drop_regime]
            drop_keys(comp, drop_regime)
            if not comp["regimes"]:
                continue
        comps.append(comp)
    data["components"] = comps
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def setup():
    canonical = V2_DATA / "output_data" / "trade_goods" / "crops"
    for name, box in SANDBOXES.items():
        box.mkdir(parents=True, exist_ok=True)
        subprocess.run(["rsync", "-a", "--delete", "--exclude", "data", "--exclude", ".venv", "--exclude", ".git", f"{V2_CODE}/", f"{box}/"], check=True)
        data = box / "data"
        (data / "output_data" / "trade_goods" / "crops").mkdir(parents=True, exist_ok=True)
        for link, target in [(data / "input_data", V2_DATA / "input_data")] + \
                [(data / "output_data" / d, V2_DATA / "output_data" / d) for d in LINKED_OUTPUTS] + \
                [(data / "output_data" / "trade_goods" / d, V2_DATA / "output_data" / "trade_goods" / d) for d in LINKED_TRADE_GOODS]:
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(target)
        eu5 = yaml.safe_load((box / "config" / "eu5_map.yaml").read_text())
        eu5["labeling_baseline"] = str(BASELINE)
        (box / "config" / "eu5_map.yaml").write_text(yaml.safe_dump(eu5, sort_keys=False))
        anchors = yaml.safe_load((box / "config" / "normalization_anchors.yaml").read_text())
        for good in anchors["goods"]:
            m = json.loads((canonical / good / "efficiency_manifest.json").read_text())["anchors"]
            anchors["goods"][good] = {"status": "accepted", "log_q05": float(m["log_q05"]), "log_q95": float(m["log_q95"])}
        (box / "config" / "normalization_anchors.yaml").write_text(yaml.safe_dump(anchors, sort_keys=False))
        crops = box / "config" / "trade_goods" / "crops"
        for good_file in sorted(crops.glob("*.yaml")):
            good = good_file.stem
            drop = NEVER_COMPUTED.get(good, []) + HISTORICAL_DROP.get(good, [])
            edit_good(good_file, drop, "LILM" if name == "rainfed" else None)
        subprocess.run(["uv", "sync", "-q"], cwd=box, check=True)
        print(f"{name}: sandbox ready at {box}")


def run():
    subprocess.run(["uv", "run", "compute-trade-good", "all", "--no-export"], cwd=SANDBOXES["rainfed"], check=True)
    subprocess.run(["uv", "run", "compute-trade-good", "sugar", "cotton"], cwd=SANDBOXES["sugar_cane"], check=True)
    # reproducibility: the unmodified cotton of the second sandbox must equal the canonical table
    a = (SANDBOXES["sugar_cane"] / "data/output_data/trade_goods/crops/cotton/location_efficiency.csv").read_bytes()
    b = (V2_DATA / "output_data/trade_goods/crops/cotton/location_efficiency.csv").read_bytes()
    print("cotton reproduces the canonical table:", a == b)


def import_tables():
    for name, target, goods in (("rainfed", ROOT / "data/raw/goods_efficiency_rainfed", None), ("sugar_cane", ROOT / "data/raw/goods_efficiency_overrides", ["sugar"])):
        box = SANDBOXES[name] / "data/output_data/trade_goods/crops"
        target.mkdir(parents=True, exist_ok=True)
        manifest = {"goods": {}, "note": (
            "Rain-fed only (LILM branches removed) V2 labor-output efficiency on the canonical anchors." if name == "rainfed" else
            "V2 labor-output efficiency with sugarcane only (sugar beet removed as anachronistic), canonical regimes and anchors."),
            "recipe": "scripts/goods_efficiency_variants.py (setup, run, import)",
            "components_dropped": {"never_computed": NEVER_COMPUTED, "historical": HISTORICAL_DROP}, "regime_dropped": "LILM" if name == "rainfed" else None,
            "v2_code": str(V2_CODE), "v2_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=V2_CODE, capture_output=True, text=True).stdout.strip()}
        for good_dir in sorted(p for p in box.iterdir() if (p / "location_efficiency.csv").exists()):
            if goods and good_dir.name not in goods:
                continue
            dest = target / f"{good_dir.name}.csv"
            shutil.copyfile(good_dir / "location_efficiency.csv", dest)
            manifest["goods"][good_dir.name] = {"sha256": sha(dest)}
        (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"{name}: {len(manifest['goods'])} tables -> {target}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["setup", "run", "import"])
    step = ap.parse_args().step
    {"setup": setup, "run": run, "import": import_tables}[step]()
