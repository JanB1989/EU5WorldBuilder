# Crop seasons and unsupported cultivated fields

This report records the preceding physical-model correction. The current map
also includes the subsequent [shared game calibration](agricultural_game_calibration.md).
The physical findings below remain relevant; their shortfall totals are the
before-state for that broader pass.

This pass is implemented in the complete equal-area location map. It resolves
40 rural starting shortfalls without creating new ones. It **does not resolve the
global overcapacity problem**: 6,209 rural locations remain above starting capacity,
including 1,562 above the modeled maximum. Scientific acceptance remains false.

## Evaluated results

| Candidate | Rural above start | Rural above max | Provinces above start | Provinces above max |
|---|---:|---:|---:|---:|
| Before this pass | 6,249 | 1,590 | 1,010 | 217 |
| Crop seasons only | 6,245 | 1,563 | 1,009 | 211 |
| Seasons + dry-field alternatives | 6,222 | 1,562 | 1,006 | 211 |
| Half of both inferred field corrections | 6,225 | 1,562 | 1,004 | 211 |
| Current complete candidate | 6,209 | 1,562 | 1,003 | 211 |

The half-share comparison reruns the canonical monthly water allocation. It is
not interpolation of endpoints: inferred historical users compete for river water.
Both current and conservative versions pass independent delivery validation.

Ownable starting capacity changes from 812.991 to 817.831 million (+0.60%);
maximum changes from 4.183 to 4.241 billion (+1.38%). Base effective units and
all productivity multipliers are unchanged. The equal-area reference, 1,000-unit
base floor and multiplier bounds of 0.25–5 remain fixed. Population never selects
calendars, alternative crops, land or water access.

| Rural region | Starting shortfalls before → now | Starting capacity, millions, before → now |
|---|---:|---:|
| Western India | 135 → 134 | 2.439 → 2.708 |
| Egypt | 41 → 38 | 3.067 → 3.313 |
| Nubia | 76 → 76 | 1.280 → 1.288 |
| Great Lakes | 76 → 73 | 4.771 → 4.956 |
| East China | 188 → 187 | 69.373 → 69.479 |
| France | 19 → 19 | 63.330 → 63.330 |

Calendar correction alone raises Egypt to 3.331 million. Additional inferred
upstream users reduce this to 3.313 million: water competition is retained.
Comfortable locations and low population frontiers are not balance failures merely
because they remain below capacity.

## Changes and evidence

**Crop seasons.** Replace six nonconsecutive highest-ET months with consecutive
crop-specific climate windows. Broad thermal suitability comes before moisture
shortage. The season never optimizes river supply. Paddy percolation remains
separate. FAO documents both [crop-specific growing periods and seasonal timing](https://www.fao.org/4/s2022e/s2022e02.htm)
and [crop water-demand principles](https://www.fao.org/4/u3160e/u3160e04.htm).
Our durations, monthly thermal bands and geographical transfers are approximate
configuration choices, not measured medieval calendars. Modern climate, a
reference-deficit proxy and the original engineering demand floor remain.
Dormancy, multiple distinct crop seasons, precise crop coefficients and
flood-recession soil-water carryover are unresolved. All current crop-management
configurations use one harvest per active year.

**Dry fields.** On reconstructed cultivated land where the representative crop
has zero rainfed output, select the first viable alternative in the existing
historical regional crop list. Do not select the highest-yielding crop. Reuse the
crop's historical yield conversion and regional rotation assumptions. No new
fields are opened. Existing irrigated fields retain their original system; later
irrigation displaces the same dry-field support instead of stacking with it.
Regional crop availability is evidence; local adoption is an inference.
[Kakapel archaeobotanical research (2024)](https://pmc.ncbi.nlm.nih.gov/articles/PMC11335020/)
independently supports finger millet and sorghum presence in the Lake Victoria
region before 1300, while emphasizing heterogeneous local adoption. It does not
establish our cell-level field shares.

**Water-dependent fields.** Where no listed rainfed alternative works, already
cultivated land within the existing low-lift river command screen can imply
unrecorded water management. This is a conditional reconciliation of the existing
land and water datasets, not a new historical irrigation survey. It creates a
request bounded by cultivated extent and river command; every request passes
the same monthly water budgets. No groundwater, distant canal or flood-storage
allowance is invented. The recorded HYDE extent remains separately available.

All of these rules run globally on the fine grid before location aggregation.
Uncertainty is explicit; neither full nor half inferred adoption is established
as a measured historical share.

## Why the remaining problem is substantial

An initial overlap-weighted audit found about 1.262 million physical hectares of
cultivated, unrecorded-irrigation land with zero assigned rainfed output in Western
India. Only about 13,469 hectares had a viable alternative in the existing crop
list. Nubia's corresponding figures were about 950,095 and 1,380 hectares. By
contrast, Great Lakes alternatives covered about 152,289 of 194,662 such hectares.
These are physical source diagnostics, not extra game-effective hectares.

Most residual shortfalls do not disappear with a crop substitution. The final
6,209 cases include 434 within 10% of capacity, 1,410 between 10% and 50% over,
and 1,243 exceeding capacity by more than fivefold. These cannot all be described
as harmless rounding or urban demand. Major cases such as Bijnot, Xianju and
Mugamba remain conspicuous. The strict seasonal water-service model, coarse
historical land allocation, crop-system assignments and game registration still
need discrimination; this pass does not establish a single global cause.

## Deliverables and reproduction

Current map: `artifacts/locations/index.html`. The Regional changes link includes
every location and region. Existing rural pressure reports retain province-level
shortfalls. `reports/water_crop_checks.json` records candidate CSV hashes, counts,
resolved cases, unchanged base/multiplier checks and validated fingerprints.

Additional native-grid diagnostics:

- `irrigation_season_start_month.tif` and `irrigation_season_conflict.tif`
- `dry_field_alternative_crop.tif` and `dry_field_alternative_people_ha.tif`
- `recorded_historical_irrigation_fraction.tif`
- `inferred_cultivated_water_fraction.tif`

The full location ledger includes alternative support and physical-area diagnostics.
All **20,893 ownable locations** have positive complete values, with all **28,573**
map locations covered. Capacity components and water accounts reconcile. The
full suite passes **131 tests**, with eight existing Rasterio pending-deprecation
warnings and no skips. Generated viewer interaction tests pass.

```bash
uv run ha1300 locations
uv run python scripts/validate_locations.py
uv run pytest -q
```

For sensitivity, copy `configs/locations.json` and change only
`dry_field_alternatives.field_share` and `inferred_cultivated_water_share` to 0.5:

```bash
uv run ha1300 locations --config data/processed/water_crop_conservative.json --output artifacts/water_crop_conservative
uv run python scripts/validate_locations.py --config data/processed/water_crop_conservative.json --output artifacts/water_crop_conservative
```

The main model fingerprint is
`4fe38a0af0df37f7ff7a1d89e2378e25754bbe279fa30744a92a85ca10265270`.
No game export, live deployment or Git push was performed in this pass.
