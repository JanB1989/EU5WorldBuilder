import numpy as np
import pytest
from historical_agriculture.water import command_fraction


def test_command_preserves_eligible_valley_fraction_and_caps_reach():
    actual=command_fraction(np.array([.2,.2,.2,.2]),np.array([0,5,10,0]),10,np.array([1,1,1,0]))
    assert np.allclose(actual,[.2,.1,0,0])


def test_command_cannot_create_more_than_physically_eligible_land():
    fine=np.linspace(0,1,20)
    actual=command_fraction(fine,np.linspace(0,20,20),10,True)
    assert np.all((actual>=0)&(actual<=fine))
    with pytest.raises(ValueError):command_fraction(.2,0,0,True)
