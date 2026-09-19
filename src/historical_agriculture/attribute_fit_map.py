"""Interactive signed residual maps on the existing EU5 location geometry."""
import json
import base64
import shutil
from pathlib import Path
import numpy as np
from PIL import Image
from .attribute_fit import sha as sha256_file


def render_map(pred, out, root, objective="absolute", no_overshoot=False):
    source = root / "artifacts/locations"
    raw = (source / "data.js").read_text()
    locations, _ = json.JSONDecoder().raw_decode(raw[len("window.LOCATIONS="):])
    del raw
    image = np.asarray(Image.open(source / "location_ids.png").convert("RGB"), dtype=np.uint32)
    ids = (image[..., 0] << 16) | (image[..., 1] << 8) | image[..., 2]
    if ids.max() > len(locations):
        raise ValueError("Geometry contains unknown location IDs")
    if set(pred.index) - {r["location_tag"] for r in locations}:
        raise ValueError("Fit locations missing from map inventory")
    data = [None] * (len(locations) + 1)
    for i, row in enumerate(locations, 1):
        tag = row["location_tag"]
        if tag not in pred.index:
            continue
        r = pred.loc[tag]
        values = {"target": [float(r.base_effective_cropland), float(r.capacity_multiplier), float(r.inert_target)]}
        for mode in ["fitted", "heldout"]:
            b = float(r[f"current_base_effective_cropland_{objective}_{mode}"])
            m = float(r[f"current_capacity_multiplier_{objective}_{mode}"])
            values[mode] = [b, m, b * m]
        if not np.isfinite(list(values.values())).all() or min(values["target"]) <= 0:
            raise ValueError(f"Invalid map values: {tag}")
        data[i] = {"tag": tag, "province": row["province"], "region": row["region"],
                   "x": row["centroid_x"] / 4, "y": row["centroid_y"] / 4, **values,
                   "attributes": {f: str(r[f]) for f in ["topography", "climate", "vegetation", "is_coastal", "river_level", "is_adjacent_to_lake", "soil_type", "fertility"]}}
    stats = {}
    # Symmetric fixed display range; values outside it remain exact in the panel.
    anchors = np.array([[42, 111, 187], [231, 234, 231], [191, 53, 58]], dtype=float)
    for mode in ["fitted", "heldout"]:
        for metric in range(3):
            palette = np.full((len(data), 3), [66, 75, 84], dtype=np.uint8)
            palette[0] = [13, 24, 36]
            errors = []
            for i, r in enumerate(data):
                if r is None:
                    if i and any(w in str(locations[i-1].get("game_zone_class", "")) for w in ["sea", "ocean", "lake"]):
                        palette[i] = [13, 24, 36]
                    continue
                e = 100 * (r[mode][metric] / r["target"][metric] - 1)
                errors.append(e)
                v = np.clip(e / 100, -1, 1)
                palette[i] = anchors[1] * (1-abs(v)) + anchors[0 if v < 0 else 2] * abs(v)
            Image.fromarray(palette[ids]).save(out / f"{mode}_{metric}.png")
            a = np.abs(errors)
            stats[f"{mode}_{metric}"] = {"median": float(np.median(a)), "within20": float(np.mean(a <= 20)*100), "over": int(np.sum(np.array(errors)>20)), "under": int(np.sum(np.array(errors)<-20))}
    shutil.copyfile(source / "location_lookup.js", out / "location_lookup.js")
    (out / "map_data.js").write_text("window.FIT=" + json.dumps({"locations": data, "stats": stats}, separators=(",", ":")) + ";\n")
    # A single local HTML avoids blocked/stale file subresources in embedded browsers.
    # Keep all viewer bindings local so host-injected scripts cannot collide with them.
    lookup = (out / "location_lookup.js").read_text().removeprefix("window.LOCATION_LOOKUP=").strip().removesuffix(";")
    payload = (out / "map_data.js").read_text().removeprefix("window.FIT=").strip().removesuffix(";")
    images = {f"{mode}_{metric}": "data:image/png;base64," + base64.b64encode((out/f"{mode}_{metric}.png").read_bytes()).decode("ascii")
              for mode in ["fitted", "heldout"] for metric in range(3)}
    html = HTML.replace('<script src="location_lookup.js"></script><script src="map_data.js"></script><script>',
                        '<script>(()=>{const FIT=' + payload + ';const LOCATION_LOOKUP=' + lookup + ';const MAP_IMAGES=' + json.dumps(images) + ';\n')
    html = html.replace('window.LOCATION_LOOKUP', 'LOCATION_LOOKUP').replace("img.src=key+'.png'", "img.src=MAP_IMAGES[key]")
    if no_overshoot:
        html = html.replace('EU5 · Attribute fitting error','EU5 · No-overshoot fitting error')
        html = html.replace('Where do the location attributes miss our targets?', 'Where does a no-overshoot fit fall short?')
        html = html.replace('Fixed, additive attribute effects, including river levels from the selected map, compared with our current equal-area model. Blue means the fit is too low; red means it is too high.', 'Same World Builder rivers and targets. Base land and multiplier are fitted with hard ceilings at each training location’s target. Blue shows the remaining shortfall; the full-map fit cannot overshoot beyond numerical solver tolerance. Held-out regions can still overshoot.')
        html = html.replace('<a href="report.md">Method and findings</a>', '<a href="comparison.md">Before / after findings</a> · <a href="../attribute_fit/index.html">Previous error map</a> · <a href="report.md">Method</a>')
        html = html.replace('Full-map fit: the coefficients were fitted using all locations.', 'Full-map fit: both fitted components are constrained below every location target. Predictions are not clipped.')
        html = html.replace('Held-out validation: each location is predicted by coefficients fitted without its entire region.', 'Held-out validation: this region was excluded from both fitting and ceiling constraints. Overshoot here measures generalization failure.')
    html = html.replace('</script></html>',  '})();</script></html>')
    (out / "index.html").write_text(html)
    present = set(np.unique(ids))
    missing = [r["tag"] for i,r in enumerate(data) if r is not None and i not in present]
    manifest = {"ownable_locations": sum(r is not None for r in data), "search_only_at_overview_resolution": missing,
                "formula": "100 * (prediction / target - 1)", "display_saturation_percent": 100,
                "combined_capacity": "separately fitted base * separately fitted multiplier; no improvements",
                "objective": objective, "no_overshoot": no_overshoot,
                "inputs": {str(p.relative_to(root)): sha256_file(p) for p in [source/"data.js", source/"location_ids.png", source/"location_lookup.js", out/"location_predictions.csv", Path(__file__)]}}
    (out / "map_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")


HTML = r'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EU5 · Attribute fitting error</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#0c1420;color:#e6edf3;font:15px system-ui,sans-serif}main{max-width:1600px;margin:auto;padding:24px}h1{font-size:25px;margin:0 0 8px}p{line-height:1.5;color:#afc2d5;margin:8px 0 18px}select,input,button{font:inherit;background:#182638;color:#e6edf3;border:1px solid #425367;border-radius:6px;padding:9px}button{cursor:pointer}label{color:#afc2d5;font-size:13px;display:grid;gap:6px}.controls{display:flex;gap:16px;flex-wrap:wrap;margin:20px 0}.controls input{width:280px}.layout{display:grid;grid-template-columns:minmax(0,1fr) 305px;gap:18px}canvas{width:100%;height:65vh;min-height:400px;display:block;touch-action:none;cursor:grab;background:#0d1824;border:1px solid #33465b;border-radius:8px}.map{position:relative}.zoom{position:absolute;left:12px;top:12px;display:flex;gap:6px}aside{padding:18px;background:#142131;border:1px solid #33465b;border-radius:8px}aside h2{font-size:20px;margin:0 0 6px}.row{display:flex;justify-content:space-between;gap:10px;padding:10px 0;border-bottom:1px solid #2c4054}.muted,small{color:#afc2d5}.legend{margin:14px 0;max-width:600px}.gradient{height:12px;background:linear-gradient(90deg,#2a6fbb,#e7eae7,#bf353a);border-radius:4px}.ticks{display:flex;justify-content:space-between;font-size:13px;margin-top:5px}.stats{margin:16px 0;font-size:14px;color:#cbd7e3}a{color:#82c6ff}details{margin-top:20px}summary{cursor:pointer}#suggestions{position:absolute;background:#182638;z-index:4;width:340px;max-height:300px;overflow:auto;border-radius:5px}#suggestions button{display:block;width:100%;text-align:left;border:0;border-radius:0}#suggestions button:hover{background:#304861}.search{position:relative}.badge{font-size:12px;color:#efcd8d}.note{font-size:13px;max-width:1000px}@media(max-width:850px){.layout{grid-template-columns:1fr}canvas{height:55vh}main{padding:16px}}
</style><main>
<h1>Where do the location attributes miss our targets?</h1>
<p>Fixed, additive attribute effects, including river levels from the selected map, compared with our current equal-area model. Blue means the fit is too low; red means it is too high.</p>
<div class="controls"><label>Value<select id="metric"><option value="2">Base × multiplier · people supported</option><option value="0">Base land · effective units</option><option value="1">Productivity multiplier</option></select></label>
<label>Evaluation<select id="mode"><option value="fitted">Fit to the full map</option><option value="heldout">Validation · regions held out</option></select></label>
<label class="search">Find a location<input id="search" placeholder="Location or province…" autocomplete="off"><div id="suggestions" style="top:66px"></div></label></div>
<div class="layout"><div><div class="map"><canvas id="map"></canvas><div class="zoom"><button id="plus" aria-label="Zoom in">+</button><button id="minus" aria-label="Zoom out">−</button><button id="reset">Reset view</button></div></div>
<div class="legend"><div class="gradient"></div><div class="ticks"><span>−100% · too low</span><span>0% · matches</span><span>+100% or more · too high</span></div></div>
<div id="stats" class="stats"></div></div><aside id="panel"><h2>Inspect a location</h2><p>Click the map or search above to compare its target with the additive fit.</p></aside></div>
<p class="note" id="explanation"></p><p class="note">Error = (fitted value − target) ÷ target. Colours saturate at ±100%; location details retain the full error. Grey land is outside the ownable-location fit. All 20,893 fitted locations are searchable, including those too small to see at this map resolution. These are fitting errors against our model, not historical error estimates.</p>
<p class="note"><a href="report.md">Method and findings</a> · <a href="location_predictions.csv">All location values</a></p>
</main><script src="location_lookup.js"></script><script src="map_data.js"></script><script>
const canvas=document.getElementById('map'),ctx=canvas.getContext('2d'),metric=document.getElementById('metric'),mode=document.getElementById('mode'),panel=document.getElementById('panel'),search=document.getElementById('search'),suggestions=document.getElementById('suggestions');
let img=new Image(),z=1,ox=0,oy=0,selected=0,drag=null,moved=false;
const pretty=s=>s.replaceAll('_',' '),fmt=n=>n.toLocaleString('en-US',{maximumFractionDigits:2}),esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
function locationAt(x,y){const m=window.LOCATION_LOOKUP;if(x<0||y<0||x>=m.width||y>=m.height)return 0;const row=m.rows[Math.floor(y)];let lo=0,hi=row.length/2;while(lo<hi){let mid=(lo+hi)>>>1;if(x<row[mid*2])hi=mid;else lo=mid+1}return lo<row.length/2?row[lo*2+1]:0}
function draw(){ctx.fillStyle='#0d1824';ctx.fillRect(0,0,canvas.width,canvas.height);if(!img.complete||!img.naturalWidth)return;const s=Math.min(canvas.width/4096,canvas.height/2048)*z;ctx.imageSmoothingEnabled=false;ctx.drawImage(img,ox,oy,4096*s,2048*s);const r=FIT.locations[selected];if(r){ctx.beginPath();ctx.arc(ox+r.x*s,oy+r.y*s,6*devicePixelRatio,0,Math.PI*2);ctx.strokeStyle='#fff';ctx.lineWidth=2*devicePixelRatio;ctx.stroke()}}
function fit(){canvas.width=canvas.clientWidth*devicePixelRatio;canvas.height=canvas.clientHeight*devicePixelRatio;draw()}
function reset(){z=1;let s=Math.min(canvas.width/4096,canvas.height/2048);ox=(canvas.width-4096*s)/2;oy=(canvas.height-2048*s)/2;draw()}
function show(id){selected=id;const r=FIT.locations[id];if(!r){panel.innerHTML='<h2>Outside this fit</h2><p>This location is not part of the ownable-location fitting dataset.</p>';draw();return}let k=+metric.value,t=r.target[k],p=r[mode.value][k],e=100*(p/t-1);panel.innerHTML='<h2>'+esc(pretty(r.tag))+'</h2><small>'+esc(pretty(r.province))+'</small><p class="badge">'+esc(metric.selectedOptions[0].text)+'</p><div class="row"><span>Model target</span><b>'+fmt(t)+'</b></div><div class="row"><span>Additive fit</span><b>'+fmt(p)+'</b></div><div class="row"><span>Difference</span><b>'+(p>=t?'+':'')+fmt(p-t)+'</b></div><div class="row"><span>Error</span><b>'+(e>=0?'+':'')+fmt(e)+'%</b></div><p>'+ (e>0?'The fit overestimates this location.':e<0?'The fit underestimates this location.':'The fit matches this location.')+'</p><details><summary>Location attributes</summary>'+Object.entries(r.attributes).map(([k,v])=>'<div class="row"><small>'+esc(pretty(k))+'</small><span>'+esc(pretty(v))+'</span></div>').join('')+'</details>';draw()}
function update(){let key=mode.value+'_'+metric.value;img=new Image();img.onload=draw;img.src=key+'.png';const s=FIT.stats[key];document.getElementById('stats').textContent='Median absolute error: '+fmt(s.median)+'%  ·  Within ±20%: '+fmt(s.within20)+'%  ·  More than 20% too low: '+fmt(s.under)+'  ·  More than 20% too high: '+fmt(s.over);document.getElementById('explanation').textContent=(mode.value==='fitted'?'Full-map fit: the coefficients were fitted using all locations.':'Held-out validation: each location is predicted by coefficients fitted without its entire region.')+(metric.value==='2'?' This view multiplies the separately fitted base and multiplier. It shows the inert capacity contribution only; improvements are excluded.':' Each prediction is a reference value plus the effects of its eight displayed attributes.');if(selected)show(selected)}
function zoom(f,x=canvas.width/2,y=canvas.height/2){let nz=Math.max(.5,Math.min(40,z*f)),r=nz/z;ox=x-(x-ox)*r;oy=y-(y-oy)*r;z=nz;draw()}
canvas.onpointerdown=e=>{drag=[e.clientX,e.clientY,ox,oy];moved=false;canvas.setPointerCapture(e.pointerId)};
canvas.onpointermove=e=>{if(!drag)return;let dx=e.clientX-drag[0],dy=e.clientY-drag[1];if(Math.abs(dx)+Math.abs(dy)>3)moved=true;ox=drag[2]+dx*devicePixelRatio;oy=drag[3]+dy*devicePixelRatio;draw()};
canvas.onpointerup=e=>{if(drag&&!moved){let b=canvas.getBoundingClientRect(),s=Math.min(canvas.width/4096,canvas.height/2048)*z,id=locationAt(((e.clientX-b.left)*devicePixelRatio-ox)/s,((e.clientY-b.top)*devicePixelRatio-oy)/s);if(id)show(id)}drag=null};canvas.onpointercancel=()=>drag=null;
canvas.addEventListener('wheel',e=>{e.preventDefault();let b=canvas.getBoundingClientRect();zoom(e.deltaY<0?1.2:1/1.2,(e.clientX-b.left)*devicePixelRatio,(e.clientY-b.top)*devicePixelRatio)},{passive:false});
document.getElementById('plus').onclick=()=>zoom(1.5);document.getElementById('minus').onclick=()=>zoom(1/1.5);document.getElementById('reset').onclick=reset;metric.onchange=update;mode.onchange=update;
function jump(id){show(id);let r=FIT.locations[id];z=5;let s=Math.min(canvas.width/4096,canvas.height/2048)*z;ox=canvas.width/2-r.x*s;oy=canvas.height/2-r.y*s;draw();suggestions.replaceChildren();search.value=pretty(r.tag)}
search.oninput=()=>{let q=search.value.toLowerCase().trim().replaceAll(' ','_');suggestions.replaceChildren();if(!q)return;FIT.locations.map((r,id)=>({r,id})).filter(({r})=>r&&(r.tag.includes(q)||r.province.includes(q))).slice(0,12).forEach(({r,id})=>{let b=document.createElement('button');b.textContent=pretty(r.tag)+' · '+pretty(r.province);b.onclick=()=>jump(id);suggestions.appendChild(b)})};search.onkeydown=e=>{if(e.key==='Enter')suggestions.querySelector('button')?.click();if(e.key==='Escape')suggestions.replaceChildren()};
window.addEventListener('resize',fit);fit();reset();update();
</script></html>'''
