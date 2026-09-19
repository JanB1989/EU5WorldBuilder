import numpy as np
import pytest

from historical_agriculture.river_network import downstream_indices, check_acyclic
from historical_agriculture.river_map import (
    select_with_closure, levels, Projection, lattice_path, erase_raster_loops, route_run,
    location_audit, snap_junction, route_branch,
)


def test_source_links_and_downstream_closure():
    ids = np.array([11, 3, 7, 21])
    down = downstream_indices(ids, np.array([3, 7, 0, 0]))
    assert down.tolist() == [1, 2, -1, -1]
    check_acyclic(down)
    selected, extra = select_with_closure(np.array([100., 2., 1., 0.]), down, 50)
    assert selected.tolist() == [True, True, True, False]
    assert extra == 2
    with pytest.raises(ValueError, match="missing"):
        downstream_indices(ids, np.array([99, 0, 0, 0]))
    with pytest.raises(ValueError, match="cycle"):
        check_acyclic(np.array([1, 0]))


def test_five_levels_can_change_without_source_changes():
    q = np.array([10, 50, 150, 500, 2000, 8000, 100000])
    untouched = q.copy()
    assert levels(q, [50, 150, 500, 2000, 8000]).tolist() == [1, 1, 2, 3, 4, 5, 5]
    assert levels(q, [50, 100, 300, 1000, 5000]).tolist() == [1, 1, 2, 3, 4, 5, 5]
    assert levels(np.array([120]), [50, 100, 300, 1000, 5000])[0] == 2
    assert levels(np.array([120]), [50, 150, 500, 2000, 8000])[0] == 1
    np.testing.assert_array_equal(q, untouched)


def test_projection_and_dateline_do_not_bridge_world():
    t = dict(x_mean=180, x_scale=1, lon_coefficients=[0, 1],
             y_mean=90, y_scale=1, lat_coefficients=[0, -1])
    p = Projection(t, 360, 180)
    xy = p.project(np.array([[179, 0], [-179, 0]]))
    assert list(lattice_path(xy, 360, 180)) == []
    assert np.isnan(p.project(np.array([[0, 91]]))[0, 1])
    np.testing.assert_allclose(p.project(np.array([[0, 0]])), [[180, 90]])


def test_raster_path_is_four_connected_and_has_no_self_touches():
    raw = next(lattice_path(np.array([[1, 1], [7, 5], [2, 5], [2, 1]]), 20, 10))
    clean = erase_raster_loops(raw)
    assert len(clean) < len(raw)
    assert all(abs(a[0]-b[0])+abs(a[1]-b[1]) == 1 for a, b in zip(clean[:-1], clean[1:]))
    assert len(set(clean)) == len(clean)
    for i, a in enumerate(clean):
        for b in clean[i+2:]:
            assert abs(a[0]-b[0])+abs(a[1]-b[1]) > 1


def test_y_junction_and_unrelated_collision(tmp_path):
    import pandas as pd
    s = np.zeros((15, 15), np.uint8); owner = np.zeros_like(s, dtype=np.int32)
    trunk = [(7, y) for y in range(13, 1, -1)]
    added, attached, reason, _ = route_run(trunk, s, owner, 1, 2, True, 2)
    assert len(added) == 12 and not attached and reason == "complete"
    branch = [(x, 7) for x in range(7, 1, -1)]
    added, attached, reason, _ = route_run(branch, s, owner, 1, 1, False, 2)
    assert attached and reason == "complete" and len(added) == 5
    markers = np.full_like(s, 255); markers[7, 6] = 1
    inv = pd.DataFrame([dict(location_tag="test", is_ownable=True)])
    audit = location_audit(inv, np.ones_like(s), s, markers, tmp_path)
    assert audit["junction_promoted_locations"] == 1
    df = pd.read_csv(tmp_path/"location_levels.csv")
    assert df.intended_river_level[0] == 2
    assert df.marker_aware_predicted_level[0] == 5
    # An unrelated river must not be allowed to join this existing trunk.
    added, _, reason, _ = route_run([(x, 9) for x in range(7, 13)], s, owner, 2, 1, True, 2)
    assert not added and reason == "collision"


def test_short_branch_rolls_back_without_damaging_trunk():
    s = np.zeros((10, 10), np.uint8); owner = np.zeros_like(s, dtype=np.int32)
    route_run([(5, y) for y in range(8, 1, -1)], s, owner, 1, 3, True, 2)
    old = s.copy()
    added, _, reason, _ = route_run([(5, 5), (4, 5), (3, 5)], s, owner, 1, 1, False, 4)
    assert not added and reason == "subpixel_or_short"
    np.testing.assert_array_equal(s, old)


def test_junction_snapping_retains_tributary_at_stair_step():
    s = np.zeros((20, 20), np.uint8); owner = np.zeros_like(s, dtype=np.int32)
    water = np.zeros_like(s, dtype=bool)
    trunk = [(9, y) for y in range(16, 9, -1)] + [(8, 10), (8, 9), (7, 9)] + [(7, y) for y in range(8, 1, -1)]
    route_run(trunk, s, owner, 1, 3, True, 2)
    tributary = [(8, 10), (7, 10), (6, 10), (6, 9), (5, 9), (4, 9), (3, 9), (2, 9)]
    old = s.copy()
    added, _, reason, _ = route_run(tributary, s, owner, 1, 1, False, 2)
    assert not added and reason == "collision"
    np.testing.assert_array_equal(old, s)
    fixed, snapped = snap_junction(tributary, s, owner, water, 1, 6)
    assert snapped
    added, attached, reason, _ = route_run(fixed, s, owner, 1, 1, False, 2)
    assert len(added) >= 4 and attached and reason == "complete"


def test_working_confluence_is_not_moved():
    s = np.zeros((20, 20), np.uint8); owner = np.zeros_like(s, dtype=np.int32)
    water = np.zeros_like(s, dtype=bool)
    route_run([(10, y) for y in range(18, 1, -1)], s, owner, 1, 3, True, 2)
    branch = [(x, 10) for x in range(10, 1, -1)]
    added, attached, reason, _, snapped = route_branch(branch, s, owner, water, 1, False, 2, 12)
    assert not snapped and attached and reason == "complete"
    assert added == branch[1:]


def test_geographic_stage_has_no_game_classes_and_rejects_stale_source(tmp_path):
    import json
    import pyarrow as pa
    import pyarrow.parquet as pq
    import shapely
    from historical_agriculture.river_network import build, verify
    raw, network = tmp_path/"raw.parquet", tmp_path/"network.parquet"
    values = {"reach_id": ["1", "2"], "downstream_reach_id": ["2", None],
        "main_basin_id": ["basin", "basin"], "river_source_id": ["river", "river"],
        "q_mean_m3_s": [10., 15.], "q_min_m3_s": [5., 7.], "q_max_m3_s": [20., 30.],
        "catchment_km2": [100., 150.], "distance_downstream_km": [10., 0.],
        "endorheic": [False, False],
        "geometry_wkb": [shapely.to_wkb(shapely.LineString([(0, 1), (0, 0)])),
                         shapely.to_wkb(shapely.LineString([(0, 0), (0, -1)]))],
        "continent_code": ["test", "test"], "source_id": ["fixture", "fixture"],
        "source_sha256": ["test", "test"], "alignment_version": ["game_alignment", "game_alignment"]}
    pq.write_table(pa.table(values), raw)
    result = build(raw, network)
    assert result["reaches"] == 2 and result["maximum_endpoint_gap_degrees"] == 0
    data = pq.read_table(network)
    assert "alignment_version" not in data.column_names
    assert "intended_size_class" not in data.column_names
    assert json.loads(data.schema.metadata[b"geo"])["primary_column"] == "geometry"
    assert data["q_mean_m3_s"].to_pylist() == [10., 15.]
    assert verify(network)["network_sha256"] == result["network_sha256"]
    values["q_mean_m3_s"] = [10., 16.]
    pq.write_table(pa.table(values), raw)
    with pytest.raises(ValueError, match="source changed"):
        verify(network)
