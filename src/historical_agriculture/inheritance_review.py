"""Report beneficiaries and adverse cases of the evidence-limited inheritance pass."""
import numpy as np
import pandas as pd
from .provenance import digest,write_json


def report(root,out,current,cfg,fingerprint):
    if not cfg.get('inheritance_review_baseline'):return
    path=root/cfg['inheritance_review_baseline']
    before=pd.read_csv(path,keep_default_na=False).set_index('location_tag')
    after=current.set_index('location_tag').loc[before.index]
    if set(before.index)!=set(current.location_tag):raise ValueError('Inheritance review inventory mismatch')
    for col in ['base_effective_cropland','capacity_multiplier','maximum_improvement_effective_cropland','maximum_capacity','source_starting_crop_ha','source_starting_served_ha','uncalibrated_starting_capacity']:
        old=pd.to_numeric(before[col],errors='coerce').to_numpy(float)
        new=pd.to_numeric(after[col],errors='coerce').to_numpy(float)
        own=after.is_ownable.to_numpy(bool)
        if not np.isfinite(old[own]).all() or not np.isfinite(new[own]).all():
            raise ValueError('Missing protected value for an ownable location: '+col)
        if not np.allclose(old,new,rtol=1e-10,atol=1e-6,equal_nan=True):
            raise ValueError('Inheritance review changed a protected value: '+col)
    drop=before.starting_capacity-after.starting_capacity
    if (drop < -.1).any():raise ValueError('Inheritance guard unexpectedly increased starting support')
    d=after[['province','region','settlement_context','eu5_start_population','is_ownable','starting_capacity','maximum_capacity','source_starting_crop_ha','physical_location_ha']].copy()
    d.eu5_start_population=pd.to_numeric(d.eu5_start_population,errors='coerce')
    d['before_starting_capacity']=before.starting_capacity
    d['capacity_moved_to_remaining']=drop
    d['effective_units_moved_to_remaining']=before.starting_improvement_effective_cropland-after.starting_improvement_effective_cropland
    d['before_fill']=d.eu5_start_population/d.before_starting_capacity.replace(0,np.nan)
    d['after_fill']=d.eu5_start_population/d.starting_capacity.replace(0,np.nan)
    d['new_shortfall']=(d.eu5_start_population<=d.before_starting_capacity)&(d.eu5_start_population>d.starting_capacity)
    d.to_csv(out/'inheritance_review_locations.csv',float_format='%.15g')
    own=d[d.is_ownable];rural=own[own.settlement_context=='rural_or_unranked']
    regions=own.groupby('region').agg(locations=('starting_capacity','size'),before=('before_starting_capacity','sum'),after=('starting_capacity','sum'),moved=('capacity_moved_to_remaining','sum'),new_shortfalls=('new_shortfall','sum'))
    regions.to_csv(out/'inheritance_review_regions.csv',float_format='%.15g')
    rural[rural.new_shortfall].to_csv(out/'inheritance_review_new_shortfalls.csv',float_format='%.15g')
    subsets={}
    for name,q in [('all_ownable',own),('rural_under_5000',rural[(rural.eu5_start_population>0)&(rural.eu5_start_population<5000)]),
                   ('rural_under_5000_and_below_capacity',rural[(rural.eu5_start_population>0)&(rural.eu5_start_population<5000)&(rural.before_fill<1)])]:
        subsets[name]={'locations':len(q),'changed':int((q.capacity_moved_to_remaining>.1).sum()),
            'before_capacity':float(q.before_starting_capacity.sum()),'after_capacity':float(q.starting_capacity.sum()),
            'before_median':float(q.before_starting_capacity.median()),'after_median':float(q.starting_capacity.median()),
            'moved_to_remaining':float(q.capacity_moved_to_remaining.sum()),'new_shortfalls':int(q.new_shortfall.sum())}
    result={'fingerprint':fingerprint,'baseline_sha256':digest(path),'protected_values_unchanged':True,
        'source_supported_works_preserved':True,'population_in_assignment':False,'subsets':subsets,
        'rural_over_start_before':int((rural.eu5_start_population>rural.before_starting_capacity).sum()),
        'rural_over_start_after':int((rural.eu5_start_population>rural.starting_capacity).sum()),
        'new_rural_shortfalls':int(rural.new_shortfall.sum()),
        'interpretation':'Only the extra inferred starting allowance is reduced; the same capacity becomes remaining opportunity. Maximum and base are unchanged. Thresholds and classifications are provisional; HYDE-derived extent is population-informed evidence.',
        'scientific_acceptance':False}
    write_json(out/'inheritance_review.json',result)
    total=subsets['all_ownable'];small=subsets['rural_under_5000']
    (out/'INHERITANCE_REVIEW.md').write_text('\n'.join([
        '# Starting-infrastructure review','',
        'Restrict additional inferred works where reconstructed cultivation is sparse and the regional assessment is extensive, rotation-based or unknown. Managed and intensive classifications retain their prior allowance. Source-supported starting land and irrigation are retained.',
        '',f"Starting capacity: {total['before_capacity']/1e6:,.2f} → {total['after_capacity']/1e6:,.2f} million. {total['moved_to_remaining']/1e6:,.2f} million becomes remaining opportunity.",
        f"Changed locations: {total['changed']:,}. Base, multiplier, maximum and source-supported works are unchanged.",
        f"Rural population below 5,000: {small['changed']:,} locations changed; {small['moved_to_remaining']/1e6:,.2f} million moved to remaining opportunity.",
        f"Rural starting shortfalls: {result['rural_over_start_before']} → {result['rural_over_start_after']}. New cases: {result['new_rural_shortfalls']}; these remain unresolved and are not concealed through local exceptions.",
        '', 'The additional extent allowance equals reconstructed cultivated extent below 1% cultivation, tapering away between 1% and 5%. These are explicit uncertainty assumptions, not observed adoption rates. Population and spare capacity are reporting dimensions only.',
        '', '[Location comparison](inheritance_review_locations.csv) · [Regions](inheritance_review_regions.csv) · [New shortfalls](inheritance_review_new_shortfalls.csv)',
        '',f'Fingerprint: `{fingerprint}`','']))
