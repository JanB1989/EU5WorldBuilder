"""Explicit temporal rotation assumptions, independent of management position."""
import json
import numpy as np


def settings(root):
    path=root/'configs/rotations.json'
    return json.loads(path.read_text()) if path.exists() else {'overrides':[], 'benchmark_annualization':{}}


def rotation_fraction(crop_years, fallow_years):
    if crop_years<=0 or fallow_years<0:
        raise ValueError('Invalid rotation durations')
    return crop_years/(crop_years+fallow_years)


def apply(root, config, crop_map, eco, frequency, fraction):
    frequency=frequency.copy();fraction=fraction.copy()
    identifiers=np.zeros(crop_map.shape,dtype=np.float32);records=[]
    for rule in settings(root)['overrides']:
        codes=[config['crop_order'].index(c)+1 for c in rule['crops']]
        mask=np.isin(crop_map,codes)&np.isin(eco,rule['ecoregion_ids'])&np.isfinite(fraction)
        if np.any(identifiers[mask]!=0):raise ValueError('Overlapping rotation overrides')
        value=rotation_fraction(rule['crop_years'],rule['fallow_years'])
        low,high=rule['fraction_range']
        if not 0<low<=value<=high<=1:raise ValueError('Invalid rotation uncertainty')
        fraction[mask]=value;frequency[mask]=rule['harvests_per_active_year'];identifiers[mask]=rule['id']
        records.append(dict(rule,cultivated_fraction=value,matched_cells=int(mask.sum())))
    return frequency,fraction,identifiers,records


def benchmark_coefficient(root, region, published):
    override=settings(root).get('benchmark_annualization',{}).get(region)
    if override:return override['coefficient'],override['label'],override['status']
    return published,region,'Published cropping coefficient; anchor denominator interpretation remains uncertain'
