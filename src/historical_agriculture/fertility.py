"""Five game fertility grades for every EU5 location.

Current producer (``caloric_yield`` in ``configs/fertility.json``): the best
caloric staple under low-input rain-fed farming (GAEZ v5, see
``fertility_caloric``). The earlier HWSD chemistry classifier stays importable
below and is kept as the ``chemistry_fertility_id`` diagnostic column. Both are
transparent proxies, not official FAO fertility maps or a 1300 survey.
"""
from pathlib import Path
import json
import shutil
import numpy as np
import pandas as pd
from . import soil_types as soil
from .location_inventory import read_zone_inventory

ROOT=Path(__file__).resolve().parents[2]


def classify_components(d,cfg):
    valid=~d.WRB2.fillna('').str.upper().isin(['GG','WR','ND','IS'])
    # Bare/urban mapping components can have every chemistry field set to -9.
    # They provide no fertility evidence: retain their missing area instead of
    # manufacturing chemistry from a global soil-group median.
    core=['PH_WATER','CEC_SOIL','BSAT']
    observed_core=np.column_stack([pd.to_numeric(d[k],errors='coerce').between(*cfg['chemistry_valid_ranges'][k]) for k in core])
    valid=valid&observed_core.any(axis=1)
    fields=list(cfg['chemistry_valid_ranges'])
    chemistry=d[fields].apply(pd.to_numeric,errors='coerce').copy()
    imputed=np.zeros(len(d),dtype=bool)
    for key,(lo,hi) in cfg['chemistry_valid_ranges'].items():
        chemistry[key]=chemistry[key].where(chemistry[key].between(lo,hi)&valid)
        missing=valid&chemistry[key].isna()
        imputed|=missing.to_numpy()
        medians=chemistry[key].groupby(d.WRB2).transform('median')
        overall=chemistry[key].median()
        if not np.isfinite(overall):raise ValueError('No chemistry evidence for '+key)
        chemistry.loc[missing,key]=medians[missing].fillna(overall)
    # pH and base saturation are correlated: combine as one availability axis.
    ph=np.asarray(cfg['ph_scores'])[np.digitize(chemistry.PH_WATER,cfg['ph_breaks'])]
    bs=np.asarray(cfg['base_saturation_scores'])[np.digitize(chemistry.BSAT,cfg['base_saturation_breaks'])]
    availability=np.minimum(ph,bs)
    retention=1+np.digitize(chemistry.CEC_SOIL,cfg['cec_breaks'])
    weight=cfg['limiting_factor_weight']
    score=weight*np.minimum(availability,retention)+(1-weight)*(availability+retention)/2
    for key,caps in cfg['constraint_caps'].items():
        for threshold,cap in caps:score=np.where(chemistry[key]>=threshold,np.minimum(score,cap),score)
    grades=np.where(valid,np.clip(np.floor(score+.5),1,5),0).astype(np.uint8)
    audit=d[['HWSD2_SMU_ID','SEQUENCE','SHARE','WRB2']].copy()
    for key in fields:audit[key]=chemistry[key]
    audit['chemistry_imputed']=imputed
    audit['availability_score']=np.where(valid,availability,np.nan)
    audit['retention_score']=np.where(valid,retention,np.nan)
    audit['fertility_score']=np.where(valid,score,np.nan)
    audit['fertility_id']=grades
    return grades,audit


def location_grades(zones,totals,denominator,lon,lat,cfg):
    d=soil.finalize(zones,totals[:,:5],denominator,lon,lat,{'types':cfg['levels']})
    d=d.rename(columns={'soil_id':'fertility_id','soil_type':'fertility'})
    names=list(cfg['levels']);fractions=d[[n+'_share' for n in names]].to_numpy()
    scores=fractions@np.arange(1,6)
    land=d.fertility_id>0
    d['fertility_score']=scores
    d.loc[land,'fertility_id']=np.clip(np.floor(scores[land]+.5),1,5).astype(int)
    d.loc[land,'fertility']=np.asarray(names)[d.loc[land,'fertility_id'].to_numpy(int)-1]
    observed=totals[:,:5].sum(axis=1)
    imputed=np.divide(totals[:,5],observed,out=np.zeros(len(d)),where=observed>0)
    # Nearest-location estimates carry the donor's chemistry uncertainty too.
    by_tag=dict(zip(d.location_tag,imputed))
    for i in np.flatnonzero(d.inferred):imputed[i]=by_tag[d.analogue_location.iloc[i]]
    d['chemistry_imputed_share']=imputed
    d['low_confidence']=d.low_confidence|(imputed>0)
    d['assignment_source']=d.assignment_source.str.replace('composition','chemistry',regex=False)
    d.loc[~land,'fertility_score']=np.nan
    assert d.loc[d.is_ownable,'fertility_id'].between(1,5).all()
    return d


def render(d,cfg,raw,out,title='Fertility — soil chemistry proxy'):
    from PIL import Image
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    Image.MAX_IMAGE_PIXELS=None
    im=Image.open(raw/'locations.png').convert('RGB');im.thumbnail((2400,1200),Image.Resampling.NEAREST)
    a=np.asarray(im,dtype=np.int32);lut=np.full((2**24,3),[17,31,45],dtype=np.uint8)
    for row in d.itertuples():
        if row.fertility in cfg['levels']:lut[int(row.map_color_rgb,16)]=cfg['levels'][row.fertility]['color']
    fig,ax=plt.subplots(figsize=(16,8),facecolor='#111f2d')
    ax.imshow(lut[(a[:,:,0]<<16)|(a[:,:,1]<<8)|a[:,:,2]]);ax.axis('off')
    ax.set_title(title,color='white',fontsize=19)
    legend=ax.legend(handles=[Patch(color=np.array(v['color'])/255,label=v['label']) for v in cfg['levels'].values()],loc='lower center',ncol=5,facecolor='#172a3a',edgecolor='none')
    for t in legend.get_texts():t.set_color('white')
    fig.tight_layout();fig.savefig(out/'fertility.png',dpi=140,facecolor=fig.get_facecolor());plt.close(fig)


CHEMISTRY_NOTES=['Modern HWSD D1 chemistry (0-20cm); not a measured 1300 map or pristine pre-human conditions.',
       'Five grades and aggregation are shared game-proxy rules, not FAO official fertility classes or a GAEZ crop suitability calculation.',
       'No population, crop yields, rain, irrigation, drainage, depth or texture class is a formula input.',
       'pH and base saturation share one availability axis; CEC is retention. Salt/sodium/aluminium constraints cap the score.',
       'Wholly missing component chemistry remains missing, never a fabricated zero or median. Partial gaps use same-WRB-group medians, then global field median; flagged. Missing locations use recorded nearest-location donors.',
       'Four fine-grid samples per registered game pixel; classify components first, preserve fractions through latitude-weighted location aggregation.',
       'Fertility adds no gameplay bonus yet; its relation to modifiers and buildings remains a later balance decision.']


def build(config_path=None):
    """Dispatch: caloric producer when the config carries ``caloric_yield``, else the chemistry classifier."""
    cp=Path(config_path or ROOT/'configs/fertility.json').resolve();cfg=json.loads(cp.read_text())
    if cfg.get('caloric_yield'):return build_caloric(cp,cfg)
    return build_chemistry(cp,cfg)


def chemistry_inputs(cp,out):
    source=ROOT/json.loads(cp.read_text())['source_directory'];raw=ROOT/'data/raw/location_inputs'
    soil.build()
    archives=soil.fetch_sources(source)
    # Ensure the component cache matches the downloaded database.
    soil.component_lookup(source,json.loads((ROOT/'configs/soil_types.json').read_text()))
    paths=[ROOT/'artifacts/soils/locations.csv',cp,Path(__file__),Path(soil.__file__),ROOT/'src/historical_agriculture/location_inventory.py',source/'topsoil_components.parquet',source/'HWSD2.mdb',raw/'locations.png',raw/'transform.json',raw/'game_default.map',raw/'game_templates.txt',raw/'game_named_locations.txt']
    inputs={str(p.relative_to(ROOT)):soil.sha(p) for p in paths};inputs['archives']=archives
    return source,raw,inputs


def chemistry_table(cp,cfg,out):
    """The HWSD chemistry grade table (previous producer); writes only the component audit."""
    source,raw,inputs=chemistry_inputs(cp,out)
    d=pd.read_parquet(source/'topsoil_components.parquet')
    grades,audit=classify_components(d,cfg);audit.to_parquet(out/'component_chemistry.parquet',index=False)
    shares=np.zeros((65536,6),dtype=np.float32)
    for grade in range(1,6):
        take=grades==grade
        np.add.at(shares[:,grade-1],d.loc[take,'HWSD2_SMU_ID'].to_numpy(int),d.loc[take,'SHARE'].to_numpy(float)/100)
    take=(grades>0)&audit.chemistry_imputed
    np.add.at(shares[:,5],d.loc[take,'HWSD2_SMU_ID'].to_numpy(int),d.loc[take,'SHARE'].to_numpy(float)/100)
    if (shares[:,:5].sum(axis=1)>1.001).any():raise ValueError('HWSD shares exceed one')
    zones=read_zone_inventory(raw)
    totals,denominator,lon,lat=soil.sample_locations(raw,source,shares,zones)
    return location_grades(zones,totals,denominator,lon,lat,cfg),audit,grades,inputs


def build_chemistry(cp,cfg):
    out=ROOT/cfg['output_directory'];out.mkdir(parents=True,exist_ok=True)
    source,raw,inputs=chemistry_inputs(cp,out)
    manifest=out/'manifest.json'
    if manifest.exists() and (out/'locations.csv').exists():
        prior=json.loads(manifest.read_text())
        if prior.get('inputs')==inputs and prior.get('csv_sha256')==soil.sha(out/'locations.csv'):return prior
    result,audit,grades,inputs=chemistry_table(cp,cfg,out)
    result.to_csv(out/'locations.csv',index=False,float_format='%.8f');render(result,cfg,raw,out)
    own=result[result.is_ownable];land=result[result.fertility_id>0]
    cross=pd.crosstab(pd.read_csv(ROOT/'artifacts/soils/locations.csv',keep_default_na=False).set_index('location_tag').soil_type, result.set_index('location_tag').fertility)
    cross.to_csv(out/'soil_type_crosscheck.csv')
    report={'schema_version':1,'inputs':inputs,'csv_sha256':soil.sha(out/'locations.csv'),
      'component_audit_sha256':soil.sha(out/'component_chemistry.parquet'),'sources':cfg['sources'],
      'game_zones':len(result),'land_locations':len(land),'ownable_locations':len(own),
      'ownable_missing':int((~own.fertility_id.between(1,5)).sum()),'ownable_distribution':own.fertility.value_counts().to_dict(),
      'inferred_ownable_locations':int(own.inferred.sum()),'chemistry_imputed_ownable_locations':int((own.chemistry_imputed_share>0).sum()),
      'chemistry_imputed_components':int(audit.chemistry_imputed.sum()),
      'unclassified_components':int((grades==0).sum()),
      'ownable_low_source_coverage':int((own.source_coverage<.5).sum()),
      'notes':CHEMISTRY_NOTES}
    manifest.write_text(json.dumps(report,indent=2));return report


def chemistry_reference(cp,cfg,out):
    """Retained chemistry grades per location tag for the diagnostic column.

    Order: ``chemistry_locations.csv`` (archived chemistry output); the previous
    chemistry-only ``locations.csv`` (archived on first migration); the column
    already carried by a caloric ``locations.csv``; a fresh chemistry run when
    HWSD sources are available. Never fails the caloric build.
    """
    ref=out/'chemistry_locations.csv';current=out/'locations.csv'
    if not ref.exists() and current.exists():
        columns=pd.read_csv(current,nrows=0).columns
        if 'fertility_id' in columns and 'best_kcal_per_ha' not in columns:
            shutil.copyfile(current,ref)
    if ref.exists():
        d=pd.read_csv(ref,usecols=['location_tag','fertility_id'],keep_default_na=False)
        return dict(zip(d.location_tag,d.fertility_id.astype(int))),'artifacts/fertility/chemistry_locations.csv (archived chemistry-only output)'
    if current.exists() and 'chemistry_fertility_id' in pd.read_csv(current,nrows=0).columns:
        d=pd.read_csv(current,usecols=['location_tag','chemistry_fertility_id'],keep_default_na=False)
        return dict(zip(d.location_tag,d.chemistry_fertility_id.astype(int))),'previous caloric locations.csv column'
    try:
        result=chemistry_table(cp,cfg,out)[0]
        result.to_csv(ref,index=False,float_format='%.8f')
        return dict(zip(result.location_tag,result.fertility_id.astype(int))),'recomputed from HWSD chemistry and archived as chemistry_locations.csv'
    except Exception as exc:  # HWSD sources may be absent offline; the diagnostic is optional.
        return {},f'unavailable ({type(exc).__name__}); chemistry_fertility_id is 0 everywhere'


def surface_water_weight(inv,sw):
    """Per-location weight of the irrigated potential: the largest configured weight whose condition holds.

    Conditions are displayed attributes only: topography classes, World Builder river level, lake adjacency.
    """
    w=np.zeros(len(inv))
    topo=pd.read_csv(ROOT/'artifacts/topography/locations.csv',keep_default_na=False).set_index('location_tag').topography.reindex(inv.location_tag).fillna('').to_numpy()
    for cls,value in sw.get('topography_weights',{}).items():w=np.maximum(w,np.where(topo==cls,value,0))
    levels=ROOT/'artifacts/river_network/location_levels.csv'
    if levels.exists():
        lv=pd.read_csv(levels,keep_default_na=False).set_index('location_tag').marker_aware_predicted_level.reindex(inv.location_tag).fillna(0).astype(int).to_numpy()
        for level,value in sw.get('river_level_weights',{}).items():w=np.maximum(w,np.where(lv>=int(level),value,0))
    if 'is_adjacent_to_lake' in inv and sw.get('lake_weight'):w=np.maximum(w,np.where(inv.is_adjacent_to_lake.astype(str).eq('True').to_numpy(),sw['lake_weight'],0))
    return w


def build_caloric(cp,cfg):
    from . import acquisition, fertility_caloric as fc
    from .location_geometry import overlap_matrix
    from .provenance import clean
    cal=cfg['caloric_yield'];out=ROOT/cfg['output_directory'];out.mkdir(parents=True,exist_ok=True)
    raw=ROOT/'data/raw/location_inputs';target=ROOT/'data/raw/gaez';manifest_path=ROOT/cal['manifest']
    crops=[c for c in cal['crops'] if c.get('include',True)]
    records,missing=acquisition.acquire_rasters(ROOT,[c['code'] for c in crops],[cal['scenario']],target,manifest_path,import_directory=cal.get('import_directory'),strict=False)
    available={r['crop']:r for r in records}
    irrigated_records=[]
    sw=cal.get('surface_water')
    if sw:
        irrigated_records,_=acquisition.acquire_rasters(ROOT,[c['code'] for c in crops],[sw['scenario']],target,ROOT/sw['manifest'],import_directory=cal.get('import_directory'),strict=False)
    if len(available)<cal.get('minimum_crops',20):raise ValueError(f'Only {len(available)} caloric crop rasters available')
    chemistry,chemistry_source=chemistry_reference(cp,cfg,out)
    code=[cp,Path(__file__),Path(fc.__file__),Path(acquisition.__file__),ROOT/'src/historical_agriculture/location_geometry.py',ROOT/'src/historical_agriculture/location_inventory.py']
    paths=code+[manifest_path,raw/'inventory.parquet',raw/'locations.png',raw/'transform.json',raw/'game_default.map',raw/'game_templates.txt',raw/'game_named_locations.txt']
    if (out/'chemistry_locations.csv').exists():paths.append(out/'chemistry_locations.csv')
    inputs={str(p.relative_to(ROOT)):soil.sha(p) for p in paths}
    inputs.update({str((target/r['name']).relative_to(ROOT)):r['sha256'] for r in records+irrigated_records})
    if sw:
        for extra in [ROOT/'artifacts/river_network/location_levels.csv',ROOT/'artifacts/topography/locations.csv']:
            if extra.exists():inputs[str(extra.relative_to(ROOT))]=soil.sha(extra)
    manifest=out/'manifest.json'
    if manifest.exists() and (out/'locations.csv').exists():
        prior=json.loads(manifest.read_text())
        if prior.get('inputs')==inputs and prior.get('csv_sha256')==soil.sha(out/'locations.csv'):return prior
    inv=pd.read_parquet(raw/'inventory.parquet').sort_values('location_tag').reset_index(drop=True)
    weights,geometry=overlap_matrix(ROOT,inv,ROOT/'artifacts/locations')
    if weights.shape!=(len(inv),2160*4320):raise ValueError('Fertility overlap grid mismatch')
    zones=read_zone_inventory(raw)
    kcal=fc.crop_table(cal)
    rasters={c:(lambda p=target/r['name']:fc.read_raster(p)) for c,r in available.items()}
    best,index,codes=fc.best_caloric_yield(rasters,kcal,nodata=cal.get('nodata',fc.NODATA))
    print(f'Best caloric staple grid from {len(codes)} crops',flush=True)
    irrigated=None;water_weight=None
    if sw and irrigated_records:
        irr={r['crop']:(lambda p=target/r['name']:fc.read_raster(p)) for r in irrigated_records}
        irrigated,_,_=fc.best_caloric_yield(irr,kcal,nodata=cal.get('nodata',fc.NODATA))
        print(f'Best irrigated staple grid from {len(irr)} crops',flush=True)
        water_weight=surface_water_weight(inv,sw)
    result,summary=fc.location_table(inv,zones,weights,best,index,codes,cfg,cp,chemistry,irrigated=irrigated,water_weight=water_weight)
    inputs[str(cp.relative_to(ROOT))]=soil.sha(cp)  # thresholds may have been frozen into the config
    result.to_csv(out/'locations.csv',index=False,float_format='%.8f')
    render(result,cfg,raw,out,title='Fertility — best caloric staple, low input, rain-fed plus surface-water-fed land (GAEZ v5)')
    own=result[result.is_ownable];land=result[result.fertility_id>0]
    soils=ROOT/'artifacts/soils/locations.csv'
    if soils.exists():
        cross=pd.crosstab(pd.read_csv(soils,keep_default_na=False).set_index('location_tag').soil_type,result.set_index('location_tag').fertility)
        cross.to_csv(out/'soil_type_crosscheck.csv')
    audit=out/'component_chemistry.parquet'
    report={'schema_version':2,'inputs':inputs,'csv_sha256':soil.sha(out/'locations.csv'),
      'component_audit_sha256':soil.sha(audit) if audit.exists() else None,'sources':cal.get('sources',[])+cfg['sources'],
      'game_zones':len(result),'land_locations':len(land),'ownable_locations':len(own),
      'ownable_missing':int((~own.fertility_id.between(1,5)).sum()),'ownable_distribution':own.fertility.value_counts().to_dict(),
      'inferred_ownable_locations':int(own.inferred.sum()),'chemistry_imputed_ownable_locations':0,
      'chemistry_imputed_components':None,'unclassified_components':None,
      'ownable_low_source_coverage':int((own.source_coverage<.5).sum()),
      'caloric':{'scenario':cal['scenario'],'kcal_source':cal.get('source_note'),
        'crops_used':sorted(codes),'crops_missing':[m['crop'] for m in missing],'crop_count':len(codes),
        'imported_rasters':sum('imported_from' in r for r in records),
        'chemistry_reference':chemistry_source,'chemistry_grade_agreement_ownable':float((own.chemistry_fertility_id==own.fertility_id).mean()),
        **summary},
      'geometry':geometry,
      'notes':['Best caloric staple: per 5-arcminute cell, the maximum over caloric crops of GAEZ v5 RES05-YXX attainable yield (LRLM: low input, rain-fed; kg/ha) times CADI kcal per 100 g times 10, i.e. kcal/ha. No crop is fixed per location.',
       'Grades are lower-bound-inclusive bins on the exact-overlap location mean; thresholds were frozen as ownable quantiles on the first build and are held constant afterwards.',
       'Attainable yield is a modelled agro-climatic potential under 1981-2010 climate, not a measured medieval harvest; it already combines climate, soil and terrain constraints.',
       'No population, cultivation, improvement, irrigation or soil-type label enters the grade. Ownable locations without valid overlap inherit the nearest ownable location, with donor and distance recorded.',
       'chemistry_fertility_id keeps the previous HWSD chemistry grade as a diagnostic; it is not used by the grade.',
       'Fertility adds no gameplay bonus yet; its relation to modifiers and buildings remains a later balance decision.']}
    manifest.write_text(json.dumps(clean(report),indent=2));return report
