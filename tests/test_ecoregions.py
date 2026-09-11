import json
from pathlib import Path
import numpy as np
import pytest
from affine import Affine
from historical_agriculture.ecoregions import burn_polygon, system_lookup

def test_polygon_not_rectangle_and_hole_preserved():
    grid=np.full((5,5),-1,dtype=np.int16)
    polygon={'type':'Polygon','coordinates':[
        [(0,0),(5,0),(5,2),(2,2),(2,5),(0,5),(0,0)],
        [(0.1,0.1),(0.1,0.9),(0.9,0.9),(0.9,0.1),(0.1,0.1)]]}
    burn_polygon(grid,polygon,(0,0,5,5),Affine(1,0,0,0,-1,5),7)
    assert grid[0,0]==7
    assert grid[0,4]==-1  # inside bounding box, outside polygon
    assert grid[4,0]==-1  # hole
    assert grid[4,4]==7

def test_ecoregion_lookup_is_complete_and_exclusive():
    assert system_lookup([{'id':8,'ecoregion_ids':[0,3]}],[0,3])=={0:8,3:8}
    with pytest.raises(ValueError,match='Duplicate'):
        system_lookup([{'id':8,'ecoregion_ids':[3,3]}],[3])
    with pytest.raises(ValueError,match='catalogue'):
        system_lookup([{'id':8,'ecoregion_ids':[3]}],[3,4])

def test_named_ecological_crop_controls():
    config=json.loads((Path(__file__).parents[1]/'configs/regions.json').read_text())
    rules={e:r for r in config['regions'] for e in r['ecoregion_ids']}
    assert len(rules)==847
    assert all('bbox' not in r for r in config['regions'])
    for eco,crop in [(657,'RCW'),(236,'RCD'),(667,'FML'),(744,'WHE'),
                     (71,'RCW'),(588,'WPO'),(337,'MZE'),(519,'MZE'),(139,'TAROD')]:
        assert rules[eco]['crops'][0]==crop
    assert rules[576]['crops']==[]  # Pampas is not preassigned grain-belt cultivation
    assert rules[533]['classification']=='unresolved'

def test_southern_china_retains_wet_rice_when_dry_rice_is_unsuitable():
    config=json.loads((Path(__file__).parents[1]/'configs/regions.json').read_text())
    rule=next(r for r in config['regions'] if 236 in r['ecoregion_ids'])
    assert rule['crops'].index('RCW') < rule['crops'].index('FML')
