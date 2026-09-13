"""Complete, conservative reclassification of existing improvement support."""
import json
import numpy as np
import pandas as pd
from scipy.ndimage import distance_transform_edt
from .raster import read
from .provenance import write_json

KINDS = ('water_supply', 'paddy_control', 'flood_bunds', 'field_drainage', 'polders')
LABELS = ('Water supply systems', 'Paddy water control', 'Flood embankments',
          'Field drainage', 'Coastal drainage / reclamation')
TRANSFER_KINDS = KINDS[1:]
RAW_COLUMNS = [f'{s}_wm_{k}_capacity' for s in ('starting', 'remaining')
               for k in (*TRANSFER_KINDS, 'clearing_transfer', 'management_transfer', 'low', 'high')]
FIELDS = [f'{s}_{k}_improvement_{v}' for s in ('starting', 'remaining', 'maximum')
          for k in (*KINDS, 'water_management') for v in ('units', 'capacity', 'share')]
FIELDS += [f'{s}_water_management_capacity_{b}' for s in ('starting', 'remaining', 'maximum')
           for b in ('low', 'high')]
FIELDS += ['water_management_status', 'wm_inferred_fraction']


def partition_settings(paddy, coastal, flood, wet):
    """Exclusive physical setting shares; paddy works include their small bunds."""
    out = {}
    remaining = np.ones_like(np.asarray(paddy), dtype=float)
    for name, score in [('paddy_control', paddy), ('polders', coastal),
                        ('flood_bunds', flood), ('field_drainage', wet)]:
        score = np.asarray(score, float)
        if np.any(~np.isfinite(score)) or np.any((score < 0) | (score > 1)):
            raise ValueError('Invalid water-management setting')
        out[name] = remaining*score
        remaining -= out[name]
    return out


def transfers(clearing, management, settings, cfg, weight=1., strength=1.):
    """Transfer only assigned clearing/management benefit, never create support."""
    c, m = np.maximum(clearing, 0), np.maximum(management, 0)
    result = {}; ct = np.zeros_like(c); mt = np.zeros_like(m)
    for kind in TRANSFER_KINDS:
        rates = cfg['transfers'][kind]
        a = c*settings[kind]*weight*min(1., rates['clearing']*strength)
        b = m*settings[kind]*weight*min(1., rates['management']*strength)
        result[kind] = a+b; ct += a; mt += b
    if np.any(ct > c+1e-7) or np.any(mt > m+1e-7):
        raise ValueError('Water transfer exceeds its source contribution')
    return result, ct, mt


def native_attribution(root, location_cfg, arrays, domain, crop, out):
    from .water_management_inputs import prepare
    from .water import wc
    cfg = json.loads((root/location_cfg['water_management_config']).read_text())
    cache = prepare(root, cfg)
    with np.load(cache) as z:
        wet = {k: z[k].copy() for k in z.files}
    food = root/location_cfg['food_directory']
    eco, _ = read(food/'food_ecoregion.tif')
    terrain, _ = read(out/'terrain_maximum_factor.tif')
    river, _ = read(root/location_cfg['water_directory']/'river_distance_km.tif')
    elev = wc(root/'data/raw/water', 'elev')
    climate = root/location_cfg['water_directory']
    import rasterio
    with rasterio.open(climate/'natural_monthly_precipitation_mm.tif') as ds:
        rain = np.nansum(ds.read(masked=True).filled(np.nan), axis=0)
    with rasterio.open(climate/'reference_et0_monthly_mm.tif') as ds:
        et = np.nansum(ds.read(masked=True).filled(np.nan), axis=0)
    # Explicit missing-data analogue rather than declaring all unmapped Arctic
    # and tiny coastal land to be dry. Existing positive improvement budget
    # remains the hard bound, including cold/unsuitable controls.
    unknown = domain & ~wet['glwd_covered']
    analog = np.clip((rain/np.maximum(et, 1)-.8)/1.2, 0, 1)*np.nan_to_num(terrain)*cfg['unmapped_wetness_weight']
    wet['wet'] = np.where(unknown, analog, wet['wet'])
    historic = np.where(wet['wetland_1700_covered'], wet['wetland_1700'], 0)
    # The 1700 layer supplies formerly wet settings, not a date of construction.
    wet_score = np.maximum(wet['wet'], historic*cfg['wetland_proxy_weight'])
    near_river = np.nan_to_num(river, nan=1e6) <= cfg['river_distance_km']
    flood_score = np.maximum(wet['flood'], historic*near_river*cfg['wetland_proxy_weight'])
    # Distance from source-land edge: only a coastal screen, not a historical
    # coastline reconstruction or a claim that all coasts needed reclamation.
    coast_km = distance_transform_edt(domain)*9.27
    low_coast = (coast_km <= cfg['coastal_distance_km']) & (elev <= cfg['coastal_lowland_elevation_m'])
    # Formerly reclaimed land may already be absent from the 1700 wetland map.
    # Native 60-second terrain retains below-sea-level pockets smoothed out by
    # 5-minute mean elevation. Restrict to low coastal land, not inland basins.
    from .water_management_inputs import mean_blocks
    below=np.zeros(domain.shape,np.float32)
    dem=root/location_cfg['input_directory']/'hydrology/ETOPO_2022_v1_60s_N90W180_surface.tif'
    with rasterio.open(dem) as ds:
        # ETOPO uses WGS84 + EGM2008 orthometric height (EPSG:9518).
        if ds.shape!=(10800,21600) or ds.crs.to_epsg() not in (4326,9518):
            raise ValueError('Unexpected coastal terrain grid')
        expected=rasterio.Affine(1/60,0,-180,0,-1/60,90)
        if not ds.transform.almost_equals(expected):raise ValueError('Coastal terrain registration mismatch')
        for row in range(0,2160,100):
            n=min(100,2160-row)
            a=ds.read(1,window=rasterio.windows.Window(0,row*5,21600,n*5),masked=True)
            low=((a>=cfg['coastal_minimum_elevation_m']) & (a<cfg['coastal_reclaimed_elevation_m'])).astype(np.uint8).filled(255)
            below[row:row+n]=mean_blocks(low,5,255).filled(0)
    coastal_score = np.maximum(wet['coastal'], low_coast*np.maximum(historic,below))
    rc = json.loads((root/'configs/reconstruction.json').read_text())
    wet_rice = crop == rc['crop_order'].index('RCW')+1
    paddy_score = wet_rice*np.maximum(np.nan_to_num(terrain), cfg['paddy_slope_access_floor'])
    # Modern paddy footprint only reinforces a historically allowed wet-rice
    # assignment. It cannot introduce rice into the pre-Columbian Americas.
    paddy_score = np.where(wet_rice, np.maximum(paddy_score, wet['modern_paddy']), 0)
    settings = partition_settings(np.clip(paddy_score, 0, 1),
        np.clip(coastal_score, 0, 1), np.clip(flood_score, 0, 1), np.clip(wet_score, 0, 1))
    weight = np.full(domain.shape, cfg['historical_system_weight']['unknown'], np.float32)
    for rule in json.loads((root/'configs/regions.json').read_text())['regions']:
        weight[np.isin(eco, rule['ecoregion_ids'])] = cfg['historical_system_weight'][rule['management']]
    # Existing historically researched managed-field refinement supersedes the
    # earlier extensive classification where it was actually applied.
    refined = arrays.get('cultivated_system_refinement_fraction', np.zeros_like(weight)) > 0
    weight[refined] = np.maximum(weight[refined], cfg['historical_system_weight']['managed'])
    for stage in ('starting', 'remaining'):
        c = arrays[f'{stage}_clearing_capacity']; m = arrays[f'{stage}_management_capacity']
        w = weight if stage == 'starting' else cfg['remaining_system_weight']
        central, ct, mt = transfers(c, m, settings, cfg, w)
        for kind, a in central.items(): arrays[f'{stage}_wm_{kind}_capacity'] = a.astype(np.float32)
        arrays[f'{stage}_wm_clearing_transfer_capacity'] = ct.astype(np.float32)
        arrays[f'{stage}_wm_management_transfer_capacity'] = mt.astype(np.float32)
        for suffix, factor in [('low', cfg['sensitivity_factors'][0]), ('high', cfg['sensitivity_factors'][-1])]:
            _, a, b = transfers(c, m, settings, cfg, w, factor)
            arrays[f'{stage}_wm_{suffix}_capacity'] = (a+b).astype(np.float32)
    arrays['wm_inferred_fraction'] = unknown.astype(np.float32)
    write_json(out/'water_management_native.json', {
        'schema': 1, 'categories': dict(zip(KINDS, LABELS)), 'configuration': cfg,
        'native_land_cells': int(domain.sum()), 'source_gap_analogue_cells': int(unknown.sum()),
        'setting_cells': {k: int(np.sum(domain & (v > 0))) for k,v in settings.items()},
        'accounting': 'Transfers from existing game-calibrated clearing/management per native cell; all prior surface-water contribution retained as supply. Base and total support unchanged.',
        'confidence': 'All numerical transfers inferred. Historical-system weights, physical overlap and effect shares are not observed infrastructure fractions.',
        'not_separate_categories': ['reservoirs', 'qanats', 'aqueducts', 'regional hydraulic monuments'],
        'coastal_screen_cells':int(np.sum(domain & low_coast)),
        'reclaimed_terrain_candidate_cells':int(np.sum(domain & low_coast & (below>0))),
        'source_cache_manifest': json.loads((cache.parent/'manifest.json').read_text())})
    return arrays


def allocate_locations(d):
    """Apply native-grid transfers to the already reconciled location budgets."""
    result = d.copy()
    present = [k in d for k in RAW_COLUMNS]
    if any(present) and not all(present):
        raise ValueError('Incomplete native water-management components')
    active = all(present)
    if active and not np.isfinite(d[RAW_COLUMNS].to_numpy(float)).all():
        raise ValueError('Missing native water-management components')
    stage_values = {}
    for stage in ('starting', 'remaining'):
        old = {k: d[f'{stage}_{k}_improvement_capacity'].to_numpy(float)
               for k in ('clearing', 'management', 'irrigation')}
        target = sum(old.values())
        raw_sum = np.maximum(d[[f'{stage}_{k}_capacity' for k in ('clearing','management','irrigation')]].to_numpy(float),0).sum(axis=1)
        factor = np.divide(target, raw_sum, out=np.zeros_like(target), where=raw_sum>0)
        vals = {'water_supply': old['irrigation']}
        ct = d[f'{stage}_wm_clearing_transfer_capacity'].to_numpy(float)*factor if active else np.zeros_like(target)
        mt = d[f'{stage}_wm_management_transfer_capacity'].to_numpy(float)*factor if active else np.zeros_like(target)
        # Only float32 source/aggregation residue may cross a source budget.
        tol = 2e-6*np.maximum(target, 1)
        if np.any(ct > old['clearing']+tol) or np.any(mt > old['management']+tol):
            raise ValueError('Location water transfer exceeds source budget')
        for k in TRANSFER_KINDS:
            vals[k] = d[f'{stage}_wm_{k}_capacity'].to_numpy(float)*factor if active else np.zeros_like(target)
        xsum = sum(vals[k] for k in TRANSFER_KINDS)
        if not np.allclose(xsum, ct+mt, rtol=2e-6, atol=1e-5):
            raise ValueError('Water subtypes do not reconcile to source transfers')
        # Normalize source-precision residual only, preserving exact capacity.
        scale = np.divide(np.minimum(ct,old['clearing'])+np.minimum(mt,old['management']),xsum,
                          out=np.zeros_like(target),where=xsum>0)
        for k in TRANSFER_KINDS: vals[k] *= scale
        vals['clearing'] = np.maximum(old['clearing']-ct, 0)
        vals['management'] = np.maximum(old['management']-mt, 0)
        vals['water_management'] = sum(vals[k] for k in KINDS)
        for bound in ('low', 'high'):
            extra = d[f'{stage}_wm_{bound}_capacity'].to_numpy(float)*factor if active else np.zeros_like(target)
            result[f'{stage}_water_management_capacity_{bound}'] = old['irrigation']+extra
        stage_values[stage] = vals
    stage_values['maximum'] = {k:stage_values['starting'][k]+stage_values['remaining'][k]
                               for k in stage_values['starting']}
    for b in ('low','high'):
        result[f'maximum_water_management_capacity_{b}'] = result[f'starting_water_management_capacity_{b}']+result[f'remaining_water_management_capacity_{b}']
    for stage, vals in stage_values.items():
        target = d[f'{stage}_improvement_effective_cropland'].to_numpy(float)*d.capacity_multiplier.to_numpy(float)
        if not np.allclose(vals['clearing']+vals['management']+vals['water_management'],target,rtol=1e-10,atol=1e-5):
            raise ValueError('Reclassified contribution total changed')
        for kind, amount in vals.items():
            result[f'{stage}_{kind}_improvement_capacity'] = amount
            result[f'{stage}_{kind}_improvement_units'] = amount / d.capacity_multiplier
            result[f'{stage}_{kind}_improvement_share'] = np.divide(amount,target,out=np.zeros_like(amount),where=target>0)
    result['water_management_status'] = np.where(d.get('is_ownable', True),
        'inferred: dated agricultural system + global wet settings; transfers conserve totals' if active else 'legacy supply only',
        'non-ownable: excluded from settlement map')
    fraction=pd.to_numeric(d['wm_inferred_fraction'],errors='raise') if 'wm_inferred_fraction' in d else pd.Series(0.,index=d.index)
    own=d['is_ownable'].astype(bool) if 'is_ownable' in d else pd.Series(True,index=d.index)
    if fraction[own].isna().any():raise ValueError('Missing ownable water-evidence coverage')
    result['wm_inferred_fraction']=fraction.fillna(0.)
    validate(result)
    return result


def validate(d):
    for stage in ('starting','remaining','maximum'):
        a=d[[f'{stage}_{k}_improvement_capacity' for k in KINDS]].to_numpy(float)
        if np.any(~np.isfinite(a)) or np.any(a<0): raise ValueError('Incomplete water maps')
        np.testing.assert_allclose(a.sum(axis=1), d[f'{stage}_water_management_improvement_capacity'],rtol=1e-10,atol=1e-5)
        low=d[f'{stage}_water_management_capacity_low'].to_numpy(float)
        high=d[f'{stage}_water_management_capacity_high'].to_numpy(float)
        central=a.sum(axis=1); tol=2e-6*np.maximum(central,1)
        if not np.isfinite(low).all() or not np.isfinite(high).all() or np.any(low>central+tol) or np.any(high<central-tol):
            raise ValueError('Invalid water-management sensitivity bounds')
        for k in (*KINDS,'water_management','clearing','management'):
            np.testing.assert_allclose(d[f'{stage}_{k}_improvement_units']*d.capacity_multiplier,
                                       d[f'{stage}_{k}_improvement_capacity'],rtol=1e-10,atol=1e-5)
        np.testing.assert_allclose(d[f'{stage}_clearing_improvement_capacity']+d[f'{stage}_management_improvement_capacity']+d[f'{stage}_water_management_improvement_capacity'],
            d[f'{stage}_improvement_effective_cropland']*d.capacity_multiplier,rtol=1e-10,atol=1e-5)
    for k in KINDS:
        np.testing.assert_allclose(d[f'maximum_{k}_improvement_capacity'],d[f'starting_{k}_improvement_capacity']+d[f'remaining_{k}_improvement_capacity'],rtol=1e-10,atol=1e-5)
    return True


def report(out,d,fingerprint):
    validate(d)
    own=d.loc[d.is_ownable].copy()
    records=[]
    for stage in ('starting','maximum'):
        for group,frame in [('World',own)]+[(str(k),v) for k,v in own.groupby('super_region')]:
            for kind in ('clearing','management',*KINDS,'water_management'):
                amount=frame[f'{stage}_{kind}_improvement_capacity']
                records.append({'scope':group,'stage':stage,'type':kind,'capacity':float(amount.sum()),
                    'positive_locations':int((amount>1e-6).sum()),'share_of_total_capacity':float(amount.sum()/frame[f'{stage}_capacity'].sum())})
    table=pd.DataFrame(records)
    table.to_csv(out/'water_management_totals.csv',index=False)
    method=out.parents[1]/'reports/water_management_method.md'
    text=method.read_text()+'\n\n## Evaluated global contributions\n\n| Type | Starting support | Maximum support |\n|---|---:|---:|\n'
    for k in ('clearing','management',*KINDS,'water_management'):
        a=table[(table.scope=='World') & (table.type==k)].set_index('stage').capacity
        text+=f'| {k} | {a["starting"]:,.0f} | {a["maximum"]:,.0f} |\n'
    text+=f'\nAll {len(own):,} ownable locations have all five starting and maximum values. Base and total capacities are unchanged.\n'
    (out/'WATER_MANAGEMENT.md').write_text(text)
    d[['location_tag','province','region','super_region','is_ownable','capacity_multiplier']+FIELDS].to_csv(out/'water_management_ledger.csv',index=False,float_format='%.15g')
    write_json(out/'water_management_validation.json',{'fingerprint':fingerprint,'passed':True,
        'map_locations':len(d),'ownable_locations':len(own),'complete_chosen_types':list(KINDS),
        'checks':['all type values finite and nonnegative','units times multiplier equals capacity',
                  'subtypes sum to water management','clearing + management + water equals original improvements',
                  'maximum equals starting plus remaining'],'totals_changed':False,
        'uncertainty':'0.5x and 1.5x transfer assumptions; not statistical confidence intervals'})
