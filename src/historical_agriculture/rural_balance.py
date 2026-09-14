"""User-authorized, explicit game allowance after physical/equal-area calculation."""
import numpy as np
import pandas as pd


def apply(d, settings):
    result=d.copy()
    limit=float(settings['maximum_starting_fill'])
    if not np.isfinite(limit) or limit<1:raise ValueError('Invalid rural fill limit')
    if 'rural_balance_added_capacity' in d:raise ValueError('Rural balance already applied')
    own=d.is_ownable.astype(bool)
    rural=own & d.settlement_context.eq('rural_or_unranked')
    population=pd.to_numeric(d.eu5_start_population,errors='coerce')
    if population[own].isna().any() or (population[own]<0).any():
        raise ValueError('Missing or invalid ownable population for rural balance')
    if np.any(~np.isfinite(d.capacity_multiplier)) or np.any(d.capacity_multiplier<=0):
        raise ValueError('Invalid multiplier for rural balance')
    gain=np.where(rural,np.maximum(population.fillna(0)/limit-d.starting_capacity,0),0)
    units=gain/d.capacity_multiplier
    for key in ['starting_capacity','maximum_capacity','inert_capacity']:
        result['pre_rural_balance_'+key]=d[key]
        result[key]+=gain
    result['rural_balance_added_capacity']=gain
    result['rural_balance_added_units']=units
    result['base_effective_cropland']+=units
    # Same-candidate water reclassification identity still refers to the base
    # before water attribution, including explicit final game allowances.
    if 'pre_water_base_capacity' in result:result['pre_water_base_capacity']+=gain
    for stage in ['starting','maximum','inert']:
        for bound in ['low','high']:
            key=f'{stage}_capacity_{bound}'
            if key in result:result[key]+=gain
    result['rural_balance_status']=np.where(gain>0,'explicit_population_based_game_allowance',
        np.where(rural,'no_allowance_needed','not_eligible'))
    result['maximum_starting_ratio']=result.maximum_capacity/result.starting_capacity.replace(0,np.nan)
    return result


def validate(d, settings):
    limit=float(settings['maximum_starting_fill'])
    rural=d.is_ownable & d.settlement_context.eq('rural_or_unranked')
    p=pd.to_numeric(d.eu5_start_population,errors='coerce').fillna(0)
    gain=d.rural_balance_added_capacity.to_numpy(float)
    expected=np.where(rural,np.maximum(p/limit-d.pre_rural_balance_starting_capacity,0),0)
    np.testing.assert_allclose(gain,expected,rtol=1e-12,atol=1e-7)
    np.testing.assert_allclose(d.rural_balance_added_units*d.capacity_multiplier,gain,rtol=1e-12,atol=1e-7)
    for key in ['starting_capacity','maximum_capacity','inert_capacity']:
        np.testing.assert_allclose(d[key]-d['pre_rural_balance_'+key],gain,rtol=1e-10,atol=1e-7)
    np.testing.assert_allclose(d.maximum_capacity-d.starting_capacity,
        d.pre_rural_balance_maximum_capacity-d.pre_rural_balance_starting_capacity,rtol=1e-10,atol=1e-7)
    if (p[rural]>limit*d.loc[rural,'starting_capacity']+1e-6).any():
        raise ValueError('Rural pressure ceiling failed')
    return {'passed':True,'maximum_rural_starting_fill':limit,
        'affected_locations':int((gain>0).sum()),'added_capacity':float(gain.sum()),
        'physical_estimates_changed':False,'urban_or_nonownable_adjustments':int((gain[~rural]>0).sum()),
        'remaining_improvement_capacity_preserved':True,'population_is_used':True}


def report(out,d,settings,fingerprint):
    from .provenance import write_json
    result=validate(d,settings)
    result.update(fingerprint=fingerprint,settings=settings)
    write_json(out/'rural_balance_validation.json',result)
    cols=['location_tag','province','region','is_ownable','settlement_context','eu5_start_population',
          'capacity_multiplier','pre_rural_balance_starting_capacity','starting_capacity',
          'pre_rural_balance_maximum_capacity','maximum_capacity','rural_balance_added_capacity',
          'rural_balance_added_units','rural_balance_status']
    d[cols].to_csv(out/'rural_balance_ledger.csv',index=False,float_format='%.15g')
    (out/'RURAL_BALANCE.md').write_text(f'''# Explicit rural game-balance allowance

User-authorized exception to population-independent historical estimation.
After equal-area conversion and the base floor, add
`max(population / {settings['maximum_starting_fill']} - starting_capacity, 0)`
to rural ownable locations. Urban and nonownable locations are unchanged.

The addition enters base effective units divided by the unchanged multiplier.
Starting and maximum capacity rise by the same amount. All typed historical
improvements and remaining improvement opportunity stay unchanged. This is
game accommodation, not evidence of extra physical land, food, or water.

Affected locations: {result['affected_locations']:,}.
Added starting capacity: {result['added_capacity']:,.2f} people.
The ceiling is 150% fill, not a guarantee of food sufficiency or growth stability.

[Every location](rural_balance_ledger.csv) · [Checks](rural_balance_validation.json)

Fingerprint: `{fingerprint}`
''')
    return result
