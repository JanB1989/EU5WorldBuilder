"""Search the shared support conversion (scale, exponent) against the fill targets.

Population is used only to evaluate candidates. Copy the chosen pair into
configs/agricultural_game_calibration.json (support_conversion.game_scale,
support_conversion.exponent) and rerun `uv run worldbuilder locations`.
"""
from pathlib import Path
import argparse,json
import numpy as np
from historical_agriculture.fill_calibration import candidates
from historical_agriculture.provenance import write_json


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--config',type=Path,default=Path('configs/locations.json'))
    p.add_argument('--output',type=Path,default=Path('artifacts/locations'))
    p.add_argument('--scales',default='1,0.8,0.6,0.5,0.4,0.3,0.25,0.2,0.15,0.1')
    p.add_argument('--exponents',default='0.3333333333333333,0.5,0.7,1.0')
    args=p.parse_args()
    cfg=json.loads(args.config.read_text())
    scales=[float(x) for x in args.scales.split(',')];exponents=[float(x) for x in args.exponents.split(',')]
    table,meta=candidates(Path.cwd(),args.output,cfg,scales,exponents)
    table.to_csv(args.output/'fill_calibration.csv',index=False,float_format='%.6g')
    write_json(args.output/'fill_calibration.json',{**meta,'best':table.head(5).to_dict(orient='records')})
    print(json.dumps(meta,indent=2))
    show=table[['game_scale','exponent','settled_rural_median_fill','settled_rural_p90_fill','rural_over_capacity_share','global_aggregate_fill','starting_total','median_fill_passed','over_capacity_passed','distance']]
    with np.printoptions(precision=3):print(show.head(20).to_string(index=False,float_format=lambda x:f'{x:,.3f}'))


if __name__=='__main__':main()
