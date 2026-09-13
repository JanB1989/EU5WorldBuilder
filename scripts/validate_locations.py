"""Independent delivery validation, including stale-input and map coverage gates."""
from pathlib import Path
import argparse,json
import numpy as np
import pandas as pd
from historical_agriculture.location_model import validate_frame,source_fingerprint,FIELDS
from historical_agriculture.location_inventory import read_zone_inventory,audit_settlement_values
from historical_agriculture.provenance import digest,write_json

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('artifacts/locations'));parser.add_argument('--config',type=Path,default=Path('configs/locations.json'));args=parser.parse_args()
    root=Path.cwd();out=args.output;cfg=json.loads(args.config.read_text());manifest=json.loads((out/'manifest.json').read_text())
    fp,_=source_fingerprint(root,args.config.resolve(),root/cfg['food_directory'],root/cfg['water_directory'])
    if fp!=manifest['fingerprint']:raise ValueError('Stale inputs or code: rebuild locations')
    for name,sha in manifest['outputs'].items():
        if digest(out/name)!=sha:raise ValueError('Changed artifact: '+name)
    d=pd.read_csv(out/'locations.csv',keep_default_na=False)
    for k in FIELDS+['inert_capacity','starting_capacity','maximum_capacity','remaining_improvement_effective_cropland']:d[k]=pd.to_numeric(d[k],errors='raise')
    inv=read_zone_inventory(root/cfg['input_directory']);checks=validate_frame(d,inv)
    settlement=audit_settlement_values(d,inv)
    equal=pd.read_csv(out/'locations_equal_area.csv',keep_default_na=False)
    validate_frame(equal,inv)
    equal_settlement=audit_settlement_values(equal,inv)
    if (equal.loc[equal.is_ownable,'base_effective_cropland']<cfg.get('equal_area_base_land_floor',0)-1e-9).any():raise ValueError('Base land below configured floor')
    from historical_agriculture.location_area import equal_area
    expected,_=equal_area(pd.read_csv(out/'locations.csv'),cfg.get('equal_reference_area_ha'),cfg.get('equal_area_base_land_floor',0))
    for col in FIELDS+['starting_capacity','maximum_capacity','base_land_floor_added_capacity']:
        if not np.allclose(equal[col],expected[col],rtol=1e-12,atol=1e-8):raise ValueError('Equal-area/floor calculation mismatch: '+col)
    from historical_agriculture.improvement_audit import validate_components
    validate_components(d);validate_components(equal)
    from historical_agriculture.improvement_distribution import allocate, FIELDS as distribution_fields
    for mode, version in [('physical', d), ('equal_area', equal)]:
        distribution=pd.read_csv(out/f'improvement_distribution_{mode}.csv',keep_default_na=False)
        expected_distribution=allocate(version)
        if distribution.location_tag.tolist()!=version.location_tag.tolist():
            raise ValueError('Improvement distribution inventory mismatch')
        for col in distribution_fields:
            if col.endswith('_status'):
                passed=distribution[col].equals(expected_distribution[col])
            else:
                passed=np.allclose(distribution[col],expected_distribution[col],rtol=1e-12,atol=1e-8)
            if not passed:raise ValueError('Improvement distribution mismatch: '+col)
    from historical_agriculture.water_management import validate as validate_water, KINDS as WATER_KINDS
    validate_water(equal)
    for stage in ('starting','maximum'):
        for kind in WATER_KINDS:
            if not (out/f'{stage}_{kind}_improvement_capacity_equal.png').is_file():
                raise ValueError('Missing required water map: '+stage+' '+kind)
    for version in [d,equal]:
        own=version.loc[version.is_ownable,'capacity_multiplier'].to_numpy(float)
        if np.any(own<cfg['multiplier_floor']) or np.any(own>cfg['multiplier_ceiling']):
            raise ValueError('Ownable multiplier outside configured bounds')
    coverage=json.loads((out/'map_coverage.json').read_text())
    if coverage['native_locations']!=len(inv):raise ValueError('Map missing locations')
    if coverage['ownable_locations']!=int(inv.is_ownable.sum()) or coverage['native_missing_ownable'] or coverage['overview_missing_ownable']:
        raise ValueError('Map missing ownable locations')
    budget=np.load(out/'water_accounts.npz');down=budget['downstream'];outlets=np.flatnonzero(down<0)
    water_cfg=json.loads((root/'configs/water.json').read_text());reserve=water_cfg['irrigation']['protected_runoff_fraction']
    residuals={}
    for mode in ['historical','maximum']:
        residual=budget['runoff_m3'].sum(axis=1)*(1-reserve)-budget[mode+'_withdrawal_m3'].sum(axis=1)-budget[mode+'_losses_m3'].sum(axis=1)-budget[mode+'_outflow_m3'][:,outlets].sum(axis=1)
        residuals[mode]=float(np.max(np.abs(residual)))
        if residuals[mode]>1:raise ValueError('Water budget does not reconcile')
    # Partial ledgers, null values, changed maps or stale fingerprints cannot certify completion.
    result={'pass':settlement['passed'] and equal_settlement['passed'],'structural_pass':True,'settlement_readiness':settlement,'equal_area_unresolved_settlements':equal_settlement['unresolved_ownable_locations'],'location_count':len(d),'checks':checks,'native_map_coverage':coverage['native_locations'],'water_residual_m3':residuals,'fingerprint':fp}
    write_json(out/'delivery_checks.json',result);print(json.dumps({**result,'settlement_readiness':{k:v for k,v in settlement.items() if k!='issues'}},indent=2))
    if not result['pass']:raise SystemExit(1)
if __name__=='__main__':main()
