import json
from pathlib import Path

import numpy as np

from .accounting import annual_food, labour_days, upper_system
from .acquisition import filename
from .provenance import write_json
from .raster import read, write, coordinates
from .transformations import factor

def surfaces(root,config,out):
    parameters=json.loads((out/'parameters.json').read_text())['parameters']
    results=[]
    for crop in config['crop_order']:
        c=config['crops'][crop];p=parameters[c['group']]
        low,profile=read(root/config['inputs']/filename(crop,'LRLM'))
        high_r,_=read(root/config['inputs']/filename(crop,'HRLM'))
        high_i,_=read(root/config['inputs']/filename(crop,'HILM'))
        low*=factor(c,'LRLM',p['low'],p['high'])
        high_r*=factor(c,'HRLM',p['low'],p['high'])
        high_i*=factor(c,'HILM',p['low'],p['high'])
        upper,system=upper_system(high_r,high_i)
        for name,a in [('lower',low),('high_rainfed',high_r),('high_irrigated',high_i),('upper',upper),('upper_system',np.where(system==255,np.nan,system))]:
            write(out/'crops'/f'{crop}_{name}.tif',a,profile,'system code 0/1/2' if name=='upper_system' else 'kg dry product / ha / crop cycle')
        results.append({'crop':crop,'reversed_cells':int(np.sum(np.isfinite(low)&np.isfinite(upper)&(upper<low))),
                        'equal_cells':int(np.sum(np.isfinite(low)&(upper==low))),
                        'positive_lower':int(np.sum(low>0)),'positive_upper':int(np.sum(upper>0))})
    write_json(out/'scenario_ordering.json',results)
    return results

def assign(root,config,out):
    reference,profile=read(root/config['inputs']/filename(config['crop_order'][0],'LRLM'))
    domain=np.isfinite(reference)
    geometry=json.loads((root/'configs/regions.json').read_text())
    regions=geometry['regions']
    if geometry.get('geometry')=='RESOLVE_Ecoregions2017':
        from .ecoregions import geometry_grid
        eco,region_id=geometry_grid(root,geometry,profile,out)
        write(out/'ecoregion.tif',np.where(domain & (eco>=0),eco,np.nan),profile,'RESOLVE ECO_ID')
    else:
        x,y=coordinates(profile);xs=x[None,:];ys=y[:,None]
        region_id=np.zeros(domain.shape,dtype=np.int16)
        for r in regions:
            w,s,e,n=r['bbox']
            mask=domain&(xs>=w)&(xs<e)&(ys>=s)&(ys<n)
            region_id[mask]=r['id']
    crop_id=np.zeros(domain.shape,dtype=np.int16)
    alternate=np.zeros_like(crop_id)
    # 0 outside GAEZ, 1 non-crop inference, 2 agricultural inference,
    # 3 proposed crop unavailable/unsuitable, 4 unresolved regional assignment.
    state=np.where(domain,4,0).astype(np.uint8)
    confidence=np.zeros_like(state)
    viable={};known={}
    for i,crop in enumerate(config['crop_order'],1):
        low,_=read(out/'crops'/f'{crop}_lower.tif')
        high,_=read(out/'crops'/f'{crop}_upper.tif')
        known[crop]=np.isfinite(low)&np.isfinite(high)
        viable[crop]=known[crop]&((low>0)|(high>0))
    any_viable=np.logical_or.reduce(list(viable.values()))
    # A source-domain ice/desert cell is not an unexplained historical assignment gap.
    # This is suitability for modeled crops only, not total food-support potential.
    all_known=np.logical_and.reduce(list(known.values()))
    state[domain&~any_viable&all_known]=5
    state[domain&~any_viable&~all_known]=6
    codes={c:i for i,c in enumerate(config['crop_order'],1)}
    counts=[]
    for r in regions:
        mask=(region_id==r['id'])&any_viable
        if not r['crops']:
            state[mask]=4 if r.get("classification")=="unresolved" else 1
        else:
            state[mask]=3
            for crop in r['crops']:
                possible=mask&viable[crop]
                second=possible&(crop_id>0)&(alternate==0)
                alternate[second]=codes[crop]
                first=possible&(crop_id==0)
                crop_id[first]=codes[crop];state[first]=2
        confidence[mask]=2 if r['confidence']=='medium' else 1
        counts.append({'region':r['name'],'cells':int(mask.sum()),'assigned':int(np.sum(mask&(state==2))),
                       'unsupported':int(np.sum(mask&(state==3))), 'unresolved':int(np.sum(mask&(state==4)))})
    for name,a in [('crop',crop_id),('alternative_crop',alternate),('region',region_id),('state',state),('confidence',confidence)]:
        write(out/f'{name}.tif',np.where(domain,a,np.nan),profile,'categorical code')
    result={'domain':'GAEZ valid land cells; outside-domain land is not asserted to be ocean',
            'domain_cells':int(domain.sum()),'states':{str(i):int(np.sum(domain&(state==i))) for i in [1,2,3,4,5,6]},
            'state_codes':{'1':'non-crop livelihood inference','2':'conditional agricultural inference','3':'no viable historically listed crop','4':'unresolved regional evidence','5':'none of the modeled crops viable; NOT negligible total food support','6':'incomplete crop scenario inputs; suitability unresolved'},
            'scope':'conditional farming-system assignment, NOT an observed cropland map',
            'crop_codes':codes,'confidence_codes':{'1':'low/inferred','2':'medium/regional evidence; boundaries approximate'},
            'regional_counts':counts}
    write_json(out/'coverage.json',result)
    return result

def calculate(root,config,out):
    crop_map,profile=read(out/'crop.tif');regions,_=read(out/'region.tif')
    state,_=read(out/'state.tif')
    shape=crop_map.shape
    position=np.full(shape,np.nan,dtype=np.float32)
    poslo=position.copy();poshi=position.copy();frequency=position.copy();fraction=position.copy();maintenance=position.copy()
    rules=json.loads((root/'configs/regions.json').read_text())['regions']
    for r in rules:
        mask=(regions==r['id'])&(state==2)
        m=config['management'][r['management']]
        position[mask]=m['position'];poslo[mask]=m['range'][0];poshi[mask]=m['range'][1]
        frequency[mask]=m['harvests'];fraction[mask]=m['cultivated_fraction'];maintenance[mask]=m['maintenance_days']
    names=['lower_dm','upper_dm','historical_dm','lower_kcal','upper_kcal','historical_kcal','gross_kcal','labour_days','kcal_per_worker_day','historical_kcal_low','historical_kcal_high','labour_low','labour_high','upper_system','envelope_valid']
    fields={k:np.full(shape,np.nan,dtype=np.float32) for k in names}
    sensitivity=[]
    for i,code in enumerate(config['crop_order'],1):
        mask=(crop_map==i)&(state==2)
        if not mask.any():continue
        c=config['crops'][code]
        low,_=read(out/'crops'/f'{code}_lower.tif');upper,_=read(out/'crops'/f'{code}_upper.tif');system,_=read(out/'crops'/f'{code}_upper_system.tif')
        fields['lower_dm'][mask]=low[mask];fields['upper_dm'][mask]=upper[mask];fields['upper_system'][mask]=system[mask]
        valid=mask&np.isfinite(low)&np.isfinite(upper)&(upper>=low)
        fields['envelope_valid'][mask]=0;fields['envelope_valid'][valid]=1
        if not valid.any():continue
        f=frequency[valid];rot=fraction[valid];m=maintenance[valid]
        historical=low[valid]+position[valid]*(upper[valid]-low[valid])
        fields['historical_dm'][valid]=historical
        _,gross,net=annual_food(historical,c,f,rot)
        _,_,lofood=annual_food(low[valid],c,f,rot)
        _,_,hifood=annual_food(upper[valid],c,f,rot)
        labour=labour_days(c['labour_days'],f,rot,m)
        for name,a in [('historical_kcal',net),('gross_kcal',gross),('lower_kcal',lofood),('upper_kcal',hifood),('labour_days',labour),('kcal_per_worker_day',net/labour)]:fields[name][valid]=a
        _,_,low_uncertain=annual_food(low[valid]*.75+poslo[valid]*(upper[valid]*.75-low[valid]*.75),c,f,rot,loss=.3)
        _,_,high_uncertain=annual_food(low[valid]*1.25+poshi[valid]*(upper[valid]*1.25-low[valid]*1.25),c,f,rot,loss=.05)
        fields['historical_kcal_low'][valid]=low_uncertain;fields['historical_kcal_high'][valid]=high_uncertain
        fields['labour_low'][valid]=labour_days(c['labour_range'][0],f,rot,m)
        fields['labour_high'][valid]=labour_days(c['labour_range'][1],f,rot,m)
        for loss in config['loss_sensitivity']:
            _,_,candidate=annual_food(historical,c,f,rot,loss=loss)
            sensitivity.append({'crop':code,'loss_share':loss,'median_kcal':float(np.median(candidate)),'median_kcal_per_worker_day':float(np.median(candidate/labour))})
    for name,a in fields.items():
        units='kg dry product / ha / crop cycle' if name.endswith('_dm') else 'kcal / rotational ha / year'
        if name.startswith('labour'):units='worker-days / rotational ha / year'
        if name=='kcal_per_worker_day':units='kcal / worker-day'
        if name in ['upper_system','envelope_valid']:units='categorical code'
        write(out/f'{name}.tif',a,profile,units)
    write(out/'management_position.tif',position,profile,'inferred relative position, not a measured efficiency')
    write(out/'cultivated_fraction.tif',fraction,profile,'rotation-time fraction, NOT actual cropland fraction')
    write_json(out/'sensitivity.json',{'loss_experiments':sensitivity,'joint_uncertainty':'illustrative +/-25% yield, management prior ranges, 5-30% losses; not a probabilistic confidence interval'})
    return {'calculated_cells':int(np.isfinite(fields['historical_kcal']).sum()),'invalid_envelope_cells':int(np.sum(fields['envelope_valid']==0))}
