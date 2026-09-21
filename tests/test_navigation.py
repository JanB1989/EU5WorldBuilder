import numpy as np
from historical_agriculture.river_navigation import classify
from historical_agriculture.navigation_map import partition, neighbours


def test_conservative_screen_requires_flow_and_relief_evidence():
    cfg={'minimum_mean_discharge_m3_s':500,'minimum_low_discharge_m3_s':75,'open_gradient_m_per_km':.35,'improvable_gradient_m_per_km':2}
    got=classify([500,500,500,499,500,500],[75,75,75,75,74,75],[.35,2,2.1,0,0,np.nan],cfg)
    assert got.tolist()==[1,2,3,0,0,0]


def test_partition_preserves_connected_pixels_and_merges_short_tail():
    points=set(range(3,18))
    groups=partition(points,30,2,6,4)
    assert set().union(*map(set,groups))==points
    assert sum(map(len,groups))==len(points)
    assert all(len(g)>=4 for g in groups)
    for group in groups:
        seen={group[0]};pending=set(group)-seen
        while pending:
            new={q for p in seen for q in neighbours(p,30,60) if q in pending}
            assert new
            pending-=new;seen|=new


def test_adjacency_does_not_wrap_row_boundaries():
    assert 10 not in set(neighbours(9,10,20))
    assert 9 not in set(neighbours(10,10,20))
