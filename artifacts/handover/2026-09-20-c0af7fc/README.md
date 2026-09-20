# World Builder handover 2026-09-20-c0af7fc

Schema 1.0, World Builder commit `c0af7fc`. All values in people (1 game unit = 1,000 people).

| File | Rows | Content |
|---|---:|---|
| attribute_rows.csv | 59 | flat capacity people per attribute class (natural fit) and goods output modifiers (`output_<good>`, blank = no row); the `reference` row is the intercept |
| building_types.csv | 8 | improvement buildings: unit people per level, level limit, gate rules (JSON), cap equation in levels (JSON), ledger totals |
| location_buildings.csv | 114091 | per location and building: starting levels, cap at start, cap at development 100, ledger people |
| location_targets.csv | 20893 | per location: targets, attribute flat, development, model values, review flag |
| goods_floor.csv | 1638 | RGO locations for the floor carve-out |

Self-check (attribute flat + levels x unit against targets): start R² 0.836, median error 22.9%; maximum R² 0.520, median error 32.4%.

Verify a rescaled or rounded levels table with `worldbuilder handover-check --levels <csv> --units <json> --version 2026-09-20-c0af7fc`.
