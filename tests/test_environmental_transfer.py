import numpy as np
from historical_agriculture.environmental_transfer import transfer, sphere


def test_constant_fields_and_true_zero_are_preserved():
    xy=sphere(np.array([0.,2.]),np.array([0.,0.]))
    features=np.array([[0.,0.],[1.,1.]])
    values=np.array([[0.,4.],[0.,4.]])
    np.testing.assert_allclose(transfer(xy,features,values,xy,features),values)


def test_climate_changes_inference_and_bounds_are_local():
    xy=sphere(np.array([-1.,1.]),np.array([0.,0.]))
    features=np.array([[0.],[10.]])
    values=np.array([[0.],[10.]])
    target=sphere(np.array([0.,0.]),np.array([0.,0.]))
    result=transfer(xy,features,values,target,features,strength=4)
    assert 0<=result[0,0]<1
    assert 9<result[1,0]<=10


def test_ocean_sized_gap_is_not_extrapolated():
    source=sphere(np.array([0.]),np.array([0.]))
    distant=sphere(np.array([30.]),np.array([0.]))
    assert np.isnan(transfer(source,np.array([[0.]]),np.array([[2.]]),distant,np.array([[0.]]))).all()


def test_dateline_has_no_rectangular_discontinuity():
    source=sphere(np.array([179.]),np.array([0.]))
    target=sphere(np.array([-179.]),np.array([0.]))
    assert transfer(source,np.array([[0.]]),np.array([[2.]]),target,np.array([[0.]]))[0,0]==2


def test_missing_donor_is_excluded_not_interpreted_as_zero():
    xy=sphere(np.array([0.,1.]),np.array([0.,0.]))
    result=transfer(xy,np.array([[0.],[0.]]),np.array([[np.nan],[4.]]),xy,np.array([[0.],[0.]]))
    np.testing.assert_allclose(result,4)
