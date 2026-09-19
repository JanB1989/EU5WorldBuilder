import numpy as np
import pytest
from historical_agriculture.location_model import luh_grazing_fraction


def test_luh_grazing_is_flipped_north_up_upsampled_and_capped_by_cultivation():
    z = {'lat': np.array([-45., 45.]), 'pastr': np.array([[0.2, 0.0], [0.1, 0.5]], dtype=np.float32), 'range': np.array([[0.1, np.nan], [0.0, 0.7]], dtype=np.float32)}
    cultivated = np.zeros((6, 6), dtype=np.float32); cultivated[0, 3:] = 0.9
    g = luh_grazing_fraction(z, cultivated)
    assert g.shape == (6, 6) and g.dtype == np.float32
    # south-up input is flipped: the northern source row (index 1) lands on top
    assert g[0, 0] == pytest.approx(0.1)
    assert g[3, 0] == pytest.approx(0.3)
    assert g[3, 3] == 0.0  # nan range contributes nothing beyond pasture 0.0
    assert g[0, 3] == pytest.approx(0.1)  # 1.2 capped to 1, then to 1 - 0.9 cultivated
    assert g[1, 3] == pytest.approx(1.0)  # capped at the cell
