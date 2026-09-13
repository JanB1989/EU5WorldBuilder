# Global land and management repair

This report records the preceding terrain/land-accounting round. The subsequent
crop-season and cultivated-field correction, including the current map's results,
is documented in [water_crop_repair.md](water_crop_repair.md). Its irrigation
inferences supersede the earlier unchanged-irrigation statement below.

This round keeps equal-area conversion, the 1,000-unit base-land floor and the 0.25–5 productivity bounds. It changes physical land screening and the accounting of inherited management. It does not fit support to population, alter crop yield coefficients, invent historical irrigated hectares or introduce fishing.

## Implemented mechanisms

1. **Evaluate terrain before aggregation.** The previous `exp(-cell relief/150 m)` factor is replaced by slope screening on ETOPO's 60-arc-second pixels, averaged onto the 5-minute GAEZ grid. Maximum one-sided gradients retain ridges and valleys instead of cancelling them. Distance calculations account for latitude. ETOPO's compound WGS84/EGM2008 CRS is checked against the output's WGS84 horizontal grid.
2. **Separate natural access from improvement opportunity.** Shared slope ratings are configured independently. Historical cultivated extent still takes precedence over those estimates. Neither slope class nor elevation alone is presented as measured arable land.
3. **Count irrigation terrain once.** The existing fine-pixel elevation/lift, distance and basin screens remain. The extra whole-cell relief discount is removed. River water is reallocated through the same monthly budgets, efficiency, protected runoff and historical-user priority. More commandable land does not create more water; competition can reduce some locations' maximum allocation.
4. **Preserve management on historical fields.** Existing cultivation overlapping the natural baseline receives its management benefit too. Previously, changing the baseline partition could reclassify unchanged fields and change their productivity. Regression tests now require unchanged support when only that partition changes. Maximum investment can maintain all baseline fields. Irrigation contributes only its gain above the relevant dry system.
5. **Expose water bottlenecks.** The location ledger now includes `water_dependent_cultivation_ha`, `unserved_historical_irrigation_ha` and `unserved_water_opportunity_ha`. These physical-area diagnostics remain independent of effective game units. A small flagged portion does not establish the cause of a location's entire deficit.

## Evidence and limits

[GAEZ v4 documentation](https://gaez-v4-data.fao.org/data/documentation/GAEZ%20v4%20Model%20Documentation.pdf) supplies the slope-class framework. Our access ratings are inferred screening choices, not published GAEZ suitability coefficients. A separate run doubles the measured slopes to expose sensitivity to DEM smoothing. Neither run resolves sub-kilometre slopes, soil depth, erosion or historical terraces.

[FAO's land-use definitions](https://www.fao.org/4/a0135e/A0135E07.htm) include temporary fallow within cropland and distinguish it from land abandoned under shifting cultivation. This does not justify removing the annualization coefficient globally. Long-fallow systems remain a denominator uncertainty. The audit found no coordinate flip or square-kilometre/hectare error; the exact 1300 slice, coordinates, grid dimensions and units are now checked directly in the land preparation stage.

The cached land files identify **HYDE3.4, April 2025**, while referencing the [published HYDE3.2 methodology](https://essd.copernicus.org/articles/9/927/2017/). This lineage distinction is retained. HYDE and LUH are related, population-informed reconstructions, not independent evidence of carrying capacity. Source receipts and direct-download restrictions are recorded in `evidence/land_repair.json`; externally restricted publications are not redistributed.

The water model still uses six high-ET months as a generic service season. Winter-crop calendars, flood recession, storage, nonlocal canals and game-to-real-world river alignment need further work. These are explicit unresolved mechanisms, not grounds for automatic water or population floors.

## Interpretation of comparisons

| Rural/unranked diagnostic | Before | Current | Double-slope sensitivity |
|---|---:|---:|---:|
| Locations above starting capacity | 7,040 | 6,249 | 6,676 |
| Locations above maximum capacity | 2,946 | 1,590 | 1,814 |
| Provinces above starting capacity | 1,134 | 1,010 | 1,072 |
| Provinces above maximum capacity | 401 | 217 | 248 |

The central correction resolves 797 local rural shortfalls and creates six: Amoltepec, Beryozovskoye, Haeju, Pushang, Rawalakot and Wonju. All remain below their modeled maximum. Starting support increases in 15,060 ownable locations and decreases in 914; maximum support increases in 17,052 and decreases in 333. Every location's before/after values are in `regional_location_changes.csv`.

Total ownable starting capacity changes from **765.139 to 812.991 million** (+6.3%). Maximum capacity changes from **2.485 to 4.183 billion** (+68.3%). The much larger upper increase is an uncertain physical-opportunity estimate, not evidence of actual historical development or a validated game ceiling. This sensitivity is a reason to retain the candidate label.

East China's rural counts above starting/maximum capacity change from 195/114 to 188/13; South China from 187/98 to 166/4; the Andes from 324/252 to 300/120; the Great Lakes from 94/27 to 76/7. Nubia changes only from 78/50 to 76/47, and Hindustan from 230/150 to 229/87. Xianju's maximum rises from 5,716 to 89,930, but its starting capacity remains only 1,953 against 222,316 people. Terrain repair alone plainly does not reconstruct the missing historical system.

Doubling slopes is a diagnostic for DEM smoothing, not a second independently measured terrain dataset. Some game values increase under stricter slopes because the fixed base floor replaces reduced natural support while inherited improvements retain their contributions. Before that floor, 42 locations still have small increases (at most 26 capacity units), reflecting the existing cropland/livelihood replacement calculation and numerical precision. These exceptions are recorded rather than concealed by a false monotonicity claim.

Both current and sensitivity outputs pass independent delivery validation: all **20,893 ownable locations** have complete positive values; all 28,573 map locations are covered; capacity components and shared river accounts reconcile. The full suite passes **121 tests**, with eight Rasterio pending-deprecation warnings. Generated viewer tests pass. Source crop rasters, historical irrigation extent and location productivity multipliers remain unchanged.

The before-state is the pushed `53d7a54` model, captured as `data/processed/land_round_before.csv` solely for the comparison. Current before/after results are in the map's **Regional changes** and **Rural pressure** links. Every ownable location and region is included, with increases and decreases reported separately. Global corrections supersede the earlier regional-only requirement that base support remain unchanged, but retain coverage, capacity identities, component reconciliation and physical water budgets.

The current map remains an evaluated reconstruction candidate. Reducing shortfalls is useful evidence; it is not sufficient for historical acceptance, and the target of only a few hundred unexplained rural shortfalls remains unmet. Increased maximum capacity is particularly uncertain and must not be mistaken for historical starting cultivation.

## Reproduction

```bash
uv run ha1300 locations
uv run python scripts/validate_locations.py
uv run pytest -q
```

For slope sensitivity, copy `configs/locations.json` and set `terrain_access.slope_multiplier` to `2.0`, keeping every other parameter fixed:

```bash
uv run ha1300 locations --config data/processed/land_slope_conservative.json --output artifacts/land_slope_conservative
uv run python scripts/validate_locations.py --config data/processed/land_slope_conservative.json --output artifacts/land_slope_conservative
```

`reports/land_repair_checks.json` records the evaluated candidate fingerprints and checks. The complete location and component tables, native-grid diagnostic rasters and canonical source manifests are generated with the map. Generated data remain local; reusable code, parameters, tests and this report belong in Git.
