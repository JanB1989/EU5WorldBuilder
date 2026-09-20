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
KINDS=LEDGER_KINDS

ROOT=Path(__file__).resolve().parents[2]
KIND_LABELS={'clearing':'Clearing','management':'Field management','water_supply':'Water supply','paddy_control':'Paddy control','flood_bunds':'Flood bunds','field_drainage':'Field drainage','polders':'Polders','oasis_irrigation':'Oasis irrigation','pastoral':'Pastoral'}


def load():
    loc=ROOT/'artifacts/locations'
    pred=pd.read_csv(ROOT/'artifacts/attribute_fit_flat/location_predictions.csv',keep_default_na=False).set_index('location_tag')
    bld=pd.read_csv(ROOT/'artifacts/building_assignment/locations.csv',keep_default_na=False).set_index('location_tag')
    fill=pd.read_csv(loc/'fill_evaluation.csv',keep_default_na=False).set_index('location_tag')
    fert=pd.read_csv(ROOT/'artifacts/fertility/locations.csv',keep_default_na=False).set_index('location_tag')
    units={r['building']:r.get('unit_people_per_level') for r in json.loads((ROOT/'artifacts/building_assignment/report.json').read_text())['buildings'] if r.get('unit_people_per_level')}
    global KINDS;KINDS=tuple(units)
    c=json.loads((ROOT/'configs/building_assignment.json').read_text())['capacity_percent_per_point']
    d=pred.copy()
    for col in bld.columns:
        if col not in d:d[col]=bld[col].reindex(d.index)
    d['population']=pd.to_numeric(fill.population,errors='coerce').reindex(d.index)
    d['context']=fill.context.reindex(d.index).fillna('unknown')
    d['best_kcal_per_ha']=pd.to_numeric(fert.get('best_kcal_per_ha',pd.Series(dtype=float)),errors='coerce').reindex(d.index)
    d['best_crop']=fert.get('best_crop',pd.Series(dtype=str)).reindex(d.index).fillna('')
    numeric=[x for x in d.columns if x not in ('climate','topography','vegetation','soil_type','fertility','river_level','is_coastal','is_adjacent_to_lake','region','macro_region','context','best_crop','start_exceeds_attribute_maximum','rgo_good')]
    for x in numeric:d[x]=pd.to_numeric(d[x],errors='coerce')
    goods=ROOT/'artifacts/goods_output_fit/location_predictions.csv'
    if goods.exists():
        gp=pd.read_csv(goods,keep_default_na=False).set_index('location_tag')
        d['rgo_good']=gp.good.reindex(d.index).fillna('')
        d['rgo_output_model']=pd.to_numeric(gp.predicted,errors='coerce').reindex(d.index)
        d['rgo_output_target']=pd.to_numeric(gp.target,errors='coerce').reindex(d.index)
    else:d['rgo_good']='';d['rgo_output_model']=np.nan;d['rgo_output_target']=np.nan
    d['fill_target']=d.population/d.starting_capacity.replace(0,np.nan)
    d['fill_model']=d.population/d.starting_capacity_model.replace(0,np.nan)
    d['buildings_start_people']=sum(d[f'{k}_levels_start']*(units.get(k) or 0) for k in KINDS)*(1+c*d.development)
    d['buildings_max_people']=sum(d[f'{k}_cap']*(units.get(k) or 0) for k in KINDS)
    d['buildings_reference_people']=sum(d[f'{k}_cap_at_reference']*(units.get(k) or 0) for k in KINDS)
    return d,units,c


def layers(d):
    """(key, label, group, kind, values); kind: seq (log), lin (0..cap), div (ratio-1), cat (labels)."""
    out=[('starting_capacity','Starting capacity · target','Targets','seq',d.starting_capacity),
         ('maximum_capacity_people','Maximum capacity · target','Targets','seq',d.maximum_capacity_people),
         ('natural_capacity_people','Natural capacity · target','Targets','seq',d.natural_capacity_people),
         ('starting_capacity_model','Starting capacity · model (attributes + buildings × development)','Model','seq',d.starting_capacity_model),
         ('maximum_capacity_model','Maximum capacity · model (caps at starting development)','Model','seq',d.maximum_capacity_model),
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
         ('rgo_output_model','RGO output modifier · from attributes (−50%…+50%)','Goods','div',d.rgo_output_model*2),
         ('rgo_output_target','RGO output modifier · target (efficiency rank)','Goods','div',d.rgo_output_target*2),
         ('rgo_output_res','RGO output: model − target (×2)','Goods','div',(d.rgo_output_model-d.rgo_output_target)*2)]
    for k in KINDS:
        out.append((f'{k}_levels_start',f'{KIND_LABELS.get(k,k)} · levels at start','Buildings · start','lin',d[f'{k}_levels_start']))
    for k in KINDS:
        out.append((f'{k}_cap',f'{KIND_LABELS.get(k,k)} · cap at starting development','Buildings · caps','lin',d[f'{k}_cap']))
    for k in KINDS:
        out.append((f'{k}_cap_at_reference',f'{KIND_LABELS.get(k,k)} · cap at reference development','Buildings · caps (reference development)','lin',d[f'{k}_cap_at_reference']))
    return out


def pages(d,units,c):
    """Tables for the Buildings, Attributes and Regions tabs."""
    fit=json.loads((ROOT/'artifacts/attribute_fit_flat/report.json').read_text())
    coef=pd.read_csv(ROOT/'artifacts/attribute_fit_flat/coefficients.csv',keep_default_na=False)
    caps=pd.read_csv(ROOT/'artifacts/building_assignment/cap_coefficients.csv',keep_default_na=False)
    bld=pd.read_csv(ROOT/'artifacts/building_assignment/buildings.csv',keep_default_na=False)
    bcfg=json.loads((ROOT/'configs/building_assignment.json').read_text())
    dcfg=json.loads((ROOT/'configs/development.json').read_text())
    dchecks=json.loads((ROOT/'artifacts/development/development_checks.json').read_text())
    targets=pd.read_csv(ROOT/'artifacts/locations/capacity_targets_equal_area.csv',keep_default_na=False,usecols=['location_tag','super_region']).set_index('location_tag')
    own=d.copy();own['super_region']=targets.super_region.reindex(own.index).fillna('unknown')
    # attributes: flat values per class for both targets, spans, counts, cap terms per building
    attrs={}
    for target in ['natural_capacity','maximum_capacity']:
        cc=coef[coef.target==target]
        for r in cc.itertuples():
            key=(r.attribute,r.value);a=attrs.setdefault(key,{'attribute':r.attribute,'value':r.value,'locations':int(r.locations)})
            a[target]={'people':float(r.people),'share':float(r.share_of_reference),'span':[float(r.span_min),float(r.span_max)]}
    for r in caps.itertuples():
        key=(r.attribute if r.attribute!='base' else 'reference',r.value if r.attribute!='base' else 'intercept')
        a=attrs.setdefault(key,{'attribute':key[0],'value':key[1],'locations':None});a.setdefault('caps',{})[r.building]=float(r.levels)
    attribute_rows=[v for k,v in attrs.items()]
    order={'reference':0,'climate':1,'topography':2,'vegetation':3,'soil_type':4,'fertility':5,'river_level':6,'is_coastal':7,'is_adjacent_to_lake':8,'development':9}
    attribute_rows.sort(key=lambda a:(order.get(a['attribute'],99),a['value']))
    # buildings: per type summary, gate, cap equation, level histogram
    buildings=[]
    for r in bld.itertuples():
        k=r.building;lv=own[f'{k}_levels_start'].to_numpy(float) if f'{k}_levels_start' in own else np.zeros(len(own))
        cap100=own[f'{k}_cap_at_reference'].to_numpy(float) if f'{k}_cap_at_reference' in own else np.zeros(len(own))
        hist={str(int(b)):int(n) for b,n in zip(*np.unique(lv[lv>0],return_counts=True))}
        terms=caps[(caps.building==k)&(caps.levels!=0)&(~caps.attribute.isin(['base','development']))]
        gamma=float(caps[(caps.building==k)&(caps.attribute=='development')].levels.iloc[0]) if ((caps.building==k)&(caps.attribute=='development')).any() else 0.
        buildings.append({'building':k,'label':KIND_LABELS.get(k,k),'unit':float(r.unit_people_per_level) if r.unit_people_per_level not in ('',None) else None,
            'eligible':int(r.eligible_locations),'users':int(getattr(r,'users_at_start',0) or 0),'ungated_share':float(r.ungated_ledger_share),
            'captured_within_25':float(getattr(r,'quantisation_captured_within_25_share',0) or 0),'at_level_limit':int(getattr(r,'quantisation_locations_at_level_limit',0) or 0),
            'cap_short':int(getattr(r,'cap_short_locations',0) or 0),'cap_excess':int(getattr(r,'cap_excess_locations',0) or 0),'base_cap':int(getattr(r,'cap_intercept',0) or 0),
            'gate':bcfg['gates'].get(k,[]),'levels_per_development_point':gamma,'cap_terms':[{'attribute':t.attribute,'value':t.value,'levels':int(t.levels)} for t in terms.itertuples()],
            'levels_hist':hist,'levels_total':int(lv.sum()),'cap100_total':int(cap100.sum()),'people_at_start':float(lv.sum()*(float(r.unit_people_per_level) if r.unit_people_per_level not in ('',None) else 0))})
    # regions: compact statistics by super and macro region
    def block(g):
        pop=g.population.fillna(0);st=g.starting_capacity;sm=g.starting_capacity_model
        rural=g.context.eq('rural_or_unranked')
        return {'locations':int(len(g)),'population':float(pop.sum()),'starting_target':float(st.sum()),'starting_model':float(sm.sum()),
            'maximum_target':float(g.maximum_capacity_people.sum()),'maximum_model':float(g.maximum_capacity_model.sum()),
            'natural_target':float(g.natural_capacity_people.sum()),'attribute_natural':float(g.attribute_natural_people.sum()),
            'fill_target':float(pop.sum()/st.sum()) if st.sum()>0 else None,'fill_model':float(pop.sum()/sm.sum()) if sm.sum()>0 else None,
            'median_fill':float((pop/st.replace(0,np.nan)).median()),'rural_over_capacity':int(((pop>st)&rural).sum()),'urban_over_capacity':int(((pop>st)&~rural).sum()),
            'development_mean':float(g.development.mean()),'development_p90':float(g.development.quantile(.9)),
            'start_residual_median':float((sm/st.replace(0,np.nan)-1).median()),'max_residual_median':float((g.maximum_capacity_model/g.maximum_capacity_people.replace(0,np.nan)-1).median()),
            'review':int(g.start_exceeds_attribute_maximum.astype(str).eq('True').sum()),
            'levels':{k:int(g[f'{k}_levels_start'].sum()) for k in KINDS if f'{k}_levels_start' in g}}
    regions={'super_region':{k:block(g) for k,g in own.groupby('super_region')},'macro_region':{k:block(g) for k,g in own.groupby('macro_region')},'world':block(own)}
    return {'attributes':attribute_rows,'buildings':buildings,'regions':regions,
        'fit':{'reference':fit['config']['reference_classes'],'reference_scale':fit['reference_scale_people'],'tau':fit['config']['tau'],'metrics':fit['metrics'],'sensibility':{k:{kk:vv for kk,vv in v.items() if kk not in ('pinned','signs')} for k,v in fit['sensibility'].items()}},
        'development':{'weights':dcfg['weights'],'percent_per_point':c,'source':(dcfg.get('source') or {}).get('kind','derived'),'checks':{k:v for k,v in dchecks['checks'].items() if k!='spot_checks'},'spot_checks':dchecks['checks']['spot_checks']['locations'],'component_means':dchecks.get('component_means',{})},
        'building_config':{'level_limit':bcfg['level_limit'],'envelope_quantile':bcfg['envelope_quantile'],'scope':bcfg.get('envelope_fit_scope','with_ledger')}}



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
                # Quantile (rank) scale over the positive values: every shade covers the same number of locations,
                # so the top of the palette is no longer spent on the few largest values.
                pos=np.sort(arr[ok&(arr>0)])
                if len(pos):
                    t=np.where(arr>0,np.searchsorted(pos,np.nan_to_num(arr),side='right')/len(pos),0.)
                    entry['ticks']=[float(np.quantile(pos,q)) for q in (0,.25,.5,.75,1)]
                else:t=np.zeros_like(arr);entry['ticks']=[0,0,0,0,0]
                entry['cap']=float(pos[-1]) if len(pos) else 1.;entry['scale']='quantile'
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
    fields=['climate','topography','vegetation','soil_type','fertility','river_level','is_coastal','is_adjacent_to_lake','best_crop','context']
    nums=['natural_capacity_people','starting_capacity','maximum_capacity_people','attribute_natural_people','attribute_maximum_people','starting_capacity_model','maximum_capacity_model','buildings_start_people','buildings_max_people','development','population','fill_target','fill_model','best_kcal_per_ha','leftover_start_total','leftover_max_total']
    for i,row in enumerate(locations,1):
        tag=row['location_tag']
        if tag not in d.index:continue
        r=d.loc[tag];rec={'tag':tag,'province':row['province'],'region':row['region'],'x':row['centroid_x']/4,'y':row['centroid_y']/4,'review':bool(r.start_exceeds_attribute_maximum) if isinstance(r.start_exceeds_attribute_maximum,(bool,np.bool_)) else str(r.start_exceeds_attribute_maximum)=='True'}
        rec['a']={f:str(r[f]) for f in fields}
        rec['n']={f:(None if pd.isna(r[f]) else round(float(r[f]),3)) for f in nums}
        rec['b']=[[k,int(r[f'{k}_levels_start']),int(r[f'{k}_cap']),int(r[f'{k}_cap_at_reference']),round(float(units.get(k) or 0))] for k in KINDS]
        data[i]=rec
    payload=json.dumps({'locations':data,'layers':manifest,'c':c,'units':units,'pages':pages(d,units,c)},separators=(',',':'))
    lookup=(source/'location_lookup.js').read_text().removeprefix('window.LOCATION_LOOKUP=').strip().removesuffix(';')
    html=HTML.replace('__PAYLOAD__',payload).replace('__LOOKUP__',lookup).replace('__IMAGES__',json.dumps(images))
    (out/'index.html').write_text(html)
    (out/'map_manifest.json').write_text(json.dumps({'layers':manifest,'locations':int(sum(x is not None for x in data)),'units':units,'capacity_percent_per_point':c},indent=2)+'\n')
    return {'output':str(out/'index.html'),'layers':len(manifest),'locations':int(sum(x is not None for x in data))}


HTML=r'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EU5 · Recalibrated capacity model</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#0c1420;color:#e6edf3;font:15px system-ui,sans-serif}main{max-width:1600px;margin:auto;padding:24px}h1{font-size:25px;margin:0 0 8px}p{line-height:1.5;color:#afc2d5;margin:8px 0 18px}select,input,button{font:inherit;background:#182638;color:#e6edf3;border:1px solid #425367;border-radius:6px;padding:9px}button{cursor:pointer}label{color:#afc2d5;font-size:13px;display:grid;gap:6px}.controls{display:flex;gap:16px;flex-wrap:wrap;margin:20px 0}.controls input{width:280px}.controls select{max-width:520px}.layout{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:18px}canvas{width:100%;height:65vh;min-height:400px;display:block;touch-action:none;cursor:grab;background:#0d1824;border:1px solid #33465b;border-radius:8px}.map{position:relative}.zoom{position:absolute;left:12px;top:12px;display:flex;gap:6px}aside{padding:18px;background:#142131;border:1px solid #33465b;border-radius:8px;font-size:14px}aside h2{font-size:20px;margin:0 0 6px}.row{display:flex;justify-content:space-between;gap:10px;padding:7px 0;border-bottom:1px solid #2c4054}.muted,small{color:#afc2d5}.legend{margin:14px 0;max-width:600px}.gradient{height:12px;border-radius:4px}.seq{background:linear-gradient(90deg,#440154,#31688e,#35b779,#fde725)}.div{background:linear-gradient(90deg,#2a6fbb,#e7eae7,#bf353a)}.ticks{display:flex;justify-content:space-between;font-size:13px;margin-top:5px}.stats{margin:16px 0;font-size:14px;color:#cbd7e3}a{color:#82c6ff}details{margin-top:12px}summary{cursor:pointer}#suggestions{position:absolute;background:#182638;z-index:4;width:340px;max-height:300px;overflow:auto;border-radius:5px}#suggestions button{display:block;width:100%;text-align:left;border:0;border-radius:0}#suggestions button:hover{background:#304861}.search{position:relative}.badge{font-size:12px;color:#efcd8d}.note{font-size:13px;max-width:1000px}table{width:100%;font-size:12px;border-collapse:collapse}td,th{padding:4px 2px;text-align:right}td:first-child,th:first-child{text-align:left}.swatch{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:6px;vertical-align:middle}.h{color:#efcd8d;font-size:13px;margin:12px 0 4px}.tabs{display:flex;gap:8px;margin:14px 0;flex-wrap:wrap}.tabs button[aria-pressed="true"]{background:#315e7e;border-color:#87c4ed;color:#fff}section h2{font-size:20px;margin:18px 0 8px}section h3{font-size:16px;margin:16px 0 6px;color:#efcd8d}.card{background:#142131;border:1px solid #33465b;border-radius:8px;padding:14px;margin:12px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:12px}.wide{overflow:auto}.wide table{min-width:900px;font-size:13px}.wide th{position:sticky;top:0;background:#182638;cursor:pointer;user-select:none}.wide th[data-dir=asc]::after{content:' ▲'}.wide th[data-dir=desc]::after{content:' ▼'}.pos{color:#9be0a3}.neg{color:#f2a1a1}.rule{display:inline-block;background:#1f3247;border-radius:4px;padding:2px 6px;margin:2px 4px 2px 0;font-size:12px}.bar{display:inline-block;height:9px;background:#5aa9e6;vertical-align:middle;border-radius:2px}@media(max-width:850px){.layout{grid-template-columns:1fr}canvas{height:55vh}main{padding:16px}}
</style><main>
<h1>Recalibrated capacity model</h1>
<p>Capacity = (attribute flat + building flat) × (1 + 1% × development). Targets are people per location in equal-area units; nothing here uses population except the fill layers and the Regions table.</p>
<nav class="tabs"><button data-tab="map" aria-pressed="true">Map</button><button data-tab="buildings" aria-pressed="false">Buildings</button><button data-tab="attributes" aria-pressed="false">Attributes &amp; development</button><button data-tab="regions" aria-pressed="false">Regions</button></nav>
<section id="tab-map">
<div class="controls"><label>Layer<select id="metric"></select></label>
<label class="search">Find a location<input id="search" placeholder="Location or province…" autocomplete="off"><div id="suggestions" style="top:66px"></div></label></div>
<div class="layout"><div><div class="map"><canvas id="map"></canvas><div class="zoom"><button id="plus" aria-label="Zoom in">+</button><button id="minus" aria-label="Zoom out">−</button><button id="reset">Reset view</button></div></div>
<div class="legend" id="legend"></div><div id="stats" class="stats"></div></div><aside id="panel"><h2>Inspect a location</h2><p>Click the map or search above.</p></aside></div>
<p class="note">Sequential layers use a quantile viridis scale: each shade covers an equal share of the locations with a positive value, and the legend ticks are the minimum, quartiles and maximum. Residual and fill layers are blue (below) to red (above), saturating at ±100%. Grey land is non-ownable. Building levels are those the ledger supports at starting development; caps are the fitted integer level limits at development 100.</p>
</section>
<section id="tab-buildings" hidden></section>
<section id="tab-attributes" hidden></section>
<section id="tab-regions" hidden></section>
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
h+='<div class="h">Model</div><div class="row"><span>Attributes only · natural at start</span><b>'+fmt(n.attribute_natural_people)+'</b></div><div class="row"><span>Buildings at start × development</span><b>'+fmt(n.buildings_start_people)+'</b></div><div class="row"><span>Starting capacity · model</span><b>'+fmt(n.starting_capacity_model)+' <small>('+pct(n.starting_capacity_model/n.starting_capacity-1)+')</small></b></div><div class="row"><span>Maximum capacity · model</span><b>'+fmt(n.maximum_capacity_model)+' <small>('+pct(n.maximum_capacity_model/n.maximum_capacity_people-1)+')</small></b></div><div class="row"><span>Development</span><b>'+fmt(n.development)+'</b></div>';
h+='<div class="h">Buildings</div><table><tr><th>Type</th><th>Start</th><th>Cap now</th><th>Cap @100</th><th>People/level</th></tr>'+r.b.map(b=>'<tr><td>'+esc(pretty(b[0]))+'</td><td>'+b[1]+'</td><td>'+b[2]+'</td><td>'+b[3]+'</td><td>'+fmt(b[4])+'</td></tr>').join('')+'</table>';
h+='<div class="h">Population (context only)</div><div class="row"><span>Starting population</span><b>'+fmt(n.population)+'</b></div><div class="row"><span>Fill vs target / vs model</span><b>'+fmt(100*n.fill_target)+'% / '+fmt(100*n.fill_model)+'%</b></div>';
h+='<details><summary>Attributes</summary>'+Object.entries(r.a).map(([k,v])=>'<div class="row"><small>'+esc(pretty(k))+'</small><span>'+esc(pretty(v))+'</span></div>').join('')+'<div class="row"><small>best staple kcal/ha</small><span>'+fmt(n.best_kcal_per_ha)+'</span></div></details>';
panel.innerHTML=h;draw()}
function update(){const m=FIT.layers[metric.value];img=new Image();img.onload=draw;img.src=MAP_IMAGES[m.key];
if(m.kind==='cat'){legend.innerHTML=Object.entries(m.legend||{}).map(([k,c])=>'<span style="margin-right:14px"><span class="swatch" style="background:rgb('+c.join(',')+')"></span>'+esc(pretty(k))+'</span>').join('');document.getElementById('stats').textContent=''}
else if(m.kind==='div'){legend.innerHTML='<div class="gradient div"></div><div class="ticks"><span>−100% · below</span><span>0</span><span>+100% or more · above</span></div>';document.getElementById('stats').textContent='Median '+pct(m.stats.median)+' · p10 '+pct(m.stats.p10)+' · p90 '+pct(m.stats.p90)}
else if(m.scale==='quantile'){legend.innerHTML='<div class="gradient seq"></div><div class="ticks">'+m.ticks.map(t=>'<span>'+fmt(t)+'</span>').join('')+'</div><div class="ticks"><span>min</span><span>p25</span><span>median</span><span>p75</span><span>max</span></div>';document.getElementById('stats').textContent='Quantile scale · median '+fmt(m.stats.median)+' · p10 '+fmt(m.stats.p10)+' · p90 '+fmt(m.stats.p90)}
else{legend.innerHTML='<div class="gradient seq"></div><div class="ticks"><span>0</span><span>'+fmt(m.cap)+'</span></div>';document.getElementById('stats').textContent='Median '+fmt(m.stats.median)+' · p10 '+fmt(m.stats.p10)+' · p90 '+fmt(m.stats.p90)}
if(selected)show(selected)}
function zoom(f,x=canvas.width/2,y=canvas.height/2){let nz=Math.max(.5,Math.min(40,z*f)),r=nz/z;ox=x-(x-ox)*r;oy=y-(y-oy)*r;z=nz;draw()}
canvas.onpointerdown=e=>{drag=[e.clientX,e.clientY,ox,oy];moved=false;canvas.setPointerCapture(e.pointerId)};
canvas.onpointermove=e=>{if(!drag)return;let dx=e.clientX-drag[0],dy=e.clientY-drag[1];if(Math.abs(dx)+Math.abs(dy)>3)moved=true;ox=drag[2]+dx*devicePixelRatio;oy=drag[3]+dy*devicePixelRatio;draw()};
canvas.onpointerup=e=>{if(drag&&!moved){let b=canvas.getBoundingClientRect(),s=Math.min(canvas.width/4096,canvas.height/2048)*z,id=locationAt(((e.clientX-b.left)*devicePixelRatio-ox)/s,((e.clientY-b.top)*devicePixelRatio-oy)/s);if(id)show(id)}drag=null};canvas.onpointercancel=()=>drag=null;
canvas.addEventListener('wheel',e=>{e.preventDefault();let b=canvas.getBoundingClientRect();zoom(e.deltaY<0?1.2:1/1.2,(e.clientX-b.left)*devicePixelRatio,(e.clientY-b.top)*devicePixelRatio)},{passive:false});
document.getElementById('plus').onclick=()=>zoom(1.5);document.getElementById('minus').onclick=()=>zoom(1/1.5);document.getElementById('reset').onclick=reset;metric.onchange=update;
function jump(id){show(id);let r=FIT.locations[id];z=5;let s=Math.min(canvas.width/4096,canvas.height/2048)*z;ox=canvas.width/2-r.x*s;oy=canvas.height/2-r.y*s;draw();suggestions.replaceChildren();search.value=pretty(r.tag)}
search.oninput=()=>{let q=search.value.toLowerCase().trim().replaceAll(' ','_');suggestions.replaceChildren();if(!q)return;FIT.locations.map((r,id)=>({r,id})).filter(({r})=>r&&(r.tag.includes(q)||r.province.includes(q))).slice(0,12).forEach(({r,id})=>{let b=document.createElement('button');b.textContent=pretty(r.tag)+' · '+pretty(r.province);b.onclick=()=>jump(id);suggestions.appendChild(b)})};search.onkeydown=e=>{if(e.key==='Enter')suggestions.querySelector('button')?.click();if(e.key==='Escape')suggestions.replaceChildren()};
const P=FIT.pages,kinds=Object.keys(FIT.units);
function parseCell(t){t=t.trim();if(t===''||t==='—')return null;const m=t.match(/^([+-]?[\d,.]+)\s*(M|%)?/);if(!m||!/\d/.test(m[1]))return t.toLowerCase();let v=parseFloat(m[1].replaceAll(',',''));if(m[2]==='M')v*=1e6;return Number.isFinite(v)?v:t.toLowerCase()}
function makeSortable(root){root.querySelectorAll('table').forEach(table=>{const head=table.rows[0];Array.from(head.cells).forEach((th,ci)=>{th.onclick=()=>{const dir=th.dataset.dir==='asc'?'desc':'asc';Array.from(head.cells).forEach(c=>c.removeAttribute('data-dir'));th.dataset.dir=dir;const rows=Array.from(table.rows).slice(1);rows.sort((a,b)=>{const x=parseCell(a.cells[ci]?.textContent||''),y=parseCell(b.cells[ci]?.textContent||'');if(x===null)return 1;if(y===null)return -1;if(typeof x==='number'&&typeof y==='number')return dir==='asc'?x-y:y-x;return dir==='asc'?String(x).localeCompare(String(y)):String(y).localeCompare(String(x))});rows.forEach(r=>table.appendChild(r))}})})}
const sign=v=>'<span class="'+(v>0?'pos':v<0?'neg':'')+'">'+(v>0?'+':'')+fmt(v)+'</span>';
function ruleText(rule){return Object.entries(rule).map(([a,vals])=>'<b>'+esc(pretty(a))+'</b> ∈ {'+vals.map(v=>esc(pretty(v))).join(', ')+'}').join(' <small>and</small> ')}
function renderBuildings(){const el=document.getElementById('tab-buildings');if(el.dataset.done)return;el.dataset.done=1;
 let h='<h2>Buildings</h2><p>One flat building per improvement type. Each level adds a fixed number of people (before the development multiplier). A location may build it only where its gate holds; its level cap is base + attribute-class terms + levels per development point × development, floored to whole levels and capped at '+P.building_config.level_limit+'. Caps were fitted as a '+fmt(100*P.building_config.envelope_quantile)+'th-percentile envelope over '+(P.building_config.scope==='gated'?'every eligible location':'eligible locations that have ledger mass')+'.</p>';
 h+='<div class="card wide"><table><tr><th>Building</th><th>People / level</th><th>Eligible</th><th>Users at start</th><th>Levels at start</th><th>People at start</th><th>Caps @100 (levels)</th><th>Ungated ledger</th><th>Captured ±25%</th><th>At level limit</th><th>Cap short</th><th>Cap excess</th></tr>';
 P.buildings.forEach(b=>{h+='<tr><td>'+esc(b.label)+'</td><td>'+fmt(b.unit)+'</td><td>'+fmt(b.eligible)+'</td><td>'+fmt(b.users)+'</td><td>'+fmt(b.levels_total)+'</td><td>'+fmt(b.people_at_start)+'</td><td>'+fmt(b.cap100_total)+'</td><td>'+fmt(100*b.ungated_share)+'%</td><td>'+fmt(100*b.captured_within_25)+'%</td><td>'+fmt(b.at_level_limit)+'</td><td>'+fmt(b.cap_short)+'</td><td>'+fmt(b.cap_excess)+'</td></tr>'});
 h+='</table><p class="note">Ungated ledger: share of the historical ledger mass sitting in locations that fail the gate (gate quality). Cap short / excess: locations whose cap at development 100 is below / above the levels the ledger maximum needs.</p></div><div class="grid">';
 P.buildings.forEach(b=>{const maxN=Math.max(1,...Object.values(b.levels_hist));h+='<div class="card"><h3>'+esc(b.label)+' · '+fmt(b.unit)+' people per level</h3><div class="h">Can be built where</div>'+(b.gate.length?b.gate.map(r=>'<div class="rule">'+ruleText(r)+'</div>').join('<small> or </small>'):'<span class="rule">everywhere</span>');
  h+='<div class="h">Level cap = '+b.base_cap+' (base)'+(b.cap_terms.length?' + terms':'')+(b.levels_per_development_point?' + '+b.levels_per_development_point+' × development (up to '+sign(Math.floor(100*b.levels_per_development_point))+' at 100)':'')+'</div>';
  const grp={};b.cap_terms.forEach(t=>(grp[t.attribute]=grp[t.attribute]||[]).push(t));
  h+=Object.entries(grp).map(([a,ts])=>'<div class="row"><small>'+esc(pretty(a))+'</small><span>'+ts.map(t=>esc(pretty(t.value))+' '+sign(t.levels)).join(', ')+'</span></div>').join('');
  h+='<div class="h">Levels at start (locations per level)</div>'+Object.entries(b.levels_hist).map(([l,n])=>'<div class="row"><small>'+l+'</small><span><span class="bar" style="width:'+Math.round(140*n/maxN)+'px"></span> '+fmt(n)+'</span></div>').join('')+'</div>'});
 h+='</div>';el.innerHTML=h;makeSortable(el)}
function renderAttributes(){const el=document.getElementById('tab-attributes');if(el.dataset.done)return;el.dataset.done=1;const f=P.fit,D=P.development;
 let h='<h2>Attribute values</h2><p>Flat people added or removed by each displayed attribute class, for the natural capacity (at starting development) and the maximum (at development 100). The reference location ('+Object.entries(f.reference).map(([k,v])=>esc(pretty(k))+'='+esc(pretty(v))).join(', ')+') has value = intercept; every other class adds its term. Values are rounded to the nearest hundred people after the fit. Spans are the allowed range; a value sitting on a span edge is a constrained value, not an estimate. Click a column header to sort. Cap columns show the extra building levels a class grants.</p>';
 h+='<div class="card wide"><table><tr><th>Attribute</th><th>Class</th><th>Locations</th><th>Natural · people</th><th>share</th><th>span</th><th>Maximum · people</th><th>share</th><th>span</th>'+kinds.map(k=>'<th>cap '+esc(pretty(k))+'</th>').join('')+'</tr>';
 P.attributes.forEach(a=>{const n=a.natural_capacity,m=a.maximum_capacity;h+='<tr><td>'+esc(pretty(a.attribute))+'</td><td>'+esc(pretty(a.value))+'</td><td>'+(a.locations===null?'—':fmt(a.locations))+'</td>'+(n?'<td>'+sign(n.people)+'</td><td>'+fmt(100*n.share)+'%</td><td><small>'+fmt(n.span[0])+' … '+fmt(n.span[1])+'</small></td>':'<td></td><td></td><td></td>')+(m?'<td>'+sign(m.people)+'</td><td>'+fmt(100*m.share)+'%</td><td><small>'+fmt(m.span[0])+' … '+fmt(m.span[1])+'</small></td>':'<td></td><td></td><td></td>')+kinds.map(k=>'<td>'+(a.caps&&a.caps[k]!==undefined?(a.caps[k]?sign(a.caps[k]):'0'):'')+'</td>').join('')+'</tr>'});
 h+='</table></div>';
 h+='<h2>Development</h2><div class="card"><p>'+(D.percent_per_point>0?'Capacity = flat × (1 + '+fmt(100*D.percent_per_point)+'% × development). ':'Development does not multiply capacity: the flat is farmland and stays flat. ')+(D.source==='game_start'?'Development is the game\'s own starting value (day-one snapshot), read as an input and never fitted. ':'Development is derived before any fit from land use and the ledger: '+Object.entries(D.weights).filter(([k,w])=>w>0).map(([k,w])=>w+' × '+esc(pretty(k))).join(' + ')+'. ')+'It raises building caps linearly: each building has its own levels per development point (the “development · per point” row in the attribute table; EU5 script: add = { value = development multiply = γ }).</p>';
 h+='<div class="h">Sanity checks</div>'+Object.entries(D.checks).filter(([k,v])=>v&&typeof v==='object'&&'passed' in v).map(([k,v])=>'<div class="row"><span>'+esc(pretty(k))+'</span><b class="'+(v.passed?'pos':'neg')+'">'+(v.passed?'pass':'fail')+(v.observed!==undefined&&typeof v.observed==='number'?' · '+fmt(v.observed):'')+'</b></div>').join('');
 h+='<div class="h">Spot checks</div>'+Object.entries(D.spot_checks).map(([k,v])=>'<div class="row"><span>'+esc(pretty(k))+'</span><b class="'+(v.passed?'pos':v.passed===false?'neg':'')+'">'+(v.observed===null?'missing':fmt(v.observed))+' <small>band '+v.band[0]+'–'+v.band[1]+'</small></b></div>').join('')+'</div>';
 h+='<div class="card"><div class="h">Attribute fit</div>'+f.metrics.map(m=>'<div class="row"><span>'+esc(pretty(m.target))+' · '+esc(pretty(m.evaluation))+'</span><b>R² '+fmt(m.r2)+' · median error '+fmt(m.median_absolute_percentage_error)+'%</b></div>').join('')+'<p class="note">tau = '+f.tau+': the fit is a low envelope with that share of locations allowed above it; reference scale '+fmt(f.reference_scale)+' people.</p></div>';
 el.innerHTML=h;makeSortable(el)}
function renderRegions(){const el=document.getElementById('tab-regions');if(el.dataset.done)return;el.dataset.done=1;
 const M=x=>fmt(x/1e6)+'M',pc=x=>x===null||x===undefined?'—':fmt(100*x)+'%';
 const table=(title,rows)=>{let h='<h3>'+title+'</h3><div class="card wide"><table><tr><th>Region</th><th>Locations</th><th>Population</th><th>Start target</th><th>Start model</th><th>Max target</th><th>Max model</th><th>Attr. natural / target</th><th>Fill (target)</th><th>Fill (model)</th><th>Median fill</th><th>Rural over cap</th><th>Urban over cap</th><th>Dev mean / p90</th><th>Start resid. med.</th><th>Max resid. med.</th><th>Review list</th>'+kinds.map(k=>'<th>'+esc(pretty(k))+' lv</th>').join('')+'</tr>';
  Object.entries(rows).sort((a,b)=>b[1].population-a[1].population).forEach(([name,r])=>{h+='<tr><td>'+esc(pretty(name))+'</td><td>'+fmt(r.locations)+'</td><td>'+M(r.population)+'</td><td>'+M(r.starting_target)+'</td><td>'+M(r.starting_model)+'</td><td>'+M(r.maximum_target)+'</td><td>'+M(r.maximum_model)+'</td><td>'+pc(r.attribute_natural/r.natural_target)+'</td><td>'+pc(r.fill_target)+'</td><td>'+pc(r.fill_model)+'</td><td>'+pc(r.median_fill)+'</td><td>'+fmt(r.rural_over_capacity)+'</td><td>'+fmt(r.urban_over_capacity)+'</td><td>'+fmt(r.development_mean)+' / '+fmt(r.development_p90)+'</td><td>'+pc(r.start_residual_median)+'</td><td>'+pc(r.max_residual_median)+'</td><td>'+fmt(r.review)+'</td>'+kinds.map(k=>'<td>'+fmt(r.levels[k]||0)+'</td>').join('')+'</tr>'});
  return h+'</table></div>'};
 el.innerHTML='<h2>Where we stand, by region</h2><p>Targets and model in people; fill is starting population over starting capacity (population is context only). Residual medians are model ÷ target − 1 per location. Building columns are total levels at start.</p>'+table('World',{world:P.regions.world})+table('Super regions',P.regions.super_region)+table('Macro regions',P.regions.macro_region);makeSortable(el)}
document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tabs button').forEach(x=>x.ariaPressed='false');b.ariaPressed='true';['map','buildings','attributes','regions'].forEach(t=>document.getElementById('tab-'+t).hidden=t!==b.dataset.tab);if(b.dataset.tab==='buildings')renderBuildings();if(b.dataset.tab==='attributes')renderAttributes();if(b.dataset.tab==='regions')renderRegions();if(b.dataset.tab==='map')fit()});
window.addEventListener('resize',fit);fit();reset();update();
})();</script></html>'''
