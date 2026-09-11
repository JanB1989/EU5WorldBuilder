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
    args=parser.parse_args()
    from .pipeline import execute
    result=execute(args.command,args.config,args.output)
    print(json.dumps(result,indent=2,allow_nan=False))
    if args.command=="validate" and not result.get("engineering_pass",False): raise SystemExit(1)
