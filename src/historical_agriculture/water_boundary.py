"""Evidence-conditioned transfer of baseline cultivation into maintained works."""
import numpy as np
from .water_management import KINDS

REQUESTS=[f'base_water_{k}_requested_capacity' for k in KINDS]
APPLIED=[f'base_water_{k}_transferred_capacity' for k in KINDS]
FIELDS=REQUESTS+APPLIED+['base_water_transferred_capacity','pre_water_base_capacity']


def requests(base, crop_gain_share, baseline_area, cultivated_area, settings, cfg):
    """Wild support and uncultivated baseline land cannot become historic works.

    The crop-gain share is the positive physical advantage of baseline crops
    over the displaced livelihood. The same fraction of the converted baseline
    is eligible, preserving its natural-food component on the game scale.
    """
    cover=np.minimum(np.divide(cultivated_area,baseline_area,
        out=np.zeros_like(np.asarray(base),dtype=float),where=baseline_area>0),1)
    eligible=base*np.clip(crop_gain_share,0,1)*np.clip(cover,0,1)
    return {k:eligible*settings.get(k,0)*cfg['base_dependency'][k] for k in KINDS}


def apply(d,cfg):
    """Final geometry normalization retains the equal-area base floor exactly."""
    d=d.copy()
    request=d[REQUESTS].to_numpy(float)
    if np.any(~np.isfinite(request)) or np.any(request<0):
        raise ValueError('Invalid baseline-water requests')
    old=d.inert_capacity.to_numpy(float)
    if np.any(request.sum(axis=1)>old+1e-5):
        raise ValueError('Baseline-water request exceeds original base')
    reference=cfg['equal_reference_area_ha']
    scale=reference/d.physical_location_ha.to_numpy(float)
    # The game floor is based on the ORIGINAL physical baseline. Preserve that
    # allowance and reserve sufficient base after both normalizations.
    physical=d.uncalibrated_base_capacity.to_numpy(float)
    protected=np.minimum(old,np.minimum(physical,
        cfg.get('equal_area_base_land_floor',0)*d.capacity_multiplier.to_numpy(float)/scale))
    available=np.maximum(old-protected,0)
    total=request.sum(axis=1)
    factor=np.minimum(np.divide(available,total,out=np.ones_like(total),where=total>0),1)
    assigned=request*factor[:,None];delta=assigned.sum(axis=1)
    d['pre_water_base_capacity']=old
    d['base_water_transferred_capacity']=delta
    for j,k in enumerate(KINDS):
        d[APPLIED[j]]=assigned[:,j]
        if k in ('water_supply','flood_bunds') and np.any(assigned[:,j]>0):
            raise ValueError('Natural flooding and baseline rainfed water supply remain natural')
        if k!='water_supply':d[f'starting_wm_{k}_capacity']+=assigned[:,j]
    # Management is the staging source in the legacy three-component ledger;
    # the full added amount transfers straight to its named water subtype.
    d['starting_management_capacity']+=delta
    d['starting_wm_management_transfer_capacity']+=delta
    for b in ('low','high'):d[f'starting_wm_{b}_capacity']+=delta
    d['inert_capacity']-=delta
    units=delta/d.capacity_multiplier
    d['base_effective_cropland']-=units
    for stage in ('starting','maximum'):
        d[f'{stage}_improvement_effective_cropland']+=units
    d['starting_improvement_capacity']+=delta
    return d


def report(root,out,d,fingerprint, historical_comparison=True):
    import pandas as pd
    from .provenance import digest,write_json
    if not historical_comparison:
        # New physical inputs supersede the fixed-output historical experiment.
        # Check the within-candidate conservation identity, not old geography.
        np.testing.assert_allclose(d.pre_water_base_capacity-d.inert_capacity,
            d.base_water_transferred_capacity,rtol=1e-10,atol=1e-6)
        summary={'fingerprint':fingerprint,'within_candidate_base_transfer_conserved':True,
            'historical_comparison':'Superseded by agricultural-system repair; see rural_system_comparison.csv',
            'base_support_reclassified':float(d.loc[d.is_ownable,'base_water_transferred_capacity'].sum())}
        write_json(out/'water_boundary_validation.json',summary)
        return summary
    baseline=root/'data/processed/water_boundary_before.csv'
    old=pd.read_csv(baseline,keep_default_na=False).set_index('location_tag')
    new=d.set_index('location_tag').loc[old.index]
    for key in ['starting_capacity','maximum_capacity','capacity_multiplier','remaining_capacity']:
        np.testing.assert_allclose(new[key],old[key],rtol=1e-12,atol=1e-6)
    delta=new.base_water_transferred_capacity
    np.testing.assert_allclose(old.inert_capacity-new.inert_capacity,delta,rtol=1e-10,atol=1e-6)
    for stage in ('starting','maximum'):
        np.testing.assert_allclose((new[f'{stage}_improvement_effective_cropland']-old[f'{stage}_improvement_effective_cropland'])*new.capacity_multiplier,delta,rtol=1e-10,atol=1e-6)
    own=new.is_ownable
    summary={'fingerprint':fingerprint,'baseline_commit':'87eef4a',
        'baseline_sha256':digest(baseline),'totals_conserved':True,
        'base_floor_pass':bool((new.loc[own].base_effective_cropland>=1000-1e-7).all()),
        'locations_with_base_transfer':int((delta[own]>1e-6).sum()),
        'base_support_reclassified':float(delta[own].sum()),'stages':{}}
    rows=new[['region','is_ownable','base_water_transferred_capacity']].copy()
    for stage in ('starting','maximum'):
        key=f'{stage}_water_management_improvement_capacity'
        total=new.loc[own,f'{stage}_capacity'].sum()
        summary['stages'][stage]={'before_water_share':float(old.loc[own,key].sum()/total),
            'after_water_share':float(new.loc[own,key].sum()/total)}
        rows[f'{stage}_water_before']=old[key];rows[f'{stage}_water_after']=new[key]
    rows.to_csv(out/'water_boundary_comparison.csv',float_format='%.15g')
    rows[rows.is_ownable].groupby('region').sum(numeric_only=True).to_csv(out/'water_boundary_regions.csv')
    write_json(out/'water_boundary_validation.json',summary)
    return summary
