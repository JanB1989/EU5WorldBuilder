"""Final game-unit area comparison; physical accounts stay untouched."""
import numpy as np
from .improvement_audit import CAPACITY_COLUMNS,ROUNDING_COLUMNS

ABSOLUTES = [
    "base_effective_cropland", "starting_improvement_effective_cropland",
    "maximum_improvement_effective_cropland", "remaining_improvement_effective_cropland",
    "inert_capacity", "starting_improvement_capacity", "starting_capacity",
    "maximum_capacity", "remaining_capacity",
]

def equal_area(d,reference_area=None,base_land_floor=0.):
    """Normalize density to one reference area while preserving global starting support."""
    land=d.modelled_land.astype(bool)
    area=d.physical_location_ha.to_numpy(float)
    if np.any(~np.isfinite(area[land]) | (area[land]<=0)):
        raise ValueError("Modelled land requires positive finite physical area")
    start=d.starting_capacity.to_numpy(float)
    density_sum=np.sum(start[land]/area[land])
    if not np.isfinite(density_sum) or density_sum<=0:
        raise ValueError("Positive starting support required for normalization")
    reference=float(np.sum(start[land])/density_sum) if reference_area is None else float(reference_area)
    if not np.isfinite(reference) or reference<=0:raise ValueError('Invalid reference area')
    scale=np.ones(len(d))
    scale[land]=reference/area[land]
    result=d.copy()
    for name in ABSOLUTES + CAPACITY_COLUMNS + ROUNDING_COLUMNS + [c for c in d if c.endswith(("_capacity_low","_capacity_high"))]:
        if name in result:result[name]=result[name]*scale
    if not np.isfinite(base_land_floor) or base_land_floor<0:raise ValueError("Invalid base land floor")
    result["base_land_floor_added_units"]=0.
    result["base_land_floor_added_capacity"]=0.
    if base_land_floor>0:
        own=result.is_ownable.astype(bool)
        added=np.where(own,np.maximum(base_land_floor-result.base_effective_cropland,0),0)
        gain=added*result.capacity_multiplier
        result["base_land_floor_added_units"]=added
        result["base_land_floor_added_capacity"]=gain
        result["base_effective_cropland"]+=added
        for name in ["inert_capacity","starting_capacity","maximum_capacity"]+[c for c in result if c.endswith(("_capacity_low","_capacity_high"))]:
            result[name]+=gain
        result["maximum_starting_ratio"]=result.maximum_capacity/result.starting_capacity.replace(0,np.nan)
    result["starting_fill"]=np.divide(result.eu5_start_population, result.starting_capacity,
        out=np.full(len(d),np.nan),where=result.starting_capacity>0)
    # These are game support densities after rescaling, not changed physical productivity.
    for prefix in ["starting","maximum"]:
        result[prefix+"_density_people_km2"]=np.divide(result[prefix+"_capacity"],area/100,
            out=np.full(len(d),np.nan),where=np.isfinite(area)&(area>0))
    result["area_comparison_factor"]=scale
    result["area_mode"]="equal_reference_area"
    meta={"mode":"equal_reference_area","reference_area_ha":reference,
        "normalization":"Fixed reference area across candidates; no global compensation or population inputs." if reference_area is not None else "Same global starting capacity as physical-area version; no population inputs.",
        "reference_is_fixed":reference_area is not None,
        "base_land_floor":float(base_land_floor),
        "base_land_floor_locations":int((result.base_land_floor_added_units>0).sum()),
        "base_land_floor_added_capacity":float(result.base_land_floor_added_capacity.sum()),
        "starting_total":float(result.starting_capacity.sum()),
        "maximum_total":float(result.maximum_capacity.sum()),
        "physical_starting_total":float(d.starting_capacity.sum()),
        "physical_maximum_total":float(d.maximum_capacity.sum()),
        "limitations":"Final game-unit comparison only. Physical hectares and water accounts remain unchanged. More location subdivisions produce more combined game capacity."}
    return result,meta
