# World Builder handover 2026-09-20-3f1d4c9

Schema 1.0, World Builder commit `3f1d4c9`. All values in people (1 game unit = 1,000 people).

| File | Rows | Content |
|---|---:|---|
| attribute_rows.csv | 59 | flat capacity people per attribute class (natural fit) and goods output modifiers (`output_<good>`, blank = no row); the `reference` row is the intercept |
| building_types.csv | 8 | improvement buildings: unit people per level, level limit, gate rules (JSON), cap equation in levels (JSON), ledger totals |
| location_buildings.csv | 114093 | per location and building: starting levels, cap at start, cap at development 100, ledger people |
| location_targets.csv | 20893 | per location: targets, attribute flat, development, model values, review flag |
| goods_floor.csv | 1638 | RGO locations for the floor carve-out |
| location_attributes.csv | 20893 | per location: its class for every attribute in attribute_rows.csv, province, super region, lon/lat |

Self-check (attribute flat + levels x unit against targets): start R² 0.524, median error 38.1%; maximum R² 0.196, median error 47.1%.

Verify a rescaled or rounded levels table with `worldbuilder handover-check --levels <csv> --units <json> --version 2026-09-20-3f1d4c9`.
