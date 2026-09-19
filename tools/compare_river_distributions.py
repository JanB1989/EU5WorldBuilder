"""Compare vanilla engine levels with the current marker-aware game-map export.

Run from the repository root: uv run python tools/compare_river_distributions.py
"""
import hashlib
import json
from pathlib import Path

import pandas as pd


def main():
    paths = {
        'vanilla': Path('artifacts/rivers/locations.csv'),
        'current': Path('artifacts/river_network/location_levels.csv'),
        'geography': Path('data/raw/location_inputs/inventory.parquet'),
        'export_manifest': Path('artifacts/river_network/export_manifest.json'),
        'vanilla_report': Path('artifacts/rivers/report.json'),
    }
    # "nan" is a real location tag; pandas' default NA conversion loses its join.
    old = pd.read_csv(paths['vanilla'], keep_default_na=False)
    new = pd.read_csv(paths['current'], keep_default_na=False)
    geo = pd.read_parquet(paths['geography'])
    for d in [old, new, geo]:
        assert not d.location_tag.duplicated().any()
    assert set(old.location_tag) == set(new.location_tag)
    joined = old[['location_tag','is_ownable','river_level']].merge(
        new[['location_tag','is_ownable','marker_aware_predicted_level','intended_river_level']],
        on='location_tag',validate='one_to_one',suffixes=('_vanilla','_current'))
    assert joined.is_ownable_vanilla.equals(joined.is_ownable_current)
    joined = joined[joined.is_ownable_vanilla].merge(
        geo[['location_tag','super_region','macro_region']],
        how='left',on='location_tag',validate='one_to_one')
    assert joined[['super_region','macro_region']].notna().all().all()
    assert len(joined)==int(old.is_ownable.sum())
    assert joined[['river_level','marker_aware_predicted_level','intended_river_level']].isin(range(6)).all().all()
    output=Path('artifacts/river_network/comparison');output.mkdir(parents=True,exist_ok=True)
    joined.to_csv(output/'locations.csv',index=False)
    rows=[]
    for dimension in ['super_region','macro_region']:
        for name,group in [('world',joined),*joined.groupby(dimension)]:
            for scenario,column in [('vanilla','river_level'),('current','marker_aware_predicted_level')]:
                counts=group[column].value_counts().reindex(range(6),fill_value=0)
                for level,count in counts.items():
                    rows.append({'grouping':dimension,'group':name,'scenario':scenario,
                        'ownable_locations':len(group),'level':int(level),'locations':int(count),
                        'percent_of_all_ownable':100*count/len(group),
                        'percent_of_river_locations':100*count/(len(group)-counts[0]) if level>0 and len(group)>counts[0] else None})
    stats=pd.DataFrame(rows);stats.to_csv(output/'distribution.csv',index=False)
    pd.crosstab(joined.river_level,joined.marker_aware_predicted_level).reindex(
        index=range(6),columns=range(6),fill_value=0).to_csv(output/'transitions.csv')
    manifest=json.loads(paths['export_manifest'].read_text())
    png=Path(manifest['output_png'])
    assert hashlib.sha256(png.read_bytes()).hexdigest()==manifest['output_sha256']
    report={'locations':len(joined),'missing_geography':0,'denominator':'ownable locations, equally weighted; includes no river',
        'level':'highest per-location native level; current includes red-marker level-5 promotions',
        'baseline':'verified vanilla EU5 1.3.11 engine export',
        'current':'bitmap-based prediction, not a fresh engine export; rare endpoint exceptions remain possible',
        'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths.values()},
        'current_png_sha256':manifest['output_sha256'],
        'river_coverage':{label:float(joined[col].gt(0).mean()*100) for label,col in [('vanilla','river_level'),('current','marker_aware_predicted_level')]},
        'gained_river':int(((joined.river_level==0)&(joined.marker_aware_predicted_level>0)).sum()),
        'lost_river':int(((joined.river_level>0)&(joined.marker_aware_predicted_level==0)).sum()),
        'current_junction_promoted_locations':int((joined.marker_aware_predicted_level>joined.intended_river_level).sum())}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    lines=['# River distribution: vanilla versus World Builder','','Percent of all ownable locations in each game supercontinent; each location counts once.',
        'Vanilla is engine-exported. Current is the marker-aware bitmap prediction.','','| Supercontinent | Map | Locations | No river | L1 | L2 | L3 | L4 | L5 |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for name in ['world','europe','africa','asia','america','oceania','atlantic_ocean_continent']:
        for scenario in ['vanilla','current']:
            chunk=stats[(stats.grouping=='super_region')&(stats.group==name)&(stats.scenario==scenario)].sort_values('level')
            assert len(chunk)==6
            cells=[f'{v:.1f}%' for v in chunk.percent_of_all_ownable]
            lines.append('| '+ ' | '.join([name,scenario,str(int(chunk.ownable_locations.iloc[0])),*cells])+' |')
    lines+=['','Atlantic contains Bermuda and St Helena. Americas are a single top-level game group; macro-region breakdowns are included in distribution.csv.',
        '',f"Junctions promote {report['current_junction_promoted_locations']:,} ownable locations above their width-based class."]
    (output/'report.md').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines));print(json.dumps(report['river_coverage']))


if __name__=='__main__': main()
