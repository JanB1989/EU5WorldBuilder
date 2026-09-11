import json
import numpy as np
import rasterio
from .acquisition import filename
from .provenance import write_json
from .transformations import factor

def independent(root,config,out):
    specifications=json.loads((root/'evidence/independent_holdouts.json').read_text())['observations']
    parameters=json.loads((out/'parameters.json').read_text())['parameters']
    results=[]
    for case in specifications:
        crop=config['crops'][case['crop']];p=parameters[crop['group']]
        west,south,east,north=case['sample_bbox']
        points=[(x,y) for y in np.arange(south,north,.25) for x in np.arange(west,east,.25)]
        a={}
        for scenario in config['scenarios']:
            with rasterio.open(root/config['inputs']/filename(case['crop'],scenario)) as ds:
                a[scenario]=np.ma.stack(list(ds.sample(points,masked=True))).astype(float).filled(np.nan)[:,0]
        valid=np.isfinite(a['LRLM'])&np.isfinite(a['HRLM'])&np.isfinite(a['HILM'])&(a['LRLM']>0)
        lower=a['LRLM'][valid]*factor(crop,'LRLM',p['low'],p['high'])/crop['dry_fraction']*(1-crop['seed_share'])
        upper=np.maximum(a['HRLM'][valid]*factor(crop,'HRLM',p['low'],p['high']),a['HILM'][valid]*factor(crop,'HILM',p['low'],p['high']))/crop['dry_fraction']*(1-crop['seed_share'])
        observed=np.array(case['pounds_per_bushel_range'])*case['reported_value']*case['pound_to_kg']/case['acre_to_ha']
        lo=float(np.median(lower));hi=float(np.median(upper))
        passed=bool(lo<=observed[1] and hi>=observed[0])
        results.append({'id':case['id'],'source':case['source'],'source_family':case['source_family'],
                        'observed_net_seed_kg_ha_range':observed.tolist(),
                        'model_lower_median_net_seed_kg_ha':lo,'model_upper_median_net_seed_kg_ha':hi,
                        'result':'passed' if passed else 'failed','comparison':'range overlap, not point-fit',
                        'spatial_status':case['spatial_note'],'sample_count':int(valid.sum()),'used_in_calibration':False})
    write_json(out/'independent_holdouts.json',results)
    return results
