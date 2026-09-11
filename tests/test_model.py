import numpy as np
import pytest
from historical_agriculture.model import scale_yield, food_energy, position

def test_zero_unsuitable_and_nodata_are_distinct():
    a=scale_yield([0,-9,1000],.5)
    assert a[0]==0 and np.isnan(a[1]) and a[2]==500

def test_position_preserves_outside_evidence_and_degenerate_bounds():
    np.testing.assert_allclose(position([0,2,4],[1,1,1],[3,3,3]),[-.5,.5,1.5])
    assert np.isnan(position(1,1,1))

def test_rotational_energy_is_not_per_harvest_energy():
    assert food_energy(1000,3600,.65,.8,2,.5)==1872000

def test_invalid_parameters_rejected():
    with pytest.raises(ValueError):scale_yield([1],-1)
    with pytest.raises(ValueError):food_energy(1,3600,2,.8)
