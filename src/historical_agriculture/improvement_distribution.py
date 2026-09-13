"""Complete, nonnegative attribution of existing improvement budgets.

This is an accounting view of the fine-grid component ledger, not a new
capacity estimate or a measured inventory of particular buildings.
"""
import numpy as np
from .improvement_audit import validate_components
from .provenance import write_json

KINDS = ('clearing', 'management', 'irrigation')
STAGES = ('starting', 'remaining', 'maximum')
FIELDS = [f'{s}_{k}_improvement_{v}' for s in STAGES for k in KINDS
          for v in ('units', 'share', 'capacity')]
FIELDS += [f'{s}_distribution_status' for s in STAGES]
FIELDS += ['maximum_improvement_capacity']
from .water_management import FIELDS as WATER_FIELDS, allocate_locations
FIELDS += WATER_FIELDS
DISPLAY_KINDS = ('clearing', 'management', 'water_management')


def allocate(d):
    """Allocate starting and remaining independently; maximum is their sum.

    Only negative contributions within float32 precision are removed. The
    positive contributions are normalized to the unchanged authoritative
    budgets. A substantive signed contribution fails rather than being hidden
    in a percentage. Zero budgets have zero shares and explicit status.
    """
    validate_components(d)
    result = d.copy()
    scale = (d.inert_capacity.abs() + d.starting_capacity.abs()
             + d.maximum_capacity.abs()).to_numpy(float)
    tolerance = 8 * np.finfo(np.float32).eps * scale + 1e-8
    totals = {}
    amounts = {}
    for stage in ('starting', 'remaining'):
        total = d[f'{stage}_improvement_effective_cropland'].to_numpy(float)
        multiplier = d.capacity_multiplier.to_numpy(float)
        if np.any(~np.isfinite(total)) or np.any(total < 0):
            raise ValueError('Invalid improvement budget')
        if np.any((total > 0) & (~np.isfinite(multiplier) | (multiplier <= 0))):
            raise ValueError('Positive improvement budget needs a multiplier')
        raw = d[[f'{stage}_{k}_capacity' for k in KINDS]].to_numpy(float)
        if np.any(raw < -tolerance[:, None]):
            raise ValueError('Signed improvement requires explicit attribution review')
        positive = np.maximum(raw, 0)
        sums = positive.sum(axis=1)
        if np.any((total > 0) & (sums <= 0)):
            raise ValueError('Positive improvement budget has no component evidence')
        weights = np.divide(positive, sums[:, None], out=np.zeros_like(positive),
                            where=sums[:, None] > 0)
        amounts[stage] = weights * total[:, None]
        totals[stage] = total
    amounts['maximum'] = amounts['starting'] + amounts['remaining']
    totals['maximum'] = d.maximum_improvement_effective_cropland.to_numpy(float)
    for stage in STAGES:
        total = totals[stage]
        if not np.allclose(amounts[stage].sum(axis=1), total, rtol=1e-10, atol=1e-7):
            raise ValueError('Improvement distribution does not reconcile')
        shares = np.divide(amounts[stage], total[:, None],
                           out=np.zeros_like(amounts[stage]), where=total[:, None] > 0)
        for j, kind in enumerate(KINDS):
            result[f'{stage}_{kind}_improvement_units'] = amounts[stage][:, j]
            result[f'{stage}_{kind}_improvement_share'] = shares[:, j]
            result[f'{stage}_{kind}_improvement_capacity'] = amounts[stage][:, j] * multiplier
        result[f'{stage}_distribution_status'] = np.where(total > 0, 'allocated', 'no_improvement_budget')
    result['maximum_improvement_capacity'] = totals['maximum'] * multiplier
    return allocate_locations(result)


def report(out, d, fingerprint, mode='equal_area'):
    allocated = allocate(d)
    columns = ['location_tag', 'is_ownable', 'province', 'region', 'capacity_multiplier']
    columns += [f'{s}_improvement_effective_cropland' for s in STAGES]
    allocated[columns + FIELDS].to_csv(out/f'improvement_distribution_{mode}.csv',
                                      index=False, float_format='%.15g')
    if mode == 'equal_area':
        own = allocated.loc[allocated.is_ownable]
        summary = {}
        for stage in STAGES:
            total = float(own[f'{stage}_improvement_effective_cropland'].sum())
            summary[stage] = {
                'total_units': total,
                'total_capacity': float(sum(own[f'{stage}_{k}_improvement_capacity'].sum() for k in DISPLAY_KINDS)),
                'capacity_by_type': {k: float(own[f'{stage}_{k}_improvement_capacity'].sum()) for k in DISPLAY_KINDS},
                'locations_without_budget': int((own[f'{stage}_distribution_status'] == 'no_improvement_budget').sum()),
                'shares': {k: float(own[f'{stage}_{k}_improvement_units'].sum()/total) if total else 0. for k in DISPLAY_KINDS}}
        write_json(out/'improvement_distribution.json', {
            'schema': 1, 'fingerprint': fingerprint, 'map_locations': len(d),
            'ownable_locations': len(own), 'totals_changed': False,
            'shares_are_fractions': True, 'maximum_includes_starting': True,
            'map_quantity': 'Population capacity contributed: improvement units multiplied by the location multiplier. Units remain available for building balancing.',
            'summary': summary,
            'evidence': 'Fine-grid clearing, management and surface-water component ledger, aggregated by location overlap, including the shared game conversion and inherited-system scenario.',
            'uncertainty': 'Model attribution, not observed infrastructure percentages. Management depends on sequential attribution. Water subtypes use global wet settings and dated crop systems; numerical shares inferred. Terraces and groundwater are not separate types.',
            'rounding': 'Negative float32-scale residues are removed and positive components renormalized to the existing budget. Substantive negative components fail.',
            'zero_budget': 'All component shares are zero; no_improvement_budget is explicit, not missing data.'})
    return allocated
