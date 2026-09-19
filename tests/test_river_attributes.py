import pandas as pd
import pytest
from historical_agriculture.river_attributes import validate_rows


def example():
    return {"location_tag": "test", "river_exporter_schema": 2,
            "river_exporter_river_level": 0,
            **{f"river_exporter_size_{i}": 0 for i in range(1, 6)}}


INV = pd.DataFrame([{"location_tag": "test", "is_ownable": True}])


def test_explicit_zero_is_valid_but_missing_export_is_not():
    row = example()
    assert validate_rows([row], INV).river_level.iloc[0] == 0
    del row["river_exporter_size_2"]
    with pytest.raises(ValueError, match="Missing"):
        validate_rows([row], INV)


def test_largest_level_and_presence_are_checked():
    row = example()
    row.update(river_exporter_size_1=1, river_exporter_size_5=1,
               river_exporter_river_level=5, river_exporter_has_river=1)
    assert validate_rows([row], INV).active_size_count.iloc[0] == 2
    row["river_exporter_river_level"] = 1
    with pytest.raises(ValueError, match="largest"):
        validate_rows([row], INV)


def test_missing_location_fails():
    with pytest.raises(ValueError, match="inventory"):
        validate_rows([example()], pd.concat([INV, pd.DataFrame([{"location_tag": "missing"}])]))
