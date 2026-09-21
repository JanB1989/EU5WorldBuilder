"""Handover contract for the constructor.

One versioned directory with everything the mod needs from the World Builder, denominated in people
(1 game capacity unit = 1,000 people; the constructor converts and rounds):

- contract.json          schema, World Builder commit, units, fit metrics, file hashes
- attribute_rows.csv     one row per attribute class: flat capacity people (natural fit) and goods
                         output modifiers (output_<good> columns, blank where no row)
- building_types.csv     one row per improvement building: unit people per level, level limit, gate
                         rules (JSON), cap equation in levels (JSON: base, class terms, development
                         per point), ledger totals
- location_buildings.csv one row per location and building: starting levels, caps, ledger people
- location_targets.csv   one row per location: targets, attribute flat, development, model values
- goods_floor.csv        RGO locations for the constructor floor carve-out
- README.md

``check`` recomputes the start and maximum model from a constructor-side levels table (after any
rescaling or rounding) and reports the fit against the targets, so scaling decisions can be verified.
"""
import json,hashlib,subprocess,datetime
from pathlib import Path
import numpy as np
import pandas as pd
from .provenance import write_json

ROOT=Path(__file__).resolve().parents[2]
SCHEMA_VERSION='1.0'


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def git_commit():
    try:return subprocess.run(['git','rev-parse','--short','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
    except Exception:return 'unknown'


def metrics(y,p):
    y=np.asarray(y,float);p=np.asarray(p,float);err=p-y;rel=np.abs(err)/np.maximum(y,1)
    ss=float(((y-y.mean())**2).sum())
    return {'r2':float(1-(err**2).sum()/ss) if ss>0 else float('nan'),'median_absolute_percentage_error':float(100*np.median(rel)),'within_25_percent':float(100*np.mean(rel<=.25)),'mean_bias':float(err.mean()),'total_model':float(p.sum()),'total_target':float(y.sum())}


def game_keys():
    """In-game identifiers per World Builder class: climate/vegetation/topography type keys (from the geography
    configs), soil and fertility ids with their scripted-trigger names, river levels as numbers."""
    keys={}
    for attr,cfgname in [('climate','climate'),('vegetation','vegetation'),('topography','topography')]:
        cfg=json.loads((ROOT/f'configs/{cfgname}.json').read_text())
        for name,t in (cfg.get('types') or {}).items():keys[(attr,name)]=str(t.get('game_key') or name)
    soil=json.loads((ROOT/'configs/soil_types.json').read_text())
    for name,sid in (soil.get('types') or {}).items():keys[('soil_type',name)]=f'ha1300_soil_is_{name}'
    fert=json.loads((ROOT/'configs/fertility.json').read_text())
    for name in (fert.get('levels') or {}):keys[('fertility',name)]=f'ha1300_fertility_is_{name}'
    return keys


def attribute_rows(fit_coef,goods_coef,features):
    cap=fit_coef[fit_coef.target=='natural_capacity'][['attribute','value','people','share_of_reference','locations']].rename(columns={'people':'capacity_people','share_of_reference':'capacity_share_of_reference'})
    mx=fit_coef[fit_coef.target=='maximum_capacity'][['attribute','value','people']].rename(columns={'people':'maximum_capacity_people_info'})
    rows=cap.merge(mx,on=['attribute','value'],how='left')
    rows['is_reference']=rows.attribute.eq('reference')
    if len(goods_coef):
        g=goods_coef.pivot_table(index=['attribute','value'],columns='good',values='modifier',aggfunc='first')
        g.columns=[f'output_{c}' for c in g.columns];rows=rows.merge(g.reset_index(),on=['attribute','value'],how='left')
        # goods intercepts live on the reference row
    order={f:i for i,f in enumerate(['reference']+list(features))}
    rows['_o']=rows.attribute.map(order).fillna(99);rows=rows.sort_values(['_o','value']).drop(columns='_o')
    keys=game_keys()
    rows['game_key']=[keys.get((a,str(v)),(str(v) if a not in ('reference','is_coastal','is_adjacent_to_lake') else '')) for a,v in zip(rows.attribute,rows.value)]
    # Vanilla-named classes not listed in the geography configs keep their own name (e.g. topography flatland).
    return rows


def building_types(buildings,caps,ledger):
    out=[]
    for r in buildings.itertuples():
        if not r.unit_people_per_level or not np.isfinite(r.unit_people_per_level):continue
        c=caps[caps.building==r.building]
        eq={'base_levels':float(c[c.attribute=='base'].levels.iloc[0]) if (c.attribute=='base').any() else 0.,
            'levels_per_development_point':float(c[c.attribute=='development'].levels.iloc[0]) if (c.attribute=='development').any() else 0.,
            'class_terms':[{'attribute':x.attribute,'value':str(x.value),'levels':float(x.levels)} for x in c[~c.attribute.isin(['base','development'])].itertuples() if x.levels]}
        out.append({'building':r.building,'unit_people_per_level':float(r.unit_people_per_level),'level_limit':int(getattr(r,'level_limit',20) or 20),'gate_json':r.gate,'cap_equation_json':json.dumps(eq),
            'levels_per_development_point':eq['levels_per_development_point'],'eligible_locations':int(r.eligible_locations),'users_at_start':int(getattr(r,'users_at_start',0) or 0),
            'starting_ledger_people':float(ledger[f'starting_{r.building}_capacity'].sum()) if f'starting_{r.building}_capacity' in ledger else float('nan'),
            'maximum_ledger_people':float(ledger[f'maximum_{r.building}_capacity'].sum()) if f'maximum_{r.building}_capacity' in ledger else float('nan')})
    return pd.DataFrame(out)


def location_buildings(assign,ledger,kinds):
    led=ledger.set_index('location_tag').reindex(assign.index)
    rows=[]
    for k in kinds:
        rows.append(pd.DataFrame({'location_tag':assign.index,'building':k,'starting_levels':assign[f'{k}_levels_start'].astype(int).to_numpy(),
            'cap_at_start':assign[f'{k}_cap'].astype(int).to_numpy(),'cap_at_reference_development':assign[f'{k}_cap_at_reference'].astype(int).to_numpy(),
            'starting_ledger_people':led.get(f'starting_{k}_capacity',pd.Series(0.,index=assign.index)).fillna(0.).to_numpy(float),
            'maximum_ledger_people':led.get(f'maximum_{k}_capacity',pd.Series(0.,index=assign.index)).fillna(0.).to_numpy(float)}))
    out=pd.concat(rows,ignore_index=True)
    return out[(out.starting_levels>0)|(out.cap_at_start>0)|(out.cap_at_reference_development>0)|(out.maximum_ledger_people>0)].reset_index(drop=True)


def check(levels,units,targets,percent_per_point=0.0,people_per_point=0.0):
    """levels: DataFrame(location_tag, building, starting_levels, cap_at_start); units: {building: people per level};
    targets: DataFrame indexed by location_tag with attribute_flat_people, starting_target_people, maximum_target_people
    and development. Capacity = (flat + levels x unit) x (1 + percent_per_point x development), the engine's multiplier."""
    lv=levels.copy();lv['unit']=lv.building.map(units).astype(float)
    if lv.unit.isna().any():raise ValueError('Missing unit for buildings: '+', '.join(sorted(lv[lv.unit.isna()].building.unique())))
    start=(lv.starting_levels*lv.unit).groupby(lv.location_tag).sum().reindex(targets.index).fillna(0.)
    mx=(lv.cap_at_start*lv.unit).groupby(lv.location_tag).sum().reindex(targets.index).fillna(0.)
    flat=targets.attribute_flat_people.to_numpy(float)
    mult=1+float(percent_per_point)*(targets.development.to_numpy(float) if 'development' in targets else 0.)
    dev=targets.development.to_numpy(float) if 'development' in targets else 0.
    s=(flat+start.to_numpy())*mult+float(people_per_point)*dev;m=(flat+mx.to_numpy())*mult+float(people_per_point)*dev
    return {'starting':metrics(targets.starting_target_people,s),'maximum':metrics(targets.maximum_target_people,m),
            'starting_model_total':float(s.sum()),'maximum_model_total':float(m.sum()),'percent_per_point':float(percent_per_point),'people_per_point':float(people_per_point)}


def build(version=None,output_root=None):
    commit=git_commit();version=version or f"{datetime.date.today().isoformat()}-{commit}"
    out=Path(output_root or ROOT/'artifacts/handover').resolve()/version;out.mkdir(parents=True,exist_ok=True)
    fit=json.loads((ROOT/'artifacts/attribute_fit_flat/report.json').read_text());fit_cfg=fit['config']
    coef=pd.read_csv(ROOT/'artifacts/attribute_fit_flat/coefficients.csv',keep_default_na=False)
    pred=pd.read_csv(ROOT/'artifacts/attribute_fit_flat/location_predictions.csv',keep_default_na=False).set_index('location_tag')
    assign=pd.read_csv(ROOT/'artifacts/building_assignment/locations.csv',keep_default_na=False).set_index('location_tag')
    breport=json.loads((ROOT/'artifacts/building_assignment/report.json').read_text())
    buildings=pd.read_csv(ROOT/'artifacts/building_assignment/buildings.csv',keep_default_na=False)
    buildings['unit_people_per_level']=pd.to_numeric(buildings.unit_people_per_level,errors='coerce')
    caps=pd.read_csv(ROOT/'artifacts/building_assignment/cap_coefficients.csv',keep_default_na=False)
    bcfg=breport['config'];buildings['level_limit']=int(bcfg['level_limit'])
    ledger=pd.read_csv(ROOT/'artifacts/locations/improvement_ledger_equal_area.csv',keep_default_na=False)
    for c in ledger.columns:
        if c.endswith('_capacity'):ledger[c]=pd.to_numeric(ledger[c],errors='raise')
    targets=pd.read_csv(ROOT/'artifacts/locations/capacity_targets_equal_area.csv',keep_default_na=False).set_index('location_tag')
    dev=pd.read_csv(ROOT/'artifacts/development/locations.csv',keep_default_na=False).set_index('location_tag')
    goods_dir=ROOT/'artifacts/goods_output_fit'
    goods_coef=pd.read_csv(goods_dir/'coefficients.csv',keep_default_na=False) if (goods_dir/'coefficients.csv').exists() else pd.DataFrame(columns=['good','attribute','value','modifier'])
    goods_report=json.loads((goods_dir/'report.json').read_text()) if (goods_dir/'report.json').exists() else None
    floors=pd.read_csv(goods_dir/'rgo_floor.csv',keep_default_na=False) if (goods_dir/'rgo_floor.csv').exists() else pd.DataFrame()
    kinds=[b for b,u in zip(buildings.building,buildings.unit_people_per_level) if np.isfinite(u)]

    rows=attribute_rows(coef,goods_coef,fit_cfg['features']);rows.to_csv(out/'attribute_rows.csv',index=False)
    bt=building_types(buildings,caps,ledger);bt.to_csv(out/'building_types.csv',index=False)
    lb=location_buildings(assign,ledger,kinds);lb.to_csv(out/'location_buildings.csv',index=False,float_format='%.1f')
    own=pred.index
    lt=pd.DataFrame({'location_tag':own,'is_ownable':True,'region':pred.region.to_numpy(),'macro_region':pred.macro_region.to_numpy(),
        'natural_target_people':pred.natural_capacity_people.to_numpy(float),'starting_target_people':pred.starting_capacity.to_numpy(float),'maximum_target_people':pred.maximum_capacity_people.to_numpy(float),
        'attribute_flat_people':pred.natural_capacity_fitted.to_numpy(float),'attribute_maximum_info_people':pred.maximum_capacity_fitted.to_numpy(float),
        'development':pd.to_numeric(dev.development,errors='coerce').reindex(own).fillna(0.).to_numpy(),
        'starting_model_people':assign.starting_capacity_model.reindex(own).to_numpy(float),'maximum_model_people':assign.maximum_capacity_model.reindex(own).to_numpy(float),
        'start_exceeds_attribute_maximum':pred.start_exceeds_attribute_maximum.astype(str).eq('True').to_numpy()})
    lt.to_csv(out/'location_targets.csv',index=False,float_format='%.1f')
    floors.to_csv(out/'goods_floor.csv',index=False)
    # Per-location attribute classes (the keys of attribute_rows.csv) plus geography for the constructor.
    inv=pd.read_parquet(ROOT/'data/raw/location_inputs/inventory.parquet').set_index('location_tag')
    la=pred[fit_cfg['features']].copy()
    for c in ['province','super_region','calibrated_lon','calibrated_lat']:
        if c in inv:la[c]=inv[c].reindex(la.index)
    la.insert(0,'location_tag',la.index);la.to_csv(out/'location_attributes.csv',index=False)
    c=float(bcfg.get('capacity_percent_per_point',0.0))
    from .development_target import capacity_people_per_point
    kdev=capacity_people_per_point()
    self_check=check(lb,{r.building:r.unit_people_per_level for r in bt.itertuples()},lt.set_index('location_tag'),c,kdev)
    from .navigation_integration import handover as navigation_handover
    navigation_files = navigation_handover(out)
    files={f.name:sha(f) for f in sorted(out.glob('*.csv'))}
    files.update(navigation_files)
    contract={'schema_version':SCHEMA_VERSION,'version':version,'worldbuilder_commit':commit,'created':datetime.datetime.now().isoformat(timespec='seconds'),
        'units':{'people_per_game_capacity_unit':1000,'note':'All people values are physical people at the equal-area reference; the constructor divides by 1000 for local_population_capacity and may rescale levels (multiply levels, divide people per level) before rounding.'},
        'attributes':{'features':fit_cfg['features'],'reference_classes':fit_cfg['reference_classes'],'capacity_percent_per_point':c,'capacity_people_per_development_point':kdev},
        'capacity_fit':fit['metrics'],'building_fit':breport['fit'],'goods_fit':goods_report['summary'] if goods_report else None,
        'development':{'source':'game_start','maximum_reference_development':bcfg.get('maximum_reference_development',100),'note':'The engine multiplies capacity by capacity_percent_per_point x development (vanilla game-start development, written per location by the constructor); development also enters the cap equations as levels per point (cap_at_start at starting development, cap_at_reference_development at the reference value).'},
        'self_check':self_check,'counts':{'attribute_rows':int(len(rows)),'building_types':int(len(bt)),'location_buildings':int(len(lb)),'locations':int(len(lt)),'goods_floor':int(len(floors)),'location_attributes':int(len(la))},
        'files':files,'rules':['No per-location capacity value: capacity = sum of attribute rows + sum of building levels x unit.',
            'Farm buildings take land: raw_modifier local_population_capacity = -land per level; max_levels = floor((flat - reserve)/land) + own levels (constructor constants).',
            'The game keeps its RGO; goods rows shape output only; the constructor keeps its floor carve-out for goods_floor.csv.']}
    write_json(out/'contract.json',contract)
    # A stable path for consumers: artifacts/handover/latest mirrors the newest version.
    import shutil;latest=out.parent/'latest'
    if latest.exists():shutil.rmtree(latest)
    shutil.copytree(out,latest)
    (out/'README.md').write_text(f"""# World Builder handover {version}

Schema {SCHEMA_VERSION}, World Builder commit `{commit}`. All values in people (1 game unit = 1,000 people).

| File | Rows | Content |
|---|---:|---|
| attribute_rows.csv | {len(rows)} | flat capacity people per attribute class (natural fit) and goods output modifiers (`output_<good>`, blank = no row); the `reference` row is the intercept |
| building_types.csv | {len(bt)} | improvement buildings: unit people per level, level limit, gate rules (JSON), cap equation in levels (JSON), ledger totals |
| location_buildings.csv | {len(lb)} | per location and building: starting levels, cap at start, cap at development 100, ledger people |
| location_targets.csv | {len(lt)} | per location: targets, attribute flat, development, model values, review flag |
| goods_floor.csv | {len(floors)} | RGO locations for the floor carve-out |
| location_attributes.csv | {len(la)} | per location: its class for every attribute in attribute_rows.csv, province, super region, lon/lat |

Self-check (attribute flat + levels x unit against targets): start R² {self_check['starting']['r2']:.3f}, median error {self_check['starting']['median_absolute_percentage_error']:.1f}%; maximum R² {self_check['maximum']['r2']:.3f}, median error {self_check['maximum']['median_absolute_percentage_error']:.1f}%.

Verify a rescaled or rounded levels table with `worldbuilder handover-check --levels <csv> --units <json> --version {version}`.
""")
    return contract
