"""One yield transformation contract for rasters and historical comparisons."""
import json
import numpy as np


def factor(crop, scenario, low, high):
    adjustment = crop.get('scenario_adjustments', {}).get(scenario, {})
    cultivar = float(adjustment.get('cultivar', 1))
    management = float(adjustment.get('management', 1))
    if cultivar <= 0 or management <= 0:
        raise ValueError('Historical yield adjustments must be positive')
    # Annual cropping and fallow are deliberately absent here.
    return (low if scenario == 'LRLM' else high) * cultivar * management


def benchmark_bounds(row, crop, low, high):
    """Select the upper system per cell, then aggregate, never vice versa."""
    if 'scenario_samples_dm' in row and isinstance(row['scenario_samples_dm'], str):
        samples = json.loads(row['scenario_samples_dm'])
        values = {s: np.asarray(a, dtype=float) * factor(crop, s, low, high)
                  for s, a in samples.items()}
        if not len(values['LRLM']):
            return np.nan, np.nan
        return float(np.median(values['LRLM'])), float(np.median(np.maximum(values['HRLM'], values['HILM'])))
    return (row['LRLM_median_dm'] * factor(crop, 'LRLM', low, high),
            max(row['HRLM_median_dm'] * factor(crop, 'HRLM', low, high),
                row['HILM_median_dm'] * factor(crop, 'HILM', low, high)))
