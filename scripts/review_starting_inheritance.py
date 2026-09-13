"""Compare inherited-starting scenarios on the current canonical native-grid cache.

Read-only with respect to the map. Outputs are diagnostics, not accepted exports.
Population is used only in reporting after the full candidate is calculated.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.ndimage import distance_transform_edt
from historical_agriculture.raster import read
from historical_agriculture.agricultural_game_calibration import activation, bound_inheritance, review_inheritance, convert
from historical_agriculture.provenance import digest,write_json

root=Path.cwd();out=root/'artifacts/locations';dest=root/'data/processed/inheritance_review'
dest.mkdir(exist_ok=True)
inputs=[]
def r(k):
    p=out/(k+'.tif');inputs.append(p);return read(p)[0]
baseline=root/'data/processed/inheritance_review_before.csv';inputs.append(baseline)
before=pd.read_csv(baseline,keep_default_na=False)
before.eu5_start_population=pd.to_numeric(before.eu5_start_population,errors='coerce')
inventory=root/'data/raw/location_inputs/inventory.parquet';inputs.append(inventory)
inv=pd.read_parquet(inventory).sort_values('location_tag')
inputs.append(out/'overlap.npz');weights=sparse.load_npz(out/'overlap.npz')
s=r('uncalibrated_starting_support');u=r('uncalibrated_maximum_support')
old=r('starting_support_per_land_ha');active=r('game_inheritance_activation_fraction')
reference=r('game_conversion_reference_support');h=r('historical_cultivated_fraction')
food=root/'artifacts/reconstruction';inputs.extend([food/'food_type.tif',food/'food_ecoregion.tif',root/'configs/regions.json'])
ft,_=read(food/'food_type.tif');eco,_=read(food/'food_ecoregion.tif');domain=np.isfinite(ft)
_,nearest=distance_transform_edt(~domain,return_indices=True)
h=np.nan_to_num(h);h=np.where(domain,h,h[tuple(nearest)])
system=np.full(domain.shape,'unknown',dtype='U10')
for rule in json.loads((root/'configs/regions.json').read_text())['regions']:
    system[np.isin(eco,rule['ecoregion_ids'])]=rule['management']
system=np.where(domain,system,system[tuple(nearest)])
eligible=np.isin(system,['unknown','extensive','rotation'])
cgap=np.maximum(r('maximum_crop_fraction')-r('source_starting_crop_fraction'),0)
wgap=np.maximum(r('maximum_served_fraction')-r('source_starting_served_fraction'),0)
config=json.loads((root/'configs/agricultural_game_calibration.json').read_text())
inputs.append(root/'configs/agricultural_game_calibration.json')
# Reconstruct the unrestricted candidate so the comparison remains repeatable
# after the guarded map replaces the old output cache.
ceiling=np.full(domain.shape,config['inheritance']['unknown_system_activation'])
for name,amount in config['inheritance']['maximum_opportunity_activation'].items():ceiling[system==name]=amount
active=activation(h,ceiling,config['inheritance']['historical_extent_half_saturation'])
old=convert(s+active*(u-s),reference,config['support_conversion']['exponent']).astype(np.float32)
results=[]
for scope,ratio in [('all',1.),('sparse_extensive_rotation',.5),('sparse_extensive_rotation',1.),('sparse_extensive_rotation',2.)]:
    settings={'full_guard_below_cultivated_fraction':.01,'no_guard_above_cultivated_fraction':.05,'extra_extent_ratio':ratio}
    a=bound_inheritance(active,h,cgap,wgap,ratio) if scope=='all' else review_inheritance(active,h,cgap,wgap,eligible,settings)
    gs=convert(s+a*(u-s),reference,config['support_conversion']['exponent']).astype(np.float32)
    delta=np.asarray(weights@(gs-old).ravel()).ravel()*100
    q=before.copy();q['change']=q.location_tag.map(pd.Series(delta,index=inv.location_tag)).fillna(0)*q.area_comparison_factor
    q['after']=q.starting_capacity+q.change
    own=q[q.is_ownable];rural=own[own.settlement_context=='rural_or_unranked']
    small=rural[(rural.eu5_start_population>0)&(rural.eu5_start_population<5000)]
    new=rural[(rural.eu5_start_population<=rural.starting_capacity)&(rural.eu5_start_population>rural.after)]
    name=f'{scope}_{ratio:g}'
    result={'name':name,'settings':settings,'starting_capacity':float(own.after.sum()),'rural_over_start':int((rural.eu5_start_population>rural.after).sum()),
        'new_rural_shortfalls':len(new),'changed_locations':int((own.change<-.1).sum()),'small_capacity_removed':float(-small.change.sum()),
        'small_before_median':float(small.starting_capacity.median()),'small_after_median':float(small.after.median()),
        'worst_new':new[['location_tag','region','eu5_start_population','starting_capacity','after']].sort_values('eu5_start_population',ascending=False).head(10).to_dict('records')}
    results.append(result);print(json.dumps(result))
    q[['location_tag','change','after']].to_csv(dest/(name+'.csv'),index=False)
write_json(dest/'candidates.json',{'candidates':results,'source_hashes':{str(p.relative_to(root)):digest(p) for p in inputs},
    'model_code_hash':digest(root/'src/historical_agriculture/agricultural_game_calibration.py'),
    'method':'Same native-grid support conversion and overlap geometry; frozen maximum and base. Published float32 caches can differ at rounding precision from a full rebuild.'})
