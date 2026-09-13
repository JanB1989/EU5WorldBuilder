# Cultivated-system correction: China and northwestern India

The central candidate is now the location map. It is a useful correction to inherited agricultural systems, **not a resolution of global rural overcapacity**. No population value was used to calculate or select a location's support. The central assumptions were frozen before comparison; the stronger case is retained as sensitivity evidence, not chosen because it removes more red locations.

## Changes and evidence

- **Chinese wet rice:** previously extensive assignments on reconstructed cultivated fields receive a maintained-field management analogue. It applies to wet rice in ecoregions 236/268/659, below 1,000 m, with at least 0.1% reconstructed cultivation. Earlier intensive lowland assignments remain intact. This adds no terraces, cultivated hectares or irrigation service.
- **Northwestern Indian cereals:** where the assigned wheat/barley system has very low rainfed productivity relative to irrigation, inherited improved rainfed fields use a summer/winter cereal mixture. The summer component averages feasible pearl millet and sorghum estimates rather than selecting their maximum. It substitutes crops on existing fields; it does not sum two harvests on one plot. The representative crop layer remains unchanged, and the mixture is explicit in the companion ledger.

[Indus archaeobotanical research](https://pmc.ncbi.nlm.nih.gov/articles/PMC6991972/) supports established use of seasonally different crops and adaptation to variable water conditions. Its much earlier dates do not measure the mixture in 1300. [Research on imperial Chinese agricultural techniques](https://www.cambridge.org/core/journals/british-journal-for-the-history-of-science/article/science-technique-technology-passages-between-matter-and-knowledge-in-imperial-chinese-agriculture/F22BA6399312F5CCF611D66D987827F9) documents maintained rice practices described by Chen Fu in 1149 and transmitted through Wang Zhen in 1313. It does not establish uniform adoption across these ecoregions. Source identities, cached document checksums and interpretations are in `evidence/location_refinements.json`.

These sources support the mechanisms. Management intensity and crop shares remain **inferred ranges**, not measured medieval assignments. HYDE cultivation remains population-related reconstruction, not independent validation.

The model holds natural base support and the reference multiplier fixed. All additional capacity is assigned to effective improvements. The 1,000-unit base floor, multiplier bounds of 0.25–5, physical opportunities and basin water allocations are unchanged. Existing irrigation on baseline fields retains its original benefit; a partition correction prevents the improved rainfed system from subtracting that benefit a second time.

## Frozen comparison

| Assumption | Conservative | Central | Strong |
|---|---:|---:|---:|
| Chinese management position | 0.30 | 0.45 | 0.60 |
| Chinese active rotation fraction | 0.375 | 0.50 | 0.625 |
| Indian summer-cereal share | 0.25 | 0.50 | 0.75 |

Each assumes one harvest per active hectare. Indian management position remains 0.60 and rotation fraction 0.75. Locations outside the eligibility masks remain unchanged.

| Equal-area diagnostic | Before | Conservative | Central | Strong |
|---|---:|---:|---:|---:|
| Rural/unranked locations above starting capacity | 7,076 | 7,057 | 7,040 | 7,006 |
| Rural/unranked locations above maximum | 2,988 | 2,969 | 2,946 | 2,921 |
| Rural provinces within starting capacity | 2,669 | 2,676 | 2,685 | 2,688 |
| Rural provinces above maximum | 414 | 405 | 401 | 398 |
| Rural starting capacity, millions | 658.385 | 660.928 | 664.158 | 668.019 |

There are 19,879 rural/unranked locations and 3,819 rural province groups. Urban locations are excluded from these rural counts, but receive the same physical corrections when eligible. The central case changes starting support in 638 ownable locations, increasing total ownable starting support from 758.435 to 765.139 million (+0.88%). It changes 4,660 Chinese and 2,656 Indian source cells. No location loses support.

| Rural region | Above starting capacity before | Central |
|---|---:|---:|
| East China | 206 | 195 |
| South China | 200 | 187 |
| West China | 146 | 141 |
| Hindustan | 237 | 230 |
| Western India | 135 | 135 |

All beneficiaries are reported in each output's `rural_region_comparison.csv`, including small border overlaps into Indochina and Persia. Unaffected regions and cells were checked globally, including American frontiers.

## What remains wrong

Even the stronger assumptions resolve only 70 of the original 7,076 local rural shortfalls. Bathinda rises from 6,089 to 16,695 capacity in the central case against 247,450 starting people; Dongyang rises from 9,200 to 28,258 against 475,939. Bijnot remains at 1,632 against 341,520 because the seasonal rainfed alternatives do not resolve its land/water problem. These are diagnostic discrepancies, not evidence that the population should be used as a capacity floor.

The remaining 7,040 local rural shortfalls split into:

- **1,883** in provinces with sufficient combined starting rural capacity. Examine food sharing before treating them as additional land requirements.
- **3,204** in provinces short at start but within the modeled maximum. These warrant inherited cultivation/infrastructure evidence and spatial-allocation checks.
- **1,953** in provinces short even at the modeled maximum. Starting improvement adjustments alone cannot resolve those provincial totals; the land/water opportunity, yield and game mapping assumptions require diagnosis.

These categories identify where to investigate, not proof of a cause or permission to inflate support. In particular, equal-area capacity is a game representation while the population snapshot retains historical location totals. This round does not establish food production, employment, trade or demographic equilibrium. Global calibration remains unaccepted.

## Reproduce and verify

Run in the repository's WSL/Linux directory:

```bash
uv run ha1300 locations
uv run python scripts/validate_locations.py
uv run pytest -q
```

For either sensitivity variant, copy `configs/locations.json` to a local JSON file and set `system_round_variant` to `conservative` or `strong`. Keep all other configuration identical, then run:

```bash
uv run ha1300 locations --config data/processed/system_round_conservative.json --output artifacts/system_round_conservative
uv run python scripts/validate_locations.py --config data/processed/system_round_conservative.json --output artifacts/system_round_conservative
uv run ha1300 locations --config data/processed/system_round_strong.json --output artifacts/system_round_strong
uv run python scripts/validate_locations.py --config data/processed/system_round_strong.json --output artifacts/system_round_strong
```

The archived before-state is `data/processed/system_round_before`. `reports/cultivated_system_round_checks.json` records fingerprints and invariant comparisons for all three candidates. Each output contains the full compatible location data, native-grid correction masks, typed component ledger, rural comparisons and source manifest.

All three independent delivery validations pass: all 20,893 ownable locations have complete positive values; all 28,573 map locations are covered; capacity/component equations and water accounts reconcile. Base land and multipliers are identical to the before-state. Cultivation, irrigation-service rasters and water-account files are byte-identical. Support is nondecreasing from before to conservative to central to strong, and unchanged outside the masks.

The full test suite passes **112 tests**, with six existing Rasterio pending-deprecation warnings. Generated viewer tests pass click selection, drag/zoom, blocked canvas readback, high-DPI and row-boundary behavior, summaries and coverage states. These are automated viewer checks, not a fresh live-browser inspection.
