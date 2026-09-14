import numpy as np
from pathlib import Path
from historical_agriculture.agricultural_system_repair import select_candidate, rules


def test_dry_millet_can_replace_irrigated_only_wheat_without_yield_maximization():
    # Viable original, irrigated-only original, no original, excluded crop.
    rank=np.array([-1,101,200,200])
    take,new=select_candidate(np.array([1,1,1,1]),np.ones(4),
                              np.array([2,2,2,100]),rank,np.ones(4,bool))
    assert take.tolist()==[False,True,True,False]
    # Higher-yielding but lower-preference later crops cannot replace it.
    later,_=select_candidate(np.ones(4)*100,np.ones(4)*100,
                            np.full(4,3),new,np.ones(4,bool))
    assert not later[:3].any()


def test_zero_and_missing_are_not_viable_and_irrigated_fallback_remains():
    take,rank=select_candidate(np.array([0,np.nan,0]),
                              np.array([0,10,10]),np.zeros(3),
                              np.full(3,200),np.ones(3,bool))
    assert take.tolist()==[False,False,True]
    assert rank[2]==100


def test_regional_crop_evidence_and_unique_ecoregions():
    result=rules(Path.cwd(),{'agricultural_system_repair':'configs/agricultural_system_repair.json'})
    ids=[i for r in result for i in r['ecoregion_ids']]
    assert len(ids)==len(set(ids))
    for eco,crop in [(295,'SRG'),(318,'PML'),(833,'WHE')]:
        assert crop in next(r for r in result if eco in r['ecoregion_ids'])['crops']
    # Historical exclusions outside these evidence-supported systems survive.
    assert next(r for r in result if 150 in r['ecoregion_ids'])['crops']==[]
