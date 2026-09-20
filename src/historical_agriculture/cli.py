import argparse, json, sys
from pathlib import Path

def main():
    if len(sys.argv)>1 and sys.argv[1] in ("fetch","scale"):
        from .legacy import main as legacy
        return legacy()
    parser=argparse.ArgumentParser(description="EU5 World Builder: location attributes, maps and capacity models")
    sub=parser.add_subparsers(dest="command",required=True)
    for name in ["acquire","audit","evidence","calibrate","assign","food-assign","calculate","compare","food-calculate","validate","maps","run"]:
        a=sub.add_parser(name)
        a.add_argument("--config",type=Path,default=Path("configs/reconstruction.json"))
        a.add_argument("--output",type=Path,default=Path("artifacts/reconstruction"))
    a=sub.add_parser("water",help="Build the independent crop-free water report")
    a.add_argument("--config",type=Path,default=Path("configs/water.json"))
    a.add_argument("--output",type=Path,default=Path("artifacts/water"))
    a=sub.add_parser("locations",help="Build the complete four-value EU5 location dataset and map")
    a.add_argument("--config",type=Path,default=Path("configs/locations.json"))
    a.add_argument("--output",type=Path,default=Path("artifacts/locations"))
    a=sub.add_parser("geography-test",help="Build and sync the EU5 World Builder geography mod")
    a.add_argument("--config",type=Path,default=Path("configs/geography_test.json"))
    a.add_argument("--local-config",type=Path,default=Path("geography_test.local.toml"))
    a.add_argument("--build-only",action="store_true",help="Build locally without copying to the live mod folder")
    a.add_argument("--export-only",action="store_true",help="Use verified existing geography assignments without recomputing datasets")
    a=sub.add_parser("soils",help="Classify HWSD soils and build the complete EU5 soil-type map")
    a.add_argument("--config",type=Path,default=Path("configs/soil_types.json"))
    a=sub.add_parser("fertility",help="Build complete five-grade fertility assignments from the best caloric staple (GAEZ v5, crop-free); HWSD chemistry when the config has no caloric_yield block")
    a.add_argument("--config",type=Path,default=Path("configs/fertility.json"))
    a=sub.add_parser("vegetation",help="Build complete historical vegetation types and global map")
    a.add_argument("--config",type=Path,default=Path("configs/vegetation.json"))
    a=sub.add_parser("topography",help="Build complete global topography refinements")
    a.add_argument("--config",type=Path,default=Path("configs/topography.json"))
    a=sub.add_parser("climate",help="Build global climate types with native winter severity")
    a.add_argument("--config",type=Path,default=Path("configs/climate.json"))
    a=sub.add_parser("attribute-fit",help="Evaluate bounded additive location attribute fits")
    a.add_argument("--config",type=Path,default=Path("configs/attribute_fit.json"))
    a.add_argument("--output",type=Path,help="Separate directory for fit reports and residual maps")
    a=sub.add_parser("development",help="Derive the starting development target with sanity checks")
    a.add_argument("--config",type=Path,default=Path("configs/development.json"))
    a.add_argument("--output",type=Path)
    a=sub.add_parser("building-assignment",help="Assign flat conditional buildings on top of the flat attribute fit")
    a.add_argument("--config",type=Path,default=Path("configs/building_assignment.json"))
    a.add_argument("--output",type=Path)
    a=sub.add_parser("goods-fit",help="Fit goods output modifiers to location attributes on RGO locations")
    a.add_argument("--config",type=Path,default=Path("configs/goods_output_fit.json"))
    a.add_argument("--output",type=Path)
    a=sub.add_parser("handover",help="Export the versioned handover contract for the constructor")
    a.add_argument("--version")
    a.add_argument("--output",type=Path)
    a=sub.add_parser("handover-check",help="Recompute the capacity model from a constructor-side levels table and report the fit")
    a.add_argument("--levels",type=Path,required=True)
    a.add_argument("--units",type=Path,required=True)
    a.add_argument("--version",required=True)
    a.add_argument("--output",type=Path)
    a=sub.add_parser("recalibration-map",help="Render the self-contained HTML map of the recalibrated capacity model")
    a.add_argument("--output",type=Path)
    a=sub.add_parser("river-import",help="Validate complete native river-size exports from an EU5 save")
    a.add_argument("--source",type=Path,default=Path("data/raw/river_attributes/export.json"))
    a.add_argument("--raw",type=Path,default=Path("data/raw/location_inputs"))
    a.add_argument("--output",type=Path,default=Path("artifacts/rivers"))
    a=sub.add_parser("rivers",help="Build an independent geographic river network and/or its EU5 bitmap")
    a.add_argument("--stage",choices=["network","export","all"],default="all")
    a.add_argument("--config",type=Path,default=Path("configs/rivers.json"))
    args=parser.parse_args()
    if args.command=="rivers":
        cfg=json.loads(args.config.read_text())
        if args.stage in ("network","all"):
            from .river_network import build
            r=build(cfg["source"],cfg["network"])
            print(json.dumps({"network":r["network"],"reaches":r["reaches"]},indent=2))
            from .river_preview import build as preview
            preview(cfg["network"],Path(cfg["output"])/"geographic_preview.png",
                cfg["geographic_preview_minimum_mean_discharge_m3_s"])
        if args.stage in ("export","all"):
            from .river_map import export
            r=export(cfg)
            print(json.dumps({k:r[k] for k in ("status","source_reaches","selected_reaches","river_pixels","junction_pixels","location_audit","engineering_checks","output_png")},indent=2))
        return
    if args.command=="river-import":
        from .river_attributes import build
        print(json.dumps(build(args.source,args.raw,args.output),indent=2))
        return
    if args.command=="attribute-fit":
        cfg=json.loads(args.config.read_text())
        if cfg.get("objective")=="quantile":
            from .attribute_fit_flat import build_flat
            r=build_flat(args.config,args.output)
            out=args.output or Path("artifacts/attribute_fit_flat")
            print(json.dumps({"locations":r["locations"],"reference_scale_people":r["reference_scale_people"],"sensibility":{k:{kk:vv for kk,vv in v.items() if kk not in ("pinned","signs")} for k,v in r["sensibility"].items()},"output":str(out/"report.md")},indent=2))
            return
        from .attribute_fit import build
        r=build(args.config,args.output)
        out=args.output or Path("artifacts/attribute_fit_no_overshoot" if r["config"].get("no_overshoot") else "artifacts/attribute_fit")
        print(json.dumps({"locations":r["locations"],"output":str(out/"report.md")},indent=2))
        return
    if args.command=="recalibration-map":
        from .recalibration_map import build
        print(json.dumps(build(args.output),indent=2))
        return
    if args.command=="goods-fit":
        from .goods_output_fit import build
        r=build(args.config,args.output)
        print(json.dumps(r["summary"],indent=2))
        return
    if args.command=="handover":
        from .handover import build
        r=build(args.version,args.output)
        print(json.dumps({"version":r["version"],"counts":r["counts"],"self_check":r["self_check"]},indent=2))
        return
    if args.command=="handover-check":
        import pandas as pd
        from .handover import check, ROOT
        root=(args.output or ROOT/"artifacts/handover")/args.version
        levels=pd.read_csv(args.levels,keep_default_na=False);units=json.loads(Path(args.units).read_text())
        targets=pd.read_csv(root/"location_targets.csv",keep_default_na=False).set_index("location_tag")
        print(json.dumps(check(levels,units,targets),indent=2))
        return
    if args.command=="development":
        from .development_target import build
        r=build(args.config,args.output)
        print(json.dumps({"all_passed":r["checks"]["all_passed"],"p90":r["checks"]["p90_in_band"],"regional_ordering":r["checks"]["regional_ordering"]["passed"],"frontier":r["checks"]["frontier_median"]["passed"],"spot_checks":r["checks"]["spot_checks"]["passed"],"quantiles":r["quantiles"]},indent=2))
        return
    if args.command=="building-assignment":
        from .building_assignment import build
        r=build(args.config,args.output)
        print(json.dumps({"fit":r["fit"],"leftover":r["leftover"],"buildings":[{k:v for k,v in b.items() if k in ("building","unit_people_per_level","eligible_locations","users_at_start","ungated_ledger_share","cap_short_locations")} for b in r["buildings"]]},indent=2))
        return
    if args.command=="climate":
        from .climate import build
        result=build(args.config)
        print(json.dumps({k:v for k,v in result.items() if k not in ("inputs","geometry","source_manifest")},indent=2))
        return
    if args.command=="topography":
        from .topography import build
        result=build(args.config)
        print(json.dumps({k:v for k,v in result.items() if k not in ("inputs","geometry","source_manifest","new_types_by_macro_region")},indent=2))
        return
    if args.command=="vegetation":
        from .vegetation import build
        result=build(args.config)
        print(json.dumps({k:v for k,v in result.items() if k not in ("inputs","geometry")},indent=2))
        return
    if args.command=="fertility":
        from .fertility import build
        result=build(args.config)
        print(json.dumps({k:v for k,v in result.items() if k!='inputs'},indent=2))
        return
    if args.command=="soils":
        from .soil_types import build
        result=build(args.config)
        print(json.dumps({k:v for k,v in result.items() if k!='inputs'},indent=2))
        return
    if args.command=="geography-test":
        from .geography_test import build
        print(json.dumps(build(args.config,args.local_config,deploy=not args.build_only,refresh_data=not args.export_only),indent=2))
        return
    if args.command=="locations":
        from .location_model import execute as location_execute
        result=location_execute(args.config,args.output)
        print(json.dumps(result,indent=2,allow_nan=False))
        return
    if args.command=="water":
        from .water import execute as water_execute
        result=water_execute(args.config,args.output)
        print(json.dumps(result,indent=2,allow_nan=False))
        if not result["engineering_pass"]:raise SystemExit(1)
        return
    from .pipeline import execute
    result=execute(args.command,args.config,args.output)
    print(json.dumps(result,indent=2,allow_nan=False))
    if args.command=="validate" and not result.get("engineering_pass",False): raise SystemExit(1)
