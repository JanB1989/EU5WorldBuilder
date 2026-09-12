"""Compact, offline water-map viewer. No dependence on the food dashboard."""
import json,csv,html
from pathlib import Path
import numpy as np,rasterio
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize, LinearSegmentedColormap
NAMES=['natural','historical','maximum']
LABELS=['Natural rainfall baseline','Estimated irrigation · 1300','Upper surface-irrigation scenario']
DISPLAY_NAMES=NAMES+['difference','historical_difference']
DISPLAY_LABELS=LABELS+['Irrigation benefit · rainfed minus upper','Starting irrigation benefit · rainfed minus 1300']
DIFF_COLORS=['#253947','#467bdd','#49d3ca','#f9e87f']
POINTS=[('Nile delta',31.15,30.8),('Upper Nile corridor',32.65,25.7),('Taihu agricultural margin',120.45,31.4),('Angkor',103.9,13.4),('Punjab',74.3,31.5),('Tarim basin',83,40),('Moscow',37.6,55.75),('Central Sahara',13,23),('Java',110.4,-7.8),('La Plata',-60,-34)]
def read(p):
    with rasterio.open(p) as d:return d.read(masked=True).filled(np.nan)
def report(out,cfg,audit):
    out=Path(out);cmap=plt.get_cmap('RdYlGn_r').copy();cmap.set_bad((0,0,0,0))
    monthdata={n:read(out/f'{n}_monthly_deficit_mm.tif') for n in NAMES}
    monthdata['difference']=monthdata['natural']-monthdata['maximum']
    monthdata['historical_difference']=monthdata['natural']-monthdata['historical']
    from .water import save
    for name in ['difference','historical_difference']:
        save(out/(name+'_monthly_mm.tif'),monthdata[name],[f'month_{m+1}_deficit_reduction_mm' for m in range(12)])
        save(out/(name+'_annual_mm.tif'),monthdata[name].sum(axis=0))
    diffcmap=LinearSegmentedColormap.from_list('irrigation_benefit',DIFF_COLORS)
    diffcmap.set_bad((0,0,0,0))
    domain=read(out/'domain.tif')[0]
    for n in DISPLAY_NAMES:
        for m in range(13):
            a=monthdata[n].sum(axis=0) if m==0 else monthdata[n][m-1]
            palette=diffcmap if n.endswith('difference') else cmap
            ceiling=(100 if m==0 else 20) if n.endswith('difference') else (2500 if m==0 else 300)
            rgba=palette(Normalize(0,ceiling,clip=True)(np.ma.masked_invalid(a)))
            # Gray explicitly marks unknown coverage / permanently frozen reference.
            rgba[(domain==2)|((domain>0)&~np.isfinite(a))]=[.34,.37,.39,1]
            plt.imsave(out/f'{n}_{m:02}.png',rgba)
    # Lightweight exact-at-preview-cell monthly values for cursor readout.
    # Display raster remains native resolution; cursor samples a stated 20-minute grid.
    preview={n:np.nan_to_num(np.rint(a[:,::4,::4]),nan=-1).astype('int16').tolist() for n,a in monthdata.items()}
    (out/'preview.js').write_text('const waterPreview='+json.dumps(preview,separators=(',',':'))+';')
    rows=[]
    for name,lon,lat in POINTS:
        r=int((90-lat)*12);c=int((lon+180)*12)
        row={'place':name,'latitude':lat,'longitude':lon}
        for n in NAMES:
            v=monthdata[n][:,r,c]
            row[n+'_deficit_mm_year']=round(float(v.sum()),1) if np.isfinite(v).all() else None
        rows.append(row)
    with (out/'reference_points.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    fig,axes=plt.subplots(3,1,figsize=(15,17),facecolor='#101920',layout='constrained')
    for ax,n,label in zip(axes,NAMES,LABELS):
        a=monthdata[n].sum(axis=0);ax.set_facecolor('#1c2933')
        im=ax.imshow(a,extent=(-180,180,-90,90),cmap=cmap,vmin=0,vmax=2500,interpolation='nearest')
        ax.set_xlim(-180,180);ax.set_ylim(-60,85);ax.set_title(label,color='#eaf1f2',loc='left',fontsize=16)
        ax.tick_params(colors='#9cadb4');ax.spines[:].set_visible(False)
    cb=fig.colorbar(im,ax=axes,orientation='horizontal',fraction=.025,pad=.015,extend='max')
    cb.set_label('Annual unmet reference water demand · mm/year · lower = wetter',color='#eaf1f2');cb.ax.tick_params(colors='#aabbc4')
    fig.suptitle('Water access scenarios · 1300 management / modern climate proxy',color='white',fontsize=19)
    fig.savefig(out/'water_overview.png',dpi=120,facecolor=fig.get_facecolor());plt.close(fig)
    for diff_name,diff_title in [('difference','Irrigation benefit · rainfed minus upper'),('historical_difference','Starting irrigation benefit · rainfed minus 1300')]:
        fig,ax=plt.subplots(figsize=(15,7),facecolor='#101920',layout='constrained')
        ax.set_facecolor('#1c2933')
        im=ax.imshow(monthdata[diff_name].sum(axis=0),extent=(-180,180,-90,90),cmap=diffcmap,vmin=0,vmax=100,interpolation='nearest')
        ax.set_xlim(-180,180);ax.set_ylim(-60,85)
        ax.set_title(diff_title,color='#eaf1f2',loc='left',fontsize=16)
        ax.tick_params(colors='#9cadb4');ax.spines[:].set_visible(False)
        cb=fig.colorbar(im,ax=ax,orientation='horizontal',fraction=.04,pad=.06,extend='max')
        cb.set_label('Reduction in water shortage · mm/year · brighter = larger improvement',color='#eaf1f2');cb.ax.tick_params(colors='#aabbc4')
        fig.savefig(out/('water_'+diff_name+'.png'),dpi=120,facecolor=fig.get_facecolor(),bbox_inches='tight',pad_inches=.15);plt.close(fig)
    page=HTML.replace('__YEAR__',str(cfg['year'])).replace('__FINGERPRINT__',audit['source_fingerprint'][:12])
    cards=''.join(f'<article><h2>{i+1}. {label}</h2><canvas id="{n}" width="1440" height="580" aria-label="{label}"></canvas><p id="{n}-value" class="value">Move over a map to compare the same point.</p></article>' for i,(n,label) in enumerate(zip(DISPLAY_NAMES,DISPLAY_LABELS)))
    difflegend='<p class="small">Rainfed deficit − upper-irrigation deficit. Positive values mean less water shortage; zero means no change. The calculation and cell averaging are unchanged.</p><div class="legend"><div class="gradient diff-gradient"></div><div class="ticks"><span>0 · no change</span><span id="diff-middle">50</span><span id="diff-upper">100+ mm/year improvement</span></div></div>'
    cards=cards.replace('<canvas id="difference"',difflegend+'<canvas id="difference"')
    startlegend=difflegend.replace('upper-irrigation',f'estimated {cfg["year"]} irrigation').replace('id="diff-', 'id="start-diff-')
    cards=cards.replace('<canvas id="historical_difference"',startlegend+'<canvas id="historical_difference"')
    page=page.replace('__CARDS__',cards)
    page=page.replace('__BUDGET__',f"{audit['historical_withdrawal_km3_year']:.0f} / {audit['maximum_withdrawal_km3_year']:.0f}")
    page=page.replace('__TABLE__',''.join('<tr><td>'+html.escape(r['place'])+'</td>'+''.join('<td>'+('—' if r[n+'_deficit_mm_year'] is None else str(r[n+'_deficit_mm_year']))+'</td>' for n in NAMES)+'</tr>' for r in rows))
    (out/'index.html').write_text(page)
HTML="""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Water access · __YEAR__</title>
<style>
:root{color-scheme:dark;font:16px/1.55 system-ui;background:#101920;color:#e9f0f2}body{max-width:1500px;margin:auto;padding:30px}h1{font-size:32px;margin:0}h2{font-size:19px;margin:12px 0}p{color:#b6c5ce;max-width:1050px}.eyebrow{font-size:12px;letter-spacing:.13em;text-transform:uppercase;color:#8badae}.toolbar{display:flex;gap:22px;align-items:center;flex-wrap:wrap;position:sticky;top:0;background:#101920f2;padding:15px 0;z-index:2;border-bottom:1px solid #30424d}select,button{font:inherit;background:#21323d;color:white;padding:7px;border:1px solid #4f626e;border-radius:6px}.legend{width:440px;max-width:95%;font-size:12px}.gradient{height:12px;border-radius:5px;background:linear-gradient(to right,#006837,#66bd63,#d9ef8b,#ffffbf,#fee08b,#f46d43,#a50026)}.diff-gradient{background:linear-gradient(to right,#253947,#467bdd,#49d3ca,#f9e87f);margin-top:6px}.ticks{display:flex;justify-content:space-between}.maps{display:grid;gap:18px}article{background:#15232d;border:1px solid #2e414e;border-radius:10px;padding:12px 16px}canvas{width:100%;display:block;background:#1c2933;border-radius:6px;cursor:crosshair;touch-action:none}.value{font-variant-numeric:tabular-nums;font-size:14px;min-height:24px;margin:5px 0}details{border-top:1px solid #30424d;margin-top:25px;padding-top:12px}summary{cursor:pointer;font-size:18px}a{color:#94d8ce}table{border-collapse:collapse;font-size:14px}th,td{text-align:right;padding:7px 18px;border-bottom:1px solid #30424d}td:first-child,th:first-child{text-align:left}.note{padding:12px 16px;border-left:3px solid #beab73;background:#252a2a;font-size:14px}.small{font-size:13px}footer{font-size:12px;color:#839ba9;padding:25px 0}@media(max-width:700px){body{padding:12px}h1{font-size:25px}.toolbar{gap:10px}article{padding:8px}.legend{width:300px}}
</style>
<div class="eyebrow">Historical Agriculture · water only · exploratory reconstruction</div>
<h1>Water access around __YEAR__</h1>
<p>Three scenarios for the same reference vegetation, plus two irrigation-benefit difference maps. The first three colour scales show <strong>unmet water demand in millimetres</strong>: green means little shortage; red means a large shortage. The fourth and fifth maps share a more sensitive scale to compare upper-scenario and starting irrigation benefits. No crop, yield or population assumptions enter these maps.</p>
<div class="note"><strong>What “1300” means here:</strong> reconstructed irrigation extent, using 1970–2000 climate and runoff as a proxy. The upper map screens traditional surface-irrigation opportunities; it is not a proven historical maximum.</div>
<div class="toolbar">
<label>Period <select id="month"><option value="0">Whole year</option></select></label>
<label>View <select id="region"><option value="world">World</option><option value="nile">Nile and Near East</option><option value="asia">South and East Asia</option><option value="europe">Europe and Central Asia</option><option value="africa">Africa</option><option value="americas">Americas</option></select></label>
<button id="reset">Reset view</button>
<div class="legend"><span>Maps 1–3 · unmet demand</span><div class="gradient"></div><div class="ticks"><span>0 · no deficit</span><span id="middle">1,250</span><span id="upper">2,500+ mm/year</span></div></div>
</div>
<p class="small">Maps zoom together: use the region selector, scroll to zoom, or drag to pan. Gray = frozen reference or missing inputs. Hover values sample a 20′ preview; downloads retain the native 5′ grid.</p>
<div class="maps">__CARDS__</div>
<details><summary>Read the maps correctly</summary>
<p><strong>1. Natural rainfall baseline:</strong> precipitation and snowmelt feed a 100 mm soil-water store. Reference evapotranspiration depletes it. This is a rainfed baseline, not a model of natural flood inundation, groundwater or wetland water tables.</p>
<p><strong>2. Estimated irrigation:</strong> HYDE's irrigation footprint for __YEAR__ receives water subject to the same river budget. Its recorded irrigated share is a modeled historical estimate, not an archaeological survey; the map does not assert continuous year-round watering in 1300.</p>
<p><strong>3. Upper surface-irrigation scenario:</strong> expansion along mapped rivers, screened by low terrain, distance and low-lift access. Existing water allocations retain priority. This scenario excludes engineered seasonal storage, wells, qanats, large transfers and explicit canal routing. It is neither a universal technological ceiling nor a complete maximum.</p>
<p><strong>4. Irrigation benefit:</strong> rainfed deficit minus upper-scenario deficit, in mm. Brighter colours mean a greater reduction in shortage. Its more sensitive scale saturates at 100 mm/year or 20 mm/month; pointer values and GeoTIFFs keep the full values. Missing inputs remain missing.</p>
<p><strong>5. Starting irrigation benefit:</strong> rainfed deficit minus estimated __YEAR__ deficit. It uses exactly the same difference colour scale as map 4, isolating the benefit of irrigation already represented at the start date. It retains the same cell averaging and source limitations.</p>
<p><strong>Common denominator:</strong> millimetres per hectare of reference land surface, averaged within each cell. Irrigation affects the serviced fraction only. Cell area is used internally to balance river withdrawals, so we cannot give every hectare the river's entire flow. This is water access, not cultivated hectares or people fed.</p>
<p><strong>Cold regions:</strong> a low water deficit does not imply good agriculture. Temperature, crop calendars, soils and drainage still matter.</p>
</details>
<details><summary>Reference locations · annual deficit in mm</summary><table><thead><tr><th>Location</th><th>Rainfall</th><th>Historical</th><th>Upper</th></tr></thead><tbody>__TABLE__</tbody></table><p class="small">Point samples illustrate the calculation; they are not regional averages or historical observations.</p></details>
<details><summary>Evidence, assumptions and water accounting</summary>
<p><a href="https://www.worldclim.org/data/worldclim21.html">WorldClim 2.1</a> supplies monthly climate. <a href="https://www.fao.org/4/X0490E/x0490e06.htm">FAO-56</a> defines reference evapotranspiration. An analytically initialized cyclic monthly soil-and-snow bucket gives water deficit.</p>
<p><a href="https://doi.org/10.5194/essd-11-1655-2019">GRUN</a> supplies local runoff. <a href="https://www.hydrosheds.org/products/hydrobasins">HydroBASINS</a> routes it between catchments. <a href="https://www.hydrosheds.org/hydroatlas">RiverATLAS</a> identifies river corridors and constrains routed discharge (including a modeled transmission-loss adjustment), and <a href="https://www.ncei.noaa.gov/products/etopo-global-relief-model">ETOPO 2022</a> screens terrain.</p>
<p><a href="https://doi.org/10.5194/essd-9-927-2017">HYDE methodology</a> explains historical irrigation allocation. The reused April 2025 netCDF files identify themselves as HYDE3.4; their cache notes say 3.5. Exact hashes and the metadata conflict are recorded rather than silently resolved.</p>
<p>Shared screening assumptions: 40% irrigation efficiency (<a href="https://www.fao.org/4/t7202e/t7202e08.htm">FAO traditional-system context</a>), 60% runoff reserve (a conservative scenario choice), no seasonal reservoir storage, a 10 km local access taper, 6 m low-lift screen plus 15 m terrain-resolution allowance. These are adjustable assumptions, not measured universal medieval limits. <a href="https://www.fao.org/4/ah810e/ah810e05.htm">FAO water-lifting devices</a> supports the low-lift mechanism, not every numeric mapping choice.</p>
<p>Runoff has a native 0.5° resolution; flow sharing is at HydroBASINS level 6. The 5′ display does not create finer hydrological evidence. The documented Nile delta distributary/canal connection is represented as a withdrawal from the main Nile, rather than from isolated coastal catchments (<a href="https://knowledge.uchicago.edu/record/1009/files/MSR_IV_2000-Borsch.pdf">Borsch</a>). Its footprint is an approximate low-elevation watershed screen. Other undocumented canal connections remain a limitation. Withdrawals are removed before water continues downstream; no return-flow credit is assumed. Annual withdrawals in the reference experiment: __BUDGET__ km³ (historical / upper).</p>
<p>Remaining limitations: modern environmental proxies, within-month rainfall timing, monthly temperature/snow approximations, incomplete natural inundation, access without engineered canal routes, modeled historical irrigation extent, no explicit competing non-irrigation withdrawals beyond the runoff reserve.</p>
</details>
<details><summary>Download and reproduce</summary>
<p><a href="water_overview.png">Three-scenario overview</a> · <a href="water_difference.png">Upper difference map</a> · <a href="water_historical_difference.png">Starting difference map</a> · <a href="manifest.json">Source and parameter manifest</a> · <a href="validation.json">Accounting validation</a> · <a href="reference_points.csv">Reference points</a> · <a href="basin_monthly_budget.npz">Monthly basin ledger</a></p>
<p><a href="natural_monthly_deficit_mm.tif">Natural monthly GeoTIFF</a> · <a href="historical_monthly_deficit_mm.tif">Historical monthly GeoTIFF</a> · <a href="maximum_monthly_deficit_mm.tif">Upper monthly GeoTIFF</a> · <a href="difference_monthly_mm.tif">Difference monthly GeoTIFF</a> · <a href="difference_annual_mm.tif">Upper difference annual GeoTIFF</a> · <a href="historical_difference_monthly_mm.tif">Starting difference monthly GeoTIFF</a> · <a href="historical_difference_annual_mm.tif">Starting difference annual GeoTIFF</a></p>
<pre>uv run python scripts/acquire_water.py
uv run ha1300 water --config configs/water.json --output artifacts/water</pre>
<p class="small">Paths to the existing large scientific caches are configured in water.json. No changes to the food dashboard or game deployment.</p>
</details>
<footer>Input fingerprint __FINGERPRINT__ · Engineering checks and scientific support are reported separately.</footer>
<script src="preview.js"></script>
<script>
const names=['natural','historical','maximum','difference','historical_difference'],months=['Whole year','January','February','March','April','May','June','July','August','September','October','November','December'];
const select=document.getElementById('month');months.slice(1).forEach((s,i)=>select.add(new Option(s,i+1)));
const regions={world:[-180,180,-60,85],nile:[20,60,5,40],asia:[65,145,-12,48],europe:[-15,105,25,72],africa:[-20,55,-37,38],americas:[-135,-30,-58,68]};
let view=regions.world.slice(),images={},serial=0,drag=null;
const canvases=names.map(n=>document.getElementById(n));
function draw(){canvases.forEach((c,i)=>{c.height=Math.round(c.width*(view[3]-view[2])/(view[1]-view[0]));const x=c.getContext('2d'),im=images[names[i]];x.fillStyle='#1c2933';x.fillRect(0,0,c.width,c.height);if(im)x.drawImage(im,(view[0]+180)*12,(90-view[3])*12,(view[1]-view[0])*12,(view[3]-view[2])*12,0,0,c.width,c.height);});}
function load(){const token=++serial,m=Number(select.value);document.getElementById('middle').textContent=m?'150':'1,250';document.getElementById('upper').textContent=m?'300+ mm/month':'2,500+ mm/year';['diff','start-diff'].forEach(prefix=>{document.getElementById(prefix+'-middle').textContent=m?'10':'50';document.getElementById(prefix+'-upper').textContent=m?'20+ mm/month improvement':'100+ mm/year improvement';});names.forEach(n=>{const im=new Image();im.onload=()=>{if(token===serial){images[n]=im;draw();}};im.src=n+'_'+String(m).padStart(2,'0')+'.png';});}
select.onchange=load;document.getElementById('region').onchange=e=>{view=regions[e.target.value].slice();draw();};document.getElementById('reset').onclick=()=>{view=regions[document.getElementById('region').value].slice();draw();};
function pos(e,c){const r=c.getBoundingClientRect();return[(e.clientX-r.left)/r.width,(e.clientY-r.top)/r.height];}
function clamp(){const w=Math.min(360,view[1]-view[0]),h=Math.min(180,view[3]-view[2]);view[0]=Math.max(-180,Math.min(180-w,view[0]));view[1]=view[0]+w;view[2]=Math.max(-90,Math.min(90-h,view[2]));view[3]=view[2]+h;}
canvases.forEach(c=>{
c.onpointerdown=e=>{drag={p:pos(e,c),v:view.slice()};c.setPointerCapture(e.pointerId);};c.onpointerup=()=>drag=null;c.onpointercancel=()=>drag=null;
c.onpointermove=e=>{const p=pos(e,c);if(drag){const dx=(p[0]-drag.p[0])*(drag.v[1]-drag.v[0]),dy=(p[1]-drag.p[1])*(drag.v[3]-drag.v[2]);view=[drag.v[0]-dx,drag.v[1]-dx,drag.v[2]+dy,drag.v[3]+dy];clamp();draw();}
const lon=view[0]+p[0]*(view[1]-view[0]),lat=view[3]-p[1]*(view[3]-view[2]),row=Math.min(539,Math.max(0,Math.round((90-lat)*3))),col=Math.min(1079,Math.max(0,Math.round((lon+180)*3))),m=Number(select.value);
names.forEach(n=>{const a=waterPreview[n],v=m?a[m-1][row][col]:a.map(x=>x[row][col]).reduce((s,x)=>s<0||x<0?-1:s+x,0);document.getElementById(n+'-value').textContent=lat.toFixed(2)+'°, '+lon.toFixed(2)+'° · '+(v<0?'Not evaluated':v.toLocaleString()+' mm '+(m?'this month':'per year')+(n.endsWith('difference')?' less water shortage':' unmet demand'));});};
c.onwheel=e=>{e.preventDefault();const p=pos(e,c),f=e.deltaY<0?.8:1.25,w=(view[1]-view[0])*f,h=(view[3]-view[2])*f;if(w<2||h<2)return;const lon=view[0]+p[0]*(view[1]-view[0]),lat=view[3]-p[1]*(view[3]-view[2]);view=[lon-p[0]*w,lon+(1-p[0])*w,lat-(1-p[1])*h,lat+p[1]*h];clamp();draw();};
});
load();
</script></html>"""
