"""Reconciled improvement attribution; no population fitting or new capacity."""
import numpy as np
from .provenance import write_json

ROUNDING_COLUMNS=['starting_component_rounding_capacity','remaining_component_rounding_capacity']
CAPACITY_COLUMNS=[f"{stage}_{kind}_capacity" for stage in ["starting","remaining"] for kind in ["clearing","management","irrigation"]]

def decompose(b,start,maximum,served,full,rf,ir,livelihood,low_rf):
    """Sequential attribution: clear at low input, apply management, then water.

    Management is signed when historically adjusted scenarios reverse. The base
    stays intact, including any practices embedded in its baseline-access land.
    These are model differences, not independently observed infrastructure.
    """
    opened=np.maximum(start-b,0)
    extra=np.maximum(maximum-b,0)-opened
    low_gain=np.maximum(low_rf-livelihood,0)
    dry_gain=np.maximum(rf-livelihood,0)
    water_gain=np.maximum(ir-np.maximum(rf,livelihood),0)
    return {
        'starting_clearing_capacity':opened*low_gain,
        'starting_management_capacity':opened*(dry_gain-low_gain),
        'starting_irrigation_capacity':served*water_gain,
        'remaining_clearing_capacity':extra*low_gain,
        'remaining_management_capacity':extra*(dry_gain-low_gain),
        'remaining_irrigation_capacity':(full-served)*water_gain,
    }

def reconcile_rounding(d):
    """Record float32 raster cancellation explicitly; never change support totals."""
    for stage,target in [('starting','starting_improvement_capacity'),('remaining','remaining_capacity')]:
        cols=[f'{stage}_{kind}_capacity' for kind in ['clearing','management','irrigation']]
        residual=d[target]-d[cols].sum(axis=1)
        scale=d[cols].abs().sum(axis=1)+d.inert_capacity.abs()+d.starting_capacity.abs()+d.maximum_capacity.abs()
        bound=4*np.finfo(np.float32).eps*scale+1e-8
        if np.any(np.abs(residual)>bound):raise ValueError('Component discrepancy exceeds raster precision')
        d[f'{stage}_component_rounding_capacity']=residual
    return d

def validate_components(d):
    for stage,target in [('starting','starting_improvement_capacity'),('remaining','remaining_capacity')]:
        cols=[f'{stage}_{kind}_capacity' for kind in ['clearing','management','irrigation']]
        if not np.isfinite(d[cols].to_numpy(float)).all():raise ValueError('Missing improvement components')
        rounding=d.get(f'{stage}_component_rounding_capacity',0)
        if not np.isfinite(np.asarray(rounding)).all():raise ValueError('Missing component rounding account')
        if not np.allclose(d[cols].sum(axis=1)+rounding,d[target],rtol=1e-9,atol=1e-7):raise ValueError('Improvement components fail reconciliation: '+stage)
    return True

def report(out,d,fingerprint):
    validate_components(d)
    own=d.loc[d.is_ownable].copy()
    cols=['location_tag','province','region','macro_region','capacity_multiplier','unbounded_reference_multiplier','inert_capacity','starting_capacity','maximum_capacity']+CAPACITY_COLUMNS+ROUNDING_COLUMNS+[
        'starting_crop_ha','maximum_crop_ha','starting_served_ha','maximum_served_ha',
        'crop_candidate_area_ha','rotation_active_area_equivalent_ha','pastoral_area_ha',
        'rainfed_management_headroom_people_per_crop_ha']
    own[cols].to_csv(out/'improvement_components_equal_area.csv',index=False,float_format='%.15g')
    summaries={}
    for group in ['province','region','macro_region']:
        total=own.groupby(group)[['inert_capacity','starting_capacity','maximum_capacity']+CAPACITY_COLUMNS+ROUNDING_COLUMNS+['starting_crop_ha','maximum_crop_ha','starting_served_ha','maximum_served_ha','crop_candidate_area_ha','rotation_active_area_equivalent_ha','pastoral_area_ha']].sum()
        total['multiplier_median']=own.groupby(group).capacity_multiplier.median()
        total['maximum_starting_ratio']=total.maximum_capacity/total.starting_capacity
        total['infrastructure_share']=1-total.inert_capacity/total.starting_capacity
        total['maximum_land_starting_ratio']=total.maximum_crop_ha/total.starting_crop_ha.replace(0,np.nan)
        total['maximum_water_starting_ratio']=total.maximum_served_ha/total.starting_served_ha.replace(0,np.nan)
        total['active_rotation_fraction']=total.rotation_active_area_equivalent_ha/total.crop_candidate_area_ha.replace(0,np.nan)
        total.to_csv(out/f'improvement_{group}_audit.csv',float_format='%.15g')
        summaries[group]=total
    regions=summaries['region']
    cases=['north_china_region','east_china_region','south_china_region','egypt_region','france_region','indochina_region','mongolia_region','ukraine_region','central_asia_region']
    case=regions.loc[regions.index.intersection(cases)]
    case.to_csv(out/'improvement_focus_cases.csv',float_format='%.15g')
    report={
        'schema':1,'fingerprint':fingerprint,'coverage':len(own),
        'capacity_changed_by_attribution':False,'base_capacity_frozen':True,
        'component_accounts_reconcile':True,
        'allocation_order':['clearing at low-input yield with the assigned rotation','management increment on that improved land','irrigation after assigned management'],
        'maximum_definition':'Expansion of clearing and irrigation with existing crop, rotation and management held fixed. Not a full technology/management maximum.',
        'not_independently_quantified':['drainage','terraces','management improvements on baseline-access land','future changes in rotations and management'],
        'maximum_absolute_component_rounding_people':float(own[ROUNDING_COLUMNS].abs().max().max()),
        'negative_management_locations':int((own.starting_management_capacity<-.0001).sum()),
        'high_multiplier_no_remaining_capacity':int(((own.capacity_multiplier>=4)&(own.remaining_capacity<=.0001)).sum()),
        'method_note':'Float32 source-raster cancellation is recorded in separate rounding columns, within a bound derived from source precision. The management component depends on attribution order; clearing receives low-input yield, including the assigned fallow. Interactions are assigned once. Physical hectares are diagnostic and not equal-area game units. Rainfed headroom compares adjusted high-input versus current yields on identical crop/rotation, per crop-candidate hectare; it is not an activated capacity gain or a medieval feasibility claim.',
        'scientific_acceptance':False}
    write_json(out/'improvement_audit.json',report)
    lines=['# Improvement audit','',f'Fingerprint: `{fingerprint}`','',
        'All ownable locations have a reconciled starting and remaining component ledger. Base and total capacities are unchanged by this attribution.',
        '', '## Interpretation','',report['maximum_definition'],'',report['method_note'],'',
        'Drainage and terraces may be embedded in existing land and yield assumptions, but are not separately quantified; they are not assumed to be zero.',
        '', '## Focus cases','',
        '| Region | Starting support (million) | Clearing | Management | Irrigation | Remaining support | Max/start |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for name,row in case.iterrows():
        vals=[row.starting_capacity,row.starting_clearing_capacity,row.starting_management_capacity,row.starting_irrigation_capacity,row.maximum_capacity-row.starting_capacity]
        lines.append('| '+name.replace('_region','').replace('_',' ')+' | '+' | '.join(f'{x/1e6:.3f}' for x in vals)+f' | {row.maximum_starting_ratio:.2f} |')
    lines+=['','Component and remaining-support columns above are million people; clearing and management are conditional model attributions, not historical observations.','',
        'Full coverage: `improvement_components_equal_area.csv`. Physical areas and regional diagnostics: `improvement_region_audit.csv`.']
    (out/'IMPROVEMENTS.md').write_text('\n'.join(lines)+'\n')
