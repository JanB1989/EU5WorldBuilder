"""Fingerprint-bound before/after evidence for the regional refinement round."""
import json,html
import numpy as np
import pandas as pd
from .provenance import digest,write_json

def report(root,out,current,cfg,fingerprint):
    if cfg.get('terrain_access'):
        from .land_repair_report import report as land_report
        return land_report(root,out,current,cfg,fingerprint)
    baseline=root/'data/processed/regional_round_02_before/locations_equal_area.csv'
    if not baseline.exists():
        (out/'regional_comparison.html').write_text('<h1>Regional refinement</h1><p>The four-value dataset is complete. The optional archived baseline is unavailable for a before/after comparison.</p>')
        return
    a=pd.read_csv(baseline,keep_default_na=False).set_index('location_tag')
    b=current.set_index('location_tag')
    if set(a.index)!=set(b.index):raise ValueError('Regional comparison inventory mismatch')
    b=b.loc[a.index];own=b.is_ownable
    flags=b[[x+'_refinement_share' for x in ['china','andes','prairie','improvement_reference','management_envelope','cultivated_system']]].fillna(0).max(axis=1)>0
    untouched=own&~flags
    physical_comparison=b.copy()
    for col in ['inert_capacity','starting_capacity','maximum_capacity']:
        physical_comparison[col]=b[col]-b.get('base_land_floor_added_capacity',0)
    for col in ['inert_capacity','starting_capacity','maximum_capacity','capacity_multiplier']:
        if not np.array_equal(a.loc[untouched,col].to_numpy(float),physical_comparison.loc[untouched,col].to_numpy(float)):
            # Serialized baseline has 15 significant digits; tolerate only that precision.
            if not np.allclose(a.loc[untouched,col],physical_comparison.loc[untouched,col],rtol=1e-13,atol=1e-9):raise ValueError('Unrelated locations changed: '+col)
    fixed_base=own&(b.prairie_refinement_share.fillna(0)==0)&(b.management_envelope_refinement_share.fillna(0)==0)
    if not np.allclose(a.loc[fixed_base,'inert_capacity'],physical_comparison.loc[fixed_base,'inert_capacity'],rtol=1e-13,atol=1e-9):raise ValueError('Base changed outside prairie/envelope exceptions')
    data=pd.DataFrame(index=b.index)
    for col in ['region','macro_region','eu5_start_population']:data[col]=b[col]
    data['refinement_applies']=flags
    for col in ['inert_capacity','starting_capacity','maximum_capacity','capacity_multiplier']:
        data['before_'+col]=a[col];data['after_'+col]=b[col];data['delta_'+col]=b[col]-a[col]
    data[own].to_csv(out/'regional_location_changes.csv',float_format='%.15g')
    totals=data[own].groupby('region')[[c for c in data if c.startswith(('before_','after_','delta_')) and 'multiplier' not in c]].sum()
    totals.to_csv(out/'regional_changes.csv',float_format='%.15g')
    unchanged=int(untouched.sum());changed=int((own&flags).sum())
    audit={'schema':1,'fingerprint':fingerprint,'baseline_sha256':digest(baseline),'variant':cfg.get('refinement_variant','central'),'all_ownable_locations':int(own.sum()),'locations_in_refinement_masks':changed,'unrelated_locations_checked':unchanged,'unrelated_values_unchanged_within_serialization_precision':True,'base_preserved_outside_prairie_and_management_envelope':True,'historical_validation':'Inferred candidate; contextual population does not determine selection. Cold-adapted field yields and prairie-access fractions require refinement.'}
    write_json(out/'regional_comparison.json',audit)
    names=['south_china_region','east_china_region','great_plains_region','andes_region','mesoamerica_region','france_region','egypt_region','mongolia_region']
    rows=[]
    for name in names:
        if name not in totals.index:continue
        r=totals.loc[name];rows.append('<tr><td>'+html.escape(name.replace('_region','').replace('_',' ').title())+'</td>'+''.join(f'<td>{r[c]/1e6:.3f}</td>' for c in ['before_starting_capacity','after_starting_capacity','before_maximum_capacity','after_maximum_capacity'])+'</tr>')
    sources=json.loads((root/'evidence/location_refinements.json').read_text())['sources']
    links=' · '.join('<a href="'+html.escape(s['url'],quote=True)+'">'+html.escape(s['id'])+'</a>' for s in sources)
    page=f"""<!doctype html><meta charset="utf-8"><title>Regional changes</title><style>body{{background:#0c1420;color:#dce8ef;font:16px system-ui;max-width:1000px;margin:40px auto;padding:20px}}a{{color:#80c4f5}}p{{line-height:1.6}}table{{width:100%;border-collapse:collapse}}td,th{{text-align:right;padding:12px;border-bottom:1px solid #405269}}td:first-child,th:first-child{{text-align:left}}small{{color:#a9b9c9}}</style><a href="index.html">← Location map</a><h1>Regional refinement: {audit['variant']}</h1><p>All capacities below are million people in the equal-area game representation. The reference area is fixed across candidates.</p><table><tr><th>Region</th><th>Starting before</th><th>Starting now</th><th>Maximum before</th><th>Maximum now</th></tr>{''.join(rows)}</table><p>{changed:,} ownable locations intersect a refinement mask. Geographical values in all {unchanged:,} unrelated ownable locations are preserved before the separately reported game floor. The global base-land floor adds {b.get("base_land_floor_added_capacity",0).sum()/1e6:.3f} million capacity to the displayed totals.</p><p><b>Interpretation:</b> Chinese cultivated lowlands receive managed-rice assumptions; prairie farmland requires preparation; qualifying Andean cultivated highlands receive an explicitly inferred cold-adapted-field analogue. Cultivated-field adjustments represent documented seasonal cereals and managed wet-rice techniques as improvement contributions, with unchanged natural support and multiplier. A global voluntary-management envelope preserves lower-input options when adjusted scenarios reverse. A conditional maize reference replaces foraging-based improvement multipliers in selected Plains/Rockies cells; this normalization changes no total support. No population fitting, new fishing, invented terrace hectares or global balancing factor.</p><p>Sources support mechanisms and conditional analogues; numerical thresholds, prairie access and transferred historical yields remain uncertain. This is an evaluated candidate, not accepted global historical balance.</p><p><a href="regional_location_changes.csv">Every ownable location</a> · <a href="regional_changes.csv">Regional totals</a> · <a href="regional_comparison.json">Checks and fingerprint</a></p><p>{links}</p><small>Fingerprint {fingerprint}</small>"""
    (out/'regional_comparison.html').write_text(page)
