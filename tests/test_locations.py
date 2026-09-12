import numpy as np
import pandas as pd
import pytest
from historical_agriculture.location_model import normalize_support,validate_frame,FIELDS
from historical_agriculture.location_geometry import axis_segments

def frame():
    b,m,i,x=normalize_support(np.array([20.,0.]),np.array([35.,0.]),np.array([60.,0.]),np.array([2.,0.]),.01)
    return pd.DataFrame({'location_tag':['a','b'],**dict(zip(FIELDS,[b,m,i,x])),'inert_capacity':[20.,0.],'starting_capacity':[35.,0.],'maximum_capacity':[60.,0.],'remaining_improvement_effective_cropland':x-i})

def test_normalization_conserves_support_with_zero_location():
    d=frame();assert validate_frame(d,d)['capacity_identities'];assert d.loc[1,'capacity_multiplier']==.01

def test_aggregate_support_before_normalization():
    # Two equal-area cells, different yields and accessible fractions. Averages
    # of independent factors would invent support: preserve 10+80=90 instead.
    b,m,i,x=normalize_support(90.,120.,180.,5.,.01)
    assert b*m==90 and (b+i)*m==120 and (b+x)*m==180

@pytest.mark.parametrize('defect',['missing_row','nan','negative','max_below_start','identity','duplicate'])
def test_reject_incomplete_or_corrupt_delivery(defect):
    d=frame();inventory=d.copy()
    if defect=='missing_row':d=d.iloc[:1]
    elif defect=='nan':d.loc[0,FIELDS[0]]=np.nan
    elif defect=='negative':d.loc[0,FIELDS[1]]=-1
    elif defect=='max_below_start':d.loc[0,FIELDS[3]]=0
    elif defect=='identity':d.loc[0,'starting_capacity']+=1
    else:d.loc[1,'location_tag']='a'
    with pytest.raises(ValueError):validate_frame(d,inventory)

def test_pixel_overlap_splits_boundary_and_wraps_dateline():
    s=axis_segments([-.25,.25],-180,.5,720,True)[0]
    assert len(s)==2 and sum(b-a for _,a,b in s)==.5
    s=axis_segments([179.75,180.25],-180,.5,720,True)[0]
    assert [i for i,_,_ in s]==[719,0]
    assert sum(b-a for _,a,b in s)==.5

def test_maximum_means_total_not_additional():
    d=frame();assert d.loc[0,'remaining_improvement_effective_cropland']==12.5


def test_csv_roundtrip_preserves_nan_named_location_and_small_multiplier(tmp_path):
    d=frame();d.loc[0,'location_tag']='nan'
    d.loc[0,'capacity_multiplier']=.0123456789123
    m=d.loc[0,'capacity_multiplier']
    d.loc[0,'base_effective_cropland']=20/m
    d.loc[0,'starting_improvement_effective_cropland']=15/m
    d.loc[0,'maximum_improvement_effective_cropland']=40/m
    d.loc[0,'remaining_improvement_effective_cropland']=25/m
    path=tmp_path/'values.csv';d.to_csv(path,index=False,float_format='%.15g')
    readback=pd.read_csv(path,keep_default_na=False)
    assert validate_frame(readback,d)['complete_inventory']


def test_inventory_completion_requires_classified_exclusions(tmp_path):
    from historical_agriculture.location_inventory import read_zone_inventory,complete_zones
    (tmp_path/'game_default.map').write_text('sea_zones={ocean} lakes={} impassable_mountains={} non_ownable={}')
    (tmp_path/'game_templates.txt').write_text('a={ topography=flatland }\nocean={topography=ocean}\n')
    (tmp_path/'game_named_locations.txt').write_text('a=abcdef\nocean=123456\n')
    inventory=read_zone_inventory(tmp_path)
    assert set(inventory.location_tag)=={'a','ocean'}
    d=frame().iloc[:1].copy();d['map_color_rgb']='abcdef';d['source_rule']='test';d['evidence_status']='test'
    full,inv,audit=complete_zones(d,tmp_path,tmp_path)
    assert len(full)==2 and audit['explicit_nonsettlement_zero_rows']==1
    assert validate_frame(full,inv)['complete_inventory']
    # An omitted buildable location must fail, not receive the sea-zone zero rule.
    (tmp_path/'game_default.map').write_text('sea_zones={} lakes={} impassable_mountains={} non_ownable={}')
    with pytest.raises(ValueError,match='Unmodeled settlement'):complete_zones(d,tmp_path,tmp_path)


def test_exact_overlap_of_synthetic_game_pixels(tmp_path):
    import json
    from PIL import Image
    from historical_agriculture.location_geometry import overlap_matrix,RADIUS_KM
    raw=tmp_path/'data/raw/location_inputs';raw.mkdir(parents=True)
    image=np.zeros((2,4,3),dtype=np.uint8);image[:,:2]=[1,1,1];image[:,2:]=[2,2,2]
    Image.fromarray(image).save(raw/'locations.png')
    inv=pd.DataFrame({'location_tag':['a','b'],'map_color_rgb':['010101','020202'],'pixel_count':[4,4]});inv.to_parquet(raw/'inventory.parquet')
    (raw/'transform.json').write_text(json.dumps({'x_mean':0,'x_scale':1,'y_mean':0,'y_scale':1,'lon_coefficients':[0,.1],'lat_coefficients':[1,-.1]}))
    out=tmp_path/'out';out.mkdir()
    matrix,audit=overlap_matrix(tmp_path,inv,out)
    expected=RADIUS_KM**2*np.deg2rad(.2)*(np.sin(np.deg2rad(1.05))-np.sin(np.deg2rad(.85)))
    assert np.allclose(np.asarray(matrix.sum(axis=1)).ravel(),expected,rtol=1e-12)
    # A uniform support field must conserve the same area-weighted total.
    assert np.allclose(matrix@np.full(2160*4320,2.),2*expected)
    assert audit['max_relative_area_error']<1e-12


def test_location_lookup_encodes_every_pixel_without_image_readback():
    from historical_agriculture.location_reporting import encode_location_lookup,HTML
    ids=np.array([[0,0,1,1,20000],[3,3,3,3,3],[5,4,3,2,1]],dtype=np.uint32)
    lookup=encode_location_lookup(ids)
    assert lookup['width']==5 and lookup['height']==3
    for y,row in enumerate(lookup['rows']):
        start=0;decoded=[]
        for end,value in zip(row[::2],row[1::2]):
            decoded.extend([value]*(end-start));start=end
        assert decoded==ids[y].tolist()
    assert 'getImageData' not in HTML
    assert '<script src="location_lookup.js"></script>' in HTML
