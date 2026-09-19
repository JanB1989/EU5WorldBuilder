"""Regression fixtures for errors observed in EU5 map.cpp (1378/1703)."""
import numpy as np
import pytest
from historical_agriculture.river_map import validate_native_rivers, route_branch, route_run


def native_y():
    a = np.full((21, 21), 255, np.uint8)
    a[2:19, 10] = 7
    a[2, 10] = 0
    a[10, 2:10] = 4
    a[10, 9] = 1
    return a


def test_native_marker_is_before_junction_and_tree_is_consumable():
    a = native_y()
    r = validate_native_rivers(a)
    assert r['components'] == 1 and r['segments'] == 2
    assert r['tributary_markers'] == 1


@pytest.mark.parametrize('turn', range(4))
def test_confluences_work_in_every_orientation(turn):
    validate_native_rivers(np.rot90(native_y(), turn))


def test_old_red_on_junction_bug_is_rejected_even_though_tree_is_acyclic():
    a = native_y(); a[10, 9] = 4; a[10, 10] = 1
    with pytest.raises(ValueError, match='degree two'):
        validate_native_rivers(a)


def test_unmarked_affluent_is_rejected():
    a = native_y(); a[10, 9] = 4
    with pytest.raises(ValueError, match='clumped affluent'):
        validate_native_rivers(a)


@pytest.mark.parametrize('extra', [False, True])
def test_missing_or_duplicate_source_rejected(extra):
    a = native_y()
    a[18, 10] = 0 if extra else 7
    if not extra: a[2, 10] = 7
    with pytest.raises(ValueError, match='exactly one'):
        validate_native_rivers(a)


def test_disconnected_unmarked_river_is_rejected():
    a = native_y(); a[15, 2:6] = 13
    with pytest.raises(ValueError, match='exactly one'):
        validate_native_rivers(a)


def test_source_at_junction_is_rejected():
    a = native_y(); a[2, 10] = 7; a[10, 10] = 0
    with pytest.raises(ValueError, match='endpoint'):
        validate_native_rivers(a)


def test_multiple_tributaries_do_not_require_extra_green_sources():
    a = native_y(); a[6, 11:18] = 13; a[6, 11] = 1
    r = validate_native_rivers(a)
    assert r['segments'] == 3 and r['sources'] == 1


def test_isolated_cycle_is_rejected():
    a = native_y()
    a[14, 2:6] = a[17, 2:6] = 4
    a[14:18, 2] = a[14:18, 5] = 4
    with pytest.raises(ValueError): validate_native_rivers(a)


def test_attach_near_existing_junction_snaps_and_preserves_markers():
    s = np.zeros((30, 30), np.uint8); owner = np.zeros_like(s, dtype=np.int32)
    wet = np.zeros_like(s, dtype=bool)
    route_run([(15,y) for y in range(28,1,-1)],s,owner,1,2,True,3)
    b = route_branch([(x,15) for x in range(15,1,-1)],s,owner,wet,1,False,3,12)
    first = b[0][0]
    c = route_branch([(15,15)]+[(x,15) for x in range(16,28)],s,owner,wet,1,False,3,12)
    assert c[0] and c[-1]
    a = np.where(s,7,255).astype(np.uint8); a[2,15]=0
    for x,y in [first,c[0][0]]:a[y,x]=1
    validate_native_rivers(a)


def test_five_widths_remain_distinct_after_encoding():
    a=np.full((15,40),255,np.uint8)
    for i,v in enumerate([4,7,11,13,15]):
        a[2+i*2,2:8]=v; a[2+i*2,2]=0
    assert validate_native_rivers(a)['components']==5
    assert set(np.unique(a))=={0,4,7,11,13,15,255}


def test_source_on_tributary_instead_of_mainstem_is_rejected():
    a=native_y(); a[2,10]=7; a[10,2]=0
    with pytest.raises(ValueError,match='receiving mainstems'):
        validate_native_rivers(a)


def test_branch_two_pixels_above_tributary_marker_keeps_valid_join():
    s=np.zeros((30,30),np.uint8); owner=np.zeros_like(s,dtype=np.int32); wet=s.astype(bool)
    route_run([(15,y) for y in range(28,1,-1)],s,owner,1,2,True,3)
    first=route_branch([(x,15) for x in range(15,1,-1)],s,owner,wet,1,False,3,12)
    second=route_branch([(13,y) for y in range(15,27)],s,owner,wet,1,False,3,12)
    assert second[0] and second[-1]
    a=np.where(s,7,255).astype(np.uint8);a[2,15]=0
    for points in [first[0],second[0]]:
        x,y=points[0];a[y,x]=1
    validate_native_rivers(a)
