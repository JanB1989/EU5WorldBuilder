import numpy as np
from historical_agriculture.land_accounting import baseline_management


def support(b,h,served,full):
    low=np.array(1.);managed=np.array(3.);wet=np.array(5.);wild=np.array(.1)
    c,m,ci,mi=baseline_management(b,h,served,full,low,managed,wet,wild)
    base=b*low+(1-b)*wild
    return base+(h-b)*2.9+served*2+c+ci,base+(.8-b)*2.9+full*2+m+mi


def test_changing_natural_partition_cannot_change_yield_of_same_historical_fields():
    a=support(.1,.4,.2,.4);b=support(.3,.4,.2,.4)
    assert np.allclose(a,b)
    assert np.isclose(a[0],.4*3+.6*.1+.2*2)
    assert np.isclose(a[1],.8*3+.2*.1+.4*2)


def test_no_management_granted_to_uncultivated_baseline_at_start():
    c,m,_,_=baseline_management(.2,0,0,0,np.array(1.),np.array(3.),np.array(5.),np.array(.1))
    assert c==0 and m==.4


def test_irrigation_does_not_claim_gain_already_in_better_baseline():
    _,_,c,m=baseline_management(.2,.2,.1,.2,np.array(4.),np.array(3.),np.array(5.),np.array(.1))
    assert np.isclose(.1*2+c,.1)
    assert np.isclose(.2*2+m,.2)
