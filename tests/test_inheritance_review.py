import json
import pandas as pd
import pytest
from historical_agriculture.inheritance_review import report


def test_optional_nonsettlement_blanks_are_preserved_but_ownable_missing_fails(tmp_path):
    d=pd.DataFrame({
        'location_tag':['field','sea'],'is_ownable':[True,False],
        'province':['p',''],'region':['r',''],'settlement_context':['rural_or_unranked','nonsettlement'],
        'eu5_start_population':[50,''],'base_effective_cropland':[50,0],
        'capacity_multiplier':[1,1],'maximum_improvement_effective_cropland':[100,0],
        'maximum_capacity':[150,0],'starting_capacity':[100,0],
        'starting_improvement_effective_cropland':[50,0],
        'source_starting_crop_ha':[10,''],'source_starting_served_ha':[1,''],
        'uncalibrated_starting_capacity':[80,''],'physical_location_ha':[100,'']})
    d.to_csv(tmp_path/'before.csv',index=False)
    current=d.copy();current.loc[0,'starting_capacity']=90;current.loc[0,'starting_improvement_effective_cropland']=40
    report(tmp_path,tmp_path,current,{'inheritance_review_baseline':'before.csv'},'test')
    result=json.loads((tmp_path/'inheritance_review.json').read_text())
    assert result['protected_values_unchanged']
    assert result['subsets']['all_ownable']['moved_to_remaining']==10
    current.loc[0,'source_starting_crop_ha']=''
    with pytest.raises(ValueError,match='Missing protected value'):
        report(tmp_path,tmp_path,current,{'inheritance_review_baseline':'before.csv'},'test')
