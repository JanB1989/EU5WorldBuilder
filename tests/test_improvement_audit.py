import numpy as np
import pandas as pd
import pytest
from historical_agriculture.improvement_audit import decompose,validate_components,CAPACITY_COLUMNS
from historical_agriculture.location_area import equal_area


def test_sequential_components_reconcile_and_displace_livelihoods():
    b=.1;start=.4;maximum=.8;served=.2;full=.5;rf=4.;ir=6.;wild=1.;low=2.
    x=decompose(b,start,maximum,served,full,rf,ir,wild,low)
    assert x['starting_clearing_capacity']==pytest.approx(.3)
    assert x['starting_management_capacity']==pytest.approx(.6)
    assert x['starting_irrigation_capacity']==pytest.approx(.4)
    base=b*rf+(1-b)*wild
    current=base+(start-b)*(rf-wild)+served*(ir-rf)
    maximum_support=base+(maximum-b)*(rf-wild)+full*(ir-rf)
    assert sum(x[k] for k in CAPACITY_COLUMNS[:3])+base==pytest.approx(current)
    assert sum(x[k] for k in CAPACITY_COLUMNS[3:])==pytest.approx(maximum_support-current)


def test_reversed_management_is_visible_not_clipped_into_extra_support():
    x=decompose(0.,1.,1.,0.,0.,2.,2.,0.,4.)
    assert x['starting_management_capacity']==-2
    assert sum(x[k] for k in CAPACITY_COLUMNS[:3])==2


def test_clearing_cannot_claim_displaced_wild_resources_twice():
    x=decompose(0.,.5,1.,.5,1.,1.,5.,3.,.5)
    assert x['starting_clearing_capacity']==0
    assert x['starting_management_capacity']==0
    assert x['starting_irrigation_capacity']==1


def test_full_vectorized_accounting_and_equal_area_components():
    rng=np.random.default_rng(73);n=100
    b=rng.uniform(0,.1,n);start=rng.uniform(.1,.3,n);maximum=rng.uniform(.3,1,n)
    served=start*.2;full=maximum*.4;rf=rng.uniform(0,5,n);ir=rf+rng.uniform(0,5,n);wild=rng.uniform(0,1,n);low=rng.uniform(0,5,n)
    parts=decompose(b,start,maximum,served,full,rf,ir,wild,low)
    base=b*rf+(1-b)*wild
    current=base+(start-b)*np.maximum(rf-wild,0)+served*np.maximum(ir-np.maximum(rf,wild),0)
    upper=base+(maximum-b)*np.maximum(rf-wild,0)+full*np.maximum(ir-np.maximum(rf,wild),0)
    d=pd.DataFrame(parts|dict(inert_capacity=base,starting_capacity=current,maximum_capacity=upper,starting_improvement_capacity=current-base,remaining_capacity=upper-current,modelled_land=True,physical_location_ha=rng.uniform(10,1000,n),eu5_start_population=0))
    assert validate_components(d)
    e,_=equal_area(d);assert validate_components(e)
    e.loc[0,'starting_irrigation_capacity']+=1
    with pytest.raises(ValueError,match='reconciliation'):validate_components(e)


def test_raster_cancellation_is_traced_and_large_errors_are_rejected():
    from historical_agriculture.improvement_audit import reconcile_rounding
    d=pd.DataFrame({c:[0.] for c in CAPACITY_COLUMNS})
    d['inert_capacity']=78000.;d['starting_capacity']=78003.;d['maximum_capacity']=78003.
    d['starting_improvement_capacity']=3.;d['remaining_capacity']=0.
    d['starting_clearing_capacity']=3.0002
    reconcile_rounding(d)
    assert d.starting_component_rounding_capacity.iloc[0]==pytest.approx(-.0002)
    assert validate_components(d)
    d.starting_clearing_capacity=10.
    with pytest.raises(ValueError,match='precision'):reconcile_rounding(d)
