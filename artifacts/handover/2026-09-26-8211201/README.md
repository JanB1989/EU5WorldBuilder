# World Builder handover 2026-09-26-8211201

Schema 1.0, World Builder commit `8211201`. All values in people (1 game unit = 1,000 people).

| File | Rows | Content |
|---|---:|---|
| attribute_rows.csv | 59 | flat capacity people per attribute class (natural fit) and goods output modifiers (`output_<good>`, blank = no row); the `reference` row is the intercept |
| building_types.csv | 8 | improvement buildings: unit people per level, level limit, gate rules (JSON), cap equation in levels (JSON), ledger totals |
| location_buildings.csv | 114381 | per location and building: starting levels, cap at start, cap at development 100, ledger people |
| location_targets.csv | 20893 | per location: targets, attribute flat, development, model values, review flag |
| goods_floor.csv | 1862 | RGO locations for the floor carve-out |
| location_attributes.csv | 20893 | per location: its class for every attribute in attribute_rows.csv, province, super region, lon/lat |

Self-check (attribute flat + levels x unit against targets): start R² 0.454, median error 46.7%; maximum R² 0.375, median error 44.6%.

Verify a rescaled or rounded levels table with `worldbuilder handover-check --levels <csv> --units <json> --version 2026-09-26-8211201`.
