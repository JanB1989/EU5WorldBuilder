"""Independent, reproducible water report on the native 5-arc-minute grid."""
from pathlib import Path
import hashlib,json,zipfile
import numpy as np
import netCDF4, rasterio, shapefile
from rasterio.features import rasterize
from rasterio.warp import reproject,Resampling
from scipy.ndimage import distance_transform_edt
import pyarrow.parquet as pq
import shapely
from .water_balance import DAYS,reference_et0,bucket,route,topology

SHAPE=(2160,4320)
TRANSFORM=rasterio.transform.from_origin(-180,90,1/12,1/12)
PROFILE=dict(driver='GTiff',height=2160,width=4320,count=1,dtype='float32',crs='EPSG:4326',transform=TRANSFORM,nodata=-9999,compress='deflate',tiled=True)
def log(s):print(s,flush=True)
def digest(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(path,a,descriptions=None):
    a=np.asarray(a);a=a[None] if a.ndim==2 else a
    profile=PROFILE|{'count':len(a)}
    with rasterio.open(path,'w',**profile) as dst:
        dst.write(np.where(np.isfinite(a),a,-9999).astype('float32'))
        if descriptions:
            for i,d in enumerate(descriptions,1):dst.set_band_description(i,d)
def wc(raw,var,m=None):
    name=f'wc2.1_5m_{var}'+(f'_{m+1:02}' if m is not None else '')+'.tif'
    with rasterio.open('/vsizip/'+str((raw/f'wc2.1_5m_{var}.zip').resolve())+'/'+name) as d:
        if d.shape!=SHAPE or not d.transform.almost_equals(TRANSFORM):raise ValueError('Climate grid mismatch')
        return d.read(1,masked=True).astype('float32').filled(np.nan)
def area_grid():
    edges=np.deg2rad(90-np.arange(2161)/12)
    row=6371.0088**2*np.deg2rad(1/12)*(np.sin(edges[:-1])-np.sin(edges[1:]))
    return np.broadcast_to(row[:,None],SHAPE).copy()
def sources(cfg):
    raw=Path(cfg['raw_directory'])
    paths=list(raw.glob('*.zip'))
    paths += [Path(cfg['hyde_directory'])/'total_irrigated.nc',Path(cfg['hyde_directory'])/'cropland.nc',Path(cfg['hydrology_directory'])/'GRUN_v1_GSWP3_WGS84_05_1902_2014.nc',Path(cfg['hydrology_directory'])/'ETOPO_2022_v1_60s_N90W180_surface.tif',Path(cfg['river_cache'])]
    return [{'path':str(p),'sha256':digest(p),'bytes':p.stat().st_size} for p in paths]
def basins(raw,out):
    rows=[];geoms=[]
    for path in sorted(raw.glob('hybas_*_lev06*.zip')):
        with zipfile.ZipFile(path) as z:
            stem=next(n[:-4] for n in z.namelist() if n.endswith('.shp'))
            with shapefile.Reader(shp=z.open(stem+'.shp'),shx=z.open(stem+'.shx'),dbf=z.open(stem+'.dbf')) as r:
                for sr in r.iterShapeRecords():
                    rows.append(sr.record.as_dict());geoms.append(sr.shape.__geo_interface__)
    ids={int(r['HYBAS_ID']):i for i,r in enumerate(rows)}
    down=np.array([ids.get(int(r['NEXT_DOWN']),-1) for r in rows],dtype=np.int32)
    missing=[r['NEXT_DOWN'] for r in rows if r['NEXT_DOWN'] and int(r['NEXT_DOWN']) not in ids]
    if missing:raise ValueError(f'Unresolved downstream basins: {missing[:5]}')
    grid=rasterize(((g,i+1) for i,g in enumerate(geoms)),out_shape=SHAPE,transform=TRANSFORM,fill=0,dtype='int32')-1
    (out/'basins.json').write_text(json.dumps(rows))
    return grid,down,rows

def river_access(cfg,raw,grid,domain,out):
    river=np.zeros(SHAPE,dtype='uint8')
    p=pq.ParquetFile(cfg['river_cache'])
    for b in p.iter_batches(batch_size=150000,columns=['q_mean_m3_s','geometry_wkb']):
        q=np.array(b.column(0));sel=q>=cfg['irrigation']['river_min_mean_m3s']
        w=np.array(b.column(1))[sel]
        if not len(w):continue
        shapes=shapely.from_wkb(w)
        rasterize(((g,1) for g in shapes),out=river,transform=TRANSFORM,all_touched=True)
    log('River corridors rasterized')
    # Topographic screen uses 60-arc-second ETOPO within each 5-minute cell.
    demfile=Path(cfg['hydrology_directory'])/'ETOPO_2022_v1_60s_N90W180_surface.tif'
    with rasterio.open(demfile) as d:
        low=np.full(SHAPE,np.nan,dtype='float32')
        reproject(rasterio.band(d,1),low,src_transform=d.transform,src_crs=d.crs,dst_transform=TRANSFORM,dst_crs='EPSG:4326',resampling=Resampling.min,dst_nodata=np.nan)
        distance,near=distance_transform_edt(river==0,return_indices=True)
        lat=90-(np.arange(2160)+.5)/12
        dy=(np.arange(2160)[:,None]-near[0])*111.195/12
        dx=(np.arange(4320)[None,:]-near[1])*111.195/12*np.cos(np.deg2rad(lat[:,None]))
        km=np.sqrt(dx**2+dy**2)
        source_low=np.maximum(low[tuple(near)],0)
        same_basin=(grid==grid[tuple(near)])&(grid>=0)
        fraction=np.zeros(SHAPE,dtype='float32')
        relief=np.zeros(SHAPE,dtype='float32')
        # 60s pixels align 5x5. Inspect elevation rather than declaring the whole
        # coarse river cell commandable. Tolerance is explicitly a resolution allowance.
        for row in range(0,2160,120):
            h=min(120,2160-row)
            a=d.read(1,window=rasterio.windows.Window(0,row*5,21600,h*5)).astype('float32')
            a=a.reshape(h,5,4320,5).transpose(0,2,1,3)
            eligible=(a>=-10)&(a<=source_low[row:row+h,:,None,None]+cfg['irrigation']['low_lift_m']+cfg['irrigation']['terrain_tolerance_m'])
            fraction[row:row+h]=eligible.mean(axis=(2,3))
            relief[row:row+h]=np.percentile(a,90,axis=(2,3))-np.percentile(a,10,axis=(2,3))
    reach=np.clip(1-km/cfg['irrigation']['reach_distance_km'],0,1)
    fraction*=reach*np.exp(-np.maximum(relief,0)/cfg['irrigation']['relief_taper_m'])*same_basin
    fraction=np.where(domain,fraction,np.nan)
    save(out/'surface_command_fraction.tif',fraction)
    save(out/'river_distance_km.tif',np.where(domain,km,np.nan))
    return fraction

def hyde(cfg,area,out):
    arrays={};metadata={}
    for v in ['total_irrigated','cropland']:
        with netCDF4.Dataset(Path(cfg['hyde_directory'])/(v+'.nc')) as d:
            dates=netCDF4.num2date(d['time'][:],d['time'].units,d['time'].calendar)
            indexes=[i for i,x in enumerate(dates) if x.year==cfg['year']]
            if len(indexes)!=1:raise ValueError('Requested HYDE year not available; no silent interpolation')
            if d[v].shape[1:]!=SHAPE:raise ValueError('HYDE grid mismatch')
            expected=90-(np.arange(2160)+.5)/12
            if not np.allclose(d['lat'][:],expected,atol=.002):raise ValueError('HYDE latitude orientation')
            arrays[v]=d[v][indexes[0]].filled(np.nan)
            metadata[v]={'version_attribute':getattr(d,'version',None),'description':getattr(d,'description',None),'date_created':getattr(d,'date_created',None),'units':d[v].units,'time_index':indexes[0],'year':cfg['year'],'licence':getattr(d,'license',None)}
    # Preserve contradictory source labelling in the manifest, never relabel silently.
    i=arrays['total_irrigated'];c=arrays['cropland']
    metadata['audit']={'irrigated_gt_cropland_cells':int(np.sum(i>c+1e-3)),'irrigated_gt_cell_area_cells':int(np.sum(i>area+1e-3)),'version_note':'Cache definitions.md says HYDE3.5; netCDF metadata says HYDE3.4. Use the exact hashed April 2025 files, with the disagreement recorded.'}
    (out/'hyde_metadata.json').write_text(json.dumps(metadata,indent=2))
    return np.clip(i/area,0,1),np.clip(c/area,0,1)

def runoff(cfg,area,grid,n,valid):
    path=Path(cfg['hydrology_directory'])/'GRUN_v1_GSWP3_WGS84_05_1902_2014.nc'
    with netCDF4.Dataset(path) as d:
        times=netCDF4.num2date(d['time'][:],d['time'].units)
        sel=np.array([cfg['reference']['climate_start']<=x.year<=cfg['reference']['climate_end'] for x in times])
        means=[]
        for m in range(1,13):
            ids=np.where(sel&np.array([x.month==m for x in times]))[0]
            a=d['Runoff'][ids,:,:].mean(axis=0).filled(np.nan)
            if d['Y'][0]<d['Y'][-1]:a=a[::-1]
            # GRUN's 0.5-degree runoff is spatially uniform within its source cell.
            fine=np.repeat(np.repeat(a,6,axis=0),6,axis=1)
            means.append(fine*DAYS[m-1])
    fine=np.stack(means)
    missing=valid&~np.all(np.isfinite(fine),axis=0)
    # Ocean-edge holes only: bounded nearest fill to 0.5deg, report separately.
    for m in range(12):
        known=np.isfinite(fine[m]);dist,idx=distance_transform_edt(~known,return_indices=True)
        fill=~known&(dist<=6)&valid
        fine[m][fill]=fine[m][tuple(idx[:,fill])]
    resolved=valid&np.all(np.isfinite(fine),axis=0)
    volumes=np.stack([np.bincount(grid[resolved],weights=fine[m][resolved]*area[resolved]*1000,minlength=n) for m in range(12)])
    return volumes,{'raw_missing_runoff_cells':int(missing.sum()),'remaining_missing_runoff_cells':int(np.sum(valid&~resolved))},resolved

def execute(config_path,output):
    cfg=json.loads(Path(config_path).read_text());out=Path(output);out.mkdir(parents=True,exist_ok=True);raw=Path(cfg['raw_directory'])
    log('Hashing water sources and configuration')
    receipts=sources(cfg)
    code={p.name:digest(p) for p in Path(__file__).parent.glob('water*.py')}
    fingerprint=hashlib.sha256(json.dumps({'sources':receipts,'config':cfg,'code':code},sort_keys=True).encode()).hexdigest()
    elev=wc(raw,'elev')
    domain=np.isfinite(elev)
    lat=90-(np.arange(2160)+.5)/12
    prec=[];et=[];temp=[]
    for m in range(12):
        lo=wc(raw,'tmin',m);hi=wc(raw,'tmax',m)
        p=wc(raw,'prec',m)
        e=reference_et0(lo,hi,wc(raw,'srad',m),wc(raw,'wind',m),wc(raw,'vapr',m),elev,lat[:,None],m)
        prec.append(p);temp.append((lo+hi)/2);et.append(e)
    prec=np.stack(prec);et=np.stack(et).astype('float32');temp=np.stack(temp)
    domain &=np.all(np.isfinite(prec)&np.isfinite(et)&np.isfinite(temp),axis=0)
    cold=np.max(temp,axis=0)<=0
    valid=domain&~cold
    log(f'Reference balance: {valid.sum():,} climate-covered, seasonally thawing cells')
    b=bucket(np.nan_to_num(prec),np.nan_to_num(et),np.nan_to_num(temp),storage_mm=cfg['reference']['soil_storage_mm'],spinup=cfg['reference']['spinup_years'],snow_threshold=cfg['reference']['snow_threshold_c'],melt_factor=cfg['reference']['snow_melt_mm_per_degree_day'])
    deficit=b['deficit'];area=area_grid()
    valid &= ~b['perennial_snow_accumulation']
    cold |= b['perennial_snow_accumulation']
    log('Preparing catchments and historical irrigation')
    grid,down,rows=basins(raw,out)
    service_grid=grid.copy()
    ids={int(r['HYBAS_ID']):i for i,r in enumerate(rows)}
    connection_counts={}
    for link in cfg.get('historical_connections',[]):
        mask=np.isin(grid,[ids[k] for k in link['recipient_basins']])&(elev<=link['max_elevation_m'])&valid
        service_grid[mask]=ids[link['source_basin']]
        connection_counts[link['id']]=int(mask.sum())
    irr,crop=hyde(cfg,area,out)
    irr=np.where(np.isfinite(irr),irr,0)
    historical_known=np.isfinite(crop)
    log('Screening surface-water access and low-lift terrain')
    command=river_access(cfg,raw,service_grid,valid,out)
    command=np.maximum(np.nan_to_num(command),irr)
    command=np.minimum(command,cfg['irrigation']['maximum_command_fraction'])
    # Three maps have identical land-hectare denominator. Existing irrigated area
    # is retained in the upper infrastructure envelope; its water is still budgeted.
    allocation_domain=valid&(grid>=0)
    q,runoff_audit,resolved=runoff(cfg,area,grid,len(rows),allocation_domain)
    allocation_domain &= resolved
    # Reconcile runoff generation with routed discharge to avoid treating water
    # lost to large floodplains / transmission as unlimited downstream supply.
    target=np.zeros(len(rows))
    for batch in pq.ParquetFile(cfg['river_cache']).iter_batches(batch_size=300000,columns=['q_mean_m3_s','centroid_lon','centroid_lat']):
        means=np.array(batch.column(0));lon=np.array(batch.column(1));latr=np.array(batch.column(2))
        rr=np.clip(((90-latr)*12).astype(int),0,2159);cc=np.clip(((lon+180)*12).astype(int),0,4319)
        indices=grid[rr,cc];ok=(indices>=0)&np.isfinite(means)&(means>=0)
        np.maximum.at(target,indices[ok],means[ok])
    natural_flow=q.copy();survival=np.ones(len(rows))
    for i in topology(down):
        annual=natural_flow[:,i].sum()
        if target[i]>0 and annual>0:survival[i]=min(1.,target[i]*365*86400/annual)
        natural_flow[:,i]*=survival[i]
        if down[i]>=0:natural_flow[:,down[i]]+=natural_flow[:,i]
    eff=cfg['irrigation']['efficiency'];g=service_grid[allocation_domain];a=area[allocation_domain]
    def demands(frac):
        return np.stack([np.bincount(g,weights=deficit[m][allocation_domain]*frac[allocation_domain]*a*1000/eff,minlength=len(rows)) for m in range(12)])
    hist_demand=demands(irr);max_demand=demands(command)
    log('Allocating each monthly river budget upstream to downstream')
    hist=route(q,hist_demand,down,cfg['irrigation']['protected_runoff_fraction'],survival=survival)
    upper=route(q,max_demand,down,cfg['irrigation']['protected_runoff_fraction'],baseline=hist['allocated'],survival=survival)
    # Existing users retain priority even inside a basin, not just between basins.
    delivered_hist=np.zeros_like(deficit);delivered_max=np.zeros_like(deficit)
    for m in range(12):
        rate=np.divide(hist['allocated'][m],hist_demand[m],out=np.zeros(len(rows)),where=hist_demand[m]>0)
        h=deficit[m][allocation_domain]*irr[allocation_domain]*rate[g]
        extension=np.maximum(command[allocation_domain]-irr[allocation_domain],0)
        # First satisfy the original historical demand (including its unmet portion),
        # then allocate the remaining water to extensions.
        maxbase=np.minimum(upper['allocated'][m],hist_demand[m])
        rb=np.divide(maxbase,hist_demand[m],out=np.zeros(len(rows)),where=hist_demand[m]>0)
        extdem=np.maximum(max_demand[m]-hist_demand[m],0)
        re=np.divide(np.maximum(upper['allocated'][m]-maxbase,0),extdem,out=np.zeros(len(rows)),where=extdem>0)
        delivered_hist[m][allocation_domain]=h
        delivered_max[m][allocation_domain]=deficit[m][allocation_domain]*(irr[allocation_domain]*rb[g]+extension*re[g])
    # Unknown irrigation history or absent hydrology stays unknown, not rainfed zero.
    current=np.where((allocation_domain&historical_known)[None],deficit-delivered_hist,np.nan)
    maximum=np.where(allocation_domain[None],deficit-delivered_max,np.nan)
    natural=np.where(valid[None],deficit,np.nan)
    et=np.where(valid[None],et,np.nan)
    for name,arr in [('natural',natural),('historical',current),('maximum',maximum)]:
        save(out/(name+'_monthly_deficit_mm.tif'),arr,[f'month_{m+1}_mm' for m in range(12)])
        save(out/(name+'_annual_deficit_mm.tif'),np.sum(arr,axis=0))
    save(out/'reference_et0_monthly_mm.tif',et)
    save(out/'historical_irrigated_fraction.tif',np.where(valid&historical_known,irr,np.nan))
    save(out/'maximum_irrigation_fraction.tif',np.where(valid,command,np.nan))
    save(out/'domain.tif',np.where(domain,np.where(cold,2,np.where(allocation_domain,1,3)),np.nan))
    save(out/'natural_monthly_eta_mm.tif',np.where(valid[None],b['eta'],np.nan))
    save(out/'natural_monthly_precipitation_mm.tif',np.where(valid[None],prec,np.nan))
    np.savez_compressed(out/'basin_monthly_budget.npz',runoff_m3=q,historical_demand_m3=hist_demand,maximum_demand_m3=max_demand,historical_withdrawal_m3=hist['allocated'],maximum_withdrawal_m3=upper['allocated'],historical_outflow_m3=hist['outflow'],maximum_outflow_m3=upper['outflow'],transmission_survival=survival,riveratlas_target_mean_m3s=target,historical_transmission_loss_m3=hist['transmission_loss'],maximum_transmission_loss_m3=upper['transmission_loss'],downstream=down,basin_ids=np.array([r['HYBAS_ID'] for r in rows]))
    diff=np.nan_to_num(current-maximum)
    audit={'climate_land_cells':int(domain.sum()),'cold_reference_excluded_cells':int((domain&cold).sum()),'natural_cells':int(valid.sum()),'historical_cells':int(np.isfinite(current[0]).sum()),'maximum_cells':int(np.isfinite(maximum[0]).sum()),'basins':len(rows),'source_fingerprint':fingerprint,
    'max_bucket_residual_mm':float(np.max(np.abs(b['residual'][:,valid]))),
    'soil_cycle_error_mm':b['soil_cycle_error_mm'],'historical_connection_cells':connection_counts,'discharge_constrained_basins':int(np.sum(survival<1)),
    'max_routing_residual_m3':float(max(np.max(np.abs(hist['residual'])),np.max(np.abs(upper['residual'])))),
    'maximum_worse_than_historical_cells':int(np.sum(np.any(diff<-.001,axis=0))),
    'historical_withdrawal_km3_year':float(hist['allocated'].sum()/1e9),'maximum_withdrawal_km3_year':float(upper['allocated'].sum()/1e9),
    'historical_demand_met_fraction':float(hist['allocated'].sum()/hist_demand.sum()),
    'maximum_demand_met_fraction':float(upper['allocated'].sum()/max_demand.sum()),
    'annual_reference_demand_mm_quantiles':np.nanquantile(et.sum(axis=0),[0,.5,.95,1]).tolist(),**runoff_audit}
    audit['engineering_pass']=audit['max_bucket_residual_mm']<.001 and audit['soil_cycle_error_mm']<.001 and audit['max_routing_residual_m3']<1 and audit['maximum_worse_than_historical_cells']==0
    audit['scientific_status']='Exploratory surface-water scenario; not validated historical water access or a complete medieval maximum.'
    (out/'validation.json').write_text(json.dumps(audit,indent=2))
    (out/'manifest.json').write_text(json.dumps({'schema':cfg['schema_version'],'fingerprint':fingerprint,'configuration':cfg,'sources':receipts,'code':code},indent=2))
    from .water_reporting import report
    report(out,cfg,audit)
    return audit
