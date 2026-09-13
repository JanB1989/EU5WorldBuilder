import pandas as pd
from historical_agriculture.rural_pressure import summaries

def test_rank_not_population_defines_urban_and_rural_province_budgets():
    d=pd.DataFrame({'location_tag':['a','b','c','d','e'],'is_ownable':[True,True,True,True,False], 'starting_location_rank':['town','rural_or_unranked','rural_settlement','unknown','rural_settlement'],'province':['p']*5,'region':['r']*5,'eu5_start_population':[10,1000,20,50,99999], 'starting_capacity':[0,100,1000,1,0],'maximum_capacity':[0,200,1000,1,0]})
    rows,p,r,s=summaries(d)
    assert s['urban']==1 and s['urban_over_start']==1
    assert s['rural_or_unranked']==2 and s['rural_over_start']==1
    assert s['unknown']==1 and s['ownable']==4
    assert p.iloc[0].capacity==1100 and p.iloc[0].population==1020
    assert p.iloc[0].category=='within_start'


def test_report_roundtrip_preserves_literal_nan_location_tag(tmp_path):
    from historical_agriculture.rural_pressure import report
    import json
    raw=tmp_path/'data/raw/location_inputs';raw.mkdir(parents=True)
    archive=tmp_path/'data/processed/rural_round_before';archive.mkdir(parents=True)
    out=tmp_path/'output';out.mkdir()
    d=pd.DataFrame({'location_tag':['nan','sea'],'is_ownable':[True,False], 'starting_location_rank':['rural_or_unranked','unknown'],'province':['p',''],'region':['r',''],'eu5_start_population':[100.,float('nan')], 'starting_capacity':[200.,0.],'maximum_capacity':[300.,0.],'management_envelope_refinement_share':[0.,0.],'base_land_floor_added_capacity':[0.,0.]})
    d.drop(columns=['starting_location_rank']).to_csv(archive/'locations_equal_area.csv',index=False)
    d[['location_tag','starting_location_rank']].to_csv(raw/'starting_population_source.csv',index=False)
    report(tmp_path,out,d,'test-fingerprint')
    result=json.loads((out/'rural_pressure.json').read_text())
    assert result['before']['rural_or_unranked']==1
    assert result['before']==result['after']
