import numpy as np
import pytest
from affine import Affine
from historical_agriculture.terrestrial_completion import estimate

def inputs():
    values=np.array([[0.,.01,.02,.03,.04,.05],[0.,.1,.2,.3,.4,.5]])
    domain=np.ones(values.shape,bool);targets=np.zeros_like(domain);targets[0,0]=True
    climate=np.zeros((*values.shape,3));eco=np.ones(values.shape)
    food=np.full(values.shape,21)
    profile={"transform":Affine(.1,0,0,0,-.1,1)}
    cfg={"neighbours":4,"donor_lower_quantile":.1,"estimate_quantile":.25,
        "distance_scale_km":1000.,"climate_scales":[5.,1.,1.]}
    return values,domain,targets,climate,eco,food,profile,cfg

def test_unsupported_cell_gets_donor_estimate_not_constant_floor():
    args=inputs();v=args[0]
    result,mask,ledger=estimate(*args)
    assert result[0,0]>0 and result[1,0]==0
    np.testing.assert_array_equal(result[~mask],v[~mask])
    assert len(ledger)==1
    assert result[0,0]==pytest.approx(np.quantile(ledger[0]["donor_support"],.25))
    doubled=list(args);doubled[0]=v*2
    again,_,_=estimate(*doubled)
    assert again[0,0]==pytest.approx(2*result[0,0])

def test_ownable_target_mask_does_not_repair_ocean_or_unrequested_zeros():
    args=list(inputs());args[1][0,0]=False
    result,mask,ledger=estimate(*args)
    assert not mask.any() and not ledger
    np.testing.assert_array_equal(result,args[0])

def test_pastoral_cells_do_not_receive_foraging_donors():
    args=list(inputs());args[5][0,:]=19
    _,_,ledger=estimate(*args)
    assert ledger[0]["system"]=="pastoral"
    assert all(x<6 for x in ledger[0]["donor_cells"])

def test_missing_island_climate_uses_recorded_analogue():
    args=list(inputs());args[3][0,0]=np.nan;args[4][0,0]=np.nan
    result,_,ledger=estimate(*args)
    assert result[0,0]>0
    assert ledger[0]["climate_inferred"]
    assert ledger[0]["climate_donor_cell"]>=0
    assert ledger[0]["match"]=="same_livelihood_climate_analogue"

def test_no_usable_donors_and_explicit_ice_fail_instead_of_fabricating():
    args=list(inputs());args[0][:]=0
    with pytest.raises(ValueError,match="donor"):estimate(*args)
    args=list(inputs());args[5][0,0]=24
    with pytest.raises(ValueError,match="polar ice"):estimate(*args)


def test_generated_delivery_has_usable_values_for_every_ownable_location_and_province():
    from pathlib import Path
    import pandas as pd
    from historical_agriculture.location_inventory import read_zone_inventory,audit_settlement_values
    from historical_agriculture.location_model import validate_frame
    root=Path(__file__).resolve().parents[1]
    raw=root/'data/raw/location_inputs'
    out=root/'artifacts/locations'
    if not (raw/'game_default.map').exists() or not (out/'locations_equal_area.csv').exists():
        pytest.skip("Full game input pack and generated location dataset not installed")
    inventory=read_zone_inventory(raw)
    for name in ['locations.csv','locations_equal_area.csv']:
        d=pd.read_csv(out/name,keep_default_na=False)
        validate_frame(d,inventory)
        audit=audit_settlement_values(d,inventory)
        assert audit['passed'],audit['issues'][:10]
        ownable=d[d.is_ownable]
        province=ownable.groupby('province')[['starting_capacity','maximum_capacity']].sum()
        assert (province>0).all().all()
