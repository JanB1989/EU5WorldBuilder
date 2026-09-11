import json
import numpy as np
import pandas as pd
import pytest

from historical_agriculture.calibration import calibrate,evaluate,enclosure_constraints
from historical_agriculture.evidence import anchor_interval_multipliers


def case(name,obs,lower,upper,raw_low=1000,raw_high=5000,role='calibration'):
    return {'region':name,'crop':'WHE','role':role,'harvest_t_ha_inferred':obs,
        'harvest_t_ha_lower_inferred':lower,'harvest_t_ha_upper_inferred':upper,
        'scenario_samples_dm':json.dumps({'LRLM':[raw_low],'HRLM':[raw_high],'HILM':[raw_high]})}


def configuration():
    return {'crops':{'WHE':{'group':'cereal','dry_fraction':1}},'scenarios':['LRLM','HRLM','HILM'],
        'calibration':{'width_penalty':.03,'low_factors':[.6,.8],
            'high_factors':{'cereal':[.3,.4]},'default_low':.8,'default_high':{'cereal':.3},
            'reference_parameters':{'cereal':{'low':.6,'high':.3}},'anchor_margin_fraction':.000001}}


def test_shared_scaling_encloses_every_anchor_interval_including_former_holdout(tmp_path):
    (tmp_path/'evidence').mkdir();out=tmp_path/'out';out.mkdir()
    frame=pd.DataFrame([case('A',1,.8,1.2),case('former holdout',.3,.2,.4,role='geographical_holdout'),case('upper',3,2,4)])
    frame.to_csv(tmp_path/'evidence/benchmarks_1300.csv',index=False)
    config=configuration();result=calibrate(tmp_path,config,out)
    p=result['parameters']['cereal']
    assert p['low']<.2 and p['high']>.8
    assert all(r['inside'] for r in evaluate(frame,config,p['low'],p['high']))
    assert p['comparable_anchors']==3


def test_point_fit_is_insufficient_when_source_interval_extends_outside():
    frame=pd.DataFrame([case('interval',1,.4,2)])
    r=evaluate(frame,configuration(),.6,.3)[0]
    assert r['point_inside'] and not r['inside']


def test_zero_modern_support_is_unresolved_not_artificially_filled():
    ceiling,floor,constraints,unresolved=enclosure_constraints(pd.DataFrame([case('zero',1,1,1,0,0)]),configuration())
    assert unresolved==['zero'] and constraints==[]
    assert np.isinf(ceiling) and floor==0


def test_anchor_range_propagation_preserves_published_midpoint():
    data=pd.DataFrame([{'NGA':'C','Variable':'Historical Productivity','Value.From':'.672','Value.To':'1.681','Date.From':800,'Date.To':1500},
                       {'NGA':'C','Variable':'Historical Productivity','Value.From':'8','Value.To':'','Date.From':1900,'Date.To':1900}])
    lo,hi=anchor_interval_multipliers(data,'C')
    assert lo==pytest.approx(.672/1.1765)
    assert hi==pytest.approx(1.681/1.1765)
    assert (lo+hi)/2==pytest.approx(1.)
