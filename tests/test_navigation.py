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


def test_native_bank_pixel_preserves_maximum_and_clears_water():
    import pandas as pd
    from historical_agriculture.navigation_cleanup import preserve_levels,LEVELS
    original=np.full((5,8),100,dtype=np.uint32)
    after=original.copy();after[:,3]=200
    river=np.full((5,8),255,dtype=np.uint8);river[:,3]=9;river[2,3]=15
    inv=pd.DataFrame([dict(location_tag='bank',map_color_rgb='000064',bbox_min_x=0,bbox_max_x=7,bbox_min_y=0,bbox_max_y=4)])
    cleaned,rows,levels=preserve_levels(river,original,after,{100},inv)
    assert levels[100]==5
    assert len(rows)==1
    assert not (cleaned[after==200]<16).any()
    assert LEVELS[cleaned[after==100]].max()==5
    assert rows[0]['distance_pixels']==1


def test_gap_closure_follows_native_line_and_respects_exclusions():
    import pandas as pd
    from historical_agriculture.navigation_cleanup import close_short_gaps
    rows=pd.DataFrame([dict(x=x,y=2,state=1 if x in (2,6) else 0,main_basin_id=10,evidence='physical_screen') for x in range(2,7)])
    assert close_short_gaps(rows,10,3)==3
    assert rows.state.eq(1).all()
    rows.loc[1:3,'state']=0;rows.loc[2,'evidence']='historical_exclusion'
    assert close_short_gaps(rows,10,3)==0


def test_mouth_snap_closes_only_short_land_to_sea_registration_gap():
    import pandas as pd
    from historical_agriculture.navigation_cleanup import snap_mouths
    original=np.full((8,12),100,dtype=np.uint32);original[:,10:]=200
    rows=pd.DataFrame([dict(x=x,y=4,state=1,land_location='bank',distance_downstream_km=5,main_basin_id=1,evidence='physical_screen') for x in (5,6,7)])
    rows.index=rows.y*12+rows.x
    fixed,audit=snap_mouths(rows,original,{100},{200},3)
    assert len(audit)==1
    assert {4*12+8,4*12+9}.issubset(fixed.index)
    assert not (fixed.x>=10).any()
    rows['state']=3
    fixed,audit=snap_mouths(rows,original,{100},{200},3)
    assert not audit
