"""Evidence-guided regional changes on native pixels; no population inputs."""
import copy,json
import numpy as np
from netCDF4 import Dataset,num2date
from .raster import read
from .accounting import annual_food
from .provenance import digest

def settings(root,cfg):
    if not cfg.get('refinement_config'):return None
    c=json.loads((root/cfg['refinement_config']).read_text())
    for key,value in c['sensitivity'][cfg.get('refinement_variant','central')].items():
        group,name=key.split('_',1);c[group][name]=value
    return c

def relief(root,cfg,profile):
    import rasterio
    from rasterio.warp import reproject,Resampling
    source=root/cfg['input_directory']/'hydrology/ETOPO_2022_v1_60s_N90W180_surface.tif'
    shape=(profile['height'],profile['width']);lo=np.full(shape,np.nan,dtype=np.float32);hi=lo.copy()
    with rasterio.open(source) as ds:
        for a,method in [(lo,Resampling.min),(hi,Resampling.max)]:
            reproject(rasterio.band(ds,1),a,src_transform=ds.transform,src_crs=ds.crs,dst_transform=profile['transform'],dst_crs=profile['crs'],resampling=method,dst_nodata=np.nan)
    return np.maximum(hi-lo,0)

def china_mask(c,eco,crop,elevation,relief_m,cropland,wet_rice_code):
    return np.isin(eco,c['ecoregion_ids'])&(crop==wet_rice_code)&np.isfinite(elevation)&(elevation<=c['maximum_elevation_m'])&np.isfinite(relief_m)&(relief_m<=c['maximum_relief_m'])&np.isfinite(cropland)&(cropland>=c['minimum_reconstructed_cropland_fraction'])

def andes_mask(c,eco,crop,elevation,maize_code,potato_upper):
    return np.isin(eco,c['ecoregion_ids'])&(crop==maize_code)&np.isfinite(elevation)&(elevation>=c['minimum_elevation_m'])&(elevation<=c['maximum_elevation_m'])&np.isfinite(potato_upper)&(potato_upper>0)

def coldfield_mask(c,eco,elevation,relief_m,cropland,potato_upper):
    return np.isin(eco,c['ecoregion_ids'])&np.isfinite(elevation)&(elevation>=c['minimum_elevation_m'])&(elevation<=c['maximum_elevation_m'])&np.isfinite(relief_m)&(relief_m<=c['maximum_relief_m'])&np.isfinite(cropland)&(cropland>=c['minimum_cropland_fraction'])&np.isfinite(potato_upper)&(potato_upper==0)

def prairie_access(c,eco,group,terrain,river_km,b,rf):
    eligible=np.isin(eco,c['ecoregion_ids'])&np.isin(group,[1,2])&(rf>0)
    distance=np.where(np.isfinite(river_km),np.maximum(river_km,0),np.inf)
    fraction=c['upland_access_fraction']+(c['river_access_fraction']-c['upland_access_fraction'])*np.exp(-distance/c['river_decay_km'])
    revised=np.where(eligible,np.minimum(b,fraction*terrain),b)
    return revised,eligible&(revised<b)

def apply_food(root,cfg,rc,domain,profile,eco,crop,rf,ir,low_rf,headroom,fraction,freq,position,fill):
    c=settings(root,cfg)
    baseline_rf=rf.copy();baseline_crop=crop.copy();flags=np.zeros(crop.shape,dtype=np.uint8)
    if c is None:return crop,rf,ir,low_rf,headroom,fraction,baseline_rf,baseline_crop,flags,{}
    for source in json.loads((root/'evidence/location_refinements.json').read_text())['sources']:
        if digest(root/source['path'])!=source['sha256']:raise ValueError('Changed refinement source: '+source['id'])
    from .water import wc,area_grid
    elevation=wc(root/'data/raw/water','elev');relief_m=relief(root,cfg,profile)
    with Dataset(root/cfg['input_directory']/'hyde/cropland.nc') as ds:
        dates=num2date(ds['time'][:],ds['time'].units,ds['time'].calendar)
        indices=[i for i,t in enumerate(dates) if t.year==cfg['evidence_year']]
        if len(indices)!=1:raise ValueError('Refinement HYDE date missing')
        extent=ds['cropland'][indices[0]].filled(np.nan)/area_grid()
    # No source-free assignments: missing extent cannot qualify for the Chinese rule.
    chi=domain&china_mask(c['china'],eco,crop,elevation,relief_m,extent,rc['crop_order'].index('RCW')+1)
    potato_upper,_=read(root/cfg['food_directory']/'crops/WPO_upper.tif')
    ande=domain&andes_mask(c['andes'],eco,crop,elevation,rc['crop_order'].index('MZE')+1,potato_upper)
    # Require a complete observed model triplet before replacing a viable crop.
    for name in ['lower','high_rainfed','high_irrigated']:
        a,_=read(root/cfg['food_directory']/f'crops/WPO_{name}.tif');ande &= np.isfinite(a)
    crop[ande]=rc['crop_order'].index('WPO')+1
    position=position.copy();freq=freq.copy();fraction=fraction.copy()
    position[chi]=c['china']['position'];fraction[chi]=c['china']['rotation_fraction'];freq[chi]=c['china']['harvests']
    flags[chi]=1;flags[ande]=2
    for code,mask in [('RCW',chi),('WPO',ande)]:
        if not mask.any():continue
        values=[]
        for suffix in ['lower','high_rainfed','high_irrigated']:
            a,_=read(root/cfg['food_directory']/f'crops/{code}_{suffix}.tif');values.append(fill(a)[0][mask])
        lo,hr,hi=values;p=position[mask];f=fraction[mask];h=freq[mask];cr=rc['crops'][code]
        from .management_envelope import yields as management_yields
        dry,wet=management_yields(lo,hr,hi,p)
        food=lambda value:annual_food(value,cr,h,f)[2]/(2500*365)
        rf[mask]=food(dry);ir[mask]=food(wet);low_rf[mask]=food(lo);headroom[mask]=np.maximum(food(hr)-food(dry),0)
    cold=domain&coldfield_mask(c['coldfields'],eco,elevation,relief_m,extent,potato_upper)
    if cold.any():
        cr=rc['crops']['WPO'];f=c['coldfields']['active_rotation_fraction'];h=c['coldfields']['harvests']
        density=annual_food(c['coldfields']['fresh_potato_kg_per_harvest']*cr['dry_fraction'],cr,h,f)[2]/(2500*365)
        crop[cold]=rc['crop_order'].index('WPO')+1
        rf[cold]=density;ir[cold]=density;low_rf[cold]=0.;headroom[cold]=0.;fraction[cold]=f;flags[cold]=3
    audit={'coldfield_cells':int(cold.sum()),'variant':cfg.get('refinement_variant','central'),'china_cells':int(chi.sum()),'andes_crop_cells':int(ande.sum()),'base_food_density_preserved':True,'parameters':c,'limitations':['Terrain and crop masks identify analogues, not surveyed medieval field systems.','Andean terraces are not assigned invented hectares; reconstructed cultivation remains the land evidence.']}
    return crop,rf,ir,low_rf,headroom,fraction,baseline_rf,baseline_crop,flags,audit


def conditional_reference(reference, domain, eco, crop, low, high_rainfed, high_irrigated, c, crop_config, management):
    """Change game-unit productivity only; do not mutate livelihood or food accounts."""
    complete=np.isfinite(low)&np.isfinite(high_rainfed)&np.isfinite(high_irrigated)
    eligible=domain&np.isin(eco,c['ecoregion_ids'])&(crop==0)&complete
    p=management['position']
    from .management_envelope import yields as management_yields
    dry,wet=management_yields(low,high_rainfed,high_irrigated,p)
    density=annual_food(np.maximum(dry,wet),crop_config,management['harvests'],management['cultivated_fraction'])[2]/(2500*365)
    changed=eligible&np.isfinite(density)&(density>reference)&(density>0)
    return np.where(changed,density,reference),changed


def apply_reference(root,cfg,rc,domain,eco,crop,reference):
    c=settings(root,cfg)
    if c is None or 'improvement_reference' not in c:return reference,np.zeros(domain.shape,dtype=bool)
    c=c['improvement_reference'];code=c['crop']
    values=[read(root/cfg['food_directory']/f'crops/{code}_{suffix}.tif')[0] for suffix in ['lower','high_rainfed','high_irrigated']]
    return conditional_reference(reference,domain,eco,crop,*values,c,rc['crops'][code],rc['management'][c['management']])
