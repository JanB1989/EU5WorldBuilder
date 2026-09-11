import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Patch

def thumbnail(path):
    with rasterio.open(path) as d:
        a=d.read(1,out_shape=(540,1080),masked=True)
    return a

def report(root,config,out):
    mapdir=out/'maps';mapdir.mkdir(exist_ok=True)
    paths=[]
    plt.rcParams.update({'font.size':10,'figure.facecolor':'#faf9f5','axes.facecolor':'#e8edf0'})
    def base(ax):
        ax.set_xlim(-180,180);ax.set_ylim(-60,85)
        ax.set_xlabel('Longitude');ax.set_ylabel('Latitude')
    def paired(names,title,unit,scale=1.):
        data=[thumbnail(out/f'{n}.tif')/scale for n in names]
        valid=np.concatenate([a.compressed() for a in data]);vmax=float(np.quantile(valid,.995)) if len(valid) else 1.
        fig,axes=plt.subplots(len(names),1,figsize=(13,4*len(names)),layout='constrained')
        axes=np.atleast_1d(axes)
        for ax,a,name in zip(axes,data,names):
            im=ax.imshow(a,extent=(-180,180,-90,90),vmin=0,vmax=max(vmax,.01),cmap='YlGn',interpolation='nearest')
            base(ax);ax.set_title(name.replace('_',' '))
        fig.colorbar(im,ax=list(axes),label=unit,shrink=.75,extend='max')
        fig.suptitle(title+'\nResearch candidate: inferred systems; modern environment retained',fontsize=14)
        dest=mapdir/(names[0]+'.png');fig.savefig(dest,dpi=140);plt.close(fig);paths.append(str(dest))
    paired(['lower_dm','upper_dm'],'1300 crop yield scenarios — best suitability class','tonnes dry product / ha / crop cycle',1000)
    paired(['lower_kcal','upper_kcal','historical_kcal'],'Annual food energy — conditional on the assigned rotation','million kcal / rotational ha / year',1e6)
    # Different labour dimensions deliberately use separate colour scales.
    paired(['labour_days'],'Labour requirement — system analogues','worker-days / rotational ha / year')
    paired(['kcal_per_worker_day'],'Food energy per worker-day','kcal / worker-day')
    paired(['management_position'],'Historical position — shared system priors','relative position (not a measured efficiency)')
    paired(['historical_kcal_low','historical_kcal_high'],'Joint assumption sensitivity — not confidence intervals','million kcal / rotational ha / year',1e6)
    paired(['alternative_kcal_ratio'],'Alternative historically eligible crop — same management assumptions','alternate / representative crop food energy')
    crop=thumbnail(out/'crop.tif');state=thumbnail(out/'state.tif')
    colors=['#c7c7c7','#b78e32','#e2bf67','#a66c23','#dcc88a','#8c633c','#edc948','#d94a3d','#ed9991','#8c68af','#b3a0ca','#9a6749','#be9a80','#bd5591','#e1a0c2','#455e98','#659ed1','#4c9b68','#91bd62']
    fig,ax=plt.subplots(figsize=(15,7),layout='constrained')
    ax.imshow(crop,extent=(-180,180,-90,90),cmap=ListedColormap(colors),norm=BoundaryNorm(np.arange(-.5,len(colors)+.5),len(colors)),interpolation='nearest')
    base(ax);ax.set_title('Representative crop in 1300 — ecoregion-based historical system inference\nConditional farming map, not observed cultivated hectares')
    ax.legend(handles=[Patch(color=colors[i],label=config['crops'][c]['name']) for i,c in enumerate(config['crop_order'],1)],loc='upper left',bbox_to_anchor=(1.01,1),fontsize=8)
    dest=mapdir/'crop_assignment.png';fig.savefig(dest,dpi=140);plt.close(fig);paths.append(str(dest))
    previous=root/'artifacts/experiments/rectangular_assignment/reconstruction/crop.tif'
    if previous.exists():
        fig,axes=plt.subplots(2,1,figsize=(15,10),layout='constrained')
        for ax,data,title in zip(axes,[thumbnail(previous),crop],['Previous rectangular rules','Ecological polygons with revised historical crop preferences']):
            ax.imshow(data,extent=(-180,180,-90,90),cmap=ListedColormap(colors),norm=BoundaryNorm(np.arange(-.5,len(colors)+.5),len(colors)),interpolation='nearest')
            base(ax);ax.set_title(title)
        axes[0].legend(handles=[Patch(color=colors[i],label=config['crops'][c]['name']) for i,c in enumerate(config['crop_order'],1)],loc='upper left',bbox_to_anchor=(1.01,1),fontsize=8)
        fig.suptitle('Crop assignment comparison — identical colour codes; inferred farming systems')
        dest=mapdir/'crop_assignment_comparison.png';fig.savefig(dest,dpi=140);plt.close(fig);paths.append(str(dest))
    labels=['Outside source grid','Non-crop inference','Crop inference','No viable listed crop','Unresolved region','No modeled crop viable','Incomplete scenario inputs']
    fig,ax=plt.subplots(figsize=(14,6),layout='constrained')
    palette=['#e8edf0','#999999','#5c9b58','#e3a142','#a34682','#deded6','#222222']
    ax.imshow(state,extent=(-180,180,-90,90),cmap=ListedColormap(palette),norm=BoundaryNorm(np.arange(-.5,7.5),7),interpolation='nearest');base(ax)
    ax.set_title('Coverage and unresolved assignments')
    ax.legend(handles=[Patch(color=c,label=l) for c,l in zip(palette,labels)],loc='lower center',ncol=3)
    dest=mapdir/'coverage.png';fig.savefig(dest,dpi=140);plt.close(fig);paths.append(str(dest))
    paired(['confidence'],'Evidence confidence — ordinal labels only','1 low/inferred; 2 medium/regional evidence')
    benchmarks=pd.read_csv(out/'benchmark_people.csv')
    fig,ax=plt.subplots(figsize=(12,9),layout='constrained')
    for i,(_,r) in enumerate(benchmarks.iterrows()):
        if bool(r['valid']):
            ax.plot([r.lower,r.upper],[i,i],color='#7f9c8d',linewidth=4)
            ax.errorbar(r.observed,i,xerr=[[max(0,r.observed-r.observed_low)],[max(0,r.observed_high-r.observed)]],fmt='o',color='#b44b3e' if r.result=='outside' else '#263b53',capsize=3)
    for i,(_,r) in enumerate(benchmarks.iterrows()):
        if not bool(r['valid']):ax.text(0,i,'unresolved',va='center',fontsize=9,color='#777777')
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([0],[0],color='#7f9c8d',lw=4,label='Modeled lower–upper range'),Line2D([0],[0],marker='o',color='#263b53',label='Seshat estimate and anchor uncertainty')],loc='lower right',fontsize=9)
    ax.set_xlim(left=0)
    ax.set_yticks(range(len(benchmarks)),benchmarks.region);ax.invert_yaxis();ax.set_xlabel('People fed / hectare of the full agricultural rotation / year')
    ax.set_title('Seshat constraints: modeled envelope and historical anchor interval\nNet edible energy; same crop losses and Seshat annual cropping coefficient for each comparison')
    dest=mapdir/'benchmarks.png';fig.savefig(dest,dpi=140);plt.close(fig);paths.append(str(dest))
    validation=json.loads((out/'validation.json').read_text());summary=json.loads((out/'benchmark_summary.json').read_text());coverage=json.loads((out/'coverage.json').read_text())
    paragraphs=['# Global agriculture 1300 — research candidate','',
        '**Engineering status:** '+('passed' if validation['engineering_pass'] else 'failed')+'. **Historical acceptance: not established.**','',
        f"Calculated cells: {validation['calculated_cells']:,}. Seshat comparisons: {summary['inside']} inside, {summary['outside']} outside, {summary['unresolved']} unresolved.",'',
        '## Interpretation','',
        'These are conditional yields on the best suitability class within each GAEZ cell. They are not cell-average yields, observed cropland, or population capacity. RESOLVE 2017 ecological polygons replace rectangular crop regions. Historical system rules distinguish lowlands, uplands, dry plains and other environments; these are inferred crop assignments, not observed 1300 crop boundaries. Unmatched coastline cells remain explicit gaps. Historical management positions are explicit shared priors, not measured efficiencies.','',
        'GAEZ low input already assumes traditional cultivars. Shared lower/upper factors must enclose every comparable Seshat anchor interval after dry/fresh and rotation-denominator conversion. The former average-loss compromise is superseded. Changes are the minimum needed to the reference crop-family factors; no cell-specific edits or clipped historical estimates are used. The upper high-input water system is recorded separately.','',
        '## Evidence limitations','',
        '- Modern climate and soil/terrain remain in the calculation.',
        '- Every Seshat case now constrains calibration. Former geographic holdouts are not independent validation; English wheat remains a separate source check.',
        '- Historical yield-anchor ranges are propagated linearly where Seshat supplies them. This does not reconstruct uncertainty in every Seshat input and is not a published 1300 confidence interval.',
        '- Regional benchmark locators are approximate. Southern China Hills is an upland system, not Taihu; its published paddy-rice proxy is retained in the benchmark while the assignment tests dry rice.',
        '- Seshat normalizes historical factors relative to its yield anchor. The harvested-area interpretation of those anchors is not uniformly verified. benchmark_denominator_sensitivity.csv preserves the consequences of alternative interpretations; these are not independent observations.',
        '- English wheat in 1300–1309 is a separate source holdout. Its net-seed yield is compared after seed deductions; uncertain bushel mass and approximate sampling remain visible.',
        '- The annualization contract is an explicit interpretation, pending an explicit product-level fallow flag.',
        '- Crop-family transfers, food recovery, losses, seed shares and labour are inferred scenarios with uncertainty. Labour evidence is predominantly much later than 1300.',
        '- Breadfruit, sago, quinoa, oca, enset and indigenous North American seed crops are missing or inadequately represented. Unsupported cells are retained explicitly.',
        '- A continuous position between rainfed and irrigated yields is a scenario interpolation, not proof of attainable intermediate farming systems.',
        '- Seasonal labour bottlenecks, irrigation water availability, actual cultivation and settlement are not modeled. The irrigated upper scenario is conditional on water delivery, not a map of proven feasible irrigation.',
        '- Regional distributions are cell-unweighted summaries, not land-area or production totals. Controlled sensitivities vary yield, crop frequency and labour separately; altered frequency is not evidence of seasonal feasibility.','',
        '## Scientific criteria','',
        '| Criterion | Result |','|---|---|']
    paragraphs += [f"| {r['criterion']} | {r['result']} |" for r in validation['scientific_criteria']]
    paragraphs += ['', '## Independent evidence', '', str(summary['independent_historical_validation']), '',
        '## Diagnostic tables', '',
        '- [Regional distributions](regional_distributions.csv)',
        '- [Ecological boundary and historical assignment ledger](ecoregion_ledger.json)',
        '- [Independent wheat comparison](independent_holdouts.json)',
        '- [Denominator sensitivity](benchmark_denominator_sensitivity.csv)',
        '- [Controlled sensitivity and crop alternatives](controlled_sensitivity.json)',
        '- [Unresolved crop-assignment cells](coverage_gaps.json)',
        '- [Shared parameter candidates](candidate_comparisons.json)']
    paragraphs += ['','## Reproduce','','```bash','uv run ha1300 acquire','uv run ha1300 run','uv run pytest -q','```','','## Sources','']
    sources=json.loads((root/'configs/sources.json').read_text())
    paragraphs += [f"- [{key}]({v['url']}): {v['role']}" for key,v in sources.items()]
    (out/'REPORT.md').write_text('\n'.join(paragraphs)+'\n')
    from .food_reporting import food_report
    return food_report(root,config,out,paths)
