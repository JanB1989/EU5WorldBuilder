# Round 03: conditional improvement productivity

The main map now separates historical non-cropping livelihoods from conditional agricultural improvement productivity in the selected Plains/Rockies ecoregions. `configs/location_refinements.json:improvement_reference` lists the affected ecological systems. Complete, finite maize scenario triplets are evaluated using the same rotation-system settings as neighbouring Eastern North American maize cells. The crop-product and food conversions are unchanged. No modern wheat or fictional historical cropland is introduced.

The higher of historically adjusted rainfed and irrigated reference productivity is conditional output per improved hectare, consistent with the existing reference convention. It is not a statement that irrigation is possible everywhere. Actual physical cultivation and water-service opportunities remain separately bounded and unchanged, including locations where the existing model supplies no agricultural improvement opportunity. This small normalization repair must not be read as completing that separate opportunity model.

The reference applies only to currently unassigned crop candidates. Missing values are excluded; unsuitable zero scenarios do not become productive. Historical food/livelihood classifications and actual food production are untouched. Effective base and improvement units are recalculated inversely to the bounded multiplier, preserving their capacity contributions.

## Results

322 ownable location multipliers change; 20,571 do not. The median changed multiplier is 2.0405. The patch does not force all selected cells above the floor: 60 ownable locations intersecting a changed reference mask still average at or below the 0.25 game floor.

| Location | Previous multiplier | New multiplier |
|---|---:|---:|
| Igmu | 0.250 | 3.388 |
| Wakmua Oin | 0.250 | 3.404 |
| Hot Springs | 0.250 | 2.191 |
| King Hill | 0.250 | 3.123 |
| Paiyo He | 0.250 | 1.774 |
| Beesowuunenno | 2.431 | 2.431 |
| Cahokia | 4.600 | 4.600 |

All location base, starting and maximum capacity values are preserved within serialization precision. Baseline, starting and maximum crop-fraction rasters and water-account arrays are byte-identical. No changed multiplier occurs outside the new reference mask. The source of the former abrupt cliff was the use of foraging support density where the historical crop candidate list was empty; this patch does not remove real low-productivity or unsuitable environments.

## Verification and reproduction

103 Python tests pass (six existing Rasterio pending-deprecation warnings), strict validation passes for every one of 20,893 ownable locations, and all viewer checks pass. The new regression covers excluded regions, existing crop assignments, missing evidence, unsuitable zeros, original-array preservation and unchanged capacity identities after normalization.

Run `uv run ha1300 locations`, `uv run python scripts/validate_locations.py`, and `uv run pytest -q` from the repository. The immediate before-state is archived locally at `data/processed/modifier_round_03_before`; per-location changes are at `data/processed/modifier_round_03_changes.csv`. These generated archives remain local. Summary checks and the current input fingerprint are recorded in `reports/modifier_round_03_checks.json`.

This is an inferred game-reference correction, not newly measured historical productivity or global scientific acceptance. No game export or deployment.
