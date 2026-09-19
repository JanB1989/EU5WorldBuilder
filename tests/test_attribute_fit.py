import itertools
import numpy as np
import pandas as pd
from historical_agriculture.attribute_fit import design,fit,region_folds,attach_river_levels
import pytest


def test_native_river_join_aligns_by_location_and_rejects_missing_or_mismatched_data():
    d=pd.DataFrame({'has_river':[True,False,True]},index=['a','b','c'])
    r=pd.DataFrame({'location_tag':['c','a','b'],'river_level':[5,1,0]})
    joined=attach_river_levels(d,r)
    assert joined.river_level.tolist()==[1,0,5]
    assert joined.index.equals(d.index)
    for invalid in [r.iloc[:2],pd.concat([r,r.iloc[:1]]),r.assign(river_level=[5,0,0]),r.assign(river_level=[5,1,6])]:
        with pytest.raises(ValueError):attach_river_levels(d,invalid)


def test_river_categories_recover_signal_hidden_by_presence():
    d=pd.DataFrame({'river_level':[0,1,3,5]*30})
    d['has_river']=d.river_level.gt(0)
    y=d.river_level.map({0:1.,1:1.2,3:1.7,5:2.2}).to_numpy()
    spec={'scale':1,'minimum':.25,'maximum':5,'coefficient_cap':1.5,'relative_floor':.5,'label':'Multiplier'}
    cfg={'ridge':1e-9,'fertility_order':[]}
    errors=[]
    for feature in ['has_river','river_level']:
        X,names,groups=design(d,[feature]);b,_=fit(X,y,names,groups,spec,cfg,'absolute')
        errors.append(np.mean((X@b-y)**2))
        if feature=='river_level':assert [v for f,v in names if f=='river_level']==['0','1','3','5']
    assert errors[1]<1e-10 and errors[0]>.01


def test_exact_additive_signal_is_recovered_without_interactions():
    d=pd.DataFrame(list(itertools.product(['sand','loam'],['dry','wet']))*20,columns=['soil','climate'])
    X,names,groups=design(d,['soil','climate'])
    y=1.5+(d.soil=='loam').to_numpy()*.3+(d.climate=='wet').to_numpy()*.4
    cfg={'ridge':1e-9,'fertility_order':[]}
    spec={'scale':1,'minimum':.25,'maximum':5,'coefficient_cap':1.5,'relative_floor':.5,'label':'Multiplier'}
    b,_=fit(X,y,names,groups,spec,cfg,'absolute')
    assert np.max(np.abs(X@b-y))<1e-4
    assert all(abs(X[:,ids].mean(axis=0)@b[ids])<1e-5 for ids in groups.values())


def test_bounds_hold_for_unseen_attribute_combinations():
    d=pd.DataFrame({'a':['low']*20+['high']*20,'b':['low']*20+['high']*20})
    X,names,groups=design(d,['a','b']);y=np.array([.25]*20+[5.]*20)
    spec={'scale':1,'minimum':.25,'maximum':5,'coefficient_cap':1.5,'relative_floor':.5,'label':'Multiplier'}
    b,_=fit(X,y,names,groups,spec,{'ridge':.0001,'fertility_order':[]},'absolute')
    for combination in itertools.product(*groups.values()):
        predicted=b[0]+sum(b[i] for i in combination)
        assert .25-1e-5<=predicted<=5+1e-5


def test_regions_are_never_split_between_validation_folds():
    d=pd.DataFrame({'region':['a']*10+['b']*5+['c']*8+['d']*2})
    folds,mapping=region_folds(d,3,1300)
    assert all(len(set(folds[d.region==r]))==1 for r in d.region.unique())
    assert set(folds)=={0,1,2}


def test_map_referenced_elements_exist_in_parsed_html():
    from html.parser import HTMLParser
    import re
    from historical_agriculture.attribute_fit_map import HTML
    class Elements(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ids = set()
        def handle_starttag(self, tag, attrs):
            self.ids.update(v for k, v in attrs if k == "id")
    elements = Elements()
    elements.feed(HTML)
    references = set(re.findall(r"getElementById\(['\"]([^'\"]+)['\"]\)", HTML))
    assert references <= elements.ids, references - elements.ids


def test_replacement_rivers_update_presence_control_without_changing_targets():
    d=pd.DataFrame({'has_river':[False,True,True],'target':[1,2,3]},index=['nan','b','c'])
    rivers=pd.DataFrame({'location_tag':['c','nan','b'],'river_level':[4,2,0]})
    result=attach_river_levels(d,rivers,replace_presence=True)
    assert result.river_level.tolist()==[2,0,4]
    assert result.has_river.tolist()==[True,False,True]
    pd.testing.assert_series_equal(result.target,d.target)
    assert d.has_river.tolist()==[False,True,True]
    with pytest.raises(ValueError):attach_river_levels(d,rivers.iloc[:2],replace_presence=True)


@pytest.mark.parametrize("objective", ["absolute", "relative"])
def test_no_overshoot_fits_shared_profile_floor_without_clipping(objective):
    # Two locations share attributes but have different targets. A shared
    # coefficient must respect the lower target, not clip each output later.
    d = pd.DataFrame({"soil": ["poor", "poor", "rich", "rich"]})
    X, names, groups = design(d, ["soil"])
    y = np.array([.5, 2., 2., 3.])
    spec = {"scale": 1, "minimum": .25, "maximum": 5,
            "coefficient_cap": 1.5, "relative_floor": .5, "label": "Multiplier"}
    cfg = {"ridge": 1e-9, "fertility_order": [], "no_overshoot": True}
    beta, info = fit(X, y, names, groups, spec, cfg, objective)
    assert np.all(X @ beta <= y + 1e-7)
    assert X @ beta == pytest.approx([.5, .5, 2., 2.], abs=1e-6)
    assert info["no_overshoot"]
    assert np.all(X @ beta >= spec["minimum"] - 1e-7)
    # A genuinely held-out target does not constrain training coefficients.
    heldout_target = .3
    assert X[0] @ beta > heldout_target


def test_no_overshoot_rejects_infeasible_target_below_global_floor():
    X, names, groups = design(pd.DataFrame({"soil": ["poor"]}), ["soil"])
    spec = {"scale": 1, "minimum": .25, "maximum": 5,
            "coefficient_cap": 1.5, "relative_floor": .5, "label": "Multiplier"}
    with pytest.raises(ValueError, match="below the global prediction minimum"):
        fit(X, np.array([.1]), names, groups, spec,
            {"ridge": .0001, "fertility_order": [], "no_overshoot": True})



def test_no_overshoot_refines_stalled_solver(monkeypatch):
    from types import SimpleNamespace
    from historical_agriculture import attribute_fit
    class StalledSolver:
        def setup(self, **kwargs):
            self.size = len(kwargs["q"])
        def solve(self, **kwargs):
            return SimpleNamespace(x=np.zeros(self.size), info=SimpleNamespace(
                status="maximum iterations reached", status_val=7, iter=1))
    monkeypatch.setattr(attribute_fit.osqp, "OSQP", StalledSolver)
    X, names, groups = design(pd.DataFrame({"soil": ["poor", "poor", "rich", "rich"]}), ["soil"])
    spec = {"scale": 1, "minimum": .25, "maximum": 5,
            "coefficient_cap": 1.5, "relative_floor": .5, "label": "Multiplier"}
    beta, info = fit(X, np.array([.5, 2., 2., 3.]), names, groups, spec,
                     {"ridge": 1e-9, "fertility_order": [], "no_overshoot": True}, "absolute")
    assert X @ beta == pytest.approx([.5, .5, 2., 2.], abs=1e-6)
    assert "SLSQP" in info["status"]
