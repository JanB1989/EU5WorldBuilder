import json
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm, SymLogNorm
from matplotlib.patches import Patch
from .reporting import thumbnail


def food_report(root,config,out,diagnostic_paths):
    folder=out/'maps'
    coverage=json.loads((out/'food_coverage.json').read_text())
    validation=json.loads((out/'food_validation.json').read_text())
    labels={int(k):v for k,v in coverage['labels'].items()}
    colors=['#eeeeee','#b78e32','#e2bf67','#a66c23','#dcc88a','#8c633c','#edc948','#d94a3d','#ed9991','#8c68af','#b3a0ca','#9a6749','#be9a80','#bd5591','#e1a0c2','#455e98','#659ed1','#4c9b68','#91bd62',
            '#926f46','#6b6559','#426e58','#388ba3','#8b7757','#e0e3e5','#adbbae']
    food=thumbnail(out/'food_type.tif')
    def base(ax):
        ax.set_xlim(-180,180);ax.set_ylim(-60,85)
        ax.set_xlabel('Longitude');ax.set_ylabel('Latitude');ax.set_facecolor('#edf2f4')
    fig,ax=plt.subplots(figsize=(16,7),layout='constrained')
    ax.imshow(food,extent=(-180,180,-90,90),cmap=ListedColormap(colors),norm=BoundaryNorm(np.arange(-.5,26.5),26),interpolation='nearest')
    base(ax);ax.set_title('Representative food system around 1300\nHistorical crop preferences and regional livelihood analogues')
    ax.legend(handles=[Patch(color=colors[i],label=labels[i]) for i in labels],loc='upper left',bbox_to_anchor=(1.01,1),fontsize=8)
    fig.savefig(folder/'food_systems.png',dpi=150);plt.close(fig)
    arrays={k:thumbnail(out/f'{k}_people.tif') for k in ['lower','upper','historical']}
    values=np.concatenate([a.compressed() for a in arrays.values()]);vmax=max(1,float(np.quantile(values,.995)))
    norm=SymLogNorm(linthresh=.001,vmin=0,vmax=vmax,base=10)
    names={'lower':'Lower food-support scenario','upper':'Upper food-support scenario','historical':'Estimated system around 1300'}
    for key,data in arrays.items():
        fig,ax=plt.subplots(figsize=(14,6),layout='constrained')
        # Unquantified land must remain distinct from zero and ocean.
        ax.imshow(np.ma.masked_where(food.mask,np.ones(food.shape)),extent=(-180,180,-90,90),cmap=ListedColormap(['#d9b9d5']),vmin=0,vmax=1,interpolation='nearest')
        im=ax.imshow(data,extent=(-180,180,-90,90),cmap='YlGn',norm=norm,interpolation='nearest')
        base(ax);ax.set_title(names[key]+' — people fed per used hectare\nCrop scenarios; experimental non-crop analogues; aquatic food excluded')
        ticks=[x for x in [0,.001,.01,.1,1,10,100] if x<=vmax]
        bar=fig.colorbar(im,ax=ax,label='People / used ha / year · shared nonlinear scale',shrink=.8,extend='max',ticks=ticks)
        bar.ax.set_yticklabels([f'{x:g}' for x in ticks])
        ax.legend(handles=[Patch(color='#d9b9d5',label='Not yet quantified')],loc='lower left',fontsize=8)
        fig.savefig(folder/f'{key}_people.png',dpi=150);plt.close(fig)
    main=[('food_systems','Food systems'),('lower_people','Lower scenario'),('upper_people','Upper scenario'),('historical_people','Estimated 1300 system'),('benchmarks','Seshat comparisons')]
    diagnostics=''.join(f'<li><a href="maps/{Path(p).name}">{Path(p).stem.replace("_"," ")}</a></li>' for p in diagnostic_paths if Path(p).stem!='benchmarks')
    sections=''.join(f'<section id="{key}"><h2>{title}</h2><a href="maps/{key}.png"><img src="maps/{key}.png" alt="{title}" loading="lazy"></a></section>' for key,title in main)
    page="""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Food productivity · 1300</title>
<style>body{font:17px/1.6 system-ui;color:#25382f;max-width:1250px;margin:40px auto;padding:0 24px;background:#faf9f5}h1{font-size:38px;line-height:1.2;margin-bottom:12px}h2{font-size:23px}p{max-width:1000px}a{color:#276047}nav{display:flex;gap:20px;flex-wrap:wrap;border-bottom:1px solid #ced6cf;padding:18px 0}section{margin:40px 0}img{width:100%;height:auto}details{border-top:1px solid #ced6cf;padding:20px 0}summary{cursor:pointer;font-weight:600}.note{background:#eef0e8;padding:12px 18px;border-radius:6px;font-size:15px}</style>
<h1>Food productivity around 1300</h1>
<p>Which food system fits here, and how many people can one hectare used by that system feed?</p>
<p class="note">Per-hectare productivity only. No cultivated-area estimates or cell totals. One person-equivalent uses DAILY kcal/day. Crops include fallow and harvest frequency; livestock use grazing hectares; foraging uses terrestrial range hectares. Fishing is identified, but its aquatic calories are excluded.</p>
<nav><a href="#food_systems">Food systems</a><a href="#lower_people">Lower</a><a href="#upper_people">Upper</a><a href="#historical_people">1300 estimate</a><a href="#benchmarks">Seshat</a></nav>
<p class="note">The food-system mask is complete on the GAEZ land domain. Non-crop numerical estimates remain experimental: non-crop patterns use a coarse process model with fine-climate-guided interpolation; livestock uses a provisional biomass-to-herd conversion. Fine spatial detail is inferred. Lower/upper non-crop values are analogue/model scenarios, not established medieval limits. UNQUANTIFIED land cells remain unquantified.</p>
"""
    page=page.replace('DAILY',f"{validation['daily_kcal_per_person']:,}").replace('UNQUANTIFIED',f"{validation['unquantified_cells']:,}")
    page+=sections+'<details><summary>Methods, evidence and diagnostics</summary><p><a href="REPORT.md">Research report</a> · <a href="FOOD_METHOD.md">Food-system method and limitations</a> · <a href="food_assignment_ledger.json">Assignment ledger</a> · <a href="benchmark_people.csv">Seshat values in people/ha</a> · <a href="food_validation.json">Food validation</a></p><ul>'+diagnostics+'</ul></details></html>'
    (out/'index.html').write_text(page)
    (out/'FOOD_METHOD.md').write_text((root/'reports/food_system_method.md').read_text())
    return {'report':str(out/'REPORT.md'),'gallery':str(out/'index.html'),'main_figures':5,'maps':len(list(folder.glob('*.png'))),'food_mask_complete':coverage['complete_mask'],'numeric_coverage_complete':validation['unquantified_cells']==0}
