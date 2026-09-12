import argparse, json, sys
from pathlib import Path

def main():
    if len(sys.argv)>1 and sys.argv[1] in ("fetch","scale"):
        from .legacy import main as legacy
        return legacy()
    parser=argparse.ArgumentParser(description="Historical Agriculture 1300 research pipeline")
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
    args=parser.parse_args()
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
