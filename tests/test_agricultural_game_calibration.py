import numpy as np
import pytest
from historical_agriculture.agricultural_game_calibration import activation,convert,transform


def test_support_conversion_is_ordered_zero_preserving_and_keeps_high_support():
    s=np.array([0,1e-8,.001,.1,1,2,10.])
    g=convert(s,1,1/3)
    assert g[0]==0 and np.all(np.diff(g)>0) and np.all(g>=s)
    assert np.array_equal(g[-3:],s[-3:])
    assert np.allclose(convert(s,1,1),s)
    with pytest.raises(ValueError):convert([-1],1,1/3)


def test_historical_footprint_bounds_activation_and_excludes_uncultivated_frontiers():
    a=activation(np.array([0,.001,.01,.1,1]),.55,.01)
    assert a[0]==0 and np.all(np.diff(a)>0) and a.max()<.55
    assert a[2]==pytest.approx(.275)
    with pytest.raises(ValueError):activation([.1],1.1,.01)


def test_signed_components_and_scenario_endpoints_reconcile():
    b=np.array([0,.01,1.]);s=b+np.array([0,.02,.5]);u=s+np.array([0,.1,1.])
    comp={}
    for stage,total in [('starting',s-b),('remaining',u-s)]:
        for kind,f in [('clearing',.8),('management',-.1),('irrigation',.3)]:comp[f'{stage}_{kind}_capacity']=total*f
    for a in [0,.4,1]:
        gb,gs,gu,c,si=transform(b,s,u,comp,a,1,1/3)
        assert np.allclose(sum(c[f'starting_{k}_capacity'] for k in ['clearing','management','irrigation']),gs-gb)
        assert np.allclose(sum(c[f'remaining_{k}_capacity'] for k in ['clearing','management','irrigation']),gu-gs)
        assert np.all(si>=s) and np.all(si<=u) and np.all(gs>=gb) and np.all(gu>=gs)
        if a==1:assert np.allclose(gs,gu)


def test_conversion_changes_absolute_units_not_location_multiplier():
    b,s,u=convert(np.array([.001,.1,.5]),1,1/3)
    for m in [.25,1.5,5]:
        B=b/m;I=(s-b)/m;J=(u-b)/m
        assert (B+I)*m==pytest.approx(s)
        assert (B+J)*m==pytest.approx(u)


def test_native_grid_inheritance_keeps_source_and_resource_limits(tmp_path,monkeypatch):
    import json
    from pathlib import Path
    import historical_agriculture.agricultural_game_calibration as model
    c=json.loads((Path(__file__).parents[1]/'configs/agricultural_game_calibration.json').read_text())
    c['inheritance'].pop('extent_guard',None)  # Explicit legacy scenario remains reproducible.
    # The live config retired activation for the targets; this test exercises the mechanism itself.
    c['inheritance']['maximum_opportunity_activation']={'extensive':.2,'rotation':.4,'managed':.55,'intensive':.7}
    c['inheritance']['unknown_system_activation']=.2
    (tmp_path/'configs').mkdir()
    (tmp_path/'configs/game.json').write_text(json.dumps(c))
    (tmp_path/'configs/regions.json').write_text(json.dumps({'regions':[{'ecoregion_ids':[1],'management':'managed'}]}))
    monkeypatch.setattr(model,'read',lambda p:(np.ones((1,2)),{}))
    arr={'baseline_support_per_land_ha':np.full((1,2),.001),
         'starting_support_per_land_ha':np.full((1,2),.01),
         'maximum_support_per_land_ha':np.full((1,2),.1),
         'starting_crop_fraction':np.full((1,2),.02),'maximum_crop_fraction':np.full((1,2),.5),
         'starting_served_fraction':np.full((1,2),.005),'maximum_served_fraction':np.full((1,2),.1),
         'dry_field_alternative_support':np.zeros((1,2))}
    for stage,total in [('starting',.009),('remaining',.09)]:
        for kind in ['clearing','management','irrigation']:arr[f'{stage}_{kind}_capacity']=np.full((1,2),total/3)
    result=model.apply(tmp_path,{'agricultural_game_calibration':'configs/game.json','food_directory':'food'},arr,np.array([[0,.1]]),np.ones((1,2)),np.ones((1,2),bool),tmp_path)
    assert result['game_inheritance_activation_fraction'][0,0]==0
    assert result['game_inheritance_activation_fraction'][0,1]==pytest.approx(.5)
    assert result['starting_crop_fraction'][0,1]==pytest.approx(.26)
    assert result['starting_served_fraction'][0,1]==pytest.approx(.0525)
    assert np.array_equal(result['uncalibrated_starting_support'],arr['starting_support_per_land_ha'])
    assert np.all(arr['starting_crop_fraction']==.02)  # input untouched
    assert np.all(result['starting_crop_fraction']<=result['maximum_crop_fraction'])
    assert np.all(result['starting_served_fraction']<=result['maximum_served_fraction'])


def test_sparse_extent_guard_keeps_managed_systems_and_dense_cultivation():
    from historical_agriculture.agricultural_game_calibration import review_inheritance
    settings={'full_guard_below_cultivated_fraction':.01,'no_guard_above_cultivated_fraction':.05,'extra_extent_ratio':1.}
    h=np.array([.005,.005,.08,.03])
    a=np.full(4,.3);gap=np.full(4,.5)
    result=review_inheritance(a,h,gap,gap/2,np.array([True,False,True,True]),settings)
    assert result[0]==pytest.approx(.01)
    assert result[1]==.3  # Managed/intensive evidence is ineligible for the guard.
    assert result[2]==.3  # Substantial cultivation unchanged.
    assert result[3]==pytest.approx(.18)  # Smooth transition, not a boundary jump.
    assert np.all(result<=a)


def test_sparse_guard_preserves_sourced_support_and_maximum_and_releases_opportunity():
    from historical_agriculture.agricultural_game_calibration import bound_inheritance
    a=bound_inheritance(np.array([.3]),np.array([.005]),np.array([.5]),np.array([.1]),1.)
    comp={f'{stage}_{kind}_capacity':np.array([amount/3]) for stage,amount in [('starting',.1),('remaining',.9)] for kind in ['clearing','management','irrigation']}
    b=np.array([.1]);s=np.array([.2]);u=np.array([1.1])
    old=transform(b,s,u,comp,np.array([.3]),1.,1/3)
    new=transform(b,s,u,comp,a,1.,1/3)
    assert np.array_equal(new[0],old[0]) and np.array_equal(new[2],old[2])
    assert np.all(new[1]<old[1]) and np.all(new[1]>=convert(s,1.,1/3))
    assert .02+a[0]*.5==pytest.approx(.025)  # Recorded .02 retained; only extra .005.
    assert np.allclose(sum(new[3][f'remaining_{k}_capacity'] for k in ['clearing','management','irrigation']),new[2]-new[1])
    with pytest.raises(ValueError):bound_inheritance(.2,.01,.2,.1,-1)
