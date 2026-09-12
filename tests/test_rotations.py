import json
import numpy as np
import pytest
from historical_agriculture.rotations import apply, rotation_fraction, benchmark_coefficient


def test_rotation_counts_time_not_hectares():
    assert rotation_fraction(1,1.6)==pytest.approx(1/2.6)
    with pytest.raises(ValueError):rotation_fraction(0,2)


def test_only_named_crop_and_ecology_change(tmp_path):
    (tmp_path/'configs').mkdir()
    rule={'id':1,'crops':['CSV'],'ecoregion_ids':[496], 'crop_years':1,'fallow_years':1.6,'fraction_range':[.15,.65],'harvests_per_active_year':1}
    (tmp_path/'configs/rotations.json').write_text(json.dumps({'overrides':[rule]}))
    f=np.ones(3);rotation=np.full(3,.23)
    _,out,ids,records=apply(tmp_path,{'crop_order':['CSV','MZE']},np.array([1,1,2]),np.array([496,500,496]),f,rotation)
    np.testing.assert_allclose(out,[1/2.6,.23,.23])
    np.testing.assert_allclose(rotation,.23)
    assert records[0]['matched_cells']==1
    np.testing.assert_array_equal(ids,[1,0,0])


def test_kansai_keeps_published_coefficient_separate():
    from pathlib import Path
    root=Path(__file__).parents[1]
    coefficient,label,status=benchmark_coefficient(root,'Kansai',2)
    assert coefficient==1 and 'rice only' in label
    assert 'winter' in status
    assert benchmark_coefficient(root,'Other',.375)[0]==.375
