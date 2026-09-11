import json
import numpy as np
import pytest
from historical_agriculture.transformations import factor, benchmark_bounds


def test_scenarios_are_independent_and_do_not_apply_fallow():
    crop={'scenario_adjustments':{'LRLM':{'cultivar':.8,'management':.5},
                                 'HRLM':{'cultivar':.5,'management':.8},
                                 'HILM':{'cultivar':.5,'management':.6}},
          'cultivated_fraction':.23}
    assert factor(crop,'LRLM',.5,.4)==pytest.approx(.2)
    assert factor(crop,'HRLM',.5,.4)==pytest.approx(.16)
    assert factor(crop,'HILM',.5,.4)==pytest.approx(.12)


def test_upper_system_is_selected_before_spatial_aggregation():
    row={'scenario_samples_dm':json.dumps({'LRLM':[1,1,1],
              'HRLM':[10,1,10],'HILM':[1,10,1]})}
    low,high=benchmark_bounds(row,{},1,1)
    assert low==1 and high==10
    crop={'scenario_adjustments':{'HRLM':{'management':.1}}}
    low,high=benchmark_bounds(row,crop,1,1)
    assert high==1  # Per-cell [1,10,1], not a reused unadjusted upper sample.


def test_empty_sampling_does_not_mean_zero_yield():
    row={'scenario_samples_dm':json.dumps({'LRLM':[],'HRLM':[],'HILM':[]})}
    assert np.isnan(benchmark_bounds(row,{},1,1)).all()


def test_invalid_adjustment_rejected():
    with pytest.raises(ValueError):
        factor({'scenario_adjustments':{'LRLM':{'cultivar':0}}},'LRLM',1,1)
