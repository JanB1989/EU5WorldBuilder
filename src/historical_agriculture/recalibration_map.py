"""One self-contained HTML map of the recalibrated capacity model.

Layers: people targets, attribute-only fits, model (attributes + buildings x development) with residuals,
development, building levels and caps per type, fertility class, population fill and review flags.
Reads the outputs of `locations`, `attribute-fit` (flat), `development` and `building-assignment`.
"""
import json,base64
from pathlib import Path
import numpy as np
import pandas as pd
from PIL import Image
from .capacity_targets import LEDGER_KINDS

ROOT=Path(__file__).resolve().parents[2]
KIND_LABELS={'clearing':'Clearing','management':'Field management','water_supply':'Water supply','paddy_control':'Paddy control','flood_bunds':'Flood bunds','field_drainage':'Field drainage','polders':'Polders'}


def load():
    loc=ROOT/'artifacts/locations'
    pred=pd.read_csv(ROOT/'artifacts/attribute_fit_flat/location_predictions.csv',keep_default_na=False).set_index('location_tag')
    bld=pd.read_csv(ROOT/'artifacts/building_assignment/locations.csv',keep_default_na=False).set_index('location_tag')
    fill=pd.read_csv(loc/'fill_evaluation.csv',keep_default_na=False).set_index('location_tag')
    fert=pd.read_csv(ROOT/'artifacts/fertility/locations.csv',keep_default_na=False).set_index('location_tag')
    units={r['building']:r.get('unit_people_per_level') for r in json.loads((ROOT/'artifacts/building_assignment/report.json').read_text())['buildings']}
    c=json.loads((ROOT/'configs/building_assignment.json').read_text())['capacity_percent_per_point']
    d=pred.copy()
    for col in bld.columns:
        if col not in d:d[col]=bld[col].reindex(d.index)
    d['population']=pd.to_numeric(fill.population,errors='coerce').reindex(d.index)
    d['context']=fill.context.reindex(d.index).fillna('unknown')
    d['best_kcal_per_ha']=pd.to_numeric(fert.get('best_kcal_per_ha',pd.Series(dtype=float)),errors='coerce').reindex(d.index)
    d['best_crop']=fert.get('best_crop',pd.Series(dtype=str)).reindex(d.index).fillna('')
    numeric=[x for x in d.columns if x not in ('climate','topography','vegetation','soil_type','fertility','river_level','is_coastal','is_adjacent_to_lake','region','macro_region','development_band','context','best_crop','start_exceeds_attribute_maximum')]
    for x in numeric:d[x]=pd.to_numeric(d[x],errors='coerce')
    d['fill_target']=d.population/d.starting_capacity.replace(0,np.nan)
    d['fill_model']=d.population/d.starting_capacity_model.replace(0,np.nan)
    d['buildings_start_people']=sum(d[f'{k}_levels_start']*(units.get(k) or 0) for k in LEDGER_KINDS)*(1+c*d.development)
    d['buildings_max_people']=sum(d[f'{k}_cap_at_development_100']*(units.get(k) or 0) for k in LEDGER_KINDS)*(1+c*100)
    return d,units,c


def layers(d):
    """(key, label, group, kind, values); kind: seq (log), lin (0..cap), div (ratio-1), cat (labels)."""
    out=[('starting_capacity','Starting capacity · target','Targets','seq',d.starting_capacity),
         ('maximum_capacity_people','Maximum capacity · target','Targets','seq',d.maximum_capacity_people),
         ('natural_capacity_people','Natural capacity · target','Targets','seq',d.natural_capacity_people),
         ('starting_capacity_model','Starting capacity · model (attributes + buildings × development)','Model','seq',d.starting_capacity_model),
         ('maximum_capacity_model','Maximum capacity · model (caps at development 100)','Model','seq',d.maximum_capacity_model),
         ('attribute_natural_people','Attributes only · natural at starting development','Model','seq',d.attribute_natural_people),
         ('attribute_maximum_people','Attributes only · maximum at development 100','Model','seq',d.attribute_maximum_people),
         ('res_start','Start: model ÷ target − 1','Residuals','div',d.starting_capacity_model/d.starting_capacity.replace(0,np.nan)-1),
         ('res_max','Maximum: model ÷ target − 1','Residuals','div',d.maximum_capacity_model/d.maximum_capacity_people.replace(0,np.nan)-1),
         ('res_attr_natural','Attributes only ÷ natural target − 1','Residuals','div',d.attribute_natural_people/d.natural_capacity_people.replace(0,np.nan)-1),
         ('res_attr_max','Attributes only ÷ maximum target − 1','Residuals','div',d.attribute_maximum_people/d.maximum_capacity_people.replace(0,np.nan)-1),
         ('development','Development (0–100)','Development','lin',d.development),
         ('fill_target','Population ÷ starting target','Population','div',d.fill_target-1),
         ('fill_model','Population ÷ starting model','Population','div',d.fill_model-1),
         ('review','Start exceeds attribute maximum (review list)','Flags','cat',d.start_exceeds_attribute_maximum.astype(str).map({'True':'on review list','False':'ok'})),
         ('fertility','Fertility class (best staple kcal/ha)','Attributes','cat',d.fertility),
         ('development_band','Development band','Attributes','cat',d.development_band)]
    for k in LEDGER_KINDS:
        out.append((f'{k}_levels_start',f'{KIND_LABELS[k]} · levels at start','Buildings · start','lin',d[f'{k}_levels_start']))
    for k in LEDGER_KINDS:
        out.append((f'{k}_cap_at_development_100',f'{KIND_LABELS[k]} · cap at development 100','Buildings · caps','lin',d[f'{k}_cap_at_development_100']))
    return out


CAT_COLORS={'very_low':[168,64,59],'low':[215,125,64],'moderate':[219,191,100],'high':[139,182,94],'very_high':[55,139,80],
            'on review list':[191,53,58],'ok':[70,110,90],'d00_20':[230,235,240],'d20_40':[170,200,220],'d40_60':[100,150,200],'d60_80':[50,100,170],'d80_100':[20,50,120]}


def build(output_path=None):
    from matplotlib import colormaps
    out=Path(output_path or ROOT/'artifacts/recalibration_map').resolve();out.mkdir(parents=True,exist_ok=True)
    source=ROOT/'artifacts/locations'
    raw=(source/'data.js').read_text();locations,_=json.JSONDecoder().raw_decode(raw[len('window.LOCATIONS='):]);del raw
    image=np.asarray(Image.open(source/'location_ids.png').convert('RGB'),dtype=np.uint32);ids=(image[...,0]<<16)|(image[...,1]<<8)|image[...,2]
    d,units,c=load()
    tags=[r['location_tag'] for r in locations];present=[t in d.index for t in tags]
    order=pd.Index(tags)
    seq=(colormaps['viridis'](np.linspace(0,1,256))[:,:3]*255).astype(np.uint8)
    anchors=np.array([[42,111,187],[231,234,231],[191,53,58]],dtype=float)
    manifest=[];images={}
    for key,label,group,kind,values in layers(d):
        v=values.reindex(order)
        palette=np.full((len(locations)+1,3),[66,75,84],dtype=np.uint8);palette[0]=[13,24,36]
        for i,row in enumerate(locations,1):
            if not present[i-1] and any(w in str(row.get('game_zone_class','')) for w in ['sea','ocean','lake']):palette[i]=[13,24,36]
        entry={'key':key,'label':label,'group':group,'kind':kind}
        if kind=='cat':
            for i,val in enumerate(v.to_numpy(),1):
                if isinstance(val,str) and val in CAT_COLORS:palette[i]=CAT_COLORS[val]
            entry['legend']={k:CAT_COLORS[k] for k in dict.fromkeys(x for x in v.dropna().unique() if x in CAT_COLORS)}
        else:
            arr=v.to_numpy(float);ok=np.isfinite(arr)
            if kind=='seq':
                cap=float(np.nanquantile(arr[ok&(arr>0)],.99)) if (ok&(arr>0)).any() else 1.
                t=np.log1p(np.maximum(arr,0))/np.log1p(cap);entry['cap']=cap;entry['scale']='log'
            elif kind=='lin':
                cap=float(np.nanmax(arr[ok])) if ok.any() else 1.;t=np.maximum(arr,0)/max(cap,1e-9);entry['cap']=cap;entry['scale']='linear'
            else:
                t=np.clip(arr,-1,1);entry['scale']='diverging'
            for i,(val,okk) in enumerate(zip(t,ok),1):
                if not okk:continue
                if kind=='div':
                    a=abs(val);palette[i]=anchors[1]*(1-a)+anchors[0 if val<0 else 2]*a
                else:palette[i]=seq[int(np.clip(val,0,1)*255)]
            fin=arr[ok]
            entry['stats']={'median':float(np.nanmedian(fin)) if len(fin) else None,'p10':float(np.nanquantile(fin,.1)) if len(fin) else None,'p90':float(np.nanquantile(fin,.9)) if len(fin) else None}
        Image.fromarray(palette[ids]).save(out/f'{key}.png')
        images[key]='data:image/png;base64,'+base64.b64encode((out/f'{key}.png').read_bytes()).decode('ascii')
        manifest.append(entry)
    data=[None]*(len(locations)+1)
    fields=['climate','topography','vegetation','soil_type','fertility','river_level','is_coastal','is_adjacent_to_lake','best_crop','context','development_band']
    nums=['natural_capacity_people','starting_capacity','maximum_capacity_people','attribute_natural_people','attribute_maximum_people','starting_capacity_model','maximum_capacity_model','buildings_start_people','buildings_max_people','development','population','fill_target','fill_model','best_kcal_per_ha','leftover_start_total','leftover_max_total']
    for i,row in enumerate(locations,1):
        tag=row['location_tag']
        if tag not in d.index:continue
        r=d.loc[tag];rec={'tag':tag,'province':row['province'],'region':row['region'],'x':row['centroid_x']/4,'y':row['centroid_y']/4,'review':bool(r.start_exceeds_attribute_maximum) if isinstance(r.start_exceeds_attribute_maximum,(bool,np.bool_)) else str(r.start_exceeds_attribute_maximum)=='True'}
        rec['a']={f:str(r[f]) for f in fields}
        rec['n']={f:(None if pd.isna(r[f]) else round(float(r[f]),3)) for f in nums}
        rec['b']=[[k,int(r[f'{k}_levels_start']),int(r[f'{k}_cap']),int(r[f'{k}_cap_at_development_100']),round(float(units.get(k) or 0))] for k in LEDGER_KINDS]
        data[i]=rec
    payload=json.dumps({'locations':data,'layers':manifest,'c':c,'units':units},separators=(',',':'))
    lookup=(source/'location_lookup.js').read_text().removeprefix('window.LOCATION_LOOKUP=').strip().removesuffix(';')
    html=HTML.replace('__PAYLOAD__',payload).replace('__LOOKUP__',lookup).replace('__IMAGES__',json.dumps(images))
    (out/'index.html').write_text(html)
    (out/'map_manifest.json').write_text(json.dumps({'layers':manifest,'locations':int(sum(x is not None for x in data)),'units':units,'capacity_percent_per_point':c},indent=2)+'\n')
    return {'output':str(out/'index.html'),'layers':len(manifest),'locations':int(sum(x is not None for x in data))}


HTML=r'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EU5 · Recalibrated capacity model</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#0c1420;color:#e6edf3;font:15px system-ui,sans-serif}main{max-width:1600px;margin:auto;padding:24px}h1{font-size:25px;margin:0 0 8px}p{line-height:1.5;color:#afc2d5;margin:8px 0 18px}select,input,button{font:inherit;background:#182638;color:#e6edf3;border:1px solid #425367;border-radius:6px;padding:9px}button{cursor:pointer}label{color:#afc2d5;font-size:13px;display:grid;gap:6px}.controls{display:flex;gap:16px;flex-wrap:wrap;margin:20px 0}.controls input{width:280px}.controls select{max-width:520px}.layout{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:18px}canvas{width:100%;height:65vh;min-height:400px;display:block;touch-action:none;cursor:grab;background:#0d1824;border:1px solid #33465b;border-radius:8px}.map{position:relative}.zoom{position:absolute;left:12px;top:12px;display:flex;gap:6px}aside{padding:18px;background:#142131;border:1px solid #33465b;border-radius:8px;font-size:14px}aside h2{font-size:20px;margin:0 0 6px}.row{display:flex;justify-content:space-between;gap:10px;padding:7px 0;border-bottom:1px solid #2c4054}.muted,small{color:#afc2d5}.legend{margin:14px 0;max-width:600px}.gradient{height:12px;border-radius:4px}.seq{background:linear-gradient(90deg,#440154,#31688e,#35b779,#fde725)}.div{background:linear-gradient(90deg,#2a6fbb,#e7eae7,#bf353a)}.ticks{display:flex;justify-content:space-between;font-size:13px;margin-top:5px}.stats{margin:16px 0;font-size:14px;color:#cbd7e3}a{color:#82c6ff}details{margin-top:12px}summary{cursor:pointer}#suggestions{position:absolute;background:#182638;z-index:4;width:340px;max-height:300px;overflow:auto;border-radius:5px}#suggestions button{display:block;width:100%;text-align:left;border:0;border-radius:0}#suggestions button:hover{background:#304861}.search{position:relative}.badge{font-size:12px;color:#efcd8d}.note{font-size:13px;max-width:1000px}table{width:100%;font-size:12px;border-collapse:collapse}td,th{padding:4px 2px;text-align:right}td:first-child,th:first-child{text-align:left}.swatch{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:6px;vertical-align:middle}.h{color:#efcd8d;font-size:13px;margin:12px 0 4px}@media(max-width:850px){.layout{grid-template-columns:1fr}canvas{height:55vh}main{padding:16px}}
</style><main>
<h1>Recalibrated capacity model</h1>
<p>Capacity = (attribute flat + building flat) × (1 + 1% × development). Targets are people per location in equal-area units; nothing here uses population except the two fill layers.</p>
<div class="controls"><label>Layer<select id="metric"></select></label>
<label class="search">Find a location<input id="search" placeholder="Location or province…" autocomplete="off"><div id="suggestions" style="top:66px"></div></label></div>
<div class="layout"><div><div class="map"><canvas id="map"></canvas><div class="zoom"><button id="plus" aria-label="Zoom in">+</button><button id="minus" aria-label="Zoom out">−</button><button id="reset">Reset view</button></div></div>
<div class="legend" id="legend"></div><div id="stats" class="stats"></div></div><aside id="panel"><h2>Inspect a location</h2><p>Click the map or search above.</p></aside></div>
<p class="note">Sequential layers use a logarithmic viridis scale up to the 99th percentile. Residual and fill layers are blue (below) to red (above), saturating at ±100%. Grey land is non-ownable. Building levels are those the ledger supports at starting development; caps are the fitted integer level limits at development 100.</p>
</main><script>(()=>{const FIT=__PAYLOAD__;const LOCATION_LOOKUP=__LOOKUP__;const MAP_IMAGES=__IMAGES__;
const canvas=document.getElementById('map'),ctx=canvas.getContext('2d'),metric=document.getElementById('metric'),panel=document.getElementById('panel'),search=document.getElementById('search'),suggestions=document.getElementById('suggestions'),legend=document.getElementById('legend');
let img=new Image(),z=1,ox=0,oy=0,selected=0,drag=null,moved=false;
const pretty=s=>String(s).replaceAll('_',' '),fmt=n=>n===null||n===undefined||Number.isNaN(n)?'—':Number(n).toLocaleString('en-US',{maximumFractionDigits:n<10?2:0}),esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
let group=null;FIT.layers.forEach((m,i)=>{if(m.group!==group){group=m.group;const g=document.createElement('optgroup');g.label=group;metric.append(g)}const o=document.createElement('option');o.value=i;o.textContent=m.label;metric.lastElementChild.append(o)});
function locationAt(x,y){const m=LOCATION_LOOKUP;if(x<0||y<0||x>=m.width||y>=m.height)return 0;const row=m.rows[Math.floor(y)];let lo=0,hi=row.length/2;while(lo<hi){let mid=(lo+hi)>>>1;if(x<row[mid*2])hi=mid;else lo=mid+1}return lo<row.length/2?row[lo*2+1]:0}
function draw(){ctx.fillStyle='#0d1824';ctx.fillRect(0,0,canvas.width,canvas.height);if(!img.complete||!img.naturalWidth)return;const s=Math.min(canvas.width/4096,canvas.height/2048)*z;ctx.imageSmoothingEnabled=false;ctx.drawImage(img,ox,oy,4096*s,2048*s);const r=FIT.locations[selected];if(r){ctx.beginPath();ctx.arc(ox+r.x*s,oy+r.y*s,6*devicePixelRatio,0,Math.PI*2);ctx.strokeStyle='#fff';ctx.lineWidth=2*devicePixelRatio;ctx.stroke()}}
function fit(){canvas.width=canvas.clientWidth*devicePixelRatio;canvas.height=canvas.clientHeight*devicePixelRatio;draw()}
function reset(){z=1;let s=Math.min(canvas.width/4096,canvas.height/2048);ox=(canvas.width-4096*s)/2;oy=(canvas.height-2048*s)/2;draw()}
function pct(x){return x===null||x===undefined||!Number.isFinite(x)?'—':(x>=0?'+':'')+fmt(100*x)+'%'}
function show(id){selected=id;const r=FIT.locations[id];if(!r){panel.innerHTML='<h2>Not ownable</h2><p>No capacity target for this zone.</p>';draw();return}const n=r.n;
let h='<h2>'+esc(pretty(r.tag))+'</h2><small>'+esc(pretty(r.province))+' · '+esc(pretty(r.region))+' · '+esc(r.a.context)+(r.review?' · <span class="badge">on review list</span>':'')+'</small>';
h+='<div class="h">Targets (people)</div><div class="row"><span>Natural</span><b>'+fmt(n.natural_capacity_people)+'</b></div><div class="row"><span>Starting</span><b>'+fmt(n.starting_capacity)+'</b></div><div class="row"><span>Maximum</span><b>'+fmt(n.maximum_capacity_people)+'</b></div>';
h+='<div class="h">Model</div><div class="row"><span>Attributes only · natural at start</span><b>'+fmt(n.attribute_natural_people)+'</b></div><div class="row"><span>Buildings at start × development</span><b>'+fmt(n.buildings_start_people)+'</b></div><div class="row"><span>Starting capacity · model</span><b>'+fmt(n.starting_capacity_model)+' <small>('+pct(n.starting_capacity_model/n.starting_capacity-1)+')</small></b></div><div class="row"><span>Maximum capacity · model</span><b>'+fmt(n.maximum_capacity_model)+' <small>('+pct(n.maximum_capacity_model/n.maximum_capacity_people-1)+')</small></b></div><div class="row"><span>Development</span><b>'+fmt(n.development)+' <small>('+esc(r.a.development_band)+')</small></b></div>';
h+='<div class="h">Buildings</div><table><tr><th>Type</th><th>Start</th><th>Cap now</th><th>Cap @100</th><th>People/level</th></tr>'+r.b.map(b=>'<tr><td>'+esc(pretty(b[0]))+'</td><td>'+b[1]+'</td><td>'+b[2]+'</td><td>'+b[3]+'</td><td>'+fmt(b[4])+'</td></tr>').join('')+'</table>';
h+='<div class="h">Population (context only)</div><div class="row"><span>Starting population</span><b>'+fmt(n.population)+'</b></div><div class="row"><span>Fill vs target / vs model</span><b>'+fmt(100*n.fill_target)+'% / '+fmt(100*n.fill_model)+'%</b></div>';
h+='<details><summary>Attributes</summary>'+Object.entries(r.a).map(([k,v])=>'<div class="row"><small>'+esc(pretty(k))+'</small><span>'+esc(pretty(v))+'</span></div>').join('')+'<div class="row"><small>best staple kcal/ha</small><span>'+fmt(n.best_kcal_per_ha)+'</span></div></details>';
panel.innerHTML=h;draw()}
function update(){const m=FIT.layers[metric.value];img=new Image();img.onload=draw;img.src=MAP_IMAGES[m.key];
if(m.kind==='cat'){legend.innerHTML=Object.entries(m.legend||{}).map(([k,c])=>'<span style="margin-right:14px"><span class="swatch" style="background:rgb('+c.join(',')+')"></span>'+esc(pretty(k))+'</span>').join('');document.getElementById('stats').textContent=''}
else if(m.kind==='div'){legend.innerHTML='<div class="gradient div"></div><div class="ticks"><span>−100% · below</span><span>0</span><span>+100% or more · above</span></div>';document.getElementById('stats').textContent='Median '+pct(m.stats.median)+' · p10 '+pct(m.stats.p10)+' · p90 '+pct(m.stats.p90)}
else{legend.innerHTML='<div class="gradient seq"></div><div class="ticks"><span>0</span><span>'+fmt(m.cap)+(m.scale==='log'?' (log scale, 99th percentile)':'')+'</span></div>';document.getElementById('stats').textContent='Median '+fmt(m.stats.median)+' · p10 '+fmt(m.stats.p10)+' · p90 '+fmt(m.stats.p90)}
if(selected)show(selected)}
function zoom(f,x=canvas.width/2,y=canvas.height/2){let nz=Math.max(.5,Math.min(40,z*f)),r=nz/z;ox=x-(x-ox)*r;oy=y-(y-oy)*r;z=nz;draw()}
canvas.onpointerdown=e=>{drag=[e.clientX,e.clientY,ox,oy];moved=false;canvas.setPointerCapture(e.pointerId)};
canvas.onpointermove=e=>{if(!drag)return;let dx=e.clientX-drag[0],dy=e.clientY-drag[1];if(Math.abs(dx)+Math.abs(dy)>3)moved=true;ox=drag[2]+dx*devicePixelRatio;oy=drag[3]+dy*devicePixelRatio;draw()};
canvas.onpointerup=e=>{if(drag&&!moved){let b=canvas.getBoundingClientRect(),s=Math.min(canvas.width/4096,canvas.height/2048)*z,id=locationAt(((e.clientX-b.left)*devicePixelRatio-ox)/s,((e.clientY-b.top)*devicePixelRatio-oy)/s);if(id)show(id)}drag=null};canvas.onpointercancel=()=>drag=null;
canvas.addEventListener('wheel',e=>{e.preventDefault();let b=canvas.getBoundingClientRect();zoom(e.deltaY<0?1.2:1/1.2,(e.clientX-b.left)*devicePixelRatio,(e.clientY-b.top)*devicePixelRatio)},{passive:false});
document.getElementById('plus').onclick=()=>zoom(1.5);document.getElementById('minus').onclick=()=>zoom(1/1.5);document.getElementById('reset').onclick=reset;metric.onchange=update;
function jump(id){show(id);let r=FIT.locations[id];z=5;let s=Math.min(canvas.width/4096,canvas.height/2048)*z;ox=canvas.width/2-r.x*s;oy=canvas.height/2-r.y*s;draw();suggestions.replaceChildren();search.value=pretty(r.tag)}
search.oninput=()=>{let q=search.value.toLowerCase().trim().replaceAll(' ','_');suggestions.replaceChildren();if(!q)return;FIT.locations.map((r,id)=>({r,id})).filter(({r})=>r&&(r.tag.includes(q)||r.province.includes(q))).slice(0,12).forEach(({r,id})=>{let b=document.createElement('button');b.textContent=pretty(r.tag)+' · '+pretty(r.province);b.onclick=()=>jump(id);suggestions.appendChild(b)})};search.onkeydown=e=>{if(e.key==='Enter')suggestions.querySelector('button')?.click();if(e.key==='Escape')suggestions.replaceChildren()};
window.addEventListener('resize',fit);fit();reset();update();
})();</script></html>'''
