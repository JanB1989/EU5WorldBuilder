"""Traditional irrigation extent per location from the Historical Irrigation Dataset (Siebert et al. 2015).

The HID gives area equipped for irrigation (ha) per 5-arc-minute cell for 1900-2005 on exactly the grid of
the location overlap matrix (2160 x 4320, north-up). The 1900 layer is pre-modern irrigation almost
everywhere it matters (Nile, Indus, Tigris-Euphrates, North China, Central Asia), so it is the evidence for
"this land is watered" that a rain-fed yield model cannot see. Output: the irrigated share of every location's
land, used by the fertility grade as the weight of the irrigated staple potential. Infrastructure evidence,
not population.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from .location_geometry import overlap_matrix
from .location_inventory import read_zone_inventory
from .provenance import write_json

ROOT = Path(__file__).resolve().parents[2]
EARTH_RADIUS_M = 6_371_000.0


def read_ascii_grid(path):
    """ESRI ASCII grid -> (values float32 array north-up, header dict)."""
    header = {}
    with open(path) as handle:
        for _ in range(6):
            key, value = handle.readline().split()
            header[key.lower()] = float(value)
    values = np.loadtxt(path, skiprows=6, dtype=np.float32)
    if values.shape != (int(header['nrows']), int(header['ncols'])):
        raise ValueError(f'{path}: unexpected grid shape {values.shape}')
    return values, header


def cell_area_ha(nrows=2160, ncols=4320):
    """Area of each 5-arc-minute cell in hectares (varies with latitude only), north-up."""
    lat_edges = np.deg2rad(np.linspace(90, -90, nrows + 1))
    band = EARTH_RADIUS_M ** 2 * np.deg2rad(360 / ncols) * (np.sin(lat_edges[:-1]) - np.sin(lat_edges[1:]))
    return np.repeat(band[:, None] / 1e4, ncols, axis=1)


def extract_grid(archive, inner_zip, member, target):
    """Pull one ASCII grid out of the nested HID archive (idempotent)."""
    target = Path(target)
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as outer:
        with outer.open(inner_zip) as inner_bytes:
            with zipfile.ZipFile(inner_bytes) as inner:
                target.write_bytes(inner.read(member))
    return target


def build(config_path=None):
    cp = Path(config_path or ROOT / 'configs/irrigation.json').resolve()
    cfg = json.loads(cp.read_text())
    raw = ROOT / 'data/raw/location_inputs'
    out = ROOT / cfg['output_directory']
    out.mkdir(parents=True, exist_ok=True)
    grid_path = extract_grid(ROOT / cfg['archive'], cfg['inner_zip'], cfg['member'], ROOT / cfg['grid'])
    aei, header = read_ascii_grid(grid_path)
    nodata = float(header.get('nodata_value', -9999))
    fraction = np.where(aei == nodata, 0., aei) / cell_area_ha(*aei.shape)
    fraction = np.clip(fraction, 0, 1).astype(np.float64)
    inv = pd.read_parquet(raw / 'inventory.parquet').sort_values('location_tag').reset_index(drop=True)
    weights, geometry = overlap_matrix(ROOT, inv, ROOT / 'artifacts/locations')
    if weights.shape != (len(inv), aei.size):
        raise ValueError('Irrigation overlap grid mismatch')
    share = np.asarray(weights @ fraction.ravel()).ravel() / np.maximum(np.asarray(weights.sum(axis=1)).ravel(), 1e-12)
    ha = np.asarray(weights @ np.where(aei == nodata, 0., aei).ravel()).ravel() / np.maximum(np.asarray(weights @ np.ones(aei.size)).ravel(), 1e-12)
    zones = read_zone_inventory(raw)
    d = inv[['location_tag']].merge(zones[['location_tag', 'is_ownable']], on='location_tag', how='left')
    d['irrigated_share'] = share
    d['irrigated_share'] = d.irrigated_share.where(d.is_ownable.fillna(False), 0.)
    d['aei_ha_per_cell_mean'] = ha
    d['year'] = int(cfg['year'])
    d['product'] = cfg['member'].rsplit('.', 1)[0]
    d.to_csv(out / 'locations.csv', index=False, float_format='%.6f')
    own = d[d.is_ownable.fillna(False)]
    report = {
        'schema_version': 1, 'source': cfg['source'], 'grid': str(Path(cfg['grid'])), 'year': int(cfg['year']),
        'ownable_locations': int(len(own)), 'ownable_with_irrigation': int((own.irrigated_share > 0).sum()),
        'ownable_share_quantiles': {q: float(own.irrigated_share.quantile(float(q))) for q in ('0.5', '0.9', '0.95', '0.99')},
        'ownable_above_5_percent': int((own.irrigated_share >= 0.05).sum()), 'ownable_above_20_percent': int((own.irrigated_share >= 0.20).sum()),
        'geometry': geometry,
        'notes': ['irrigated_share = area-weighted mean over the location of (area equipped for irrigation / cell area), HID 1900.',
                  'Population-free: the HID downscales national and sub-national irrigation statistics with cropland maps; it is infrastructure evidence.'],
    }
    write_json(out / 'report.json', report)
    return report
