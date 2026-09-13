import numpy as np
from historical_agriculture.dry_field_alternatives import choose,contributions,infer_water


def test_preference_before_yield_and_missing_not_zero():
    values=np.array([[1,0,np.nan,5],[20,2,0,100.]])
    ranks=np.array([[0,0,0,100],[1,1,1,100]])
    assert choose(values,ranks).tolist()==[0,1,-1,-1]


def test_land_and_food_competition_across_water_states():
    # 1 cultivated hectare, .2 already irrigated; original dry=0, wet=4,
    # wild=.1, alternative dry=2. Full irrigation must replace alternative.
    current,displaced=contributions(1,.2,1,0,4,.1,2)
    assert np.isclose(current,.8*1.9)
    assert np.isclose(displaced,current)
    old_start=.1+.2*3.9;old_max=.1+3.9
    assert np.isclose(old_start+current,.2*4+.8*2)
    assert np.isclose(old_max+current-displaced,4)


def test_better_dry_crop_is_retained_without_extra_irrigation_gain():
    gain,displaced=contributions(1,0,1,0,1,.1,2)
    assert np.isclose(gain,1.9) and np.isclose(displaced,.9)
    assert np.isclose(.1+.9+gain-displaced,2)


def test_no_gain_on_served_or_uncultivated_land_and_share_sensitivity():
    assert contributions(0,0,1,0,4,0,2)==(0,0)
    assert contributions(1,1,1,0,4,0,2)==(0,0)
    a,b=contributions(1,0,.5,0,4,0,2,.5)
    assert a==1 and b==1


def test_inferred_water_requires_existing_land_command_and_no_dry_alternative():
    cultivated=np.array([.5,.5,0,.5,.5,.5])
    recorded=np.array([.1,0,0,0,0,.1])
    command=np.array([.4,.4,.4,0,.4,.4])
    rf=np.array([0,1,0,0,0,0])
    alt=np.array([0,0,0,0,1,0])
    got=infer_water(cultivated,recorded,command,rf,np.ones(6),alt,.5)
    assert np.allclose(got,[.25,0,0,0,0,.25])
    assert np.all(got<=cultivated) and np.all(got>=recorded)
