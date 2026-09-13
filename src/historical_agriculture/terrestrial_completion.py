"""Explicit terrestrial analogues for ownable locations lost by coarse food models.

No fish, population floors, new cropland or water allocations are introduced.
The donor distribution, not an epsilon capacity, determines inferred support.
"""
import numpy as np
from scipy.spatial import cKDTree
from .environmental_transfer import sphere

def estimate(values, domain, targets, climate, ecoregion, food, profile, cfg):
    values=np.asarray(values);result=values.copy()
    targets=np.asarray(targets,bool)&domain&(values<=0)
    if np.any(targets&(food==24)):
        raise ValueError("Ownable settlement maps to explicit polar ice; repair geometry")
    records=[]
    if not targets.any():return result,targets,records
    h,w=values.shape
    flat=np.arange(h*w).reshape(h,w)
    def coordinates(ids):
        return (profile['transform'].c+(ids%w+.5)*profile['transform'].a,
                profile['transform'].f+(ids//w+.5)*profile['transform'].e)
    # Livestock and terrestrial foraging use different resource pools.
    pastoral=np.isin(food,[19,20,23])
    eco=np.where(np.isfinite(ecoregion),ecoregion,-1).astype(int).ravel()
    features=climate.reshape(-1,climate.shape[-1])
    scales=np.asarray(cfg['climate_scales'],float)
    for system in [False,True]:
        selected=targets&(pastoral==system)
        if not selected.any():continue
        valid=domain&(pastoral==system)&(food!=24)&np.isfinite(values)&(values>0)&np.isfinite(climate).all(axis=-1)
        positive=values[valid]
        if not len(positive):raise ValueError("No comparable terrestrial donor pool")
        # Discard near-zero interpolation tails; this is a donor-quality filter,
        # not a lower bound applied to a location's capacity.
        threshold=float(np.quantile(positive,cfg['donor_lower_quantile']))
        valid &= values>=threshold
        donor_ids=flat[valid];donor_values=values.ravel()[donor_ids]
        target_ids=flat[selected]
        dx,dy=coordinates(donor_ids);tx,ty=coordinates(target_ids)
        donor_geo=sphere(dx,dy)
        target_geo=sphere(tx,ty)
        donor_climate=features[donor_ids]
        target_climate=features[target_ids].copy()
        missing=~np.isfinite(target_climate).all(axis=1)
        climate_donor=np.full(len(target_ids),-1,dtype=int)
        if missing.any():
            _,ix=cKDTree(donor_geo).query(target_geo[missing])
            target_climate[missing]=donor_climate[ix]
            climate_donor[missing]=donor_ids[ix]
        donor_features=np.column_stack([donor_geo/cfg['distance_scale_km'],donor_climate/scales])
        target_features=np.column_stack([target_geo/cfg['distance_scale_km'],target_climate/scales])
        global_tree=cKDTree(donor_features)
        for ec in np.unique(eco[target_ids]):
            t=np.flatnonzero(eco[target_ids]==ec)
            pool=np.flatnonzero(eco[donor_ids]==ec) if ec>=0 else np.array([],dtype=int)
            local=len(pool)>=cfg['neighbours']
            if not local:pool=np.arange(len(donor_ids))
            tree=cKDTree(donor_features[pool]) if local else global_tree
            k=min(cfg['neighbours'],len(pool))
            _,indices=tree.query(target_features[t],k=k)
            indices=np.asarray(indices).reshape(len(t),k)
            picked=pool[indices]
            estimates=np.quantile(donor_values[picked],cfg['estimate_quantile'],axis=1)
            result.ravel()[target_ids[t]]=estimates
            for j,index in enumerate(t):
                donors=donor_ids[picked[j]]
                records.append({
                    "cell":int(target_ids[index]),"longitude":float(tx[index]),"latitude":float(ty[index]),
                    "ecoregion":int(ec),"system":"pastoral" if system else "terrestrial_foraging",
                    "match":"same_ecoregion_and_climate" if local else "same_livelihood_climate_analogue",
                    "climate_inferred":bool(missing[index]),"climate_donor_cell":int(climate_donor[index]),
                    "donor_cells":[int(x) for x in donors],
                    "donor_support":[float(x) for x in donor_values[picked[j]]],
                    "donor_quality_threshold":threshold,
                    "max_donor_distance_km":float(np.linalg.norm(donor_geo[picked[j]]-target_geo[index],axis=1).max()),
                    "support_people_per_ha":float(result.ravel()[target_ids[index]]),
                    "status":"inferred low-confidence terrestrial analogue; not measured historical capacity"})
    if not np.all(np.isfinite(result[targets])&(result[targets]>0)):
        raise ValueError("Incomplete terrestrial support estimate")
    return result,targets,records
