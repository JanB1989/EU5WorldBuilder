"""One-time, hash-pinned import of evidence caches and licensed local game geometry."""
import argparse, json, shutil
from pathlib import Path
from historical_agriculture.provenance import digest, write_json

def main():
    a=argparse.ArgumentParser()
    a.add_argument('--constructor-data',type=Path,required=True)
    a.add_argument('--hyde',type=Path,required=True)
    a.add_argument('--game-map',type=Path,required=True)
    args=a.parse_args(); root=Path(__file__).resolve().parents[1]
    dest=root/'data/raw/location_inputs';dest.mkdir(parents=True,exist_ok=True)
    items=[
      (args.game_map.parent/'default.map','game_default.map','Local game zone classification; no redistribution'),
      (args.game_map.parent/'location_templates.txt','game_templates.txt','Local game template inventory; no redistribution'),
      (args.game_map.parent/'named_locations/00_default.txt','game_named_locations.txt','Local game RGB identifier mapping; no redistribution'),
      (args.game_map,'locations.png','EU5 local licensed installation; no redistribution'),
      (args.constructor_data/'geometry_land_contract_candidate_v1/location_geometry_candidate.parquet','inventory.parquet','Local game inventory; extraction snapshot, no capacity assignments imported'),
      (args.constructor_data/'geometry_land_contract_candidate_v1/coordinate_transform_candidate.json','transform.json','Existing robust map registration; approximate geographic reconstruction'),
      (args.constructor_data/'current_capacity_map/starting_population_locations.csv','starting_population_source.csv','Cached game starting population; contextual only'),
      (args.constructor_data/'landcover_sources/luh2/states_1300_v2.npz','luh1300.npz','LUH2 v2h, https://luh.umd.edu/LUH2/LUH2_v2h/states.nc; HYDE-related evidence family'),
      (args.constructor_data/'landcover_sources/sage_pnv/vegtype_5min.nc','pnv.nc','SAGE potential vegetation, https://sage-public-files.s3.amazonaws.com/global-potential-vegetation/potveg_nc.tar.gz; source attribution required'),
      (args.constructor_data/'landcover_sources/sage_pnv/README','pnv_README','Source legend and methodology'),
      (args.constructor_data/'landcover_sources/landcover_source_manifest.json','landcover_provenance.json','Preserved upstream extraction metadata'),
      (args.hyde/'cropland.nc','hyde/cropland.nc','HYDE cached April 2025; embedded 3.4 versus cache 3.5 disagreement; embedded CC BY 3.0'),
      (args.hyde/'total_irrigated.nc','hyde/total_irrigated.nc','Same HYDE evidence family, https://doi.org/10.5194/essd-9-927-2017 methodology'),
      (args.hyde/'definitions.md','hyde/definitions.md','Preserve disputed source version labelling'),
      (args.constructor_data/'hydrology_alignment/river_reaches.parquet','hydrology/river_reaches.parquet','HydroATLAS 1.0 source geometry/attributes, https://www.hydrosheds.org/hydroatlas; CC BY 4.0'),
      (args.constructor_data/'hydrology_sources/hydrology/GRUN_v1_GSWP3_WGS84_05_1902_2014.nc','hydrology/GRUN_v1_GSWP3_WGS84_05_1902_2014.nc','GRUN v1, https://doi.org/10.5194/essd-11-1655-2019; original licensing retained, cache not redistributed'),
      (args.constructor_data/'hydrology_sources/hydrology/ETOPO_2022_v1_60s_N90W180_surface.tif','hydrology/ETOPO_2022_v1_60s_N90W180_surface.tif','NOAA ETOPO 2022, https://www.ncei.noaa.gov/products/etopo-global-relief-model; attribution'),
    ]
    receipts=[]
    for src,name,role in items:
        dst=dest/name;dst.parent.mkdir(parents=True,exist_ok=True)
        sha=digest(src)
        if not dst.exists() or digest(dst)!=sha:shutil.copyfile(src,dst)
        if digest(dst)!=sha:raise ValueError('Import checksum mismatch: '+name)
        receipts.append({'path':str(dst.relative_to(root)),'sha256':sha,'bytes':dst.stat().st_size,'origin':str(src),'role':role})
        print('Imported '+name,flush=True)
    write_json(root/'evidence/location_input_manifest.json',{'schema':1,'role':'Pinned imported source pack; no sibling runtime dependence. Source origins are provenance, not runtime paths.','sources':receipts})
    cfg=json.loads((root/'configs/water.json').read_text())
    cfg['hyde_directory']='data/raw/location_inputs/hyde'
    cfg['hydrology_directory']='data/raw/location_inputs/hydrology'
    cfg['river_cache']='data/raw/location_inputs/hydrology/river_reaches.parquet'
    write_json(root/'configs/water.json',cfg)
if __name__=='__main__':main()
