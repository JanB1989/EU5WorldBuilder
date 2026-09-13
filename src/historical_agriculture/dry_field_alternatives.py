"""Historically listed dry-crop alternatives on already cultivated, unserved land.

No additional land is opened. Preference is the existing historical ordering,
not yield maximization. Regional availability is not proof of local adoption;
the transfer remains explicitly inferred and can be disabled for sensitivity.
"""
import json
import numpy as np
from .raster import read,write
from .accounting import annual_food
from .provenance import write_json


def choose(values,ranks):
    """First historically preferred positive, finite candidate; -1 if none."""
    v=np.asarray(values);r=np.asarray(ranks)
    valid=np.isfinite(v)&(v>0)&(r<100)
    score=np.where(valid,r,100)
    best=score.argmin(axis=0)
    return np.where(valid.any(axis=0),best,-1)


def contributions(cultivated,served,full,rf,ir,livelihood,alternative,share=1):
    """Preserve served original crops; new irrigation replaces the same dry land.

    Return starting gain and opportunity gain displaced by future irrigation.
    Subtracting displacement from remaining irrigation prevents double counting.
    """
    if not 0<=share<=1:raise ValueError('Alternative field share outside [0,1]')
    field=np.maximum(cultivated-served,0)*share
    gain=np.maximum(alternative-np.maximum(rf,livelihood),0)
    water=np.maximum(ir-np.maximum(rf,livelihood),0)
    added=field*gain
    displaced=np.minimum(np.maximum(full-served,0),field)*np.minimum(gain,water)
    return added,displaced


def infer_water(cultivated,recorded,command,rf,ir,alternative,share=1):
    """Conditional water-access inference, never an allocation or extra land.

    Only already cultivated cells lacking a viable listed rainfed system qualify.
    Every added request still has to pass the canonical monthly river allocation.
    """
    if not 0<=share<=1:raise ValueError('Inferred water share outside [0,1]')
    eligible=(rf<=1e-6)&(ir>1e-6)&(alternative<=1e-6)
    room=np.maximum(np.minimum(cultivated,command)-recorded,0)
    return recorded+np.where(eligible,room*share,0)


def estimate(root,cfg,domain,profile,crop,rf,historical,served,out):
    rc=json.loads((root/'configs/reconstruction.json').read_text())
    rules=json.loads((root/'configs/regions.json').read_text())['regions']
    eco=read(root/cfg['food_directory']/'food_ecoregion.tif')[0]
    target=domain&(rf<=1e-6)&(historical>1e-8)
    cells=np.flatnonzero(target);ec=eco.ravel()[cells];original=crop.ravel()[cells]
    values=[];ranks=[];specs=[]
    for code,c in enumerate(rc['crop_order'],1):
        rank=np.full(cells.size,100,np.int16);fraction=np.ones(cells.size);position=np.zeros(cells.size);freq=np.ones(cells.size)
        for rule in rules:
            if c not in rule['crops']:continue
            use=np.isin(ec,rule['ecoregion_ids'])&(original!=code)
            m=rc['management'][rule['management']]
            rank[use]=rule['crops'].index(c);fraction[use]=m['cultivated_fraction'];position[use]=m['position'];freq[use]=m['harvests']
        # Match crop-specific rotation overrides once, as in the canonical crop stage.
        rotations=json.loads((root/'configs/rotations.json').read_text())
        for rule in rotations['overrides']:
            if c in rule['crops']:
                use=np.isin(ec,rule['ecoregion_ids'])
                fraction[use]=rule['crop_years']/(rule['crop_years']+rule['fallow_years'])
                freq[use]=rule['harvests_per_active_year']
        lo=read(root/cfg['food_directory']/'crops'/f'{c}_lower.tif')[0].ravel()[cells]
        hi=read(root/cfg['food_directory']/'crops'/f'{c}_high_rainfed.tif')[0].ravel()[cells]
        dm=(1-position)*lo+position*np.maximum(lo,hi)
        density=annual_food(dm,rc['crops'][c],freq,fraction)[2]/(2500*365)
        values.append(density);ranks.append(rank);specs.append(c)
    values=np.asarray(values);selected=choose(values,np.asarray(ranks))
    alt=np.zeros(crop.size,np.float32);chosen=np.zeros(crop.size,np.int16)
    ok=selected>=0
    alt[cells[ok]]=values[selected[ok],np.flatnonzero(ok)]
    chosen[cells[ok]]=selected[ok]+1
    alt=alt.reshape(crop.shape);chosen=chosen.reshape(crop.shape)
    write(out/'dry_field_alternative_crop.tif',np.where(domain,chosen,np.nan),profile,'Crop code for inferred rainfed alternative; 0 no viable listed alternative')
    write(out/'dry_field_alternative_people_ha.tif',np.where(domain,alt,np.nan),profile,'People per rotation hectare, conditional rainfed alternative')
    write_json(out/'dry_field_alternatives.json',{'configuration':cfg['dry_field_alternatives'],
        'target_cells':int(target.sum()),'viable_alternative_cells':int(ok.sum()),
        'chosen_crop_cells':{c:int(np.sum(chosen==i+1)) for i,c in enumerate(specs)},
        'selection':'First viable crop in existing regional historical preference order; finite local lower/high-rainfed inputs only.',
        'no_new_land':True,'no_population_predictor':True,'local_adoption_observed':False})
    return alt,chosen
