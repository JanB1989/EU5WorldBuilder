# Global soil type test

2026-09-14. Research classifications are owned by HistoricalAgriculture1300;
the isolated Land Clearance Geography Test mod demonstrates their game interface.

## Reproduce

```
uv run ha1300 soils
uv run pytest -q tests/test_soil_types.py tests/test_geography_test.py
uv run ha1300 geography-test
```

The last command builds and syncs only the dedicated test mod using
`geography_test.local.toml`. Use `--build-only` to omit sync. No main-mod changes.

## In the game

Restart EU5, enable Land Clearance Geography Test alone and start a new campaign.
Open Geography in the map-mode selector, then the terrain/climate/vegetation group.
Soil Type is in that same group (`category = geography`, `index = 2`). It has a
six-color categorical legend. A seventh compact icon in the location geography
strip shows Soil Type after lake adjacency. Hover for the type and description.
It displays no unrelated development, rank or food-modifier breakdown.

The six types are Sand, Loam, Silt, Clay, Peat and Stony. Fertility is separate and
is not implemented here. There are no new economic effects or soil level bonuses.
Soil names refer to substrate, not a best-to-worst ranking.

One `on_game_start` hook stores a class variable in each land location. Native
template modifiers remain intact. No recurring soil update, location-specific
scripted lookup chain, or geographical recomputation runs during the campaign.
Building conditions can use the six emitted `ha1300_soil_is_*` scripted triggers.
The variables persist in saves; saves created before this version need a new
campaign to initialize them. Startup/performance and rendering still require
in-engine observation; file checks cannot establish those behaviors.

## Data and scope

FAO HWSD2_DB.zip and HWSD2_RASTER.zip are fetched from the official download links.
Native 30-arcsecond soil-unit component shares are classified before aggregation.
Each registered game pixel is sampled at four points; this is quadrature, not
exact polygon intersection. Latitude-dependent pixel area weights are used to
calculate within-location composition only, not location capacity or size bonuses.
Class selection is the final step; all six shares are retained in the CSV.

Histosols become Peat. Substantial coarse fragments (35% or more) or documented
stony/rudic/skeletic/gravelly/concretionary phases become Stony. Depth alone is
never a classifier. Peat takes priority over Stony. Remaining mineral textures
use the explicit code mapping in configs/soil_types.json. This broad mapping is
an adjustable game simplification: sandy loam belongs to Sand and clay loam to
Loam. Modern soil observations approximate physical substrate, not measured 1300
fertility, historical field management, or agricultural productivity.

The output covers all 28,573 game zones: 22,864 terrestrial zones receive types,
including all 20,893 ownable locations. Water zones have an explicit water state.
Seven ownable locations lack direct soil coverage and use flagged nearby donors
(about 29–91 km away). There are 114 donor-based land assignments in total,
including remote unownable zones with much greater uncertainty. Those estimates
must not be interpreted as observations of exposed soil on glaciers. Broad or
mixed locations retain their dominant share and a low-confidence flag.

Ownable counts in the initial build: Loam 12,009; Sand 4,036; Stony 2,744;
Silt 1,079; Clay 881; Peat 144. These are location counts, not global area shares.

## Artifacts and checks

- `artifacts/soils/locations.csv`: complete classifications, six shares, source
  coverage, donor location/distance and confidence flags.
- `artifacts/soils/soil_types.png`: categorical location preview.
- `artifacts/soils/manifest.json`: source/configuration/code fingerprints and counts.
- `artifacts/soils/engineering_checks.json`: generated-code and assignment checks.
- The built mod includes the exact consumed CSV and source manifest.

Ten focused tests pass. Twelve generated script files parse. All generated
location assignments match the CSV, every ownable location is covered, and the
inventory matches the installed game's location templates. The original template
effects are byte-for-byte preserved except for the four pre-existing clearing-test
geography edits. These checks do not claim in-game rendering has been observed.

Source documentation: https://www.fao.org/land-water/resources/tools/databases/hwsd/en/
