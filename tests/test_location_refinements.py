import numpy as np
import pytest
from historical_agriculture.location_refinements import china_mask,andes_mask,prairie_access
from historical_agriculture.location_area import equal_area


def test_china_requires_correct_system_crop_cultivation_and_lowland():
    c={'ecoregion_ids':[236],'maximum_elevation_m':400,'maximum_relief_m':100,'minimum_reconstructed_cropland_fraction':.01}
    eco=np.array([236,237,236,236,236,236,236]);crop=np.array([7,7,8,7,7,7,7])
    elevation=np.array([30,30,30,500,30,30,30]);relief=np.array([20,20,20,20,200,20,20]);extent=np.array([.1,.1,.1,.1,.1,0,np.nan])
    assert china_mask(c,eco,crop,elevation,relief,extent,7).tolist()==[True,False,False,False,False,False,False]


def test_andes_altitude_preference_requires_viable_potato_and_existing_maize():
    c={'ecoregion_ids':[444],'minimum_elevation_m':3300,'maximum_elevation_m':3800}
    assert andes_mask(c,np.array([444]*6+[500]),np.array([6,6,6,6,13,6,6]),np.array([3500,3000,4000,3500,3500,3500,3500]),6,np.array([1,1,1,0,1,np.nan,1])).tolist()==[True,False,False,False,False,False,False]


def test_prairie_keeps_river_advantage_and_does_not_change_other_systems():
    c={'ecoregion_ids':[388],'upland_access_fraction':.015,'river_access_fraction':.05,'river_decay_km':2}
    b=np.full(5,.15)
    revised,changed=prairie_access(c,np.array([388,388,388,400,388]),np.array([2,2,2,2,0]),np.ones(5),np.array([0,10,np.nan,0,0]),b,np.ones(5))
    assert revised[0]==pytest.approx(.05)
    assert .015<revised[1]<.016
    assert revised[2]==.015
    assert revised[3]==revised[4]==.15
    current=np.array([.2,.03,.002,.2,.2])
    starting=np.maximum(revised,current)
    assert np.all(starting>=current)
    assert changed.tolist()==[True,True,True,False,False]


def test_equal_area_fixed_reference_has_no_cross_region_compensation():
    import pandas as pd
    d=pd.DataFrame({'modelled_land':[True,True], 'physical_location_ha':[100.,200.], 'starting_capacity':[100.,200.], 'maximum_capacity':[300.,600.], 'eu5_start_population':[0.,0.]})
    first,_=equal_area(d,150)
    d.loc[0,'starting_capacity']=50
    second,meta=equal_area(d,150)
    assert first.loc[1,'starting_capacity']==second.loc[1,'starting_capacity']
    assert first.loc[0,'starting_capacity']==2*second.loc[0,'starting_capacity']
    assert meta['reference_is_fixed']
    with pytest.raises(ValueError,match='reference'):equal_area(d,0)


def test_cold_field_analogue_needs_dated_cultivation_and_zero_standard_crop():
    from historical_agriculture.location_refinements import coldfield_mask
    c={'ecoregion_ids':[588,589],'minimum_elevation_m':3800,'maximum_elevation_m':4200,'maximum_relief_m':100,'minimum_cropland_fraction':.001}
    e=np.array([588,588,588,588,588,588,500]);alt=np.array([3900,4500,3900,3900,3900,3900,3900]);r=np.array([30,30,200,30,30,30,30]);a=np.array([.01,.01,.01,0,.01,.01,.01]);y=np.array([0,0,0,0,10,np.nan,0])
    assert coldfield_mask(c,e,alt,r,a,y).tolist()==[True,False,False,False,False,False,False]


def test_inherited_prairie_cultivation_reclassification_preserves_total_support():
    b=np.array([.05,.015]);cultivated=np.array([.01,.03]);maximum=np.array([.5,.5]);yield_net=4.;wild=.2
    start=np.maximum(b,cultivated)
    original_base=b*yield_net+(1-b)*wild
    original_start=original_base+(start-b)*(yield_net-wild)
    original_max=original_base+(maximum-b)*(yield_net-wild)
    new_b=b-np.minimum(b,cultivated)
    new_base=new_b*yield_net+(1-new_b)*wild
    np.testing.assert_allclose(new_base+(start-new_b)*(yield_net-wild),original_start)
    np.testing.assert_allclose(new_base+(maximum-new_b)*(yield_net-wild),original_max)
    assert np.all(start-new_b>0)


def test_conditional_reference_separates_opportunity_from_historical_livelihood():
    from historical_agriculture.location_refinements import conditional_reference
    from historical_agriculture.location_model import normalize_support
    c={'ecoregion_ids':[396]}
    cr={'dry_fraction':1.,'kcal_kg':3500.,'recovery':1.,'seed_share':.05,'loss_share':.1}
    m={'position':.45,'harvests':1.,'cultivated_fraction':.5}
    ref=np.full(7,.001);eco=np.array([396,397,396,396,396,396,396]);crop=np.array([0,0,6,0,0,0,0]);domain=np.array([1,1,1,1,1,0,1],dtype=bool)
    lo=np.array([100,100,100,np.nan,0,100,0]);hi=np.array([3000,3000,3000,3000,0,3000,0])
    revised,changed=conditional_reference(ref,domain,eco,crop,lo,hi,hi,c,cr,m)
    assert changed.tolist()==[True,False,False,False,False,False,False]
    assert revised[0]>.25
    assert np.all(ref==.001)
    base=np.full(7,100.);start=np.full(7,150.);maximum=np.full(7,300.)
    b,mult,i,mx=normalize_support(base,start,maximum,revised,.25,5)
    np.testing.assert_allclose(b*mult,base)
    np.testing.assert_allclose((b+i)*mult,start)
    np.testing.assert_allclose((b+mx)*mult,maximum)
