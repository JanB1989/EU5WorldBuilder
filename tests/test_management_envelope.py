import numpy as np
import pytest
from historical_agriculture.management_envelope import yields

def test_normal_scenarios_preserve_interpolation():
    d,w=yields(100.,300.,500.,.5)
    assert d==200 and w==300

def test_voluntary_management_never_discards_lower_input_option():
    d,w=yields(np.array([100.,100.,0.]),np.array([0.,50.,0.]),np.array([0.,200.,0.]),.6)
    np.testing.assert_allclose(d,[100,100,0])
    np.testing.assert_allclose(w,[100,160,0])

def test_missing_evidence_is_not_replaced_with_productivity():
    d,w=yields(np.nan,100,200,.5)
    assert np.isnan(d) and np.isnan(w)
    with pytest.raises(ValueError):yields(1,2,3,1.1)
