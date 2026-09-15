"""Five game fertility grades from HWSD chemistry, before location aggregation.
This is a transparent proxy, not an official FAO fertility map or a 1300 survey.
"""
from pathlib import Path
import json
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


def render(d,cfg,raw,out):
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
    ax.set_title('Fertility — soil chemistry proxy',color='white',fontsize=19)
    legend=ax.legend(handles=[Patch(color=np.array(v['color'])/255,label=v['label']) for v in cfg['levels'].values()],loc='lower center',ncol=5,facecolor='#172a3a',edgecolor='none')
    for t in legend.get_texts():t.set_color('white')
    fig.tight_layout();fig.savefig(out/'fertility.png',dpi=140,facecolor=fig.get_facecolor());plt.close(fig)


def build(config_path=None):
    cp=Path(config_path or ROOT/'configs/fertility.json').resolve();cfg=json.loads(cp.read_text())
    source=ROOT/cfg['source_directory'];out=ROOT/cfg['output_directory'];out.mkdir(parents=True,exist_ok=True)
    soil.build()
    archives=soil.fetch_sources(source);raw=ROOT/'data/raw/location_inputs'
    # Ensure the component cache matches the downloaded database.
    soil.component_lookup(source,json.loads((ROOT/'configs/soil_types.json').read_text()))
    paths=[ROOT/'artifacts/soils/locations.csv',cp,Path(__file__),Path(soil.__file__),ROOT/'src/historical_agriculture/location_inventory.py',source/'topsoil_components.parquet',source/'HWSD2.mdb',raw/'locations.png',raw/'transform.json',raw/'game_default.map',raw/'game_templates.txt',raw/'game_named_locations.txt']
    inputs={str(p.relative_to(ROOT)):soil.sha(p) for p in paths};inputs['archives']=archives
    manifest=out/'manifest.json'
    if manifest.exists() and (out/'locations.csv').exists():
        prior=json.loads(manifest.read_text())
        if prior.get('inputs')==inputs and prior.get('csv_sha256')==soil.sha(out/'locations.csv'):return prior
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
    result=location_grades(zones,totals,denominator,lon,lat,cfg)
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
      'notes':['Modern HWSD D1 chemistry (0-20cm); not a measured 1300 map or pristine pre-human conditions.',
       'Five grades and aggregation are shared game-proxy rules, not FAO official fertility classes or a GAEZ crop suitability calculation.',
       'No population, crop yields, rain, irrigation, drainage, depth or texture class is a formula input.',
       'pH and base saturation share one availability axis; CEC is retention. Salt/sodium/aluminium constraints cap the score.',
       'Wholly missing component chemistry remains missing, never a fabricated zero or median. Partial gaps use same-WRB-group medians, then global field median; flagged. Missing locations use recorded nearest-location donors.',
       'Four fine-grid samples per registered game pixel; classify components first, preserve fractions through latitude-weighted location aggregation.',
       'Fertility adds no gameplay bonus yet; its relation to modifiers and buildings remains a later balance decision.']}
    manifest.write_text(json.dumps(report,indent=2));return report
