"""Final game-unit area comparison; physical accounts stay untouched."""
import numpy as np

ABSOLUTES = [
    "base_effective_cropland", "starting_improvement_effective_cropland",
    "maximum_improvement_effective_cropland", "remaining_improvement_effective_cropland",
    "inert_capacity", "starting_improvement_capacity", "starting_capacity",
    "maximum_capacity", "remaining_capacity",
]

def equal_area(d):
    """Normalize density to one reference area while preserving global starting support."""
    land=d.modelled_land.astype(bool)
    area=d.physical_location_ha.to_numpy(float)
    if np.any(~np.isfinite(area[land]) | (area[land]<=0)):
        raise ValueError("Modelled land requires positive finite physical area")
    start=d.starting_capacity.to_numpy(float)
    density_sum=np.sum(start[land]/area[land])
    if not np.isfinite(density_sum) or density_sum<=0:
        raise ValueError("Positive starting support required for normalization")
    reference=float(np.sum(start[land])/density_sum)
    scale=np.ones(len(d))
    scale[land]=reference/area[land]
    result=d.copy()
    for name in ABSOLUTES + [c for c in d if c.endswith(("_capacity_low","_capacity_high"))]:
        if name in result:result[name]=result[name]*scale
    result["starting_fill"]=np.divide(result.eu5_start_population, result.starting_capacity,
        out=np.full(len(d),np.nan),where=result.starting_capacity>0)
    # These are game support densities after rescaling, not changed physical productivity.
    for prefix in ["starting","maximum"]:
        result[prefix+"_density_people_km2"]=np.divide(result[prefix+"_capacity"],area/100,
            out=np.full(len(d),np.nan),where=np.isfinite(area)&(area>0))
    result["area_comparison_factor"]=scale
    result["area_mode"]="equal_reference_area"
    meta={"mode":"equal_reference_area","reference_area_ha":reference,
        "normalization":"Same global starting capacity as physical-area version; no population inputs.",
        "starting_total":float(result.starting_capacity.sum()),
        "maximum_total":float(result.maximum_capacity.sum()),
        "physical_starting_total":float(d.starting_capacity.sum()),
        "physical_maximum_total":float(d.maximum_capacity.sum()),
        "limitations":"Final game-unit comparison only. Physical hectares and water accounts remain unchanged. More location subdivisions produce more combined game capacity."}
    return result,meta
