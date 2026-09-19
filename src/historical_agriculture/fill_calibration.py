"""Offline search over the shared support conversion (scale k, exponent e).

Starting and maximum capacity per location are recomputed from the native-grid
rasters that the location build already writes, without rerunning the build.
The formula never sees population; population is joined only to evaluate each
candidate against the configured fill targets. The user copies the chosen pair
into configs/agricultural_game_calibration.json and rebuilds.
"""
import json
import numpy as np
import pandas as pd
from .agricultural_game_calibration import convert
from .fill_report import evaluate, DEFAULT_TARGETS


def capacity_proxy(weights,support,reference,scale,exponent,area_factor):
    """People per location: k * sum over cells of converted support, then equal-area scaling."""
    converted=convert(np.nan_to_num(np.asarray(support,float)),reference,exponent)
    totals=np.asarray(weights@converted.ravel()).ravel()*100.0
    return scale*totals*np.asarray(area_factor,float)


def load_inputs(root,out,cfg):
    from .raster import read
    from .location_geometry import overlap_matrix
    raw=root/'data/raw/location_inputs'
    inv=pd.read_parquet(raw/'inventory.parquet').sort_values('location_tag').reset_index(drop=True)
    weights,_=overlap_matrix(root,inv,out)
    grids={name:read(out/f'{name}.tif')[0] for name in ['inherited_physical_starting_support','uncalibrated_maximum_support','uncalibrated_base_support','game_conversion_reference_support']}
    equal=pd.read_csv(out/'locations_equal_area.csv',keep_default_na=False).set_index('location_tag')
    frame=equal.loc[inv.location_tag].reset_index()
    for c in ['physical_location_ha','area_comparison_factor','starting_capacity','maximum_capacity','eu5_start_population','source_starting_crop_ha']:
        frame[c]=pd.to_numeric(frame[c],errors='coerce')
    frame['is_ownable']=frame.is_ownable.astype(str).eq('True')
    return weights,grids,frame


def candidates(root,out,cfg,scales,exponents):
    weights,grids,frame=load_inputs(root,out,cfg)
    c=json.loads((root/cfg['agricultural_game_calibration']).read_text())['support_conversion']
    reference=grids['game_conversion_reference_support']
    area=frame.area_comparison_factor.to_numpy(float)
    current=capacity_proxy(weights,grids['inherited_physical_starting_support'],reference,c.get('game_scale',1.0),c['exponent'],area)
    baseline=frame.starting_capacity.to_numpy(float)
    for col in ['base_land_floor_added_capacity','rural_balance_added_capacity']:
        if col in frame:baseline=baseline-pd.to_numeric(frame[col],errors='coerce').fillna(0).to_numpy(float)
    own=frame.is_ownable.to_numpy()
    deviation=float(np.max(np.abs(current[own]-baseline[own])/np.maximum(baseline[own],1)))
    rows=[]
    for k in scales:
        for e in exponents:
            start=capacity_proxy(weights,grids['inherited_physical_starting_support'],reference,k,e,area)
            maximum=capacity_proxy(weights,grids['uncalibrated_maximum_support'],reference,k,e,area)
            natural=capacity_proxy(weights,grids['uncalibrated_base_support'],reference,k,e,area)
            trial=frame.copy();trial['starting_capacity']=start;trial['maximum_capacity']=np.maximum(maximum,start);trial['inert_capacity']=natural
            ev,_=evaluate(trial,cfg.get('fill_targets'))
            s=ev['summary'];ch=ev['checks']
            rows.append({'game_scale':k,'exponent':e,'settled_rural_median_fill':s['settled_old_world_rural']['median_location_fill'],
                'settled_rural_p90_fill':s['settled_old_world_rural']['p90_location_fill'],'settled_rural_aggregate_fill':s['settled_old_world_rural']['aggregate_fill'],
                'rural_over_capacity_share':s['rural']['over_capacity_share'],'rural_over_capacity_locations':s['rural']['over_capacity_locations'],
                'global_aggregate_fill':s['global']['aggregate_fill'],'urban_over_capacity_locations':s['urban']['over_capacity_locations'],
                'starting_total':s['global']['starting_capacity'],'maximum_total':s['global']['maximum_capacity'],
                'median_fill_passed':ch['settled_median_fill']['passed'],'over_capacity_passed':ch['rural_over_capacity_share']['passed']})
    table=pd.DataFrame(rows)
    targets={**DEFAULT_TARGETS,**(cfg.get('fill_targets') or {})}
    table['distance']=np.abs(table.settled_rural_median_fill-targets['settled_median_fill'])+np.maximum(table.rural_over_capacity_share-targets['rural_over_capacity_share'],0)*4
    table=table.sort_values('distance').reset_index(drop=True)
    return table,{'current_scale':c.get('game_scale',1.0),'current_exponent':c['exponent'],'proxy_max_relative_deviation_from_build':deviation,
        'targets':targets,'note':'Proxy recomputes k * sum(G(inherited support; r, e)) per location with the cached overlap matrix and equal-area factor; deviation from the last build should be ~0 at the built (k, e) when floor and allowance are off.'}
