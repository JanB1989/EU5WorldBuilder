import json
from pathlib import Path
import numpy as np
import pytest
import historical_agriculture.agricultural_game_calibration as model


def run(tmp_path, monkeypatch, scale):
    c = json.loads((Path(__file__).parents[1] / 'configs/agricultural_game_calibration.json').read_text())
    c['inheritance'].pop('extent_guard', None)
    (tmp_path / 'configs').mkdir(exist_ok=True)
    (tmp_path / 'configs/regions.json').write_text(json.dumps({'regions': [{'ecoregion_ids': [1], 'management': 'managed'}]}))
    monkeypatch.setattr(model, 'read', lambda p: (np.ones((1, 2)), {}))
    c['support_conversion']['game_scale'] = scale
    (tmp_path / f'configs/game_{scale}.json').write_text(json.dumps(c))
    arr = {'baseline_support_per_land_ha': np.full((1, 2), .001), 'starting_support_per_land_ha': np.full((1, 2), .01),
           'maximum_support_per_land_ha': np.full((1, 2), .1), 'starting_crop_fraction': np.full((1, 2), .02), 'maximum_crop_fraction': np.full((1, 2), .5),
           'starting_served_fraction': np.full((1, 2), .005), 'maximum_served_fraction': np.full((1, 2), .1), 'dry_field_alternative_support': np.full((1, 2), .002)}
    for stage, total in [('starting', .009), ('remaining', .09)]:
        for kind in ['clearing', 'management', 'irrigation']:
            arr[f'{stage}_{kind}_capacity'] = np.full((1, 2), total / 3)
    return model.apply(tmp_path, {'agricultural_game_calibration': f'configs/game_{scale}.json', 'food_directory': 'food'}, arr,
                       np.array([[0, .1]]), np.ones((1, 2)), np.ones((1, 2), bool), tmp_path)


def test_game_scale_is_one_global_linear_factor_on_game_support_only(tmp_path, monkeypatch):
    one = run(tmp_path, monkeypatch, 1.0); half = run(tmp_path, monkeypatch, 0.5)
    for key in ['baseline_support_per_land_ha', 'starting_support_per_land_ha', 'maximum_support_per_land_ha',
                'starting_clearing_capacity', 'remaining_irrigation_capacity', 'dry_field_alternative_support']:
        np.testing.assert_allclose(half[key], .5 * one[key])
    for key in ['uncalibrated_starting_support', 'game_inheritance_activation_fraction', 'starting_crop_fraction', 'game_conversion_reference_support']:
        np.testing.assert_array_equal(half[key], one[key])
    for stage, lo, hi in [('starting', 'baseline_support_per_land_ha', 'starting_support_per_land_ha'),
                          ('remaining', 'starting_support_per_land_ha', 'maximum_support_per_land_ha')]:
        np.testing.assert_allclose(sum(half[f'{stage}_{k}_capacity'] for k in ['clearing', 'management', 'irrigation']), half[hi] - half[lo])
    audit = json.loads((tmp_path / 'agricultural_game_calibration.json').read_text())
    assert audit['game_scale'] == 0.5 and audit['population_in_formula'] is False


def test_invalid_game_scale_is_rejected(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match='game scale'):
        run(tmp_path, monkeypatch, 0.0)
