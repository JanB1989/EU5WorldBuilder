import pandas as pd
from historical_agriculture.evidence import anchor_cropping

def test_historical_anchor_does_not_double_discount_kansai():
    rows=pd.DataFrame([
        {'NGA':'Kansai','Variable':'Cropping System Coefficient','Date.From':710,'Date.To':1150,'Value.From':'1'},
        {'NGA':'Kansai','Variable':'Cropping System Coefficient','Date.From':1150,'Date.To':1900,'Value.From':'2'},
        {'NGA':'Kansai','Variable':'Historical Productivity','Date.From':1100,'Date.To':1300,'Value.From':'1.3'}])
    year,factor=anchor_cropping(rows,'Kansai')
    assert year==1200 and factor==2
    assert 1.3*factor/2==1.3

def test_modern_anchor_forces_at_least_continuous_cropping():
    rows=pd.DataFrame([{'NGA':'upland','Variable':'Cropping System Coefficient','Date.From':-2650,'Date.To':1941,'Value.From':'.375'}])
    assert anchor_cropping(rows,'upland')==(2000,1.)
