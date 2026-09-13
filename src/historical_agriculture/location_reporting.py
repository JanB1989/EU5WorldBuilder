"""One focused EU5 location map; all location values remain inspectable."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from matplotlib import colormaps
from .provenance import write_json

METRICS=[('starting_capacity','Starting capacity','people'),('maximum_capacity','Maximum capacity','people'),('inert_capacity','Base contribution','people'),('capacity_multiplier','Location multiplier','people / effective ha'),('starting_improvement_capacity','Starting improvement contribution','people'),('maximum_improvement_capacity','Maximum improvement contribution','people'),('remaining_capacity','Remaining improvement contribution','people'),('starting_fill','Starting population / capacity','ratio'),('inferred_area_share','Inferred input share','share')]
IMPROVEMENT_METRICS = [(f'{stage}_{kind}_improvement_capacity', f'{label} · {name}', 'people')
            for stage, label in [('starting', 'Starting'), ('maximum', 'Maximum')]
            for kind, name in [('clearing', 'Clearing'), ('management', 'Field management'), ('water_management', 'Water management')]]
from .water_management import KINDS as WATER_KINDS, LABELS as WATER_LABELS
WATER_METRICS = [(f'{stage}_{kind}_improvement_capacity', f'{label} · {name}', 'people')
    for stage, label in [('starting','Starting'),('maximum','Maximum')]
    for kind,name in zip(WATER_KINDS,WATER_LABELS)]
WATER_KEYS = {m[0] for m in WATER_METRICS}
METRICS += IMPROVEMENT_METRICS + WATER_METRICS
IMPROVEMENT_KEYS = {m[0] for m in IMPROVEMENT_METRICS}

def encode_location_lookup(ids):
    """Lossless scanline runs; classic local script avoids canvas readback/CORS."""
    ids=np.asarray(ids)
    if ids.ndim!=2 or not np.issubdtype(ids.dtype,np.integer) or np.any(ids<0):
        raise ValueError('Expected nonnegative 2D integer location IDs')
    rows=[]
    for row in ids:
        ends=np.r_[np.flatnonzero(row[1:]!=row[:-1])+1,len(row)]
        starts=np.r_[0,ends[:-1]]
        rows.append(np.column_stack((ends,row[starts])).ravel().tolist())
    return {'width':ids.shape[1],'height':ids.shape[0],'rows':rows}

def report(out,d,raw,cfg,audit,fingerprint):
    Image.MAX_IMAGE_PIXELS=None
    src=np.asarray(Image.open(raw/'locations.png').convert('RGB'))
    lut=np.zeros(2**24,dtype=np.uint32)
    lut[[int(x,16) for x in d.map_color_rgb]]=np.arange(1,len(d)+1)
    # Preserve a native-pixel ID raster for exact location geometry access.
    native=np.zeros(src.shape,dtype=np.uint8)
    for y in range(0,len(src),128):
        a=src[y:y+128].astype(np.uint32);ids=lut[(a[...,0]<<16)|(a[...,1]<<8)|a[...,2]]
        native[y:y+128, :,0]=(ids>>16)&255;native[y:y+128,:,1]=(ids>>8)&255;native[y:y+128,:,2]=ids&255
    Image.fromarray(native).save(out/'location_ids_native.png')
    idsimg=Image.fromarray(native).resize((4096,2048),Image.Resampling.NEAREST)
    idsimg.save(out/'location_ids.png');a=np.asarray(idsimg).astype(np.uint32);ids=(a[...,0]<<16)|(a[...,1]<<8)|a[...,2]
    (out/'location_lookup.js').write_text('window.LOCATION_LOOKUP='+json.dumps(encode_location_lookup(ids),separators=(',',':'))+';\n')
    palette=(colormaps['RdYlGn'](np.linspace(0,1,256))[:,:3]*255).astype(np.uint8)
    fields=['location_tag','province','region','eu5_start_population']+[m[0] for m in METRICS]+['inert_capacity','starting_improvement_capacity','physical_location_ha','coastline_transfer_share','terrestrial_analogue_share','unbounded_reference_multiplier','multiplier_bound_status','china_refinement_share','andes_refinement_share','prairie_refinement_share','improvement_reference_refinement_share','management_envelope_refinement_share','cultivated_system_refinement_share','starting_location_rank','settlement_context','starting_clearing_capacity','starting_management_capacity','starting_irrigation_capacity','remaining_clearing_capacity','remaining_management_capacity','remaining_irrigation_capacity','evidence_status','modelled_land','is_ownable','game_zone_class','centroid_x','centroid_y']
    d=d.copy()
    d['base_land_floor_added_units']=0.
    d['base_land_floor_added_capacity']=0.
    fields+=['base_land_floor_added_units','base_land_floor_added_capacity','base_effective_cropland','starting_improvement_effective_cropland','maximum_improvement_effective_cropland','remaining_improvement_effective_cropland']
    from .location_area import equal_area
    equal,comparison=equal_area(d,cfg.get("equal_reference_area_ha"),cfg.get("equal_area_base_land_floor",0))
    from .improvement_distribution import report as distribution_report, FIELDS as distribution_fields
    d=distribution_report(out,d,fingerprint,'physical')
    equal=distribution_report(out,equal,fingerprint)
    from .water_management import report as water_report
    water_report(out,equal,fingerprint)
    fields+=distribution_fields
    fields=list(dict.fromkeys(fields))
    data=json.loads(equal[fields].to_json(orient='records'))
    equal.to_csv(out/'locations_equal_area.csv',index=False,float_format='%.15g')
    primary=['location_tag','base_effective_cropland','capacity_multiplier','starting_improvement_effective_cropland','maximum_improvement_effective_cropland']
    equal[primary].to_csv(out/'location_values_equal_area.csv',index=False,float_format='%.15g')
    write_json(out/'area_comparison.json',comparison)
    from .improvement_audit import report as improvement_report
    improvement_report(out,equal,fingerprint)
    if cfg.get('refinement_config'):
        from .regional_comparison import report as regional_report
        regional_report(raw.parents[2],out,equal,cfg,fingerprint)
    from .rural_pressure import report as rural_report
    rural_report(raw.parents[2],out,equal,fingerprint,cfg)
    from .game_calibration_report import report as game_report
    game_report(raw.parents[2],out,equal,cfg,fingerprint)
    from .inheritance_review import report as inheritance_report
    inheritance_report(raw.parents[2],out,equal,cfg,fingerprint)
    own=equal.loc[equal.is_ownable].copy()
    prior=own.unbounded_reference_multiplier.clip(lower=.01)
    comparison_bounds={
        'lower':cfg['multiplier_floor'],'upper':cfg.get('multiplier_ceiling'),
        'interpretation':'Hard game-unit bounds. Capacity components, land and water are conserved; raw reference remains in the ledger. Earlier normalization used a 0.01 floor.',
        'ownable_locations':len(own),
        'raised':int((own.capacity_multiplier>prior).sum()),
        'lowered':int((own.capacity_multiplier<prior).sum()),
        'unchanged':int((own.capacity_multiplier==prior).sum()),
        'before_quantiles':prior.quantile([0,.1,.25,.5,.75,.9,.99,1]).to_dict(),
        'after_quantiles':own.capacity_multiplier.quantile([0,.1,.25,.5,.75,.9,.99,1]).to_dict()}
    write_json(out/'multiplier_comparison.json',comparison_bounds)
    own['previous_multiplier']=prior
    own['absolute_unit_rescale']=prior/own.capacity_multiplier
    own[['location_tag','macro_region','previous_multiplier','capacity_multiplier','absolute_unit_rescale','starting_capacity','maximum_capacity']].to_csv(out/'multiplier_comparison.csv',index=False,float_format='%.15g')
    own.groupby('macro_region').agg(locations=('location_tag','size'),before_median=('previous_multiplier','median'),after_median=('capacity_multiplier','median'),after_min=('capacity_multiplier','min'),after_max=('capacity_multiplier','max')).to_csv(out/'multiplier_regions.csv')
    versions={'physical':d,'equal':equal}
    caps={}
    for key,label,unit in METRICS:
        family=['starting_capacity','maximum_capacity'] if key in ['starting_capacity','maximum_capacity'] else ['inert_capacity','starting_improvement_capacity','maximum_improvement_capacity','remaining_capacity'] if key in ['inert_capacity','starting_improvement_capacity','maximum_improvement_capacity','remaining_capacity'] else [key]
        if key in IMPROVEMENT_KEYS:
            family=sorted(IMPROVEMENT_KEYS)
        if key in WATER_KEYS:
            family=sorted(WATER_KEYS)
        caps[key]=max(float(v.loc[v.modelled_land & (v[k]>0),k].quantile(.99)) if (v.modelled_land & (v[k]>0)).any() else 1 for v in [equal] for k in family)
    manifest=[]
    original=d
    for mode,d in versions.items():
      for key,label,unit in METRICS:
          vals=d[key].to_numpy(float);pos=vals[np.isfinite(vals)&(vals>0)]
          cap=caps[key] or 1
          if key=='inferred_area_share':cap=1
          mix=key in IMPROVEMENT_KEYS or key in WATER_KEYS
          if key=='starting_fill':cap=2
          log=(key in WATER_KEYS) or (key not in ['starting_fill','inferred_area_share'] and not mix)
          t=np.log1p(np.maximum(vals,0))/np.log1p(cap) if log else np.maximum(vals,0)/cap
          colors=np.full((len(d)+1,3),[65,70,78],dtype=np.uint8);colors[0]=[13,24,36]
          known=np.isfinite(vals);indices=(np.clip(t[known],0,1)*255).astype(int)
          if key in ['starting_fill','inferred_area_share']:indices=255-indices
          colors[1:][known]=palette[indices]
          if mix:
              no_budget=d[key.split('_')[0]+'_distribution_status'].eq('no_improvement_budget').to_numpy()
              colors[1:][no_budget]=[65,70,78]
          # Distinguish domain-zero seas/lakes/wastelands from low productive land.
          for ix,row in enumerate(d.itertuples(),1):
              if not row.is_ownable:colors[ix]=[13,24,36] if ('sea_zones' in row.game_zone_class or 'lakes' in row.game_zone_class) else [55,61,69]
          rgb=colors[ids];Image.fromarray(rgb).save(out/(key+('_equal' if mode=='equal' else '')+'.png'))
          if mode=='physical':manifest.append({'key':key,'label':label,'unit':unit,'cap':cap,'log':log})
    d=original
    native_present=set(np.unique((native[...,0].astype(np.uint32)<<16)|(native[...,1].astype(np.uint32)<<8)|native[...,2]))-{0}
    overview_present=set(np.unique(ids))-{0}
    ownable_ids=set(np.flatnonzero(d.is_ownable.to_numpy())+1)
    write_json(out/'map_coverage.json',{
        'native_locations':len(native_present),'overview_locations':len(overview_present),
        'ownable_locations':len(ownable_ids),
        'native_missing_ownable':[str(d.iloc[i-1].location_tag) for i in sorted(ownable_ids-native_present)],
        'overview_missing_ownable':[str(d.iloc[i-1].location_tag) for i in sorted(ownable_ids-overview_present)],
        'note':'Overview is downsampled; ownable coverage is checked separately from all-zone counts. Native ID raster preserves every location.'})
    (out/'data.js').write_text('window.LOCATIONS='+json.dumps(data,separators=(',',':'))+';\nwindow.METRICS='+json.dumps(manifest)+';\n')
    html=HTML.replace('__COUNT__',f'{len(d):,}').replace('__START__',f"{comparison['starting_total']/1e6:,.1f} million").replace('__MAX__',f"{comparison['maximum_total']/1e6:,.1f} million").replace('__HASH__',fingerprint[:16])
    html=html.replace('__REFERENCE_AREA__',f"{comparison['reference_area_ha']:,.0f}").replace('__BASE_FLOOR__',f"{comparison['base_land_floor']:,.0f}")
    settlement=audit['settlement_readiness']
    notice=f"<p class='tag'>Game eligibility checked: {settlement['ownable_locations']:,} ownable locations. {settlement['unresolved_ownable_locations']:,} have unresolved support values. <a href='multiplier_comparison.csv'>Multiplier comparison</a> · <a href='repaired_settlements.csv'>See repaired locations</a> · <a href='settlement_validation.json'>Eligibility audit</a></p>"
    notice+=f"<p class='tag'>Multiplier bounds: ×{cfg['multiplier_floor']:g}–×{cfg['multiplier_ceiling']:g}. Absolute units rescaled to preserve starting and maximum capacity.</p>"
    html=html.replace('<div class="controls">',notice+'<div class="controls">')
    if cfg.get('agricultural_game_calibration'):
        html=html.replace('<div class="controls">',"<p class='tag'>Game-calibrated support: inherited agricultural systems and compressed geographical disadvantages. Physical food estimates remain separate. <a href='GAME_CALIBRATION.md'>Calibration and remaining cases</a></p><div class=\"controls\">")
        html=html.replace('First-iteration estimates; subject to refinement.','Game-calibrated capacity; historical inputs and physical food estimates retained separately.')
        html=html.replace('Maximum holds cultivation practices fixed.','Maximum includes the shared game conversion; physical resource opportunity remains bounded.')
    if cfg.get('inheritance_review_baseline'):
        html=html.replace("<a href='GAME_CALIBRATION.md'>Calibration and remaining cases</a>", "<a href='GAME_CALIBRATION.md'>Calibration and remaining cases</a> · <a href='INHERITANCE_REVIEW.md'>Starting-infrastructure review</a>")
    (out/'index.html').write_text(html)
    lines=['# Location iteration 01 — complete inferred dataset','',f"All {len(d):,} inventory locations have all four required values. Engineering completion is separate from historical acceptance.",'',f"Starting support: {comparison['starting_total']:,.0f} people. Maximum support: {comparison['maximum_total']:,.0f} people.",'',f"{int((equal.is_ownable & (equal.eu5_start_population > equal.starting_capacity)).sum()):,} locations are below the cached starting population. This is reported, not corrected through population fitting.",'','## Required values and evidence','', 'The viewer uses equal-area game values. See `location_values_equal_area.csv`, `locations_equal_area.csv`, `manifest.json`, `validation.json` and the native-grid TIFFs. The central maximum is the configured preindustrial clearing and seasonal surface-water scenario; it is not a measured universal maximum.','', '## Limitations','']+['- '+x for x in audit['limitations']]
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')

HTML=r"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>EU5 location capacity · iteration 01</title>
<style>*{box-sizing:border-box}body{margin:0;background:#0c1420;color:#e0e8ef;font:15px system-ui}main{max-width:1550px;margin:auto;padding:24px}h1{margin:0;font-size:27px}p{color:#a9b9c9;line-height:1.5}header{display:flex;justify-content:space-between;gap:20px;align-items:center}.tag{color:#ecd59c;font-size:13px}.stats{display:flex;gap:36px;margin:20px 0}.stats strong{display:block;font-size:23px}.stats span{color:#9aacbd;font-size:13px}select,input,button{background:#1b2a3d;color:#e0e8ef;border:1px solid #405269;border-radius:6px;padding:9px;font:inherit}button{cursor:pointer}.controls{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}.layout{display:grid;grid-template-columns:minmax(0,1fr) 310px;gap:18px}.map{position:relative;overflow:hidden;border:1px solid #344357;border-radius:9px;background:#0d1824}canvas{display:block;width:100%;height:560px;touch-action:none;cursor:grab}aside{background:#142032;border:1px solid #344357;padding:17px;border-radius:9px}aside h2{font-size:20px;margin:0 0 15px}.row{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid #28384c;padding:9px 0}.row span{color:#a7b9ca}.row b{text-align:right}.legend{display:flex;align-items:center;gap:12px;margin:12px 0;font-size:12px;color:#b5c5d4}.bar{height:12px;width:240px;background:linear-gradient(90deg,#a50026,#f46d43,#ffffbf,#66bd63,#006837);border-radius:3px}a{color:#80c4f5}.links{display:flex;gap:20px;flex-wrap:wrap}small{color:#a8b9c9}#matches{display:none;max-height:180px;overflow:auto;background:#1b2a3d;border:1px solid #405269;padding:6px}#matches button{display:block;width:100%;text-align:left;border:0}footer{margin-top:18px;font-size:12px;color:#8c9eaf}.location-heading{margin-bottom:4px}aside .place{display:block;margin-bottom:18px;font-size:12px}.capacity-overview{background:#1c3046;border-radius:8px;padding:14px}.capacity-pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}.capacity-pair span,.maximum-summary span{display:block;font-size:12px;color:#b4c7d8}.capacity-pair strong{display:block;margin-top:3px;font-size:24px;font-variant-numeric:tabular-nums}.fill-summary{margin-top:10px;color:#b4d8ec;font-size:13px}.maximum-summary{margin-top:13px;padding-top:12px;border-top:1px solid #3b5065;display:flex;align-items:center;justify-content:space-between;gap:10px}.maximum-summary strong{font-size:21px;font-variant-numeric:tabular-nums}.input-heading{font-size:14px;margin:22px 0 5px}.model-input{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 0;border-bottom:1px solid #28384c}.model-input span{font-size:14px}.model-input small{display:block;font-size:11px;margin-top:3px}.model-input b{font-size:16px;white-space:nowrap;font-variant-numeric:tabular-nums}.model-formula{font-size:13px;line-height:1.6;margin:13px 0 5px;color:#d7e7f4}.unit-note{font-size:11px;line-height:1.5;margin:0 0 16px}aside details{border-top:1px solid #344357;padding-top:13px}aside summary{cursor:pointer;color:#9cc9e9;font-size:13px}aside details .row{font-size:12px}aside details p{font-size:12px}.model-status{font-size:11px;color:#cfbf99;margin:8px 0 0}@media(max-width:950px){.layout{grid-template-columns:1fr}canvas{height:420px}.stats{gap:15px;flex-wrap:wrap}header{display:block}}</style>
<style>.map-tabs{display:flex;gap:8px;margin:22px 0 8px;flex-wrap:wrap}.map-tabs button[aria-pressed="true"]{background:#315e7e;border-color:#87c4ed;color:white}.map-tabs button:focus-visible{outline:2px solid #a6d8f7;outline-offset:3px}#viewNote{font-size:13px;margin:8px 0}</style><main><header><div><h1>EU5 location capacity</h1><p>Four values per location · baseline, productivity, inherited improvements and feasible maximum</p></div><div class="tag">Iteration 01 · all map zones covered<br>Historical calibration remains provisional</div></header>
<div class="stats"><div><strong>__COUNT__ / __COUNT__</strong><span>map zones with all four values</span></div><div><strong id="startingTotal">__START__</strong><span>starting support</span></div><div><strong id="maximumTotal">__MAX__</strong><span>maximum scenario support</span></div></div>
<nav class="map-tabs" aria-label="Map views"><button id="tabCapacity" aria-pressed="true">Capacity</button><button id="tabPressure" aria-pressed="false">Population pressure</button><button id="tabImprovements" aria-pressed="false">Improvement mix</button><button id="tabWater" aria-pressed="false">Water management</button></nav><p id="viewNote">Starting support and the opportunity to expand it.</p><div class="controls"><select id="metric"></select><input id="search" placeholder="Find a location…" aria-label="Find location"><button id="reset">World view</button><button id="plus">+</button><button id="minus">−</button></div><div id="matches"></div>
<p id="areaNote">Equal-area model: every land location uses the same __REFERENCE_AREA__ ha reference. Minimum base land: __BASE_FLOOR__ effective units per ownable location. Location size does not scale capacity.</p><div class="layout"><section><div class="map"><canvas id="map"></canvas></div><div class="legend"><span>0</span><div class="bar"></div><span id="scale"></span></div><small>20,929 modelled land locations; 7,644 nonsettlement zones have explicit zero capacity. Drag to pan · scroll to zoom · click a location. Colour saturation is a display limit; values are not capped.</small></section><aside id="detail"><h2>Select a location</h2><p>Each location has all four required estimates. Search includes small islands that may disappear at world-view resolution.</p><p>Maximum improvements include existing improvements.</p></aside></div>
<p>Capacity = multiplier × (base + improvements). Effective hectares are support equivalents; physical land and water are accounted separately. The maximum holds the crop system fixed and allows additional clearing and constrained surface-water investment.</p>
<div class="links"><a id="valuesLink" href="location_values_equal_area.csv">Four-value dataset</a><a id="ledgerLink" href="locations_equal_area.csv">Full location ledger</a><a href="REPORT.md">Iteration findings</a><a href="IMPROVEMENTS.md">Improvement audit</a><a href="WATER_MANAGEMENT.md">Water-management evidence</a><a href="water_management_ledger.csv">Water ledger</a><a href="improvement_distribution_equal_area.csv">Improvement shares</a><a href="rural_pressure.html">Rural pressure</a> · <a href="regional_comparison.html">Regional changes</a><a href="validation.json">Validation</a><a href="manifest.json">Source and parameter manifest</a><a href="location_ids_native.png">Native location geometry</a></div>
<footer>Fingerprint __HASH__ · Modern environmental proxies, historical evidence around 1300. Starting population is context, not a fitted target. Water-management and land-access estimates carry uncertainty.</footer></main>
<script src="data.js"></script><script src="location_lookup.js"></script><script>
const canvas=document.getElementById('map'),ctx=canvas.getContext('2d'),select=document.getElementById('metric');
const metricOptions=[];
METRICS.forEach((m,i)=>{const o=document.createElement('option');o.value=i;o.textContent=m.label;select.append(o);metricOptions.push(o)});
let activeTab='capacity';
const tabSelections={};
function metricTab(m){return /^(starting|maximum)_(water_supply|paddy_control|flood_bunds|field_drainage|polders)_improvement_capacity$/.test(m.key)?'water':/^(starting|maximum)_(clearing|management|water_management)_improvement_capacity$/.test(m.key)?'improvements':m.key==='starting_fill'?'pressure':'capacity'}
function setTab(tab){
 tabSelections[activeTab]=Number(select.value);activeTab=tab;
 const available=METRICS.map((m,i)=>metricTab(m)===tab?i:-1).filter(i=>i>=0);
 metricOptions.forEach((o,i)=>{o.hidden=!available.includes(i)});
 select.value=available.includes(tabSelections[tab])?tabSelections[tab]:available[0];
 for(const [key,id] of [['capacity','tabCapacity'],['pressure','tabPressure'],['improvements','tabImprovements'],['water','tabWater']])document.getElementById(id).ariaPressed=String(key===tab);
 document.getElementById('viewNote').textContent=tab==='water'?'Five complete water-management layers, each at starting and maximum conditions. Values = units × location multiplier. All ten share one logarithmic scale so smaller drainage contributions remain visible. Maximum includes existing works. Inferred from global wet settings and historical farming evidence; no extra total capacity is created.':tab==='improvements'?'Choose a type and starting or maximum amount. Values are population capacity contributed: improvement units × location multiplier. All six maps share one linear scale. Grey = no improvement budget. Maximum includes existing improvements. Water management combines supply, paddy control, flood embankments, drainage and reclamation. Inspect its five types in the Water management tab.':tab==='pressure'?'Starting population relative to starting capacity. Above 100% means over capacity.':'Starting support and the opportunity to expand it.';
 if(window.history&&window.location)window.history.replaceState(null,'','#'+tab);
 if(selected>=0)show(selected);
 load();
}
for(const [key,id] of [['capacity','tabCapacity'],['pressure','tabPressure'],['improvements','tabImprovements'],['water','tabWater']])document.getElementById(id).onclick=()=>setTab(key);
let img=new Image(),z=1,ox=0,oy=0,selected=-1,drag=null,moved=false;
function locationAt(x,y){const map=window.LOCATION_LOOKUP;if(!map||x<0||y<0||x>=map.width||y>=map.height)return 0;const row=map.rows[Math.floor(y)];let lo=0,hi=row.length/2;while(lo<hi){const mid=(lo+hi)>>>1;if(x<row[mid*2])hi=mid;else lo=mid+1}return lo<row.length/2?row[lo*2+1]:0}
function fit(){canvas.width=canvas.clientWidth*devicePixelRatio;canvas.height=canvas.clientHeight*devicePixelRatio;draw()}
function draw(){ctx.fillStyle='#0d1824';ctx.fillRect(0,0,canvas.width,canvas.height);if(!img.complete)return;let s=Math.min(canvas.width/4096,canvas.height/2048)*z;ctx.imageSmoothingEnabled=false;ctx.drawImage(img,ox,oy,4096*s,2048*s)}
function load(){let m=METRICS[select.value];document.querySelector('.bar').style.transform=(m.key==='starting_fill'||m.key==='inferred_area_share')?'scaleX(-1)':'none';img=new Image();img.onload=draw;img.src=m.key+'_equal.png';document.getElementById('scale').textContent=new Intl.NumberFormat('en',{maximumFractionDigits:2,notation:'compact'}).format(m.cap)+'+ '+m.unit+(m.log?' · logarithmic':' · linear');}
function esc(x){return String(x).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function fmt(x){return x===null?'Unavailable':new Intl.NumberFormat('en',{maximumFractionDigits:2}).format(x)}
function whole(x){return x===null||x===undefined?'Unavailable':new Intl.NumberFormat('en',{maximumFractionDigits:0}).format(x)}
function placeName(x){return String(x||'').replace(/_(province|region)$/,'').replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase())}
function waterDistribution(d){
 const names=[['water_supply','Water supply'],['paddy_control','Paddy control'],['flood_bunds','Flood embankments'],['field_drainage','Field drainage'],['polders','Coastal reclamation']];
 return '<details'+(activeTab==='water'?' open':'')+'><summary>Five water-management types</summary><table style="width:100%;font-size:12px;text-align:right"><thead><tr><th>People supported</th><th>Starting</th><th>Maximum</th></tr></thead><tbody>'+names.map(([k,label])=>'<tr><td style="text-align:left;padding:6px 0">'+label+'</td><td>'+whole(d['starting_'+k+'_improvement_capacity'])+'</td><td>'+whole(d['maximum_'+k+'_improvement_capacity'])+'</td></tr>').join('')+'</tbody></table><p>Transfer sensitivity: starting '+whole(d.starting_water_management_capacity_low)+'–'+whole(d.starting_water_management_capacity_high)+'; maximum '+whole(d.maximum_water_management_capacity_low)+'–'+whole(d.maximum_water_management_capacity_high)+' people. These are assumption tests, not confidence intervals.</p></details>';
}
function improvementDistribution(d){
  if(!d.starting_distribution_status)return '';
  const pct=(stage,kind)=>d[stage+'_distribution_status']==='no_improvement_budget'?'—':fmt(100*d[stage+'_'+kind+'_improvement_share'])+'%';
  const amount=(stage,kind)=>d[stage+'_distribution_status']==='no_improvement_budget'?'—':whole(d[stage+'_'+kind+'_improvement_capacity'])+'<br><small>'+pct(stage,kind)+'</small>';
  const names=[['clearing','Clearing'],['management','Field management'],['water_management','Water management']];
  return '<h3 class="input-heading">What the improvements represent</h3><table style="width:100%;font-size:12px;text-align:right"><thead><tr><th style="text-align:left">Type</th><th>Starting</th><th>Maximum</th></tr></thead><tbody>'+names.map(([k,label])=>'<tr><td style="text-align:left;padding:6px 0">'+label+'</td><td>'+amount('starting',k)+'</td><td>'+amount('maximum',k)+'</td></tr>').join('')+'</tbody></table><p class="unit-note">People supported: improvement units × location multiplier. Shares appear underneath; raw units are in the detailed breakdown. Maximum includes existing improvements. — means there is no improvement budget. Inferred attribution; water-management details below. No support is counted twice.</p>';
}
function show(i){
  selected=i;const d=LOCATIONS[i];if(!d)return;
  const input=(label,value,hint='')=>'<div class="model-input"><div><span>'+label+'</span>'+(hint?'<small>'+hint+'</small>':'')+'</div><b>'+value+'</b></div>';
  const factor=new Intl.NumberFormat('en',{maximumFractionDigits:3}).format(d.capacity_multiplier);
  const fill=Number.isFinite(d.starting_fill)?whole(d.starting_fill*100)+'% of starting capacity occupied':'Starting fill unavailable';
  const rows=[['Starting settlement rank',d.starting_location_rank||'unknown'],['Base contribution',whole(d.inert_capacity)+' people'],['Capacity from minimum base land',whole(d.base_land_floor_added_capacity||0)+' people'],['Existing improvement contribution',whole(d.starting_improvement_capacity)+' people'],['Additional capacity still possible',whole(d.maximum_capacity-d.starting_capacity)+' people'],['Remaining improvement units',whole(d.remaining_improvement_effective_cropland)],['Regional refinement coverage',fmt(100*Math.max(d.china_refinement_share||0,d.andes_refinement_share||0,d.prairie_refinement_share||0,d.improvement_reference_refinement_share||0,d.management_envelope_refinement_share||0,d.cultivated_system_refinement_share||0))+'%'],['Original clearing attribution',whole(d.starting_clearing_capacity)+' people'],['Original management attribution',whole(d.starting_management_capacity)+' people'],['Original water-supply attribution',whole(d.starting_irrigation_capacity)+' people'],['Remaining clearing + management',whole(d.remaining_clearing_capacity+d.remaining_management_capacity)+' people'],['Remaining irrigation',whole(d.remaining_irrigation_capacity)+' people'],['Reference productivity before game bounds',fmt(d.unbounded_reference_multiplier)],['Physical location area',d.physical_location_ha===null?'Not evaluated':fmt(d.physical_location_ha/100)+' km²']];
  for(const [kind,label] of [['clearing','Clearing'],['management','Field management'],['water_management','Water management']]){
    rows.push([label+' raw units · starting / maximum',whole(d['starting_'+kind+'_improvement_units'])+' / '+whole(d['maximum_'+kind+'_improvement_units'])]);
  }
  document.getElementById('detail').innerHTML=
    '<h2 class="location-heading">'+esc(placeName(d.location_tag))+'</h2><small class="place">'+esc(placeName(d.province))+' · '+esc(placeName(d.region))+'</small>'+
    '<div class="capacity-overview"><div class="capacity-pair"><div><span>Starting population</span><strong>'+whole(d.eu5_start_population)+'</strong></div><div><span>Starting capacity</span><strong>'+whole(d.starting_capacity)+'</strong></div></div><div class="fill-summary">'+fill+'</div><div class="maximum-summary"><span>Maximum capacity</span><strong>'+whole(d.maximum_capacity)+'</strong></div></div>'+
    '<h3 class="input-heading">The four model values</h3>'+
    input('Base land',whole(d.base_effective_cropland),'Before represented improvements')+
    input('Productivity','× '+factor,'People supported per effective land unit')+
    input('Existing improvements',whole(d.starting_improvement_effective_cropland),'Already present at game start')+
    input('Maximum improvements',whole(d.maximum_improvement_effective_cropland),'Total limit, including existing improvements')+
    '<p class="model-formula">Capacity = (base + improvements)<br>× productivity</p><p class="unit-note">Land and improvements use effective units, not physical hectares. Display values are rounded.</p>'+
    improvementDistribution(d)+waterDistribution(d)+
    '<details><summary>Breakdown &amp; evidence</summary>'+rows.map(([k,v])=>'<div class="row"><span>'+k+'</span><b>'+v+'</b></div>').join('')+'<p>The raw source ledger follows clearing → management → water supply. The displayed breakdown reassigns wet-field benefits to water management without changing totals. Maximum holds cultivation practices fixed. Drainage and flood-control attribution is inferred from wet settings; terraces are not separate.</p><p>'+esc(d.evidence_status)+'<br>Coastline analogue: '+fmt(d.coastline_transfer_share*100)+'%<br>Terrestrial support analogue: '+fmt((d.terrestrial_analogue_share||0)*100)+'%</p></details>'+
    '<p class="model-status">'+(d.is_ownable===false?'Not ownable in EU5. Any physical estimates shown here are not settlement capacity.':d.maximum_capacity<=0?'Unresolved: ownable location has zero modeled food support.':'First-iteration estimates; subject to refinement.')+'</p>';
}
function pick(e){let b=canvas.getBoundingClientRect(),s=Math.min(canvas.width/4096,canvas.height/2048)*z,x=Math.floor(((e.clientX-b.left)*devicePixelRatio-ox)/s),y=Math.floor(((e.clientY-b.top)*devicePixelRatio-oy)/s);const id=locationAt(x,y);if(id)show(id-1)}
canvas.onpointerdown=e=>{drag=[e.clientX,e.clientY,ox,oy];moved=false;canvas.setPointerCapture(e.pointerId)};canvas.onpointermove=e=>{if(!drag)return;let dx=e.clientX-drag[0],dy=e.clientY-drag[1];if(Math.abs(dx)+Math.abs(dy)>3)moved=true;ox=drag[2]+dx*devicePixelRatio;oy=drag[3]+dy*devicePixelRatio;draw()};canvas.onpointerup=e=>{if(drag&&!moved)pick(e);drag=null};canvas.onpointercancel=()=>{drag=null};
function zoom(f,x=canvas.width/2,y=canvas.height/2){let nz=Math.min(40,Math.max(.5,z*f));let r=nz/z;ox=x-(x-ox)*r;oy=y-(y-oy)*r;z=nz;draw()}
canvas.onwheel=e=>{e.preventDefault();let b=canvas.getBoundingClientRect();zoom(e.deltaY<0?1.2:1/1.2,(e.clientX-b.left)*devicePixelRatio,(e.clientY-b.top)*devicePixelRatio)};
document.getElementById('plus').onclick=()=>zoom(1.5);document.getElementById('minus').onclick=()=>zoom(1/1.5);document.getElementById('reset').onclick=()=>{z=1;ox=oy=0;draw()};select.onchange=load;
const search=document.getElementById('search'),matches=document.getElementById('matches');search.oninput=()=>{matches.replaceChildren();let q=search.value.trim().toLowerCase().replaceAll(' ','_');matches.style.display=q?'block':'none';if(!q)return;LOCATIONS.map((d,i)=>[d,i]).filter(([d])=>d.location_tag.includes(q)||d.province.includes(q)).slice(0,15).forEach(([d,i])=>{let b=document.createElement('button');b.textContent=d.location_tag+' · '+d.province;b.onclick=()=>{show(i);matches.style.display='none';search.value=d.location_tag;if(d.centroid_x!==null){z=5;let s=Math.min(canvas.width/4096,canvas.height/2048)*z;ox=canvas.width/2-d.centroid_x/4*s;oy=canvas.height/2-d.centroid_y/4*s;draw()}};matches.append(b)})};window.onresize=fit;fit();load();const requestedTab=window.location?window.location.hash.slice(1):'capacity';setTab(['capacity','pressure','improvements','water'].includes(requestedTab)?requestedTab:'capacity');
</script></html>"""
