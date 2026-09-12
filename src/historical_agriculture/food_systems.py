"""Food-system classification and per-used-hectare energy equivalents.

No cell area, cultivated extent or population observation enters these calculations.
Non-crop numerical transfers remain explicitly experimental.
"""
import json
import zipfile
import numpy as np
import pandas as pd
from netCDF4 import Dataset
from scipy.ndimage import distance_transform_edt
from .raster import read, write, coordinates
from .provenance import digest, write_json
from .accounting import annual_food

LABELS={19:'Pastoral dairy and meat',20:'Alpine pastoralism',21:'Hunting and gathering',
        22:'Fishing and terrestrial foraging',23:'North Atlantic livestock and wild foods',
        24:'Rock / ice and Antarctic terrestrial zero',25:'Wild-food potential; local history uncertain'}

def settings(root):return json.loads((root/'configs/food_systems.json').read_text())

def people_from_kcal(kcal, daily=2500, days=365):
    if daily<=0 or days<=0:raise ValueError('Food requirement must be positive')
    return np.asarray(kcal)/(daily*days)

def bounded_fill(values,max_cells):
    known=np.isfinite(values)
    if not known.any():return values.copy(),np.zeros(values.shape,dtype=bool)
    distance,indices=distance_transform_edt(~known,return_indices=True)
    fill=~known&(distance<=max_cells)
    result=values.copy();result[fill]=values[tuple(indices[:,fill])]
    return result,fill

def assign_food(root,config,out):
    cfg=settings(root)
    crops,profile=read(out/'crop.tif');eco,_=read(out/'ecoregion.tif');states,_=read(out/'state.tif')
    domain=np.isfinite(states)
    completed,filled=bounded_fill(eco,cfg['spatial_fill_max_cells'])
    food=np.where(domain,25,0).astype(np.int16)
    evidence=np.where(domain,1,0).astype(np.uint8)
    ledger=json.loads((out/'ecoregion_ledger.json').read_text())['ecoregions']
    rules=json.loads((root/'configs/regions.json').read_text())['regions']
    crop_rules={r['id']:r for r in rules}
    # Preserve explicit historical staple preferences in matched coastal pixels.
    effective_crop=np.where(domain,crops,0).astype(np.int16)
    for entry in ledger:
        mask=domain&(completed==entry['ecoregion_id'])
        realm=entry['realm'];biome=entry['biome'].lower()
        code=21
        if realm=='Antarctica' or entry['ecoregion_id']==0:code=24
        elif realm in ['Palearctic','Afrotropic'] and ('desert' in biome or 'grassland' in biome):code=19
        if entry['ecoregion_id'] in cfg['alpine_ecoregions']:code=20
        if entry['ecoregion_id'] in cfg['norse_ecoregions']:code=23
        food[mask]=code
        entry['fallback_food_code']=code
        entry['fallback_source']=('norse_livelihoods' if code==23 else 'yak_traditional' if code==20 else 'fao_pastoral' if code==19 else 'australia_food' if realm=='Australasia' else 'forge_2021')
        entry['fallback_evidence_status']='broad regional/ecological analogue; not a cell-level historical observation'
        entry['candidate_crops']=crop_rules[entry['system_id']]['crops']
    # Coastal geometry reconciliation can use the neighbouring ecological crop list,
    # but actual local GAEZ suitability must still be positive.
    priority=np.full(domain.shape,100,dtype=np.int16)
    for code,crop in enumerate(config['crop_order'],1):
        lo,_=read(out/'crops'/f'{crop}_lower.tif');hi,_=read(out/'crops'/f'{crop}_upper.tif')
        viable=np.isfinite(lo)&np.isfinite(hi)&((lo>0)|(hi>0))
        ranks=np.full(848,100,dtype=np.int16)
        for entry in ledger:
            if crop in entry['candidate_crops']:
                ranks[entry['ecoregion_id']]=entry['candidate_crops'].index(crop)
        local_rank=ranks[np.where(np.isfinite(completed),completed,847).astype(int)]
        mask=domain&filled&viable&(priority>local_rank)
        effective_crop[mask]=code;priority[mask]=local_rank[mask]
    agricultural=domain&(effective_crop>0)
    food[agricultural]=effective_crop[agricultural];evidence[agricultural]=2
    overrides=domain&np.isin(completed,cfg['pastoral_override_ecoregions'])
    food[overrides]=19;evidence[overrides]=1
    food[overrides&np.isin(completed,cfg['alpine_ecoregions'])]=20
    food[overrides&np.isin(completed,cfg['norse_ecoregions'])]=23
    # Proximity identifies an aquatic-associated possibility, not measured fish yield.
    water_distance=distance_transform_edt(domain)
    aquatic=domain&(food==21)&((water_distance<=2)|np.isin(completed,cfg['coastal_ecoregions']))
    food[aquatic]=22
    _,latitude=coordinates(profile)
    food[domain&(latitude[:,None]<-60)]=24
    evidence[filled|~np.isfinite(completed)]=1
    evidence[food==24]=3
    for name,a in [('food_type',food),('food_evidence',evidence),('food_ecoregion',completed),('food_geometry_inferred',filled.astype(float))]:
        write(out/f'{name}.tif',np.where(domain,a,np.nan),profile,'categorical code')
    labels={i:config['crops'][c]['name'] for i,c in enumerate(config['crop_order'],1)}|LABELS
    counts={str(k):int(np.sum(domain&(food==k))) for k in labels}
    result={'complete_mask':bool(np.all(food[domain]>0)),'domain_cells':int(domain.sum()),'counts':counts,'labels':labels,
      'geometry_inferred_cells':int(np.sum(domain&filled)),'geometry_unmatched_cells':int(np.sum(domain&~np.isfinite(completed))),
      'evidence_codes':{'1':'regional analogue or geometry inference','2':'historical crop preference plus GAEZ viability','3':'rock/ice ecological class'},
      'interpretation':cfg['classification_status'],'hyde_role':cfg['hyde_role'],
      'aquatic_rule':'non-cropping cells within two native cells of source-mask water or listed coastal ecoregions: fishing/foraging possibility, aquatic output excluded'}
    write_json(out/'food_coverage.json',result)
    write_json(out/'food_assignment_ledger.json',{'rules':ledger,'pastoral_overrides':cfg['pastoral_override_ecoregions'],'source':'configs/food_systems.json'})
    return result

def forage_arrays(root,cfg,profile,target_mask):
    path=root/cfg['forge']['path']
    if digest(path)!=cfg['forge']['sha256']:raise ValueError('FORGE source checksum mismatch')
    outputs=[];stocks=[]
    with zipfile.ZipFile(path) as archive:
        for scenario in cfg['forge']['scenarios']:
            with Dataset('memory',memory=archive.read(f'SourceCode/OUTPUT/globe_{scenario}.nc')) as ds:
                if ds['hum_popu'].units!='ind./m2':raise ValueError('Unexpected FORGE human units')
                if ds['ani_popu'].units!='ind./(m2 PFT area)':raise ValueError('Unexpected FORGE grazer units')
                lon=np.asarray(ds['lon'][:]);lat=np.asarray(ds['lat'][:])
                def get(name,level=0):return ds[name][0,level].astype(float).filled(np.nan)
                density=get('hum_popu');intake=get('intake_veg')+get('intake_ani')
                # Annual mean product approximation: exact daily covariance unavailable.
                energy=density*10000*intake*cfg['forge']['energy_mj_per_kg_dm']*(1e6/4184)*365
                energy[density<=cfg['forge']['human_density_floor_m2']*1.001]=0
                grazer=get('ani_popu')
                stock=grazer*10000*cfg['forge']['grazer_mass_kg']/cfg['pastoral']['tlu_kg']
                stock[grazer<=1.001e-9]=0
                outputs.append(energy)
                stocks.append(stock)
    from .environmental_transfer import reconstruct
    result, report = reconstruct(root,cfg['climate_transfer'],profile,lon,lat,
                                 np.stack(outputs+stocks,axis=-1),target_mask)
    n=len(outputs)
    return [result[...,i] for i in range(n)], [result[...,i+n] for i in range(n)], report

def calculate_food(root,config,out):
    cfg=settings(root);food,profile=read(out/'food_type.tif');eco,_=read(out/'food_ecoregion.tif')
    region,_=read(out/'region.tif');domain=np.isfinite(food)
    fields=[np.full(food.shape,np.nan,dtype=np.float32) for _ in range(3)]
    numeric=np.where(domain,0,np.nan).astype(np.float32)
    # Existing canonical crop scenarios, with consistent full-rotation annualization.
    rules=json.loads((root/'configs/regions.json').read_text())['regions']
    system_lookup=np.zeros(848,dtype=np.int16)
    for r in rules:system_lookup[r['ecoregion_ids']]=r['id']
    local_system=system_lookup[np.where(np.isfinite(eco),eco,847).astype(int)]
    frequency=np.full(food.shape,np.nan,dtype=np.float32);fraction=frequency.copy()
    for r in rules:
        m=config['management'][r['management']];mask=local_system==r['id']
        frequency[mask]=m['harvests'];fraction[mask]=m['cultivated_fraction']
    from .rotations import apply
    frequency,fraction,_,_=apply(root,config,food,eco,frequency,fraction)
    for code,crop in enumerate(config['crop_order'],1):
        mask=food==code
        if not mask.any():continue
        lo,_=read(out/'crops'/f'{crop}_lower.tif');hi,_=read(out/'crops'/f'{crop}_upper.tif')
        for r in rules:
            if crop not in r['crops']:continue
            use=mask&(local_system==r['id'])&np.isfinite(lo)&np.isfinite(hi)&(hi>=lo)
            if not use.any():continue
            management=config['management'][r['management']]
            cur=lo[use]+management['position']*(hi[use]-lo[use])
            for array,dm in zip(fields,[lo[use],cur,hi[use]]):
                _,_,net=annual_food(dm,config['crops'][crop],frequency[use],fraction[use])
                array[use]=people_from_kcal(net,cfg['daily_kcal_per_person'],cfg['days_per_year'])
            numeric[use]=1
    forage,stocks,fill_records=forage_arrays(root,cfg,profile,domain&np.isin(food,[19,20,21,22,23,25]))
    stack=np.stack(forage);complete=np.isfinite(stack).all(axis=0)
    lower=np.min(stack,axis=0);upper=np.max(stack,axis=0);current=forage[cfg['forge']['scenarios'].index(cfg['forge']['current'])]
    foraging=domain&np.isin(food,[21,22,25])&complete
    for array,value in zip(fields,[lower,current,upper]):array[foraging]=people_from_kcal(value[foraging],cfg['daily_kcal_per_person'],cfg['days_per_year'])
    numeric[foraging]=2
    # A transparent experimental domestic-stock transfer, not published FORGE output.
    p=cfg['pastoral'];stock=stocks[cfg['forge']['scenarios'].index(cfg['forge']['current'])]
    pastoral=domain&np.isin(food,[19,20,23])&np.isfinite(stock)
    for j,array in enumerate(fields):
        net=stock[pastoral]*(p['milk_kg_per_tlu'][j]*p['milk_kcal_kg']+p['meat_kg_per_tlu'][j]*p['meat_kcal_kg'])*p['postharvest_retention']
        array[pastoral]=people_from_kcal(net,cfg['daily_kcal_per_person'],cfg['days_per_year'])
    numeric[pastoral]=3
    for array in fields:array[food==24]=0
    numeric[food==24]=4
    for name,array in zip(['lower_people','historical_people','upper_people'],fields):write(out/f'{name}.tif',array,profile,'food-energy equivalent people / used hectare / year',{'daily_kcal_per_person':str(cfg['daily_kcal_per_person'])})
    write(out/'food_numeric_basis.tif',numeric,profile,'categorical code')
    valid=np.isfinite(fields[1]);checks={'complete_food_mask':bool(np.all(food[domain]>0)),
       'ordered_people_scenarios':bool(np.all((fields[0][valid]<=fields[1][valid]+1e-6)&(fields[1][valid]<=fields[2][valid]+1e-6))),
       'nonnegative_people':bool(all(np.all(a[np.isfinite(a)]>=0) for a in fields)),
       'no_old_world_livestock_in_australia_or_americas':True}
    # Use source ecological realms, rather than geographic rectangles, for exclusion.
    ledger=json.loads((out/'ecoregion_ledger.json').read_text())['ecoregions']
    forbidden=[e['ecoregion_id'] for e in ledger if e['realm'] in ['Nearctic','Neotropic','Australasia','Oceania']]
    checks['no_old_world_livestock_in_australia_or_americas']=bool(not np.any(np.isin(eco,forbidden)&np.isin(food,[19,20,23])))
    missing=domain&~valid
    missing_by_type={str(int(k)):int(np.sum(missing&(food==k))) for k in np.unique(food[missing])}
    result={'unquantified_by_food_type':missing_by_type,'engineering_pass':all(checks.values()),'checks':checks,'numeric_cells':int(valid.sum()),'unquantified_cells':int(np.sum(domain&~valid)),
      'basis_codes':{'0':'unquantified; not zero','1':'GAEZ/Seshat-calibrated crop scenario','2':'FORGE terrestrial energy proxy; modern 2-degree model sensitivity','3':'experimental grazing-biomass to domestic-livestock transfer','4':'rock/ice terrestrial zero'},
      'basis_counts':{str(i):int(np.sum(numeric==i)) for i in range(5)},'forage_interpolation':fill_records,
      'denominator':cfg['denominator'],'daily_kcal_per_person':cfg['daily_kcal_per_person'],
      'aquatic_food':'excluded; fishing-associated numeric values show terrestrial component only',
      'scientific_acceptance':False,'pastoral_limitations':p['status'],
      'forage_limitations':cfg['forge']['density_interpretation']}
    write_json(out/'food_validation.json',result)
    return result

def benchmark_people(root,config,out):
    cfg=settings(root);observations=pd.read_csv(root/'evidence/benchmarks_1300.csv').set_index('region')
    comparison=pd.read_csv(out/'benchmark_comparison.csv');rows=[]
    for _,r in comparison.iterrows():
        record={'region':r.region,'crop':r.crop,'range_crop':r.crop,'result':r.result,'valid':bool(r.valid),'assumed':False,'source_comparison_valid':bool(r.valid)}
        published=float(observations.loc[r.region,'cropping_coefficient'])
        from .rotations import benchmark_coefficient
        coefficient,label,status=benchmark_coefficient(root,r.region,published)
        record.update(published_cropping_coefficient=published,display_label=label,annualization_status=status)
        for name in ['lower','upper','observed','observed_low','observed_high']:
            _,_,net=annual_food(float(r[name]),config['crops'][r.crop],max(1,coefficient),min(1,coefficient))
            record[name]=float(people_from_kcal(net,cfg['daily_kcal_per_person'],cfg['days_per_year'])) if r.valid else np.nan
        if not bool(r.valid):
            from .benchmark_proxies import assumed_range
            proxy=assumed_range(root,config,out,r.region,observations.loc[r.region],coefficient,cfg['daily_kcal_per_person'],cfg['days_per_year'])
            if proxy is not None:
                record.update(proxy,valid=True,assumed=True,result='assumed_cross_crop')
                for name in ['observed','observed_low','observed_high']:
                    _,_,net=annual_food(float(r[name]),config['crops'][r.crop],max(1,coefficient),min(1,coefficient))
                    record[name]=float(people_from_kcal(net,cfg['daily_kcal_per_person'],cfg['days_per_year']))
        record['annual_cropping_coefficient']=coefficient;rows.append(record)
    pd.DataFrame(rows).to_csv(out/'benchmark_people.csv',index=False)
    return rows
