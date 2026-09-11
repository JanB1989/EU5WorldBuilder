"""Compare the archived coarse checkpoint with a rebuilt environmental transfer.

uv run python scripts/compare_food_transfer.py OLD_DIR NEW_DIR
"""
import json
import sys
from pathlib import Path
import numpy as np
from historical_agriculture.raster import read
from historical_agriculture.provenance import write_json

old, new = map(Path, sys.argv[1:3])
food, _ = read(new/'food_type.tif')
report = {'baseline':str(old),'candidate':str(new),'fields':{}}
for name in ['lower_people','historical_people','upper_people']:
    a,_=read(old/f'{name}.tif'); b,_=read(new/f'{name}.tif')
    crop=(food>0)&(food<=18)
    record={'crop_values_unchanged':bool(np.array_equal(a[crop],b[crop],equal_nan=True)), 'systems':{}}
    for code in [19,20,21,22,23,25]:
        mask=food==code
        entry={}
        for label,values in [('old',a),('new',b)]:
            v=values[mask & np.isfinite(values)]
            entry[label]={'count':len(v),'zeros':int(np.sum(v==0)), 'quantiles':np.quantile(v,[0,.25,.5,.75,.99,1]).tolist() if len(v) else []}
        record['systems'][str(code)]=entry
    # Sampling seams: compare mean horizontal jump on old source boundaries
    # to neighbouring within-source edges, restricting to unchanged food types.
    for label,values in [('old',a),('new',b)]:
        valid=(food[:,1:]==food[:,:-1])&(food[:,1:]>=19)&(food[:,1:]!=24)&np.isfinite(values[:,1:])&np.isfinite(values[:,:-1])
        difference=np.abs(values[:,1:]-values[:,:-1])
        seam=np.broadcast_to((np.arange(1,values.shape[1])%24==0),valid.shape)
        boundary=float(np.mean(difference[valid&seam]));interior=float(np.mean(difference[valid&~seam]))
        record[label+'_source_seams']={'mean_boundary_jump':boundary,'mean_interior_jump':interior,'ratio':boundary/interior if interior else None}
    report['fields'][name]=record
write_json(new/'food_transfer_comparison.json',report)
print(json.dumps(report,indent=2))
