import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import rdata

from .acquisition import filename
from .provenance import digest, write_json

# Approximate locators only. These are not NGA polygon boundaries.
LOCATORS = {
    'Latium': (12.7,41.8), 'Paris Basin': (2.3,48.8),
    'Upper Egypt': (32.6,25.7), 'Niger Inland Delta': (-4.5,14.8),
    'Susiana': (48.3,32.2), 'Konya Plain': (32.5,37.9),
    'Yemeni Coastal Plain': (43,14.5), 'Kachi Plain': (67.5,28.5),
    'Deccan': (76,17), 'Garo Hills': (90.3,25.5),
    'Cambodian Basin': (104,13.4), 'Central Java': (110.4,-7.5),
    'Middle Yellow River Valley': (112,35), 'Kansai': (135.5,34.7),
    'Southern China Hills': (104.5,26.5), 'Sogdiana': (67,39.7),
    'Valley of Oaxaca': (-96.7,17), 'Cahokia': (-90.1,38.7),
    'Finger Lakes': (-76.5,42.7), 'Cuzco': (-72,-13.5),
    'North Colombia': (-74,10), 'Lowland Andes': (-78.17,-2.46),
    'Big Island Hawaii': (-155.5,19.6)
}
HOLDOUTS = {'Paris Basin','Kansai','Cahokia','Cuzco','Central Java'}
CROP_MAP = {'Wheat':'WHE','Maize':'MZE','Rice, paddy':'RCW','Sweet potatoes':'SPO','Yams':'YAM'}

def anchor_interval_multipliers(data,name):
    """Propagate the published model's earliest yield-anchor interval linearly.

    This is anchor uncertainty only, not a published 1300 confidence interval.
    Missing upper bounds remain point estimates, not invented error bars.
    """
    rows=data[(data.NGA==name)&(data.Variable=='Historical Productivity')].copy()
    if rows.empty:return 1.,1.
    dates=(rows['Date.From'].astype(float)+rows['Date.To'].astype(float))/2
    rows=rows[dates==dates.min()]
    lower=pd.to_numeric(rows['Value.From'],errors='raise').to_numpy(float)
    upper=pd.to_numeric(rows['Value.To'],errors='coerce').to_numpy(float)
    upper=np.where(np.isfinite(upper),upper,lower)
    if np.any(lower<=0) or np.any(upper<lower):raise ValueError(f'Invalid Seshat anchor interval: {name}')
    centre=np.mean((lower+upper)/2)
    return float(np.mean(lower)/centre),float(np.mean(upper)/centre)

def anchor_cropping(data,name):
    """Recover the rotation normalization at the published model's yield anchor."""
    local=data[data.NGA==name]
    observations=local[local.Variable=='Historical Productivity']
    if len(observations):
        midpoint=(observations['Date.From'].astype(float)+observations['Date.To'].astype(float))/2
        year=int(100*np.rint(midpoint.min()/100))
    else:year=2000
    sequence=np.zeros(121)
    times=np.arange(-10000,2001,100)
    for _,row in local[local.Variable=='Cropping System Coefficient'].iterrows():
        sequence[(times>=row['Date.From'])&(times<=row['Date.To'])]=float(row['Value.From'])
    sequence[-1]=max(sequence[-2],sequence[-1],1.)
    return year,float(sequence[np.where(times==year)[0][0]])

def prepare(root, config):
    archive = root / 'data/raw/seshat.zip'
    with zipfile.ZipFile(archive) as z:
        original = rdata.conversion.convert(rdata.parser.parse_data(z.read('Agri.Rdata')))
        yields = pd.read_csv(io.BytesIO(z.read('HistYield_out.csv')))
    yields = yields[yields.Time == config['target_year']].merge(original['NGAs'][['NGA','FAO.Crop']],on='NGA')
    rows = []
    for _, row in yields.iterrows():
        name = row.NGA
        if name not in LOCATORS:
            continue
        code = CROP_MAP[row['FAO.Crop']]
        # Retain the published FAOSTAT paddy proxy for benchmark matching.
        # The crop assignment separately distinguishes upland rice; this mismatch is reported.
        d = original['SeshatData']
        cropping = d[(d.NGA == name) & (d.Variable == 'Cropping System Coefficient') &
                     (d['Date.From'] <= 1300) & (d['Date.To'] >= 1300)]
        coefficient = float(cropping.iloc[-1]['Value.From']) if len(cropping) else np.nan
        x,y = LOCATORS[name]
        anchor_year,anchor_fraction=anchor_cropping(d,name)
        interval_low,interval_high=anchor_interval_multipliers(d,name)
        values = {'region':name,'crop':code,'longitude':x,'latitude':y,
                  'spatial_status':'approximate 1-degree sampling box; not verified NGA boundary',
                  'role':'authoritative_seshat_anchor',
                  'previous_role':'geographical_holdout' if name in HOLDOUTS else 'calibration',
                  'source':'seshat','source_family':'Seshat2021',
                  'published_yield_t_ha':float(row.Yield),
                  'cropping_coefficient':coefficient,
                  'anchor_year':anchor_year,'anchor_cropping':anchor_fraction,
                  'harvest_t_ha_inferred':float(row.Yield)*anchor_fraction/coefficient if coefficient>0 else np.nan,
                  'observation_status':'historical model estimate, not a direct measured yield'}
        values['harvest_t_ha_lower_inferred']=values['harvest_t_ha_inferred']*interval_low
        values['harvest_t_ha_upper_inferred']=values['harvest_t_ha_inferred']*interval_high
        values['interval_status']='Earliest historical yield-anchor bounds propagated through the published linear normalization; other model uncertainty is not included'
        # The published script uses interval lower bounds. Preserve and flag this.
        values['cropping_interpretation'] = 'remove cropping_t / cropping_anchor, NOT cropping_t alone; anchor harvested-area interpretation remains explicit'
        all_samples={}
        points = [(x+dx,y+dy) for dy in np.linspace(-.5,.5,11) for dx in np.linspace(-.5,.5,11)]
        for scenario in config['scenarios']:
            path = root / config['inputs'] / filename(code,scenario)
            with rasterio.open(path) as ds:
                all_samples[scenario]=np.ma.stack(list(ds.sample(points,masked=True))).astype(float).filled(np.nan)[:,0]
        stack=np.stack(list(all_samples.values()))
        common=np.all(np.isfinite(stack)&(stack>=0),axis=0)&np.any(stack>0,axis=0)
        values['sampled_cells']=len(points)
        values['conditionally_viable_cells']=int(common.sum())
        values['sampling_contract']='same feasible crop-cell subset for all scenarios; per-cropped-hectare comparison, not all-land mean'
        values['scenario_samples_dm']=json.dumps({s:a[common].tolist() for s,a in all_samples.items()})
        all_samples['upper']=np.maximum(all_samples['HRLM'],all_samples['HILM'])
        for scenario,array in all_samples.items():
                samples=array[common]
                values[scenario+'_median_dm'] = float(np.median(samples)) if len(samples) else np.nan
                values[scenario+'_p10_dm'] = float(np.quantile(samples,.1)) if len(samples) else np.nan
                values[scenario+'_p90_dm'] = float(np.quantile(samples,.9)) if len(samples) else np.nan
        rows.append(values)
    path = root / 'evidence/benchmarks_1300.csv'
    pd.DataFrame(rows).to_csv(path,index=False)
    write_json(root/'evidence/benchmark_manifest.json',{
        'source_sha256':digest(archive),'version':2,'rows':len(rows),
        'geographic_holdouts':[],
        'former_geographic_holdouts_now_calibration':sorted(HOLDOUTS),
        'policy':'All comparable Seshat cases are mandatory enclosure anchors; none are claimed as independent validation.',
        'independent_source_holdout':False,
        'notes':['Locators approximate; geography must not certify exact regional replication.',
                 'The model normalizes cropping relative to its anchor; undo that relative factor before harvested-hectare comparison.',
                 'Anchor area conventions still require source review; paddy is retained as the published rice proxy.',
                 'All model-derived Seshat rows share a source family.']})
    return {'benchmarks':len(rows),'path':str(path)}
