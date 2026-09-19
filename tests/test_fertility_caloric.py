"""Pure-function checks for the crop-free caloric fertility producer on tiny grids."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from historical_agriculture import fertility_caloric as fc

CFG=json.loads((Path(__file__).resolve().parents[1]/'configs/fertility.json').read_text())
NODATA=-9
KCAL={'WHE':377.,'MZE':407.}


def rasters():
    # 2x3 cells. Cell (0,1) is nodata for both crops; (1,2) is nodata for wheat and negative for maize.
    return {'WHE':np.array([[1000,NODATA,0],[500,2000,NODATA]],dtype=np.float32),
            'MZE':np.array([[NODATA,NODATA,100],[600,NODATA,-3]],dtype=np.float32),
            'COT':np.array([[9e9]*3]*2,dtype=np.float32)}  # no kcal entry: ignored


def test_best_is_kcal_max_with_nodata_excluded_and_absent_crop_ignored():
    best,index,codes=fc.best_caloric_yield(rasters(),KCAL,nodata=NODATA)
    assert codes==['WHE','MZE']
    expected=np.array([[1000*3770,np.nan,100*4070],[600*4070,2000*3770,np.nan]],dtype=float)
    np.testing.assert_allclose(best,expected)
    assert fc.best_crop_codes(index,codes).tolist()==[['WHE','','MZE'],['MZE','WHE','']]
    # A callable source is loaded lazily and gives the same result.
    lazy={k:(lambda a=v:a) for k,v in rasters().items()}
    np.testing.assert_allclose(fc.best_caloric_yield(lazy,KCAL,nodata=NODATA)[0],expected)


def test_aggregate_excludes_nodata_from_denominator_and_reports_coverage():
    best,_,_=fc.best_caloric_yield(rasters(),KCAL,nodata=NODATA)
    # Location 0 overlaps all six cells with equal area; location 1 only the two invalid cells.
    weights=sparse.csr_matrix(np.array([[1,1,1,1,1,1],[0,2,0,0,0,3]],dtype=float))
    mean,coverage=fc.aggregate(weights,best)
    assert mean[0]==pytest.approx((3770000+407000+2442000+7540000)/4)
    assert coverage[0]==pytest.approx(4/6)
    assert np.isnan(mean[1]) and coverage[1]==0


def test_thresholds_are_quantiles_and_classify_is_lower_bound_inclusive():
    values=np.arange(1,11,dtype=float)
    bounds=fc.thresholds(values)
    assert bounds==pytest.approx(list(np.quantile(values,[.2,.4,.6,.8])))
    ids=fc.classify(np.array([0,2.8,2.79,4.6,10,np.nan]),[2.8,4.6,6.4,8.2])
    assert ids.tolist()==[1,2,1,3,5,0]


def test_frozen_thresholds_override_quantiles_and_first_run_writes_them(tmp_path):
    cp=tmp_path/'fertility.json';frozen={'caloric_thresholds_kcal_ha':[10,20,30,40]}
    cp.write_text(json.dumps(frozen))
    cfg=json.loads(cp.read_text())
    assert fc.resolve_thresholds(cfg,cp,np.array([1,2,3,4,5.]))==([10.,20.,30.,40.],False)
    assert json.loads(cp.read_text())==frozen
    cfg={};cp.write_text('{}')
    bounds,now=fc.resolve_thresholds(cfg,cp,np.arange(1,11,dtype=float))
    saved=json.loads(cp.read_text())
    assert now and saved['caloric_thresholds_kcal_ha']==bounds==[2.8,4.6,6.4,8.2]
    assert saved['thresholds_frozen_on'] and saved['thresholds_note']
    assert fc.resolve_thresholds(saved,cp,np.array([100.,200.]))==(bounds,False)


def test_zero_coverage_location_inherits_nearest_ownable_donor(tmp_path):
    best,index,codes=fc.best_caloric_yield(rasters(),KCAL,nodata=NODATA)
    inv=pd.DataFrame({'location_tag':['dry','gap','high','ice'],'map_color_rgb':['000001','000002','000003','000004'],
                      'calibrated_lon':[10.,10.5,30.,10.6],'calibrated_lat':[50.,50.,50.,50.]})
    zones=pd.DataFrame({'location_tag':['dry','gap','high','ice','sea'],
                        'game_zone_class':['settlement_land','settlement_land','settlement_land','impassable_mountains','sea_zones'],
                        'is_ownable':[True,True,True,False,False]})
    # dry: cell (0,2) only (407,000); gap: only invalid cells; high: cell (1,1) (7,540,000); ice: non-ownable with data.
    weights=sparse.csr_matrix(np.array([[0,0,1,0,0,0],[0,1,0,0,0,1],[0,0,0,0,1,0],[1,0,0,0,0,0]],dtype=float))
    cfg={'levels':CFG['levels'],'caloric_thresholds_kcal_ha':[1e6,2e6,3e6,4e6]}
    cp=tmp_path/'fertility.json';cp.write_text(json.dumps(cfg))
    d,summary=fc.location_table(inv,zones,weights,best,index,codes,cfg,cp,chemistry={'dry':4})
    d=d.set_index('location_tag')
    assert list(d.columns)==fc.CONTRACT_COLUMNS[1:]+fc.DIAGNOSTIC_COLUMNS
    assert d.loc['gap','inferred'] and d.loc['gap','analogue_location']=='dry'
    assert d.loc['gap','analogue_distance_km']==pytest.approx(35.8,abs=.5)
    assert d.loc['gap','fertility_id']==d.loc['dry','fertility_id']==1 and d.loc['gap','best_crop']=='MZE'
    assert d.loc['gap','assignment_source']=='nearest ownable caloric location; inferred' and d.loc['gap','low_confidence']
    assert d.loc['high','fertility_id']==5 and d.loc['high','best_crop']=='WHE' and d.loc['high','very_high_share']==1
    assert d.loc['high','fertility_score']==pytest.approx(7540000) and not d.loc['high','inferred']
    assert d.loc['ice','fertility_id']==0 and d.loc['ice','fertility']=='unassigned' and d.loc['ice','best_kcal_per_ha']==pytest.approx(3770000)
    assert d.loc['sea','fertility']=='water' and d.loc['sea','fertility_id']==0 and np.isnan(d.loc['sea','longitude'])
    assert d.chemistry_fertility_id.to_dict()=={'dry':4,'gap':0,'high':0,'ice':0,'sea':0}
    assert (d.chemistry_imputed_share==0).all()
    assert summary['class_counts_ownable']=={'very_low':2,'low':0,'moderate':0,'high':0,'very_high':1}
    assert summary['coverage_ownable']['zero']==1 and summary['thresholds_frozen_now'] is False
