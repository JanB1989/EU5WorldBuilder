import numpy as np
import pandas as pd
import pytest
from historical_agriculture.development_target import game_start_development, ROOT


def test_game_start_development_reads_clips_and_zeroes_non_ownable(tmp_path, monkeypatch):
    table = tmp_path / 'dev.csv'
    table.write_text('location_tag,profile_start_development\na,120\nb,-3\nc,17.5\n')
    monkeypatch.setattr('historical_agriculture.development_target.ROOT', tmp_path)
    frame = pd.DataFrame({'location_tag': ['a', 'b', 'c'], 'province': ['p'] * 3, 'region': ['r'] * 3, 'macro_region': ['m'] * 3,
                          'is_ownable': [True, True, False], 'settlement_context': ['urban', 'rural_or_unranked', 'rural_or_unranked']})
    cfg = {'source': {'kind': 'game_start', 'path': 'dev.csv', 'column': 'profile_start_development'}}
    d = game_start_development(frame, cfg).set_index('location_tag').development
    assert d['a'] == 100 and d['b'] == 0 and d['c'] == 0
    missing = frame.assign(location_tag=['a', 'zz', 'c'])
    with pytest.raises(ValueError, match='missing'):
        game_start_development(missing, cfg)
