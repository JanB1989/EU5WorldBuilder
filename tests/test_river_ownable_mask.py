import numpy as np
import pandas as pd

from historical_agriculture.river_map import (
    routing_mask, split_visible_runs, route_branch, route_run, validate_native_rivers,
)


def test_eligibility_uses_game_ownability_and_keeps_water_distinct():
    inv=pd.DataFrame({'is_ownable':[True,False,False,False],
        'game_zone_class':['settlement_land','non_ownable','impassable_mountains','lakes']})
    zones=np.array([[0,1,2,3,4]])
    water=np.array([[True,False,False,False,True]])
    original=water.copy()
    assert routing_mask(inv,zones,water,True).tolist()==[[True,False,True,True,True]]
    np.testing.assert_array_equal(water,original)
    np.testing.assert_array_equal(routing_mask(inv,zones,water,False),water)


def test_crossing_excluded_land_creates_two_valid_rivers_without_orphan_markers():
    blocked=np.zeros((12,20),bool);blocked[:,9:11]=True
    path=[(x,6) for x in range(2,18)]
    runs=split_visible_runs(path,blocked)
    assert runs==[path[:7],path[9:]]
    sizes=np.zeros_like(blocked,dtype=np.uint8);owner=np.zeros_like(sizes,dtype=np.int32)
    pixels=np.full_like(sizes,255)
    for run in runs:
        added,attached,reason,_,_=route_branch(run,sizes,owner,blocked,1,True,2,6)
        assert not attached and reason=='complete'
        for x,y in added:pixels[y,x]=7
        x,y=added[-1];pixels[y,x]=0
    assert validate_native_rivers(pixels)['components']==2
    assert not np.any(pixels[blocked]<16)
    assert np.all(pixels[blocked]==255)  # excluded land stays land, not sea


def test_all_excluded_or_boundary_clipping_retains_only_allowed_pixels():
    blocked=np.zeros((3,8),bool);blocked[:,[0,1,5,6,7]]=True
    path=[(x,1) for x in range(8)]
    assert split_visible_runs(path,blocked)==[[(2,1),(3,1),(4,1)]]
    assert split_visible_runs(path,np.ones_like(blocked))==[]


def test_junction_snapping_cannot_cross_unownable_strip():
    sizes=np.zeros((25,25),np.uint8);owner=np.zeros_like(sizes,dtype=np.int32)
    blocked=np.zeros_like(sizes,dtype=bool);blocked[:,10:12]=True
    route_run([(8,y) for y in range(22,1,-1)],sizes,owner,1,3,True,2)
    branch=[(x,12) for x in range(12,23)]
    added,_,_,_,_=route_branch(branch,sizes,owner,blocked,1,False,2,12)
    assert not added
    assert not np.any(sizes[blocked])
