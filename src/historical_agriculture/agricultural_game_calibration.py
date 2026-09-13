"""Shared native-grid historical-system assignments and explicit game conversion.

The physical food estimate and the game capacity scale are different outputs.
This module never reads population, country ownership, settlement rank or location IDs.
"""
import json
import numpy as np
from .raster import read
from .provenance import write_json
from .improvement_audit import CAPACITY_COLUMNS


def convert(support,reference,exponent):
    s,r=np.broadcast_arrays(np.asarray(support,dtype=float),np.asarray(reference,dtype=float))
    if not 0<exponent<=1 or np.any(r<=0) or not np.isfinite(r).all():
        raise ValueError('Invalid support conversion')
    if np.any(s<0) or not np.isfinite(s).all():raise ValueError('Invalid physical support')
    return np.maximum(s,r*np.power(s/r,exponent))


def activation(extent,maximum,half_saturation):
    h,m=np.broadcast_arrays(np.asarray(extent,float),np.asarray(maximum,float))
    if half_saturation<=0 or np.any((m<0)|(m>1)) or not np.isfinite(m).all():
        raise ValueError('Invalid inheritance configuration')
    if np.any((h<0)|(h>1)) or not np.isfinite(h).all():raise ValueError('Invalid historical extent')
    return m*h/(h+half_saturation)


def transform(base,start,maximum,components,active,reference,exponent):
    """Telescoping component attribution preserves both capacity identities.

    First activate part of the existing remaining improvements. Then convert
    support into game units, distributing each stage's nonlinear conversion
    proportionally over its existing signed component ledger.
    """
    b,s,u,a=np.broadcast_arrays(base,start,maximum,active)
    if np.any(b<0) or np.any(s<b-1e-7) or np.any(u<s-1e-7) or np.any((a<0)|(a>1)):
        raise ValueError('Invalid physical scenario ordering')
    s=np.maximum(b,s);u=np.maximum(s,u)
    inherited=s+a*(u-s)
    gb=convert(b,reference,exponent);gs=convert(inherited,reference,exponent);gu=convert(u,reference,exponent)
    first=np.divide(gs-gb,inherited-b,out=np.ones_like(gs),where=inherited>b)
    last=np.divide(gu-gs,u-inherited,out=np.ones_like(gs),where=u>inherited)
    converted={}
    for kind in ['clearing','management','irrigation']:
        initial=components[f'starting_{kind}_capacity'];remaining=components[f'remaining_{kind}_capacity']
        converted[f'starting_{kind}_capacity']=(initial+a*remaining)*first
        converted[f'remaining_{kind}_capacity']=(1-a)*remaining*last
    return gb,gs,gu,converted,inherited


def apply(root,cfg,arrays,historical_extent,food_type,domain,out):
    path=cfg.get('agricultural_game_calibration')
    if not path:return arrays
    c=json.loads((root/path).read_text());ic=c['inheritance'];gc=c['support_conversion']
    eco,_=read(root/cfg['food_directory']/'food_ecoregion.tif')
    rules=json.loads((root/'configs/regions.json').read_text())['regions']
    ceiling=np.full(domain.shape,ic['unknown_system_activation'],float)
    for rule in rules:
        ceiling[np.isin(eco,rule['ecoregion_ids'])]=ic['maximum_opportunity_activation'][rule['management']]
    h=np.clip(np.nan_to_num(historical_extent),0,1)
    active=activation(h,ceiling,ic['historical_extent_half_saturation'])
    active=np.where(domain,active,0)
    reference=np.where((food_type>=1)&(food_type<=18),gc['crop_reference_support'],gc['noncrop_reference_support'])
    b=arrays['baseline_support_per_land_ha'];s=arrays['starting_support_per_land_ha'];u=arrays['maximum_support_per_land_ha']
    components={name:arrays[name] for name in CAPACITY_COLUMNS}
    gb,gs,gu,converted,inherited=transform(b,s,u,components,active,reference,gc['exponent'])
    result=dict(arrays)
    for name,values in [('uncalibrated_base_support',b),('uncalibrated_starting_support',s),('uncalibrated_maximum_support',u),('inherited_physical_starting_support',inherited)]:
        result[name]=values.copy()
    for name in CAPACITY_COLUMNS:result['uncalibrated_'+name]=arrays[name].copy()
    result.update(converted)
    result['baseline_support_per_land_ha']=gb;result['starting_support_per_land_ha']=gs;result['maximum_support_per_land_ha']=gu
    result['game_inheritance_activation_fraction']=active
    result['game_conversion_reference_support']=reference
    # Retain reconstructed source extents separately from the inherited scenario.
    for current,limit in [('starting_crop_fraction','maximum_crop_fraction'),('starting_served_fraction','maximum_served_fraction')]:
        old=arrays[current];end=arrays[limit]
        if np.any(old[domain]>end[domain]+1e-7):raise ValueError('Invalid resource opportunity')
        result['source_'+current]=old.copy()
        result[current]=old+active*np.maximum(end-old,0)
        if np.any(result[current][domain]>end[domain]+1e-7):raise ValueError('Inheritance exceeds physical opportunity')
    # Existing diagnostic contribution undergoes the same initial-stage conversion.
    initial_scale=np.divide(gs-gb,inherited-b,out=np.ones_like(gs),where=inherited>b)
    result['dry_field_alternative_support']=arrays['dry_field_alternative_support']*initial_scale
    result['game_inheritance_support']=gs-convert(s,reference,gc['exponent'])
    result['game_conversion_added_support']=convert(s,reference,gc['exponent'])-s
    result['game_base_added_support']=gb-b
    write_json(out/'agricultural_game_calibration.json',{
        'configuration':c,'population_in_formula':False,'location_specific_parameters':False,
        'inherits_from_existing_simultaneous_maximum':True,'physical_water_or_land_created':False,
        'base_can_change':True,'productivity_multiplier_changes':False,
        'inherited_cells':int(np.sum(domain&(active>0))),
        'inherited_fraction_quantiles':np.quantile(active[domain],[0,.25,.5,.75,.95,1]).tolist(),
        'conversion_changed_cells':int(np.sum(domain&(gs>inherited+1e-9))),
        'units':'Converted support is game capacity density. Uncalibrated rasters retain physical food-support estimates.',
        'scientific_acceptance':False})
    return result
