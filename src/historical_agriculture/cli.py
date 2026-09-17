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
    a=sub.add_parser("geography-test",help="Build and sync the isolated Land Clearance Geography Test mod")
    a.add_argument("--config",type=Path,default=Path("configs/geography_test.json"))
    a.add_argument("--local-config",type=Path,default=Path("geography_test.local.toml"))
    a.add_argument("--build-only",action="store_true",help="Build locally without copying to the live mod folder")
    a=sub.add_parser("soils",help="Classify HWSD soils and build the complete EU5 soil-type map")
    a.add_argument("--config",type=Path,default=Path("configs/soil_types.json"))
    a=sub.add_parser("fertility",help="Build complete five-grade fertility assignments from HWSD chemistry")
    a.add_argument("--config",type=Path,default=Path("configs/fertility.json"))
    a=sub.add_parser("vegetation",help="Build complete historical vegetation types and global map")
    a.add_argument("--config",type=Path,default=Path("configs/vegetation.json"))
    a=sub.add_parser("topography",help="Build complete global topography refinements")
    a.add_argument("--config",type=Path,default=Path("configs/topography.json"))
    a=sub.add_parser("climate",help="Build global climate types with native winter severity")
    a.add_argument("--config",type=Path,default=Path("configs/climate.json"))
    args=parser.parse_args()
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
        print(json.dumps(build(args.config,args.local_config,deploy=not args.build_only),indent=2))
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
