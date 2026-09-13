"""Complete iteration of native-grid support -> EU5 four-value location output."""
import json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from netCDF4 import Dataset
from scipy.ndimage import distance_transform_edt
from .raster import read,write
from .provenance import digest,write_json
from .accounting import annual_food
from .rotations import apply as apply_rotations
from .water import area_grid,basins,wc
from .water_balance import route

FIELDS=['base_effective_cropland','capacity_multiplier','starting_improvement_effective_cropland','maximum_improvement_effective_cropland']

def log(x):print(x,flush=True)

def fill_nearest(a,valid=None):
    a=np.asarray(a,dtype=np.float32);known=np.isfinite(a) if valid is None else np.isfinite(a)&valid
    if not known.any():raise ValueError('No evidence for spatial estimate')
    _,indices=distance_transform_edt(~known,return_indices=True)
    return np.where(known,a,a[tuple(indices)]),~known

def validate_frame(d,inventory):
    if len(d)!=len(inventory) or d.location_tag.duplicated().any() or set(d.location_tag)!=set(inventory.location_tag):raise ValueError('Incomplete or duplicated location inventory')
    a=d[FIELDS].to_numpy(float)
    if not np.isfinite(a).all():raise ValueError('Missing/nonfinite required values')
    if np.any(a[:,0]<0) or np.any(a[:,1]<=0) or np.any(a[:,2]<0) or np.any(a[:,3]<a[:,2]-1e-7):raise ValueError('Invalid primary-value ordering')
    for name,target in [('inert_capacity',a[:,0]*a[:,1]),('starting_capacity',(a[:,0]+a[:,2])*a[:,1]),('maximum_capacity',(a[:,0]+a[:,3])*a[:,1]),('remaining_improvement_effective_cropland',a[:,3]-a[:,2])]:
        if not np.allclose(d[name],target,rtol=1e-7,atol=1e-5):raise ValueError('Accounting mismatch: '+name)
    return {'complete_inventory':True,'finite_primary_values':True,'ordered_values':True,'capacity_identities':True}

def normalize_support(base,start,maximum,reference,floor,ceiling=None):
    base,start,maximum,reference=np.broadcast_arrays(base,start,maximum,reference)
    if not np.isfinite(np.stack([base,start,maximum,reference])).all():raise ValueError('Nonfinite support')
    if np.any(base<0) or np.any(start<base-1e-8) or np.any(maximum<start-1e-8):raise ValueError('Support order violation')
    if not np.isfinite(floor) or floor<=0 or (ceiling is not None and (not np.isfinite(ceiling) or ceiling<floor)):
        raise ValueError("Invalid multiplier bounds")
    m=np.maximum(reference,floor)
    if ceiling is not None:m=np.minimum(m,ceiling)
    return base/m,m,np.maximum(start-base,0)/m,np.maximum(maximum-base,0)/m

def source_fingerprint(root,config_path,food,water):
    paths=[Path(config_path),root/'evidence/location_input_manifest.json',root/'configs/water.json',root/'configs/reconstruction.json',root/'configs/regions.json',root/'configs/rotations.json',root/'pyproject.toml',root/'uv.lock']
    paths+=list((root/'src/historical_agriculture').glob('*.py'))
    paths+=list((root/'data/raw/location_inputs').rglob('*'))
    paths+=list(food.glob('*.tif'))+list((food/'crops').glob('*.tif'))
    paths+=[food/'manifest.json',food/'parameters.json',food/'food_assignment_ledger.json',food/'ecoregion_ledger.json',food/'food_coverage.json']
    paths+=list(water.glob('*.tif'))+[water/'manifest.json',water/'basin_monthly_budget.npz']
    paths+=list((root/'data/raw/water').glob('*.zip'))
    paths+=list((root/'data/raw/food_systems').glob('*'))
    paths+=list((root/'data/processed/location_forage').glob('*'))
    paths+=[root/'configs/food_systems.json',root/'reports/location_iteration_01_method.md']
    paths+=list((root/'scripts').glob('*.py'))
    paths+=[root/'evidence/land_repair.json',root/'configs/crop_seasons.json',root/'data/processed/water_season_before.csv',root/'configs/agricultural_game_calibration.json',root/'data/processed/system_calibration_before.csv']+list((root/'data/raw/land_repair_sources').glob('*'))
    active_config=json.loads(Path(config_path).read_text())
    if active_config.get('agricultural_game_calibration'):paths+=[root/active_config['agricultural_game_calibration']]
    paths+=[root/'configs/location_refinements.json',root/'evidence/location_refinements.json',root/'configs/cultivated_systems.json',root/'data/processed/land_round_before.csv',root/'data/processed/system_round_before/locations_equal_area.csv']
    paths+=list((root/'data/raw/regional_refinement_sources').glob('*'))
    if active_config.get('inheritance_review_baseline'):paths.append(root/active_config['inheritance_review_baseline'])
    paths+=[root/'data/processed/regional_round_02_before/locations_equal_area.csv',root/'data/processed/rural_round_before/locations_equal_area.csv']
    details={str(p.relative_to(root)):digest(p) for p in sorted(set(paths)) if p.is_file()}
    return hashlib.sha256(json.dumps(details,sort_keys=True).encode()).hexdigest(),details

def crop_densities(root,cfg,out):
    food=root/cfg['food_directory'];rc=json.loads((root/'configs/reconstruction.json').read_text())
    ft,profile=read(food/'food_type.tif');eco,_=read(food/'food_ecoregion.tif')
    domain=np.isfinite(ft);eco_f,eco_missing=fill_nearest(eco)
    eco_f=eco_f.astype(int)
    rules=json.loads((root/'configs/regions.json').read_text())['regions']
    crop=np.where((ft>0)&(ft<=len(rc['crop_order'])),ft,0).astype(np.int16)
    rank=np.where(crop>0,-1,100).astype(np.int16)
    # Extend only with historically listed candidates, in evidence preference order.
    # This is potential for future cultivation, not a claim of historic presence per cell.
    for code,c in enumerate(rc['crop_order'],1):
        lo,_=read(food/'crops'/f'{c}_lower.tif');hi,_=read(food/'crops'/f'{c}_upper.tif')
        ranks=np.full(int(eco_f.max())+1,100,dtype=np.int16)
        for r in rules:
            if c in r['crops']:ranks[r['ecoregion_ids']]=r['crops'].index(c)
        rr=ranks[eco_f];use=domain&(rank>rr)&np.isfinite(lo)&np.isfinite(hi)&(hi>0)
        crop[use]=code;rank[use]=rr[use]
    rf=np.zeros(ft.shape,dtype=np.float32);ir=rf.copy();reference=rf.copy();low_rf=rf.copy();rainfed_headroom=rf.copy();fraction=np.ones_like(rf);freq=np.ones_like(rf);position=np.full_like(rf,.45)
    for r in rules:
        use=np.isin(eco_f,r['ecoregion_ids']);m=rc['management'][r['management']]
        fraction[use]=m['cultivated_fraction'];freq[use]=m['harvests'];position[use]=m['position']
    freq,fraction,_,_=apply_rotations(root,rc,crop,eco_f,freq,fraction)
    inferred=np.zeros(ft.shape,dtype=bool);reversed_cells=0
    envelope_changed=np.zeros(ft.shape,dtype=bool)
    for code,c in enumerate(rc['crop_order'],1):
        use=domain&(crop==code)
        if not use.any():continue
        lo,_=read(food/'crops'/f'{c}_lower.tif');hr,_=read(food/'crops'/f'{c}_high_rainfed.tif');hi,_=read(food/'crops'/f'{c}_high_irrigated.tif')
        # Missing model pixels use same-crop spatial analogues, including true zeros.
        for name,a in [('lo',lo),('hr',hr),('hi',hi)]:
            filled,missing=fill_nearest(a);inferred|=use&missing
            if name=='lo':lo=filled
            elif name=='hr':hr=filled
            else:hi=filled
        old_dry=(1-position)*lo+position*hr
        old_wet=np.maximum(old_dry,(1-position)*lo+position*hi)
        from .management_envelope import yields as management_yields
        dry,wet=management_yields(lo,hr,hi,position)
        envelope_changed|=use&((dry>old_dry+1e-5)|(wet>old_wet+1e-5))
        reversed_cells+=int(np.sum(use&(wet<dry)))
        # Voluntary intervention: choose rainfed when adjusted irrigation is inferior.
        wet=np.maximum(wet,dry)
        cr=rc['crops'][c]
        drycal=annual_food(dry,cr,freq,fraction)[2]/(2500*365)
        wetcal=annual_food(wet,cr,freq,fraction)[2]/(2500*365)
        rf[use]=drycal[use];ir[use]=wetcal[use];reference[use]=wetcal[use]
        low_rf[use]=(annual_food(lo,cr,freq,fraction)[2]/(2500*365))[use]
        rainfed_headroom[use]=np.maximum((annual_food(hr,cr,freq,fraction)[2]/(2500*365))[use]-drycal[use],0)
    from .location_refinements import apply_food
    crop,rf,ir,low_rf,rainfed_headroom,fraction,baseline_rf,baseline_crop,refinement_flags,refinement_audit=apply_food(root,cfg,rc,domain,profile,eco_f,crop,rf,ir,low_rf,rainfed_headroom,fraction,freq,position,fill_nearest)
    envelope_changed|=(refinement_flags>0)
    write(out/'management_envelope_refined.tif',envelope_changed.astype(float),profile,'Voluntary management envelope applied; raw GAEZ scenarios retained')
    reference=np.maximum(rf,ir)
    historical,_=read(food/'historical_people.tif')
    # Baseline wild-food support also exists in crop-labelled cells. Omitting it
    # incorrectly turned dry, irrigation-dependent crop cells into terrestrial zero.
    from .food_systems import forage_arrays,settings as food_settings
    fc=food_settings(root)
    forage_key=hashlib.sha256(json.dumps({'forge':fc['forge'],'transfer':fc['climate_transfer'],'code':digest(root/'src/historical_agriculture/environmental_transfer.py'),'food_code':digest(root/'src/historical_agriculture/food_systems.py'),'mask':digest(food/'food_type.tif')},sort_keys=True).encode()).hexdigest()
    cache=root/'data/processed/location_forage';cache.mkdir(parents=True,exist_ok=True)
    if (cache/'manifest.json').exists() and json.loads((cache/'manifest.json').read_text())['key']==forage_key:
        livelihood,_=read(cache/'people.tif')
    else:
        log('Extending existing FORGE terrestrial-food model to the agricultural baseline')
        energies,stocks,transfer_report=forage_arrays(root,fc,profile,domain&(ft!=24))
        livelihood=energies[fc['forge']['scenarios'].index(fc['forge']['current'])]/(fc['daily_kcal_per_person']*fc['days_per_year'])
        known=domain&np.isfinite(livelihood)&(ft!=24)
        livelihood,missing=fill_nearest(livelihood,known)
        livelihood[ft==24]=0
        write(cache/'people.tif',livelihood,profile,'terrestrial food-equivalent people per physical hectare')
        write_json(cache/'manifest.json',{'key':forage_key,'transfer':transfer_report,'inferred_missing_cells':int(np.sum(domain&missing&(ft!=24)))})
    inferred|=domain&(refinement_flags>0)
    inferred|=domain&(ft<=18)  # FORGE transfer is an explicit baseline estimate.
    # Fill numeric livelihood gaps within their own food class, not from crop yields.
    for code in np.unique(ft[domain]).astype(int):
        if code<=18:continue
        use=domain&(ft==code);known=use&np.isfinite(historical)
        if known.any():a,miss=fill_nearest(historical,known);livelihood[use]=a[use];inferred|=use&~known
        else:
            # Explicit terrestrial foraging analogue, never implicit numeric zero.
            known=domain&np.isin(ft,[21,22,25])&np.isfinite(historical)
            a,_=fill_nearest(historical,known);livelihood[use]=a[use];inferred|=use
    reference=np.maximum(reference,livelihood)
    from .location_refinements import apply_reference
    reference,reference_changed=apply_reference(root,cfg,rc,domain,eco_f,crop,reference)
    inferred|=reference_changed
    write(out/'improvement_reference_refined.tif',reference_changed.astype(float),profile,'Conditional crop reference only; total food and land support unchanged')
    write(out/'potential_crop.tif',np.where(domain,crop,np.nan),profile,'historically available representative crop code')
    diagnostics={'low_rf':low_rf,'rainfed_headroom':rainfed_headroom,'rotation_fraction':np.where(crop>0,fraction,0),'crop_candidate':(crop>0).astype(float),'pastoral':np.isin(ft,[19,20,23]).astype(float),'baseline_rf':baseline_rf,'baseline_crop':baseline_crop,'refinement_flags':refinement_flags,'refinement_audit':refinement_audit}
    return domain,profile,ft,crop,rf,ir,reference,livelihood,inferred,diagnostics,{'irrigation_inferior_cells_using_rainfed':reversed_cells,'numeric_crop_or_livelihood_inferred_cells':int(inferred.sum()),'potential_crop_assigned_cells':int(np.sum(domain&(crop>0))),'no_compatible_historical_crop_cells':int(np.sum(domain&(crop==0)))}

def land_inputs(root,cfg,domain,profile,rf,crop,out):
    raw=root/cfg['input_directory'];area=area_grid();meta={}
    from netCDF4 import num2date
    vals={}
    for var in ['cropland','total_irrigated']:
        with Dataset(raw/'hyde'/(var+'.nc')) as ds:
            dates=num2date(ds['time'][:],ds['time'].units,ds['time'].calendar)
            ix=[i for i,t in enumerate(dates) if t.year==cfg['evidence_year']]
            if len(ix)!=1:raise ValueError('HYDE date unavailable')
            if ds[var].units!='km**2' or ds[var].shape[1:]!=domain.shape:
                raise ValueError('Historical land units/grid mismatch')
            expected_lat=90-(np.arange(domain.shape[0])+.5)/12
            expected_lon=-180+(np.arange(domain.shape[1])+.5)/12
            if not np.allclose(ds['lat'][:],expected_lat,atol=.002) or not np.allclose(ds['lon'][:],expected_lon,atol=.002):
                raise ValueError('Historical land grid orientation mismatch')
            vals[var]=ds[var][ix[0]].filled(np.nan).astype(np.float32)/area
            meta[var]={'year':int(dates[ix[0]].year),'units':ds[var].units,'version':getattr(ds,'version','unknown')}
    z=np.load(raw/'luh1300.npz')
    luh=sum(z[k] for k in ['c3ann','c4ann','c3per','c4per','c3nfx'])
    if z['lat'][0]<z['lat'][-1]:luh=luh[::-1]
    luh=np.repeat(np.repeat(luh,3,axis=0),3,axis=1)
    invalid=~np.isfinite(vals['cropland'])|(vals['cropland']<0)
    lu,lu_missing=fill_nearest(np.where((luh>=0)&(luh<=1),luh,np.nan))
    current=np.clip(np.where(invalid,lu,vals['cropland']),0,1)
    write(out/'historical_cultivated_fraction.tif',current,profile,'Dated HYDE/LUH cultivated land, before natural-access union')
    ii=~np.isfinite(vals['total_irrigated'])|(vals['total_irrigated']<0)
    # Unknown irrigation receives local irrigated/cropland-ratio analogue, explicitly flagged.
    ratio=np.divide(vals['total_irrigated'],np.maximum(vals['cropland'],1e-10))
    known=~ii&~invalid&(vals['cropland']>0)
    rr,_=fill_nearest(np.clip(ratio,0,1),known)
    irrigated=np.clip(np.where(ii,current*rr,vals['total_irrigated']),0,current)
    with Dataset(raw/'pnv.nc') as ds:
        pnv=ds['vegtype'][0,0].filled(np.nan).astype(np.float32)
        if ds['latitude'][0]<ds['latitude'][-1]:pnv=pnv[::-1]
    pnv,pm=fill_nearest(pnv);group=np.full(pnv.shape,7,dtype=np.int8)
    for codes,g in [([1,2,3,4,5,6,7,8],0),([9],1),([10],2),([11,12],3),([13],4),([14],5),([15],6)]:group[np.isin(pnv,codes)]=g
    labels=['forest','savanna','grassland','shrub','tundra','desert','ice','unknown']
    from .terrain_access import calculate as terrain_access
    dem=raw/'hydrology/ETOPO_2022_v1_60s_N90W180_surface.tif'
    terrain,maximum_terrain,tm=terrain_access(dem,profile,cfg['terrain_access'],out)
    b=np.array([cfg['baseline_access_by_pnv'][x] for x in labels])[group]*terrain*(rf>0)
    cap=np.array([cfg['maximum_rainfed_by_pnv'][x] for x in labels])[group]*maximum_terrain*(rf>0)
    from .location_refinements import settings,prairie_access
    ref_cfg=settings(root,cfg)
    prairie_changed=np.zeros(domain.shape,dtype=bool)
    if ref_cfg is not None:
        eco,_=read(root/cfg['food_directory']/'food_ecoregion.tif')
        river,_=read(root/cfg['water_directory']/'river_distance_km.tif')
        b,prairie_changed=prairie_access(ref_cfg['prairie'],eco,group,terrain,river,b,rf)
    write(out/'prairie_access_refined.tif',prairie_changed.astype(float),profile,'1 if natural agricultural access revised')
    # Dated cultivation is evidence of access even where the broad terrain proxy is pessimistic.
    cap=np.maximum.reduce([cap,current,b]);start=np.maximum(b,current)
    # Reclassify the reconstructed cultivated overlap as inherited field preparation.
    # Total starting/max cropped area is unchanged by this accounting step.
    inherited_overlap=np.where(prairie_changed,np.minimum(b,current),0)
    b=b-inherited_overlap
    meta['prairie_reclassified_cropland_ha']=float(np.sum(np.where(domain,inherited_overlap,0)*area)*100)
    if np.any(cap>1+1e-8):raise ValueError('Land fraction exceeds cell')
    inferred=invalid|ii|pm|tm|prairie_changed
    meta.update({'cropland_inferred_cells':int(np.sum(domain&invalid)),'irrigation_inferred_cells':int(np.sum(domain&ii)),'source_note':'HYDE and LUH are related reconstructions. No population raster used. Natural access and maximum clearing fractions are shared explicit priors.'})
    meta['prairie_access_changed_cells']=int(np.sum(domain&prairie_changed))
    return area,b,start,cap,irrigated,inferred,meta


def allocate_irrigation(root,cfg,domain,crop,start,maximum,irr,area,out):
    water=root/cfg['water_directory'];wc_cfg=json.loads((root/'configs/water.json').read_text())
    budget=np.load(water/'basin_monthly_budget.npz');grid,down,rows=basins(root/'data/raw/water',out)
    if not np.array_equal(budget['basin_ids'],[r['HYBAS_ID'] for r in rows]):raise ValueError('Basin ordering mismatch')
    service=grid.copy();elev=wc(root/'data/raw/water','elev');ids={int(r['HYBAS_ID']):i for i,r in enumerate(rows)}
    for link in wc_cfg.get('historical_connections',[]):
        use=np.isin(grid,[ids[k] for k in link['recipient_basins']])&(elev<=link['max_elevation_m'])
        service[use]=ids[link['source_basin']]
    command,command_profile=read(water/'surface_command_fraction.tif');command_missing=~np.isfinite(command)
    command=np.nan_to_num(command)
    candidate=np.maximum(irr,np.minimum(command,cfg['maximum_water_land_fraction']))
    import rasterio
    with rasterio.open(water/'reference_et0_monthly_mm.tif') as d:et=d.read(masked=True).filled(np.nan)
    with rasterio.open(water/'natural_monthly_deficit_mm.tif') as d:deficit=d.read(masked=True).filled(np.nan)
    et=np.nan_to_num(et);deficit=np.nan_to_num(deficit)
    from .crop_seasons import global_seasons,demand
    calendar=json.loads((root/cfg['crop_season_config']).read_text())
    active,season_start,season_unknown,season_records=global_seasons(root,calendar,crop,domain,et)
    demand_mm=demand(active,deficit,crop,cfg['minimum_seasonal_irrigation_demand_mm'],cfg['wet_rice_extra_water_mm_per_active_month'])
    write(out/'irrigation_season_start_month.tif',np.where(domain,season_start+1,np.nan),command_profile,'1 January through 12 December; 0 no crop')
    write(out/'irrigation_season_conflict.tif',np.where(domain,season_unknown,np.nan),command_profile,'1 if thermal calendar conflict or missing climate')
    write_json(out/'crop_seasons.json',{'configuration':calendar,'crops':season_records,'yields_or_area_changed':False})
    eligible=domain&(service>=0)&(crop>0)
    g=service[eligible];n=len(rows);eff=wc_cfg['irrigation']['efficiency']
    irr=np.where(eligible,irr,0);candidate=np.where(eligible,candidate,0)
    def demands(f):return np.stack([np.bincount(g,weights=demand_mm[m][eligible]*f[eligible]*area[eligible]*1000/eff,minlength=n) for m in range(12)])
    hd=demands(irr);md=demands(candidate)
    h=route(budget['runoff_m3'],hd,down,wc_cfg['irrigation']['protected_runoff_fraction'],survival=budget['transmission_survival'])
    u=route(budget['runoff_m3'],md,down,wc_cfg['irrigation']['protected_runoff_fraction'],baseline=h['allocated'],survival=budget['transmission_survival'])
    hs=np.ones(domain.shape,dtype=np.float32);us=hs.copy();xs=hs.copy()
    for m in range(12):
        hr=np.divide(h['allocated'][m],hd[m],out=np.ones(n),where=hd[m]>0)
        ub=np.minimum(u['allocated'][m],hd[m]);ur=np.divide(ub,hd[m],out=np.ones(n),where=hd[m]>0)
        er=np.divide(np.maximum(u['allocated'][m]-ub,0),np.maximum(md[m]-hd[m],0),out=np.ones(n),where=md[m]>hd[m])
        act=active[m][eligible]
        hs[eligible]=np.minimum(hs[eligible],np.where(act,hr[g],1))
        us[eligible]=np.minimum(us[eligible],np.where(act,ur[g],1))
        xs[eligible]=np.minimum(xs[eligible],np.where(act,er[g],1))
    served=irr*hs;full=irr*us+np.maximum(candidate-irr,0)*xs
    write(out/'water_candidate_fraction.tif',candidate,command_profile,'Land within surface command screen before river-budget limitations')
    if np.any(full+1e-7<served):raise ValueError('Expansion removed existing water service')
    np.savez_compressed(out/'water_accounts.npz',runoff_m3=budget['runoff_m3'],historical_demand_m3=hd,maximum_demand_m3=md,historical_withdrawal_m3=h['allocated'],maximum_withdrawal_m3=u['allocated'],historical_outflow_m3=h['outflow'],maximum_outflow_m3=u['outflow'],historical_losses_m3=h['transmission_loss'],maximum_losses_m3=u['transmission_loss'],downstream=down)
    audit={'max_monthly_budget_residual_m3':float(max(np.abs(h['residual']).max(),np.abs(u['residual']).max())),'historical_withdrawal_km3_year':float(h['allocated'].sum()/1e9),'maximum_withdrawal_km3_year':float(u['allocated'].sum()/1e9),'historical_irrigation_requested_ha':float(np.sum(irr*area)*100),'historical_irrigation_reliably_served_ha':float(np.sum(served*area)*100),'maximum_irrigation_reliably_served_ha':float(np.sum(full*area)*100),'water_unknown_or_unmapped_cells':int(np.sum(domain&(command_missing|(service<0)))),'interpretation':'Conservative seasonal service uses worst active month; unused allocations are not converted to extra hectares. Expansion uses a simultaneous upstream-first allocation with current priority. Modern hydrology and shared seasonal/engineering priors.'}
    if audit['max_monthly_budget_residual_m3']>1:raise ValueError('Water account failed')
    audit['seasonal_calendar']='crop-specific climate analogue; see crop_seasons.json'
    audit['seasonal_calendar_flagged_cells']=int(np.sum(domain&season_unknown))
    return served,full,command_missing|(service<0)|season_unknown,audit



def ensure_supporting_products(root,food,water):
    """Rebuild changed scientific prerequisites; location/report code is not a crop change."""
    path=food/'manifest.json';rebuild=not path.exists()
    if path.exists():
        manifest=json.loads(path.read_text())
        for name,sha in manifest['inputs'].items():
            relevant=name.startswith(('configs/','evidence/','data/raw/','src/historical_agriculture/'))
            if name=='src/historical_agriculture/cli.py':relevant=False
            if relevant and (not (root/name).is_file() or digest(root/name)!=sha):rebuild=True;break
        if not rebuild:
            for name,sha in manifest['output_hashes'].items():
                if (name.endswith('.tif') or name in ['parameters.json','food_assignment_ledger.json','ecoregion_ledger.json','food_coverage.json']) and (not (food/name).is_file() or digest(food/name)!=sha):rebuild=True;break
    if rebuild:
        log('Refreshing changed canonical crop/food prerequisites')
        from .pipeline import execute as build_food
        build_food('run',root/'configs/reconstruction.json',food)
    from .water import sources,execute as build_water
    current=json.loads((root/'configs/water.json').read_text());wm=water/'manifest.json';refresh=not wm.exists()
    if wm.exists():
        old=json.loads(wm.read_text());a=old['configuration'].copy();b=current.copy()
        for key in ['raw_directory','hyde_directory','hydrology_directory','river_cache']:a.pop(key,None);b.pop(key,None)
        refresh=a!=b
        old_sources={Path(x['path']).name:x['sha256'] for x in old['sources']}
        new_sources={Path(x['path']).name:x['sha256'] for x in sources(current)}
        refresh |= old_sources!=new_sources
        for name in ['water.py','water_balance.py']:
            refresh |= old['code'].get(name)!=digest(root/'src/historical_agriculture'/name)
    if refresh:
        log('Refreshing changed canonical hydrology prerequisites')
        build_water(root/'configs/water.json',water)

def execute(config_path,output):
    root=Path.cwd();config_path=Path(config_path).resolve();out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
    cfg=json.loads(config_path.read_text());raw=root/cfg['input_directory'];food=root/cfg['food_directory'];water=root/cfg['water_directory']
    ensure_supporting_products(root,food,water)
    log('Verifying repo-owned input pack')
    manifest=json.loads((root/'evidence/location_input_manifest.json').read_text())
    for item in manifest['sources']:
        if digest(root/item['path'])!=item['sha256']:raise ValueError('Changed imported source: '+item['path'])
    inventory=pd.read_parquet(raw/'inventory.parquet').sort_values('location_tag').reset_index(drop=True)
    log('Calculating crop, livelihood and land states on the native grid')
    domain,profile,food_type,crop,rf,ir,reference,livelihood,yinf,diagnostics,ya=crop_densities(root,cfg,out)
    area,b,start,maximum,irr,linf,la=land_inputs(root,cfg,domain,profile,diagnostics['baseline_rf'],diagnostics['baseline_crop'],out)
    historical_cultivated=read(out/'historical_cultivated_fraction.tif')[0]
    from .cultivated_systems import apply as apply_cultivated_systems
    rf,ir,system_flags=apply_cultivated_systems(root,cfg,domain,profile,crop,rf,ir,diagnostics,out)
    from .dry_field_alternatives import estimate as dry_alternatives,contributions as alternative_contributions,infer_water
    alternative,alternative_crop=dry_alternatives(root,cfg,domain,profile,crop,rf,historical_cultivated,irr,out)
    alternative_share=cfg['dry_field_alternatives']['field_share']
    linf|=alternative_crop>0
    recorded_irrigation=irr.copy()
    command=np.clip(np.nan_to_num(read(water/'surface_command_fraction.tif')[0]),0,cfg['maximum_water_land_fraction'])
    irr=infer_water(historical_cultivated,irr,command,rf,ir,alternative,cfg['inferred_cultivated_water_share'])
    inferred_water=irr-recorded_irrigation
    linf|=inferred_water>0
    write(out/'recorded_historical_irrigation_fraction.tif',recorded_irrigation,profile,'HYDE/LUH historical irrigation before conditional inference')
    write(out/'inferred_cultivated_water_fraction.tif',inferred_water,profile,'Additional water-access request on existing cultivated land; subject to river budget')
    la['inferred_cultivated_water_requested_ha']=float(np.sum(np.where(domain,inferred_water,0)*area)*100)
    la['inferred_cultivated_water_note']='Already cultivated; no viable listed rainfed crop; inside low-lift command. Inferred access, not observed irrigation. Same monthly river limits, no new land.'
    log('Reallocating shared river water for seasonal crop-service requirements')
    served,full,winf,wa=allocate_irrigation(root,cfg,domain,np.where(diagnostics['refinement_flags']==3,diagnostics['baseline_crop'],crop),start,maximum,irr,area,out)
    max_land=np.maximum(maximum,full)
    dry_gain=np.maximum(rf-livelihood,0)
    water_gain=np.maximum(ir-np.maximum(rf,livelihood),0)
    base=b*diagnostics['baseline_rf']+(1-b)*livelihood
    from .land_accounting import baseline_management
    current_management,maximum_management,base_irrigation_current,base_irrigation_max=baseline_management(b,historical_cultivated,served,full,diagnostics['baseline_rf'],rf,ir,livelihood)
    current=base+np.maximum(start-b,0)*dry_gain+served*water_gain+current_management+base_irrigation_current
    upper=base+np.maximum(max_land-b,0)*dry_gain+full*water_gain+maximum_management+base_irrigation_max
    alternative_gain,alternative_displaced=alternative_contributions(historical_cultivated,served,full,rf,ir,livelihood,alternative,alternative_share)
    current+=alternative_gain;upper+=alternative_gain-alternative_displaced
    if not np.all(upper[domain]+1e-6>=current[domain]):raise ValueError('Grid capacity order failure')
    # Eligibility identifies output gaps; population is still absent at this stage.
    from .location_geometry import overlap_matrix
    from .location_inventory import read_zone_inventory
    from .terrestrial_completion import estimate
    from .environmental_transfer import climate_layers
    log('Checking ownable locations for coarse terrestrial-model gaps')
    weights,ga=overlap_matrix(root,inventory,out)
    zones=read_zone_inventory(raw).set_index('location_tag')
    ownable=inventory.location_tag.map(zones.is_ownable).to_numpy(bool)
    _,nearest=distance_transform_edt(~domain,return_indices=True)
    nearest_flat=np.ravel_multi_index(tuple(nearest),domain.shape)
    mapped_current=np.where(domain,current,current.ravel()[nearest_flat])
    before=np.asarray(weights@mapped_current.ravel()).ravel()*100
    zero=ownable&(before<=0)
    columns=np.unique(weights[zero].indices)
    target=np.zeros(domain.size,dtype=bool)
    sources=np.where(domain.ravel()[columns],columns,nearest_flat.ravel()[columns])
    target[sources]=True
    target=target.reshape(domain.shape)
    eco,_=read(food/'food_ecoregion.tif')
    rc=json.loads((root/'configs/food_systems.json').read_text())
    climate=climate_layers(root,rc['climate_transfer'],profile)
    livelihood,completed,completion_records=estimate(livelihood,domain,target,climate,eco,food_type,profile,cfg['zero_support_completion'])
    dry_gain=np.maximum(rf-livelihood,0)
    water_gain=np.maximum(ir-np.maximum(rf,livelihood),0)
    base=b*diagnostics['baseline_rf']+(1-b)*livelihood
    from .land_accounting import baseline_management
    current_management,maximum_management,base_irrigation_current,base_irrigation_max=baseline_management(b,historical_cultivated,served,full,diagnostics['baseline_rf'],rf,ir,livelihood)
    current=base+np.maximum(start-b,0)*dry_gain+served*water_gain+current_management+base_irrigation_current
    upper=base+np.maximum(max_land-b,0)*dry_gain+full*water_gain+maximum_management+base_irrigation_max
    alternative_gain,alternative_displaced=alternative_contributions(historical_cultivated,served,full,rf,ir,livelihood,alternative,alternative_share)
    current+=alternative_gain;upper+=alternative_gain-alternative_displaced
    reference=np.maximum(reference,livelihood)
    mapped_completion=np.where(domain,completed,completed.ravel()[nearest_flat])
    write(out/'terrestrial_completion.tif',mapped_completion.astype(float),profile,'1 if explicit terrestrial analogue replaces unsupported ownable-location source cell')
    completion_audit={'previously_zero_ownable_locations':inventory.loc[zero,'location_tag'].tolist(),
        'source_cells_completed':len(completion_records),'fish_included':False,'population_used':False,
        'method':cfg['zero_support_completion'],'cells':completion_records}
    write_json(out/'terrestrial_completion.json',completion_audit)
    arrays={'baseline_support_per_land_ha':base,'starting_support_per_land_ha':current,'maximum_support_per_land_ha':upper,'reference_people_per_effective_ha':reference,
       'baseline_crop_fraction':b,'starting_crop_fraction':start,'maximum_crop_fraction':max_land,'historical_irrigated_fraction':irr,'starting_served_fraction':served,'maximum_served_fraction':full}
    from .improvement_audit import decompose,CAPACITY_COLUMNS,validate_components,reconcile_rounding
    components=decompose(b,start,max_land,served,full,rf,ir,livelihood,diagnostics['low_rf'])
    components['starting_management_capacity']+=current_management
    components['remaining_management_capacity']+=maximum_management-current_management
    components['starting_irrigation_capacity']+=base_irrigation_current
    components['remaining_irrigation_capacity']+=base_irrigation_max-base_irrigation_current
    components['starting_management_capacity']+=alternative_gain
    components['remaining_irrigation_capacity']-=alternative_displaced
    arrays.update(components)
    arrays['dry_field_alternative_support']=alternative_gain
    arrays['inferred_cultivated_water_fraction']=inferred_water
    arrays['dry_field_alternative_fraction']=np.where(alternative>np.maximum(rf,livelihood),np.maximum(historical_cultivated-served,0)*alternative_share,0)
    arrays['water_dependent_cultivation_fraction']=np.where((rf<=1e-6)&(ir>1e-6),start,0)
    arrays['unserved_historical_irrigation_fraction']=np.maximum(irr-served,0)
    arrays['unserved_water_opportunity_fraction']=np.maximum(read(out/'water_candidate_fraction.tif')[0]-full,0)
    arrays.update({k:diagnostics[k] for k in ['rainfed_headroom','rotation_fraction','crop_candidate','pastoral']})
    arrays['china_refinement_fraction']=(diagnostics['refinement_flags']==1).astype(float)
    arrays['andes_refinement_fraction']=np.isin(diagnostics['refinement_flags'],[2,3]).astype(float)
    arrays['prairie_refinement_fraction']=read(out/'prairie_access_refined.tif')[0]
    arrays['improvement_reference_refinement_fraction']=read(out/'improvement_reference_refined.tif')[0]
    arrays['management_envelope_refinement_fraction']=read(out/'management_envelope_refined.tif')[0]
    arrays['cultivated_system_refinement_fraction']=(system_flags>0).astype(float)
    from .agricultural_game_calibration import apply as apply_game_calibration
    arrays=apply_game_calibration(root,cfg,arrays,historical_cultivated,food_type,domain,out)
    write_json(out/'regional_refinement.json',diagnostics['refinement_audit'])
    # Game coastlines and tiny islands do not match real raster masks exactly.
    # Full-grid completion is a labelled nearest terrestrial analogue, never omission.
    _,nearest=distance_transform_edt(~domain,return_indices=True)
    evidence_inferred=yinf|linf|winf|completed
    grid_reports={}
    for name,a in arrays.items():
        finite=np.isfinite(a)&domain
        if not np.all(finite[domain]):
            a,missing=fill_nearest(a,finite);evidence_inferred|=domain&missing
        a=np.where(domain,a,a[tuple(nearest)]).astype(np.float32)
        arrays[name]=a
        unit='fraction' if (name.endswith('fraction') or name in ['crop_candidate','pastoral']) else 'people per effective hectare'
        if 'support' in name or name.endswith('_capacity') or name=='rainfed_headroom':
            unit='game capacity per reference land hectare' if cfg.get('agricultural_game_calibration') and not name.startswith(('uncalibrated_','inherited_physical_')) and name!='rainfed_headroom' else 'physical food-support people per land hectare'
        write(out/(name+'.tif'),a,profile,unit,{'completion':'Outside source land uses flagged nearest terrestrial analogue for game-coastline registration only'})
        grid_reports[name]={'min':float(a[domain].min()),'max':float(a[domain].max())}
    eco,_=read(food/'food_ecoregion.tif')
    write(out/'inference.tif',np.where(domain,evidence_inferred,True).astype(float),profile,'1 if any inferred input or coastline transfer')
    write(out/'coastline_transfer.tif',(~domain).astype(float),profile,'1 if outside original terrestrial mask')
    from .location_geometry import overlap_matrix
    log('Aggregating exact registered game-pixel/grid-cell overlaps')
    area_ha=np.asarray(weights.sum(axis=1)).ravel()*100
    totals={k:np.asarray(weights@v.ravel()).ravel()*100 for k,v in arrays.items()}
    ref=totals['reference_people_per_effective_ha']/area_ha
    vals=normalize_support(totals['baseline_support_per_land_ha'],totals['starting_support_per_land_ha'],totals['maximum_support_per_land_ha'],ref,cfg['multiplier_floor'],cfg.get('multiplier_ceiling'))
    d=inventory[['location_tag','location_id','map_color_rgb','province','region','super_region','macro_region','calibrated_lon','calibrated_lat','centroid_x','centroid_y']].copy()
    for name,a in zip(FIELDS,vals):d[name]=a
    d['unbounded_reference_multiplier']=ref
    d['multiplier_bound_status']=np.where(ref<cfg['multiplier_floor'],'lower',np.where(ref>cfg.get('multiplier_ceiling',float('inf')),'upper','unchanged'))
    d['inert_capacity']=totals['baseline_support_per_land_ha'];d['starting_capacity']=totals['starting_support_per_land_ha'];d['maximum_capacity']=totals['maximum_support_per_land_ha']
    d['starting_improvement_capacity']=d.starting_capacity-d.inert_capacity
    d['remaining_improvement_effective_cropland']=d.maximum_improvement_effective_cropland-d.starting_improvement_effective_cropland
    d['remaining_capacity']=d.maximum_capacity-d.starting_capacity
    d['dry_field_alternative_capacity']=totals['dry_field_alternative_support']
    d['dry_field_alternative_ha']=totals['dry_field_alternative_fraction']
    d['inferred_cultivated_water_requested_ha']=totals['inferred_cultivated_water_fraction']
    if cfg.get('agricultural_game_calibration'):
        for field,grid in [('game_conversion_added_capacity','game_conversion_added_support'),('game_inheritance_capacity','game_inheritance_support'),('game_base_added_capacity','game_base_added_support'),('game_inheritance_removed_capacity','game_inheritance_removed_support'),('uncalibrated_base_capacity','uncalibrated_base_support'),('uncalibrated_starting_capacity','uncalibrated_starting_support'),('uncalibrated_maximum_capacity','uncalibrated_maximum_support')]:d[field]=totals[grid]
        d['game_inheritance_activation_share']=totals['game_inheritance_activation_fraction']/area_ha
        d['source_starting_crop_ha']=totals['source_starting_crop_fraction']
        d['source_starting_served_ha']=totals['source_starting_served_fraction']
    for name in CAPACITY_COLUMNS:d[name]=totals[name]
    for rule in ['china','andes','prairie','improvement_reference','management_envelope','cultivated_system']:d[rule+'_refinement_share']=totals[rule+'_refinement_fraction']/area_ha
    for name in ['water_dependent_cultivation','unserved_historical_irrigation','unserved_water_opportunity']:
        d[name+'_ha']=totals[name+'_fraction']
    d['crop_candidate_area_ha']=totals['crop_candidate']
    d['rotation_active_area_equivalent_ha']=totals['rotation_fraction']
    d['pastoral_area_ha']=totals['pastoral']
    d['rainfed_management_headroom_people_per_crop_ha']=np.divide(totals['rainfed_headroom'],totals['crop_candidate'],out=np.zeros(len(d)),where=totals['crop_candidate']>0)
    d['physical_location_ha']=area_ha
    for name in ['baseline_crop_fraction','starting_crop_fraction','maximum_crop_fraction','historical_irrigated_fraction','starting_served_fraction','maximum_served_fraction']:
        d[name.replace('_fraction','_ha')]=totals[name]
    d['inferred_area_share']=np.clip(np.asarray(weights@np.where(domain,evidence_inferred,True).ravel()).ravel()*100/area_ha,0,1)
    d['coastline_transfer_share']=np.clip(np.asarray(weights@(~domain).ravel()).ravel()*100/area_ha,0,1)
    d['evidence_status']=np.where(d.coastline_transfer_share>.1,'low: substantial coastline analogue','inferred: shared physical and historical-system rules')
    d['terrestrial_analogue_share']=np.clip(np.asarray(weights@mapped_completion.ravel()).ravel()*100/area_ha,0,1)
    d.loc[d.terrestrial_analogue_share>0,'evidence_status']='low: explicit terrestrial analogue for coarse-model zero support'
    d['source_rule']='iteration01:grid_food+HYDE_LUH+PNV_terrain+seasonal_basin_water'
    for rule in ['china','andes','prairie','improvement_reference','management_envelope','cultivated_system']:
        d.loc[d[rule+'_refinement_share']>0,'source_rule']+='+refinement:'+rule
        d.loc[d[rule+'_refinement_share']>0,'evidence_status']='inferred: source-guided '+rule+' refinement; numerical assumptions uncertain'
    d.loc[d.terrestrial_analogue_share>0,'source_rule']+='+terrestrial_analogue'
    d.loc[d.dry_field_alternative_ha>0,'source_rule']+='+inferred_dry_field_alternative'
    d.loc[d.dry_field_alternative_ha>0,'evidence_status']='inferred: historically listed alternative on otherwise unsupported cultivated dry fields'
    d.loc[d.inferred_cultivated_water_requested_ha>0,'source_rule']+='+inferred_cultivated_water_access'
    if cfg.get('agricultural_game_calibration'):
        d['source_rule']+='+shared_game_support_conversion+historical_system_inheritance'
        d['evidence_status']='game calibrated; historical agricultural-system and extent priors; physical food estimates retained separately'
    repaired=d.loc[zero,['location_tag','starting_capacity','maximum_capacity','capacity_multiplier','terrestrial_analogue_share']].copy()
    repaired['previous_starting_capacity']=before[zero]
    repaired.to_csv(out/'repaired_settlements.csv',index=False,float_format='%.15g')
    d['zero_support_reason']=np.where(d.starting_capacity==0,'No modeled terrestrial support after explicit crop and FORGE estimates; aquatic contribution excluded','not_zero')
    # Population is joined only after all model values have been computed.
    ranks=pd.read_csv(raw/'starting_population_source.csv',usecols=['location_tag','starting_location_rank'],keep_default_na=False).set_index('location_tag')['starting_location_rank']
    d['starting_location_rank']=d.location_tag.map(ranks).fillna('unknown')
    d['settlement_context']=np.where(d.starting_location_rank.isin(['town','city','megalopolis']),'urban',np.where(d.starting_location_rank.isin(['rural_or_unranked','rural_settlement']),'rural_or_unranked','unknown'))
    pop=pd.read_csv(raw/'starting_population_source.csv',usecols=['location_tag','eu5_start_population'],keep_default_na=False)
    pop['eu5_start_population']=pd.to_numeric(pop.eu5_start_population,errors='coerce')
    if pop.location_tag.duplicated().any():raise ValueError('Duplicate contextual population')
    d=d.merge(pop,on='location_tag',how='left',validate='one_to_one')
    d['starting_fill']=np.divide(d.eu5_start_population,d.starting_capacity,out=np.full(len(d),np.nan),where=d.starting_capacity>0)
    d['starting_density_people_km2']=d.starting_capacity/(area_ha/100)
    d['maximum_density_people_km2']=d.maximum_capacity/(area_ha/100)
    d['maximum_starting_ratio']=np.divide(d.maximum_capacity,d.starting_capacity,out=np.full(len(d),np.nan),where=d.starting_capacity>0)
    # First-iteration uncertainty bands, not statistical confidence intervals.
    for col in ['inert_capacity','starting_capacity','maximum_capacity']:
        d[col+'_low']=d[col]*(1-cfg['land_uncertainty_fraction'])*(1-cfg['yield_uncertainty_fraction'])
        d[col+'_high']=d[col]*(1+cfg['land_uncertainty_fraction'])*(1+cfg['yield_uncertainty_fraction'])
    from .location_inventory import complete_zones,audit_settlement_values
    d,delivery_inventory,inventory_audit=complete_zones(d,raw,out)
    checks=validate_frame(d,delivery_inventory)
    d=reconcile_rounding(d)
    checks['improvement_components']=validate_components(d)
    settlement=audit_settlement_values(d,delivery_inventory)
    write_json(out/'settlement_validation.json',settlement)
    pd.DataFrame(settlement['issues'],columns=['location_tag','issues','starting_population','starting_capacity','maximum_capacity','reason']).to_csv(out/'unresolved_settlements.csv',index=False)
    if not settlement['passed']:raise ValueError('Ownable settlement support gate failed; see settlement_validation.json')
    d.to_parquet(out/'locations.parquet',index=False)
    d.to_csv(out/'locations.csv',index=False,float_format='%.15g')
    roundtrip=pd.read_csv(out/'locations.csv',keep_default_na=False);validate_frame(roundtrip,delivery_inventory)
    d[['location_tag','starting_capacity']].rename(columns={'starting_capacity':'population_capacity'}).to_csv(out/'population_capacity.csv',index=False,float_format='%.15g')
    d[['location_tag']+FIELDS+['source_rule','evidence_status','inferred_area_share','coastline_transfer_share']].to_csv(out/'location_values.csv',index=False,float_format='%.15g')
    for group in ['province','region','super_region','macro_region']:
        table=d.groupby(group,dropna=False).agg(locations=('location_tag','size'),population=('eu5_start_population','sum'),starting_capacity=('starting_capacity','sum'),maximum_capacity=('maximum_capacity','sum'),inert_capacity=('inert_capacity','sum'),area_ha=('physical_location_ha','sum'),multiplier_median=('capacity_multiplier','median'),capacity_min=('starting_capacity','min'),capacity_max=('starting_capacity','max'),capacity_median=('starting_capacity','median'))
        table.to_csv(out/(group+'_summary.csv'))
    # Parameter sensitivities retain the same evidence, allocation and location geometry.
    sensitivity=[]
    for scale in [.75,1,1.25]:
        s=d.starting_capacity*scale;mx=d.maximum_capacity*scale
        sensitivity.append({'yield_scale':scale,'starting_total':float(s.sum()),'maximum_total':float(mx.sum()),'locations_below_context_population':int(np.sum(s<d.eu5_start_population))})
    write_json(out/'sensitivity.json',{'status':'First-pass yield sensitivity; land-access uncertainty bands are scenario brackets, not probability intervals. Basin allocations unchanged.','comparisons':sensitivity})
    quantiles={k:d.loc[d.modelled_land,k].quantile([0,.1,.5,.9,.99,1]).to_dict() for k in FIELDS+['starting_capacity','maximum_capacity','starting_fill']}
    audit={'iteration':cfg['iteration'],'engineering_pass':True,'iteration_complete':True,'scientific_acceptance':False,'location_count':len(d),'inventory':inventory_audit,'settlement_readiness':settlement,'terrestrial_completion':{k:v for k,v in completion_audit.items() if k!='cells'},'checks':checks,'zero_starting_capacity_locations':int(((d.starting_capacity==0)&d.modelled_land).sum()),'population_context_missing_locations':int((d.eu5_start_population.isna()&d.modelled_land).sum()),'below_starting_population_locations':int((d.starting_capacity<d.eu5_start_population).sum()),'total_starting_capacity':float(d.starting_capacity.sum()),'total_maximum_capacity':float(d.maximum_capacity.sum()),'total_context_population':float(d.eu5_start_population.sum()),'substantial_coastline_transfer_locations':int((d.coastline_transfer_share>.1).sum()),'quantiles':quantiles,'geometry':ga,'yield':ya,'land':la,'water':wa,'grid':grid_reports,
       'limitations':['Complete inferred iteration, not historically accepted balance.','Modern climate and runoff proxies; dated cropland evidence around 1300 compared to cached EU5 1337 population.','Shared access/clearing fractions and crop-season water demand are explicit priors, not surveyed hectares.','Drainage/flood protection beyond reconstructed cropland and retained crop-system effectiveness are not independently identified.','No separate improvement-building counts; no game export or deployment.','Aquatic food excluded; existing noncrop terrestrial transfers remain low-confidence.','No per-location population fitting or area-compression coefficient. Large physical locations can have large support.']}
    audit['game_calibration_applied']=bool(cfg.get('agricultural_game_calibration'))
    if audit['game_calibration_applied']:
        audit['limitations'].insert(0,'Main capacities use an explicit nonlinear game conversion and inferred starting-infrastructure scenario; they are not physical calorie-derived population limits. Raw food estimates are retained separately.')
    write_json(out/'validation.json',audit)
    # Manifest binds code, imported sources and supporting native-grid products.
    log('Hashing complete iteration and rendering location map')
    fingerprint,inputs=source_fingerprint(root,config_path,food,water)
    from .location_reporting import report
    report(out,d,raw,cfg,audit,fingerprint)
    outputs={str(f.relative_to(out)):digest(f) for f in out.iterdir() if f.is_file() and f.name not in ['manifest.json','overlap.npz','overlap_manifest.json','delivery_checks.json','viewer_syntax.js']}
    write_json(out/'manifest.json',{'schema':1,'iteration':cfg['iteration'],'fingerprint':fingerprint,'config':cfg,'inputs':inputs,'outputs':outputs,'completion':audit['iteration_complete'],'scientific_acceptance':False})
    return {k:audit[k] for k in ['iteration','engineering_pass','iteration_complete','scientific_acceptance','location_count','zero_starting_capacity_locations','below_starting_population_locations','total_starting_capacity','total_maximum_capacity']}
