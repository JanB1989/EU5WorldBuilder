"""Local climate-conditioned transfer of coarse process outputs.

This is interpolation with environmental covariates, not a new historical model.
No population observation, cell-area multiplier or global yield ranking is used.
"""
import zipfile
import numpy as np
from scipy.spatial import cKDTree
from rasterio.io import MemoryFile
from .provenance import digest


def climate_layers(root, cfg, profile):
    path = root / cfg['path']
    if digest(path) != cfg['sha256']:
        raise ValueError('WorldClim source checksum mismatch')
    layers = []
    with zipfile.ZipFile(path) as archive:
        for variable in cfg['variables']:
            with MemoryFile(archive.read(f'wc2.1_5m_bio_{variable}.tif')) as memory:
                with memory.open() as ds:
                    if (ds.shape != (profile['height'], profile['width']) or
                        ds.crs != profile['crs'] or not ds.transform.almost_equals(profile['transform'])):
                        raise ValueError('WorldClim and GAEZ grids must align')
                    value = ds.read(1, masked=True).filled(np.nan)
                    if variable in [12, 15]:
                        value = np.log1p(value)
                    layers.append(value)
    return np.stack(layers, axis=-1)


def sphere(lon, lat):
    lon, lat = np.radians(lon), np.radians(lat)
    return 6371 * np.column_stack([np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)])


def transfer(source_xy, source_climate, values, target_xy, target_climate,
             strength=1., neighbours=12, radius_km=600.):
    """Convex local interpolation: zeros participate, missing donors do not."""
    result = np.full((len(target_xy), values.shape[1]), np.nan)
    valid = np.isfinite(source_xy).all(axis=1) & np.isfinite(source_climate).all(axis=1) & np.isfinite(values).all(axis=1)
    source_xy, source_climate, values = source_xy[valid], source_climate[valid], values[valid]
    if not len(source_xy):
        return result
    scales = np.nanstd(source_climate, axis=0)
    scales = np.maximum(scales, .1)
    tree = cKDTree(source_xy)
    k = min(neighbours, len(source_xy))
    for start in range(0, len(target_xy), 50000):
        end = min(start+50000, len(target_xy))
        distance, index = tree.query(target_xy[start:end], k=k)
        if k == 1:
            distance, index = distance[:, None], index[:, None]
        climate_distance = np.mean(((source_climate[index] - target_climate[start:end, None])/scales)**2, axis=-1)
        weight = np.exp(-strength*climate_distance - .5*(distance/200.)**2)
        weight[distance > radius_km] = 0
        weight[~np.isfinite(weight)] = 0
        # Coarse cells are support averages, not exact point observations.
        # A finite kernel avoids artificial bullseyes at source-cell centres.
        denom = weight.sum(axis=1)
        good = denom > 0
        result[start:end][good] = np.einsum('nk,nkj->nj', weight[good], values[index[good]])/denom[good, None]
    return result


def reconstruct(root, cfg, profile, lon, lat, coarse, target_mask):
    climate = climate_layers(root, cfg, profile)
    # FORGE is a cell model: aggregate climate to its 2-degree support first.
    h, w, n = climate.shape
    factor = round(abs((lon[1]-lon[0])/profile['transform'].a))
    if (h, w) != (len(lat)*factor, len(lon)*factor):
        raise ValueError('Unexpected FORGE grid support')
    blocks = climate.reshape(len(lat), factor, len(lon), factor, n)
    finite = np.isfinite(blocks)
    count = finite.sum(axis=(1,3))
    coarse_climate = np.divide(np.where(finite, blocks, 0).sum(axis=(1,3)), count,
                               out=np.full(count.shape, np.nan), where=count>0)
    # WorldClim runs north to south; FORGE orientation is read from coordinates.
    if lat[0] < lat[-1]:
        coarse_climate = coarse_climate[::-1]
    if lon[0] > lon[-1]:
        coarse_climate = coarse_climate[:, ::-1]
    xx, yy = np.meshgrid(lon, lat)
    valid = np.isfinite(coarse).all(axis=-1) & np.isfinite(coarse_climate).all(axis=-1)
    xy = sphere(xx[valid], yy[valid]); features = coarse_climate[valid]; values = coarse[valid]
    # Five deterministic geographical folds; selection never uses observed people.
    fold = (np.floor((xx[valid]+180)/10).astype(int) + 2*np.floor((yy[valid]+90)/10).astype(int)) % 5
    comparisons = []
    scale = np.maximum(np.median(values, axis=0), 1e-8)
    for strength in cfg['candidate_climate_strengths']:
        errors = []; evaluated = 0
        for f in range(5):
            train, test = fold != f, fold == f
            pred = transfer(xy[train], features[train], values[train], xy[test], features[test],
                            strength, cfg['neighbours'], cfg['radius_km'])
            good = np.isfinite(pred).all(axis=1)
            error = np.log1p(pred[good]/scale)-np.log1p(values[test][good]/scale)
            errors.extend(np.mean(error**2, axis=1).tolist()); evaluated += int(good.sum())
        comparisons.append({'climate_strength':strength, 'spatial_holdout_log_rmse':float(np.sqrt(np.mean(errors))), 'evaluated_source_cells':evaluated})
    selected = min(comparisons, key=lambda r:r['spatial_holdout_log_rmse'])['climate_strength']
    target = target_mask & np.isfinite(climate).all(axis=-1)
    rows, cols = np.where(target)
    x = profile['transform'].c + (cols+.5)*profile['transform'].a
    y = profile['transform'].f + (rows+.5)*profile['transform'].e
    predicted = transfer(xy, features, values, sphere(x,y), climate[target], selected,
                         cfg['neighbours'], cfg['radius_km'])
    outputs = np.full((*target.shape, coarse.shape[-1]), np.nan, dtype=np.float32)
    outputs[target] = predicted
    report = {'method':'local finite-kernel transfer conditioned on fine climate; no nearest-filled coastal source cells',
              'native_process_resolution_degrees':2, 'climate_resolution_degrees':1/12,
              'source_cells':int(valid.sum()), 'target_cells':int(target_mask.sum()),
              'quantified_cells':int(np.isfinite(predicted).all(axis=1).sum()),
              'selected_climate_strength':selected, 'spatial_cross_validation':comparisons,
              'interpretation':'holdouts test reproduction of FORGE, not historical accuracy; fine detail is inferred',
              'climate_period':'1970-2000; environmental analogue, not a reconstruction of 1300 climate',
              'source':'WorldClim 2.1 temperature, rainfall, rainfall seasonality; FORGE S0-S2 process outputs'}
    return outputs, report
