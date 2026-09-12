"""Read-only validation of water artifacts and their input fingerprints."""
from pathlib import Path
import json,hashlib
import numpy as np,rasterio
from historical_agriculture.water import digest,area_grid
out=Path('artifacts/water')
manifest=json.loads((out/'manifest.json').read_text());cfg=manifest['configuration']
checks={}
checks['source_hashes_match']=all(digest(r['path'])==r['sha256'] for r in manifest['sources'])
checks['code_hashes_match']=all(digest(Path('src/historical_agriculture')/n)==h for n,h in manifest['code'].items())
checks['configuration_matches']=json.loads(Path('configs/water.json').read_text())==cfg
checks['declared_fingerprint_matches']=hashlib.sha256(json.dumps({'sources':manifest['sources'],'config':cfg,'code':manifest['code']},sort_keys=True).encode()).hexdigest()==manifest['fingerprint']
def read(name):
 with rasterio.open(out/name) as d:return d.read(masked=True).filled(np.nan)
natural=read('natural_monthly_deficit_mm.tif');current=read('historical_monthly_deficit_mm.tif');maximum=read('maximum_monthly_deficit_mm.tif')
checks['nonnegative_deficits']=all(np.nanmin(x)>=-.001 for x in [natural,current,maximum])
checks['historical_never_worse_than_rainfall']=bool(np.nanmin(natural-current)>=-.001)
checks['upper_never_worse_than_historical']=bool(np.nanmin(current-maximum)>=-.001)
checks['monthly_annual_maps_match']=all(np.allclose(np.sum(a,axis=0),read(n+'_annual_deficit_mm.tif')[0],equal_nan=True,atol=.001) for n,a in [('natural',natural),('historical',current),('maximum',maximum)])
z=np.load(out/'basin_monthly_budget.npz');a=area_grid();errors={}
for key,arr in [('historical',current),('maximum',maximum)]:
 represented=np.nansum((natural-arr).astype('float64')*a[None]*1000/cfg['irrigation']['efficiency'],axis=(1,2))
 actual=z[key+'_withdrawal_m3'].sum(axis=1)
 errors[key]=float(np.max(np.abs(represented-actual)/np.maximum(actual,1)))
 checks[key+'_maps_reconcile_with_budget']=bool(np.allclose(represented,actual,rtol=1e-5,atol=100))
 outlets=z['downstream']<0
 residual=z['runoff_m3'].sum(axis=1)*(1-cfg['irrigation']['protected_runoff_fraction'])-actual-z[key+'_transmission_loss_m3'].sum(axis=1)-z[key+'_outflow_m3'][:,outlets].sum(axis=1)
 checks[key+'_network_conserves_water']=bool(np.max(np.abs(residual))<1)
checks['65_monthly_and_annual_images']=all((out/f'{name}_{month:02}.png').is_file() for name in ['natural','historical','maximum','difference','historical_difference'] for month in range(13))
checks['difference_monthly_matches_subtraction']=bool(np.allclose(read('difference_monthly_mm.tif'),natural-maximum,equal_nan=True,atol=1e-5))
checks['difference_annual_matches_monthly_sum']=bool(np.allclose(read('difference_annual_mm.tif')[0],np.sum(natural-maximum,axis=0),equal_nan=True,atol=.001))
checks['starting_difference_monthly_matches_subtraction']=bool(np.allclose(read('historical_difference_monthly_mm.tif'),natural-current,equal_nan=True,atol=1e-5))
checks['starting_difference_annual_matches_monthly_sum']=bool(np.allclose(read('historical_difference_annual_mm.tif')[0],np.sum(natural-current,axis=0),equal_nan=True,atol=.001))
checks['nile_delta_uses_documented_water_connection']=bool(current[:,int((90-30.8)*12),int((31.15+180)*12)].sum()<natural[:,int((90-30.8)*12),int((31.15+180)*12)].sum()-100)
result={'passed':all(checks.values()),'checks':checks,'map_to_budget_relative_errors':errors,'input_fingerprint':manifest['fingerprint'],'scientific_validation':'Not established by engineering checks; see reports/water_method.md and the HTML limitations.'}
(out/'artifact_checks.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
if not result['passed']:raise SystemExit(1)
