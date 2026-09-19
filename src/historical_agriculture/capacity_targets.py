"""People-denominated capacity targets and the disjoint typed improvement ledger.

The game model fits flat capacity from attributes and conditional buildings,
times development. Its targets are therefore plain people per location:
natural capacity (land before represented improvements), starting capacity
and maximum capacity, plus one disjoint ledger of typed improvements for the
start and for the maximum. The historical base/multiplier split, the
multiplier bounds and any unit floors are diagnostics only. No population
column is written here.
"""
import numpy as np
import pandas as pd
from .water_management import KINDS as WATER_KINDS, RAW_COLUMNS
from .improvement_audit import CAPACITY_COLUMNS, ROUNDING_COLUMNS
from .water_boundary import FIELDS as BOUNDARY_FIELDS

LEDGER_KINDS=('clearing','management')+tuple(WATER_KINDS)
STAGES=('starting','maximum')
IDENTITY=['location_tag','location_id','province','region','super_region','macro_region','is_ownable','modelled_land','physical_location_ha']
TARGETS=['natural_capacity','starting_capacity','maximum_capacity','starting_improvement_capacity','remaining_capacity']
LEDGER_COLUMNS=[f'{stage}_{kind}_capacity' for stage in STAGES for kind in LEDGER_KINDS]
DIAGNOSTICS=['reference_people_per_effective_ha','capacity_multiplier','base_effective_cropland',
    'starting_improvement_effective_cropland','maximum_improvement_effective_cropland','evidence_status','source_rule']
FORBIDDEN=['eu5_start_population','starting_fill','rural_balance_added_capacity','rural_balance_added_units']


def derive(frame):
    """Split an allocated location frame into targets, ledger and diagnostics."""
    d=frame.reset_index(drop=True)
    missing=[c for c in IDENTITY+['inert_capacity','starting_capacity','maximum_capacity','unbounded_reference_multiplier'] if c not in d]
    missing+=[f'{stage}_{kind}_improvement_capacity' for stage in STAGES for kind in LEDGER_KINDS if f'{stage}_{kind}_improvement_capacity' not in d]
    if missing:raise ValueError('Targets need allocated location columns: '+', '.join(missing))
    # CSV round trips carry empty strings for non-modelled zones; treat them as zero capacity and missing diagnostics.
    num=lambda c:pd.to_numeric(d[c],errors='coerce').to_numpy(float)
    targets=d[IDENTITY].copy()
    targets['physical_location_ha']=num('physical_location_ha')
    targets['natural_capacity']=np.nan_to_num(num('inert_capacity'))
    targets['starting_capacity']=np.nan_to_num(num('starting_capacity'))
    targets['maximum_capacity']=np.nan_to_num(num('maximum_capacity'))
    targets['starting_improvement_capacity']=targets.starting_capacity-targets.natural_capacity
    targets['remaining_capacity']=targets.maximum_capacity-targets.starting_capacity
    targets['reference_people_per_effective_ha']=num('unbounded_reference_multiplier')
    for c in ['evidence_status','source_rule']:targets[c]=d[c] if c in d else ''
    ledger=d[['location_tag','is_ownable','macro_region','region']].copy()
    ledger['natural_capacity']=targets.natural_capacity
    ledger['starting_capacity']=targets.starting_capacity
    ledger['maximum_capacity']=targets.maximum_capacity
    for stage in STAGES:
        total=np.zeros(len(d))
        for kind in LEDGER_KINDS:
            value=np.nan_to_num(num(f'{stage}_{kind}_improvement_capacity'))
            ledger[f'{stage}_{kind}_capacity']=value;total=total+value
        ledger[f'{stage}_ledger_total']=total
        ledger[f'{stage}_residual']=(targets[f'{stage}_capacity']-targets.natural_capacity).to_numpy(float)-total
    diagnostics_columns=['location_tag']+[c for c in DIAGNOSTICS if c in d and c!='reference_people_per_effective_ha']
    diagnostics_columns+=[c for c in d if c in RAW_COLUMNS or c in CAPACITY_COLUMNS or c in ROUNDING_COLUMNS or c in BOUNDARY_FIELDS
        or c.endswith(('_improvement_units','_improvement_share','_distribution_status','_capacity_low','_capacity_high'))
        or c.startswith(('base_land_floor_','rural_balance_','pre_rural_balance_','game_','uncalibrated_'))]
    diagnostics=d[list(dict.fromkeys(diagnostics_columns))].copy()
    return targets,ledger,diagnostics


def validate_targets(targets,inventory=None):
    forbidden=[c for c in FORBIDDEN if c in targets]
    if forbidden:raise ValueError('Population must not enter capacity targets: '+', '.join(forbidden))
    if targets.location_tag.duplicated().any():raise ValueError('Duplicate target location')
    if inventory is not None and set(targets.location_tag)!=set(inventory.location_tag):raise ValueError('Targets do not cover the location inventory')
    a=targets[['natural_capacity','starting_capacity','maximum_capacity']].to_numpy(float)
    if not np.isfinite(a).all():raise ValueError('Nonfinite capacity target')
    tol=1e-6*np.maximum(np.abs(a).max(axis=1),1)
    if np.any(a[:,0]<-tol) or np.any(a[:,1]<a[:,0]-tol) or np.any(a[:,2]<a[:,1]-tol):
        raise ValueError('Capacity targets must satisfy 0 <= natural <= starting <= maximum')
    own=targets.is_ownable.astype(bool).to_numpy()
    if np.any(a[own,2]<=0):raise ValueError('Ownable location without positive maximum capacity')
    for name,expected in [('starting_improvement_capacity',a[:,1]-a[:,0]),('remaining_capacity',a[:,2]-a[:,1])]:
        if not np.allclose(targets[name],expected,rtol=1e-9,atol=1e-6):raise ValueError('Target identity mismatch: '+name)
    return {'complete_inventory':inventory is not None,'ordered':True,'population_free':True,
        'ownable_locations':int(own.sum()),'natural_total':float(a[own,0].sum()),'starting_total':float(a[own,1].sum()),'maximum_total':float(a[own,2].sum())}


def validate_ledger(ledger):
    checks={}
    for stage in STAGES:
        cols=[f'{stage}_{kind}_capacity' for kind in LEDGER_KINDS]
        a=ledger[cols].to_numpy(float)
        if not np.isfinite(a).all() or np.any(a<-1e-9):raise ValueError('Ledger entries must be finite and nonnegative: '+stage)
        target=(ledger[f'{stage}_capacity']-ledger.natural_capacity).to_numpy(float)
        if np.any(np.abs(a.sum(axis=1)-target)>1e-6*np.maximum(np.abs(target),1)):
            raise ValueError('Typed ledger does not sum to the improvement capacity: '+stage)
        checks[stage]={'total':float(a.sum()),'by_kind':{k:float(a[:,i].sum()) for i,k in enumerate(LEDGER_KINDS)}}
    for kind in LEDGER_KINDS:
        s=ledger[f'starting_{kind}_capacity'].to_numpy(float);m=ledger[f'maximum_{kind}_capacity'].to_numpy(float)
        if np.any(m<s-1e-6*np.maximum(np.abs(s),1)):raise ValueError('Maximum ledger below starting ledger: '+kind)
    checks['disjoint_and_exact']=True
    return checks


def write(out,frame,mode):
    """Write targets, ledger and diagnostics for one area mode; return the checks."""
    from .provenance import write_json
    targets,ledger,diagnostics=derive(frame)
    checks={'targets':validate_targets(targets),'ledger':validate_ledger(ledger)}
    targets.to_csv(out/f'capacity_targets_{mode}.csv',index=False,float_format='%.15g')
    ledger.to_csv(out/f'improvement_ledger_{mode}.csv',index=False,float_format='%.15g')
    diagnostics.to_csv(out/f'improvement_ledger_diagnostics_{mode}.csv',index=False,float_format='%.15g')
    checks['columns']={'targets':list(targets.columns),'ledger_kinds':list(LEDGER_KINDS)}
    checks['units']='people; equal-area game units' if mode=='equal_area' else 'people; physical location area'
    checks['note']='Natural capacity is land before represented improvements. The ledger is one disjoint partition of improvement capacity; base/multiplier units, transfers and sensitivity bounds are diagnostics only. No population enters these files.'
    write_json(out/f'capacity_targets_{mode}.json',checks)
    return checks
