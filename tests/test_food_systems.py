import json
import numpy as np
import pandas as pd
import pytest
from historical_agriculture.food_systems import people_from_kcal, bounded_fill, benchmark_people
from historical_agriculture.accounting import annual_food

def test_one_person_year_energy_and_no_area_argument():
    np.testing.assert_allclose(people_from_kcal([0,912500,1825000]),[0,1,2])
    assert np.isnan(people_from_kcal(np.nan))
    with pytest.raises(ValueError):people_from_kcal(1,0)

def test_geometry_fill_bounded_and_zero_is_known():
    source=np.array([[0.,np.nan,np.nan,np.nan,8.]])
    filled,flag=bounded_fill(source,1)
    assert filled[0,1]==0 and filled[0,3]==8
    assert np.isnan(filled[0,2])
    assert flag.sum()==2

def test_rotation_and_multiple_cropping_have_matching_person_units():
    crop={'dry_fraction':1,'recovery':1,'kcal_kg':3650,'seed_share':0,'loss_share':0}
    assert people_from_kcal(annual_food(250,crop,1,1)[2])==1
    assert people_from_kcal(annual_food(250,crop,1,.5)[2])==.5
    assert people_from_kcal(annual_food(250,crop,2,1)[2])==2

def test_graph_conversion_uses_benchmark_rotation_not_global_prior(tmp_path):
    (tmp_path/'configs').mkdir();(tmp_path/'evidence').mkdir();out=tmp_path/'out';out.mkdir()
    (tmp_path/'configs/food_systems.json').write_text(json.dumps({'daily_kcal_per_person':2500,'days_per_year':365}))
    pd.DataFrame([{'region':'A','cropping_coefficient':2}]).to_csv(tmp_path/'evidence/benchmarks_1300.csv',index=False)
    pd.DataFrame([{'region':'A','crop':'WHE','valid':True,'result':'inside','lower':125,'upper':500,'observed':250,'observed_low':200,'observed_high':300}]).to_csv(out/'benchmark_comparison.csv',index=False)
    crop={'dry_fraction':1,'recovery':1,'kcal_kg':3650,'seed_share':0,'loss_share':0}
    row=benchmark_people(tmp_path,{'crops':{'WHE':crop}},out)[0]
    assert row['lower']==1 and row['upper']==4 and row['observed']==2
    assert row['observed_low']==1.6 and row['observed_high']==2.4

def test_coastal_rule_names_are_coastal_not_interior_canada():
    from pathlib import Path
    root=Path(__file__).parents[1]
    cfg=json.loads((root/'configs/food_systems.json').read_text())
    assert 349 in cfg['coastal_ecoregions']
    assert not set([353,374,376,377,378,379,381]) & set(cfg['coastal_ecoregions'])
    assert cfg['forge']['energy_mj_per_kg_dm']==9.8
    assert cfg['forge']['grazer_mass_kg']==180


def test_proxy_chart_preserves_wheat_observation_and_raw_invalidity(tmp_path):
    import rasterio
    from rasterio.transform import from_origin
    (tmp_path/'configs').mkdir();(tmp_path/'evidence').mkdir()
    out=tmp_path/'out';(out/'crops').mkdir(parents=True)
    (tmp_path/'configs/food_systems.json').write_text(json.dumps({'daily_kcal_per_person':2500,'days_per_year':365}))
    (tmp_path/'configs/benchmark_proxies.json').write_text(json.dumps({'proxies':{'A':{'crop':'SRG','source':'test','reason':'explicit assumption'}}}))
    pd.DataFrame([{'region':'A','cropping_coefficient':.5,'longitude':0,'latitude':0}]).to_csv(tmp_path/'evidence/benchmarks_1300.csv',index=False)
    pd.DataFrame([{'region':'A','crop':'WHE','valid':False,'result':'unresolved','lower':np.nan,'upper':np.nan,'observed':2000,'observed_low':1800,'observed_high':2200}]).to_csv(out/'benchmark_comparison.csv',index=False)
    for name,value in [('lower',100),('upper',200)]:
        with rasterio.open(out/'crops'/f'SRG_{name}.tif','w',driver='GTiff',height=2,width=2,count=1,dtype='float32',crs='EPSG:4326',transform=from_origin(-1,1,1,1),nodata=-9999) as ds:
            ds.write(np.full((2,2),value,dtype='float32'),1)
    wheat={'dry_fraction':1,'recovery':1,'kcal_kg':3650,'seed_share':0,'loss_share':0}
    sorghum=dict(wheat,kcal_kg=1825)
    row=benchmark_people(tmp_path,{'crops':{'WHE':wheat,'SRG':sorghum}},out)[0]
    assert row['valid'] and row['assumed'] and not row['source_comparison_valid']
    assert row['crop']=='WHE' and row['range_crop']=='SRG'
    assert row['lower']==.1 and row['upper']==.2
    assert row['observed']==4  # original wheat conversion, outside proxy; never clipped
    assert row['proxy_cells']==121
