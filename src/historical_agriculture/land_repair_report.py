"""Global corrections may increase or reduce support: report both explicitly."""
import html,json
import numpy as np
import pandas as pd
from .provenance import write_json,digest


def report(root,out,current,cfg,fingerprint):
    source=root/cfg['pressure_comparison_baseline']
    if not source.exists():
        (out/'regional_comparison.html').write_text('<h1>Global land repair</h1><p>Before-state is unavailable; current values remain independently validated.</p>')
        return
    a=pd.read_csv(source,keep_default_na=False).set_index('location_tag')
    b=current.set_index('location_tag').loc[a.index]
    own=b.is_ownable
    if not np.allclose(a.capacity_multiplier,b.capacity_multiplier,rtol=1e-12,atol=1e-9):
        raise ValueError('Land correction changed productivity multipliers')
    data=b[['province','region','macro_region','eu5_start_population']].copy()
    for col in ['inert_capacity','starting_capacity','maximum_capacity']:
        data['before_'+col]=a[col];data['after_'+col]=b[col];data['delta_'+col]=b[col]-a[col]
    data[own].to_csv(out/'regional_location_changes.csv',float_format='%.15g')
    totals=data[own].groupby('region')[[c for c in data if c.startswith(('before_','after_','delta_'))]].sum()
    totals.to_csv(out/'regional_changes.csv',float_format='%.15g')
    audit={'fingerprint':fingerprint,'baseline_sha256':digest(source),'scope':'global land/water correction; increases and decreases are legitimate results',
           'productivity_multipliers_preserved':True,'population_used_as_predictor':False,'terrain_configuration':cfg['terrain_access'],
           'starting_increases':int((data.loc[own,'delta_starting_capacity']>1e-6).sum()),'starting_decreases':int((data.loc[own,'delta_starting_capacity']<-1e-6).sum())}
    write_json(out/'regional_comparison.json',audit)
    rows=''.join('<tr><td>'+html.escape(name.replace('_region','').replace('_',' ').title())+'</td>'+''.join(f'<td>{r[c]/1e6:.3f}</td>' for c in ['before_starting_capacity','after_starting_capacity','before_maximum_capacity','after_maximum_capacity'])+'</tr>' for name,r in totals.iterrows())
    explanation=('Crop-specific, consecutive climate seasons replace the generic six highest-evaporation months. River budgets, crop-yield rasters, productivity multipliers and historical cultivated extent are unchanged. Calendars are explicit agronomic analogues, not measured medieval sowing dates.' if cfg.get('crop_season_config') else 'Fine-pixel slope classes replace whole-cell relief penalties. Access weights remain inferred; finer terrain data may revise them. Yield and productivity multipliers are unchanged.')
    if cfg.get('dry_field_alternatives'):
        explanation+=' On already cultivated dry fields with zero representative-crop yield, use the first viable historically listed alternative. Local adoption is inferred; no additional fields or free irrigation are introduced. Future irrigation displaces that same dry-crop support.'
    if cfg.get('inferred_cultivated_water_share',0)>0:
        explanation+=' Where no listed rainfed alternative works, existing cultivation inside the low-lift river command screen implies a conditional starting water-access request. Recorded HYDE irrigation and inferred requests are retained separately; all requests pass the same river budget.'
    if cfg.get('agricultural_game_calibration'):
        explanation='The current candidate adds a shared starting-infrastructure scenario based on historical crop-system classes and cultivated footprint, then compresses extreme low support in game units. Base support can rise. Location productivity multipliers are unchanged. Physical food estimates, land and water remain separately recorded; converted capacities are not literal food-production measurements. See GAME_CALIBRATION.md for the complete evaluation.'
    (out/'regional_comparison.html').write_text('''<!doctype html><meta charset="utf-8"><title>Global land and water correction</title><style>body{background:#0c1420;color:#dce8ef;font:16px system-ui;max-width:1000px;margin:40px auto}a{color:#80c4f5}td,th{padding:8px;text-align:right}td:first-child{text-align:left}</style><a href="index.html">Map</a><h1>Global land and water correction</h1><p>Equal-area capacity, in millions. '''+explanation+''' Both increases and decreases are reported; historical cultivation is retained.</p><table><tr><th>Region</th><th>Starting before</th><th>Starting now</th><th>Maximum before</th><th>Maximum now</th></tr>'''+rows+'</table><p><a href="regional_location_changes.csv">Every location</a> · <a href="regional_comparison.json">Checks</a> · <a href="rural_pressure.html">Rural shortfalls</a></p><small>'+fingerprint+'</small>')
