"""Additional building types carved from the existing ledger by explicit, evidence-based rules.

- oasis_irrigation: the water-supply ledger of locations that have no surface water in the
  displayed attributes (no river level, no lake) but sit in arid or steppe climates; the
  historical works there were qanats, wells and oasis channels rather than river canals.
- pastoral: the share of natural capacity that stands on pastoral land (World Builder
  pastoral_area_ha / physical area). It is carved out of the natural target so the attribute
  fit no longer has to carry herding land, and represented as a flat building with no expansion.

Both are gated by attribute rules from the building-assignment config; no per-location term.
"""
import numpy as np
import pandas as pd
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
EXTENSION_KINDS=('oasis_irrigation','pastoral')


def _gate(d,rules):
    if not rules:return np.ones(len(d),bool)
    mask=np.zeros(len(d),bool)
    for rule in rules:
        m=np.ones(len(d),bool)
        for attr,allowed in rule.items():m&=d[attr].astype(str).isin([str(a) for a in allowed]).to_numpy()
        mask|=m
    return mask


def pastoral_share(index):
    loc=pd.read_csv(ROOT/'artifacts/locations/locations_equal_area.csv',keep_default_na=False,usecols=['location_tag','pastoral_area_ha','physical_location_ha']).set_index('location_tag')
    area=pd.to_numeric(loc.physical_location_ha,errors='coerce').reindex(index).to_numpy(float)
    past=pd.to_numeric(loc.pastoral_area_ha,errors='coerce').reindex(index).fillna(0).to_numpy(float)
    return np.clip(np.divide(past,area,out=np.zeros(len(index)),where=area>0),0,1)


def extend(d,ledger,cfg):
    """Return (ledger with the extension kinds, natural carve-out per location in people).

    ``d`` is the attribute frame indexed by location_tag (with natural_capacity_people or natural_capacity),
    ``ledger`` the disjoint improvement ledger, ``cfg`` the building-assignment config (``extensions`` block).
    """
    ext=cfg.get('extensions') or {}
    led=ledger.set_index('location_tag').loc[d.index].copy()
    carve=np.zeros(len(d))
    if ext.get('oasis_irrigation',{}).get('enabled'):
        g=_gate(d,ext['oasis_irrigation']['gate'])
        for stage in ('starting','maximum'):
            ws=led[f'{stage}_water_supply_capacity'].to_numpy(float)
            led[f'{stage}_oasis_irrigation_capacity']=np.where(g,ws,0.);led[f'{stage}_water_supply_capacity']=np.where(g,0.,ws)
    else:
        for stage in ('starting','maximum'):led[f'{stage}_oasis_irrigation_capacity']=0.
    if ext.get('pastoral',{}).get('enabled'):
        g=_gate(d,ext['pastoral']['gate']);share=pastoral_share(d.index)*float(ext['pastoral'].get('share_multiplier',1.0))
        natural=(d['natural_capacity_people'] if 'natural_capacity_people' in d else d['natural_capacity']).to_numpy(float)
        carve=np.where(g,natural*np.clip(share,0,1),0.)
        led['starting_pastoral_capacity']=carve;led['maximum_pastoral_capacity']=carve*float(ext['pastoral'].get('maximum_multiplier',1.0))
    else:
        led['starting_pastoral_capacity']=0.;led['maximum_pastoral_capacity']=0.
    return led.reset_index(),carve
