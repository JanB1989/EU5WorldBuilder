"""Dated crop-system analogues on inherited improved land, before aggregation."""
import json
import numpy as np
from netCDF4 import Dataset, num2date
from .raster import read, write
from .accounting import annual_food
from .management_envelope import yields
from .water import wc, area_grid
from .provenance import write_json


def eligible(eco, extent, region_ids, minimum):
    return np.isin(eco, region_ids) & np.isfinite(extent) & (extent >= minimum)


def cereal_mix(original, alternatives, share):
    """Equal-weight feasible cereal alternatives; never select the largest yield."""
    if not 0 <= share <= 1:
        raise ValueError('Invalid summer share')
    values = np.asarray(alternatives)
    valid = np.isfinite(values) & (values > 0)
    count = valid.sum(axis=0)
    mean = np.divide(np.where(valid, values, 0).sum(axis=0), count,
                     out=np.zeros_like(original), where=count > 0)
    candidate = (1-share)*original + share*mean
    return np.where((count > 0) & (candidate > original), candidate, original), count


def configuration(root, cfg):
    p = cfg.get('system_round_config')
    if not p:
        return None
    c = json.loads((root/p).read_text())
    variant = cfg.get('system_round_variant', c['variant'])
    for key, value in c['variants'][variant].items():
        group, name = key.split('_', 1)
        c[group][name] = value
    c['variant'] = variant
    return c


def apply(root, cfg, domain, profile, crop, rf, ir, diagnostics, out):
    c = configuration(root, cfg)
    flags = np.zeros(crop.shape, dtype=np.uint8)
    if c is None:
        return rf, ir, flags
    rc = json.loads((root/'configs/reconstruction.json').read_text())
    eco, _ = read(root/cfg['food_directory']/'food_ecoregion.tif')
    with Dataset(root/cfg['input_directory']/'hyde/cropland.nc') as ds:
        dates = num2date(ds['time'][:], ds['time'].units, ds['time'].calendar)
        index = [i for i, t in enumerate(dates) if t.year == cfg['evidence_year']]
        if len(index) != 1:
            raise ValueError('Missing dated cultivated extent')
        extent = ds['cropland'][index[0]].filled(np.nan)/area_grid()
    elevation = wc(root/'data/raw/water', 'elev')
    old_rf = rf.copy()
    rf, ir = rf.copy(), ir.copy()

    def densities(code, settings):
        a = [read(root/cfg['food_directory']/f'crops/{code}_{suffix}.tif')[0]
             for suffix in ['lower', 'high_rainfed', 'high_irrigated']]
        complete = np.isfinite(a[0]) & np.isfinite(a[1]) & np.isfinite(a[2])
        dry, wet = yields(*a, settings['management_position'])
        convert = lambda x: annual_food(x, rc['crops'][code], settings['harvests'],
                                        settings['active_rotation_fraction'])[2]/(2500*365)
        return convert(dry), convert(wet), convert(np.maximum(a[0], a[1])), complete

    chi = c['china']
    mask = domain & eligible(eco, extent, chi['ecoregion_ids'], chi['minimum_cropland_fraction'])
    mask &= (crop == rc['crop_order'].index('RCW')+1)
    mask &= np.isfinite(elevation) & (elevation <= chi['maximum_elevation_m'])
    mask &= diagnostics['rotation_fraction'] < chi['active_rotation_fraction']
    dry, wet, high, complete = densities('RCW', chi)
    changed = mask & complete & ((dry > rf) | (wet > ir))
    rf[changed] = np.maximum(rf[changed], dry[changed])
    ir[changed] = np.maximum.reduce([ir[changed], wet[changed], rf[changed]])
    diagnostics['rotation_fraction'][changed] = chi['active_rotation_fraction']
    diagnostics['rainfed_headroom'][changed] = np.maximum(high[changed]-rf[changed], 0)
    flags[changed] = 1

    ind = c['india']
    mask = domain & eligible(eco, extent, ind['ecoregion_ids'], ind['minimum_cropland_fraction'])
    mask &= np.isin(crop, [rc['crop_order'].index(x)+1 for x in ['WHE', 'BRL']])
    mask &= (ir > 0) & (rf <= ind['maximum_rainfed_irrigated_ratio']*ir)
    alternatives = []
    for code in ind['summer_crops']:
        dry, _, _, complete = densities(code, ind)
        alternatives.append(np.where(complete, dry, np.nan))
    mixed, count = cereal_mix(rf, alternatives, ind['summer_share'])
    changed = mask & (count > 0) & (mixed > rf)
    diagnostics['rainfed_headroom'][changed] = np.maximum(
        rf[changed]+diagnostics['rainfed_headroom'][changed]-mixed[changed], 0)
    rf[changed] = mixed[changed]
    ir[changed] = np.maximum(ir[changed], rf[changed])
    flags[changed] = 2

    write(out/'cultivated_system_refined.tif', flags.astype(float), profile,
          '1 managed wet-rice fields; 2 summer/winter cereal system; 0 unchanged')
    write(out/'cultivated_system_rainfed_gain.tif', np.where(domain, rf-old_rf, np.nan),
          profile, 'Additional people per improved crop hectare; no new hectares')
    write_json(out/'cultivated_systems.json', {
        'parameters': c, 'china_cells': int((flags == 1).sum()),
        'india_cells': int((flags == 2).sum()), 'population_used': False,
        'natural_support_and_reference_preserved': True,
        'land_and_water_unchanged': True,
        'limitations': ['Field shares and management adoption are inferred, not measured in 1300.',
                       'India is a substitution on rainfed fields, not two summed harvests.',
                       'Primary crop map remains representative; mixed fields are identified in this ledger.']})
    return rf, ir, flags


def irrigation_corrections(base_fraction,served,full,old_rf,old_ir,new_rf,new_ir,livelihood):
    """Baseline-served fields retain their old irrigation benefit exactly once."""
    old_gain=np.maximum(old_ir-np.maximum(old_rf,livelihood),0)
    new_gain=np.maximum(new_ir-np.maximum(new_rf,livelihood),0)
    return np.minimum(served,base_fraction)*(old_gain-new_gain),np.minimum(full,base_fraction)*(old_gain-new_gain)
