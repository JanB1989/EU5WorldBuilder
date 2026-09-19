"""Crop-free fertility: the best caloric staple under low-input rain-fed farming.

GAEZ v5 RES05-YXX attainable yields (kg/ha, scenario LRLM: low input, rain-fed)
for the caloric staples are converted to kcal/ha with the CADI kcal table and
reduced, per 5-arcminute cell, to the single best crop. Only that elementwise
maximum reaches the exact-overlap location aggregation: no crop is chosen for a
location beforehand, and no population, cultivation, improvement or soil-type
label enters the grade. Five grades come from frozen quantile thresholds.
"""
from datetime import date
from pathlib import Path
import json

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

RASTER_SHAPE = (2160, 4320)
RASTER_TRANSFORM = (1 / 12, 0, -180, 0, -1 / 12, 90)
NODATA = -9
THRESHOLD_KEY = 'caloric_thresholds_kcal_ha'
RADIUS_KM = 6371.0088
CONTRACT_COLUMNS = ['location_tag', 'map_color_rgb', 'game_zone_class', 'is_ownable', 'longitude', 'latitude',
                    'assignment_source', 'analogue_location', 'analogue_distance_km', 'source_coverage', 'dominant_share',
                    'very_low_share', 'low_share', 'moderate_share', 'high_share', 'very_high_share',
                    'fertility', 'fertility_id', 'inferred', 'low_confidence', 'fertility_score', 'chemistry_imputed_share']
DIAGNOSTIC_COLUMNS = ['best_kcal_per_ha', 'best_crop', 'coverage', 'chemistry_fertility_id']


def crop_table(block):
    """``{code: kcal_per_100g}`` for the included caloric crops of a ``caloric_yield`` block."""
    return {c['code']: float(c['kcal_per_100g']) for c in block['crops'] if c.get('include', True)}


def read_raster(path):
    """One GAEZ v5 RES05-YXX raster as a north-up (2160, 4320) array; contract is checked, never assumed."""
    import rasterio
    with rasterio.open(path) as ds:
        if ds.count != 1 or tuple(ds.shape) != RASTER_SHAPE or ds.crs.to_epsg() != 4326 \
                or not np.allclose(tuple(ds.transform)[:6], RASTER_TRANSFORM):
            raise ValueError('Unexpected GAEZ raster contract: ' + Path(path).name)
        return ds.read(1)


def best_caloric_yield(rasters, kcal_per_100g, nodata=NODATA):
    """Elementwise maximum over crops of ``yield_kg_ha * kcal_per_100g * 10`` (kcal/ha).

    ``rasters`` maps crop code to a yield array (or to a zero-argument callable
    returning it, so large inputs can be loaded one at a time). Crops without a
    kcal entry are ignored. Nodata and negative cells are excluded per crop;
    cells with no valid crop are NaN. Returns ``(best, best_index, codes)`` where
    ``best_index`` holds the index into ``codes`` of the winning crop (-1 where
    none; the first crop wins ties).
    """
    codes = [c for c in rasters if c in kcal_per_100g]
    if not codes: raise ValueError('No caloric crop rasters available')
    best = index = None
    for i, code in enumerate(codes):
        source = rasters[code]
        a = np.asarray(source() if callable(source) else source, dtype=np.float64)
        valid = np.isfinite(a) & (a != nodata) & (a >= 0)
        kcal = np.where(valid, a * (kcal_per_100g[code] * 10.), np.nan)
        if best is None:
            best = kcal; index = np.where(valid, i, -1).astype(np.int16)
        else:
            better = valid & (~np.isfinite(best) | (kcal > best))
            best = np.where(better, kcal, best); index[better] = i
    return best, index, codes


def best_crop_codes(best_index, codes):
    """Crop code per cell for a ``best_index`` array ('' where no crop is valid)."""
    lookup = np.array([''] + list(codes), dtype=object)
    return lookup[np.asarray(best_index, dtype=np.int64) + 1]


def aggregate(weights, values):
    """Overlap-weighted location mean of a north-up grid, excluding NaN cells.

    ``weights`` is the sparse location x cell overlap matrix (rows in inventory
    order, columns the ``.ravel()`` of a (2160, 4320) north-up grid). Returns
    ``(mean, coverage)``: NaN mean where no valid cell overlaps; coverage is the
    valid overlap area divided by the location's total overlap area.
    """
    v = np.asarray(values, dtype=np.float64).ravel()
    finite = np.isfinite(v)
    den = np.asarray(weights @ finite.astype(np.float64)).ravel()
    num = np.asarray(weights @ np.where(finite, v, 0.)).ravel()
    mean = np.divide(num, den, out=np.full(len(den), np.nan), where=den > 0)
    total = np.asarray(weights.sum(axis=1)).ravel()
    coverage = np.divide(den, total, out=np.zeros(len(den)), where=total > 0)
    return mean, coverage


def area_share(weights, mask, den):
    """Share of a location's valid overlap area whose cells satisfy ``mask``."""
    part = np.asarray(weights @ np.asarray(mask, dtype=np.float64).ravel()).ravel()
    return np.divide(part, den, out=np.zeros(len(den)), where=den > 0)


def thresholds(values_ownable, quantiles=(0.2, 0.4, 0.6, 0.8)):
    """Grade boundaries as quantiles of the finite ownable-location values."""
    v = np.asarray(values_ownable, dtype=np.float64); v = v[np.isfinite(v)]
    if not len(v): raise ValueError('No ownable caloric values for thresholds')
    return [float(x) for x in np.quantile(v, quantiles)]


def classify(values, bounds):
    """Grade ids 1..5, lower-bound inclusive (a value equal to a boundary takes the upper grade); NaN -> 0."""
    v = np.asarray(values, dtype=np.float64)
    ids = 1 + np.searchsorted(np.asarray(bounds, dtype=np.float64), v, side='right')
    return np.where(np.isfinite(v), ids, 0).astype(np.int64)


def resolve_thresholds(cfg, config_path, values_ownable, key=THRESHOLD_KEY):
    """Frozen thresholds from the config, or compute them once and write them back.

    Returns ``(thresholds, frozen_now)``. Boundaries are frozen on first use so
    later rebuilds with different inputs keep the same class meaning.
    """
    if cfg.get(key): return [float(x) for x in cfg[key]], False
    bounds = [round(x, 1) for x in thresholds(values_ownable)]
    cfg[key] = bounds
    cfg['thresholds_frozen_on'] = date.today().isoformat()
    cfg['thresholds_note'] = ('Frozen on first caloric build as the 20/40/60/80% quantiles of the ownable-location mean '
                              'best caloric yield (kcal/ha, GAEZ v5 LRLM). Later rebuilds keep these boundaries; delete '
                              'the key to re-derive them deliberately.')
    Path(config_path).write_text(json.dumps(cfg, indent=2) + '\n')
    return bounds, True


def nearest_donors(lon, lat, donors, targets):
    """Nearest donor (great-circle on the unit sphere) for each target; returns ``(donor_index, distance_km)``."""
    r = np.deg2rad(np.column_stack([np.asarray(lon, dtype=np.float64), np.asarray(lat, dtype=np.float64)]))
    xyz = np.column_stack([np.cos(r[:, 1]) * np.cos(r[:, 0]), np.cos(r[:, 1]) * np.sin(r[:, 0]), np.sin(r[:, 1])])
    chord, near = cKDTree(xyz[donors]).query(xyz[targets])
    return np.asarray(donors)[near], 2 * RADIUS_KM * np.arcsin(np.minimum(chord / 2, 1))


def location_table(inv, zones, weights, best, best_index, codes, cfg, config_path, chemistry=None):
    """Complete per-zone table in the fertility contract plus diagnostic columns.

    Ownable locations are graded from their overlap-weighted mean best kcal/ha;
    ownable locations with no valid overlap inherit the nearest ownable donor
    (recorded). Non-ownable zones keep ``fertility_id`` 0. ``chemistry`` maps
    location tags to the retained chemistry grade (0 where unknown).
    """
    names = list(cfg['levels'])
    d = inv[['location_tag', 'map_color_rgb', 'calibrated_lon', 'calibrated_lat']].rename(columns={'calibrated_lon': 'longitude', 'calibrated_lat': 'latitude'})
    d = d.merge(zones[['location_tag', 'game_zone_class', 'is_ownable']], on='location_tag', validate='one_to_one', sort=False)
    if d.location_tag.tolist() != inv.location_tag.tolist(): raise ValueError('Fertility overlap order changed')
    if weights.shape[0] != len(d): raise ValueError('Fertility overlap rows do not match the inventory')
    n = len(d)
    mean, coverage = aggregate(weights, best)
    own = d.is_ownable.to_numpy(bool); has = coverage > 0
    bounds, frozen_now = resolve_thresholds(cfg, config_path, mean[own & has])
    finite = np.isfinite(best).ravel(); den = np.asarray(weights @ finite.astype(np.float64)).ravel()
    cell_class = classify(best, bounds).ravel()
    shares = np.column_stack([area_share(weights, cell_class == k, den) for k in range(1, 6)])
    flat = np.asarray(best_index).ravel()
    crop_area = np.column_stack([np.asarray(weights @ (flat == i).astype(np.float64)).ravel() for i in range(len(codes))])
    crop = np.array(list(codes), dtype=object)[crop_area.argmax(axis=1)]; crop[~has] = ''
    water = d.game_zone_class.str.contains('sea_zones|lakes').to_numpy()
    source = np.where(water, 'water', np.where(own, 'GAEZ v5 best caloric staple', 'Native non-ownable zone')).astype(object)
    analogue = np.full(n, '', dtype=object); distance = np.zeros(n)
    missing = own & ~has; donors = np.flatnonzero(own & has)
    if missing.any():
        if not len(donors): raise ValueError('No ownable location has caloric evidence')
        near, km = nearest_donors(d.longitude.to_numpy(), d.latitude.to_numpy(), donors, np.flatnonzero(missing))
        mean[missing] = mean[near]; shares[missing] = shares[near]; crop[missing] = crop[near]
        source[missing] = 'nearest ownable caloric location; inferred'
        analogue[missing] = d.location_tag.to_numpy()[near]; distance[missing] = km
    ids = classify(mean, bounds); ids[~own] = 0
    if not ((ids[own] >= 1) & (ids[own] <= 5)).all(): raise ValueError('Ownable location without a fertility grade')
    label = np.where(water, 'water', 'unassigned').astype(object)
    label[ids > 0] = np.asarray(names, dtype=object)[ids[ids > 0] - 1]
    d['assignment_source'] = source; d['analogue_location'] = analogue; d['analogue_distance_km'] = distance
    d['source_coverage'] = coverage; d['dominant_share'] = shares.max(axis=1)
    for k, name in enumerate(names): d[name + '_share'] = shares[:, k]
    d['fertility'] = label; d['fertility_id'] = ids; d['inferred'] = missing
    d['low_confidence'] = own & ((coverage < .5) | (shares.max(axis=1) < .5) | missing)
    d['fertility_score'] = np.where(ids > 0, mean, np.nan)
    d['chemistry_imputed_share'] = 0.
    d['best_kcal_per_ha'] = mean; d['best_crop'] = crop; d['coverage'] = coverage
    extras = zones[~zones.location_tag.isin(d.location_tag)].copy()
    if extras.is_ownable.any(): raise ValueError('Ownable location absent from the overlap inventory')
    ew = extras.game_zone_class.str.contains('sea_zones|lakes').to_numpy()
    extras['longitude'] = np.nan; extras['latitude'] = np.nan
    extras['assignment_source'] = np.where(ew, 'water', 'Native non-ownable zone')
    extras['analogue_location'] = ''; extras['analogue_distance_km'] = 0.; extras['source_coverage'] = 0.; extras['dominant_share'] = 0.
    for name in names: extras[name + '_share'] = 0.
    extras['fertility'] = np.where(ew, 'water', 'unassigned'); extras['fertility_id'] = 0
    extras['inferred'] = False; extras['low_confidence'] = False; extras['fertility_score'] = np.nan
    extras['chemistry_imputed_share'] = 0.; extras['best_kcal_per_ha'] = np.nan; extras['best_crop'] = ''; extras['coverage'] = 0.
    d = pd.concat([d, extras], ignore_index=True).sort_values('location_tag').reset_index(drop=True)
    d['chemistry_fertility_id'] = d.location_tag.map(chemistry or {}).fillna(0).astype(int)
    d = d[CONTRACT_COLUMNS + DIAGNOSTIC_COLUMNS]
    ownable = d[d.is_ownable]
    summary = {'thresholds_kcal_ha': bounds, 'thresholds_frozen_now': frozen_now,
               'class_counts_ownable': {name: int((ownable.fertility == name).sum()) for name in names},
               'coverage_ownable': {'zero': int((ownable.coverage == 0).sum()), 'below_half': int((ownable.coverage < .5).sum()),
                                    'min': float(ownable.coverage.min()), 'median': float(ownable.coverage.median()), 'mean': float(ownable.coverage.mean())},
               'best_kcal_per_ha_ownable': {'min': float(np.nanmin(ownable.best_kcal_per_ha)), 'median': float(np.nanmedian(ownable.best_kcal_per_ha)),
                                            'max': float(np.nanmax(ownable.best_kcal_per_ha))},
               'best_crop_ownable': {k: int(v) for k, v in ownable.best_crop.value_counts().items()},
               'mixed_class_ownable': int((ownable.dominant_share < .5).sum())}
    return d, summary
