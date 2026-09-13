# Global rural-capacity review

This round implements a valid global calculation correction, but does not resolve rural geographical balance. Scientific acceptance remains false.

## Evaluated outcome

The cached snapshot identifies 1,014 urban locations (town, city, megalopolis), of which 440 exceed starting capacity. These are excluded from rural pressure counts. The 19,879 remaining ownable locations have rural_settlement or rural_or_unranked source labels; unranked remains an uncertain classification.

| Rural metric | Before | After |
|---|---:|---:|
| Locations above starting capacity | 7,080 | 7,076 |
| Locations above modeled maximum | 2,995 | 2,988 |
| Provinces within starting capacity | 2,669 | 2,669 |
| Provinces short at start but within maximum | 735 | 736 |
| Provinces above maximum | 415 | 414 |

Rural capacity increases from 658.015 to 658.385 million against 336.638 million contextual population. Global abundance does not validate local distribution. Rural province tables pool rural capacity and population only; urban capacity is not treated as free surplus.

## Implemented correction

Some adjusted high-input yields are below low-input yields. Management now retains the lower-input option when this happens:

- Rainfed: `(1-p)*low + p*max(low, high_rainfed)`.
- Irrigated: the greater of rainfed and `(1-p)*low + p*max(low, high_irrigated)`.

Raw scenario rasters remain unchanged and reversals remain inspectable. This is a voluntary scenario-choice rule, not newly observed historical productivity. It applies consistently to ordinary cells, regional refinements and conditional improvement references.

Baseline, starting and maximum crop fractions and water accounts are byte-identical to the previous round. Physical support does not decrease. The separate base-land floor can absorb additional natural support while the incremental irrigation gain shrinks: final game support falls slightly at Asaka (about 3.89) and Tih Go Tel (about 1.92). This interaction is recorded rather than hidden through a population floor.

## Remaining diagnoses

- Northwestern India: winter wheat/barley alone may miss seasonal systems. At sampled Bathinda coordinates, existing sorghum and pearl-millet rainfed scenarios outperform nearly-zero rainfed wheat. At Bijnot all sampled rainfed alternatives are zero, indicating a separate water/land question. These samples do not justify maximizing crops globally.
- Chinese outliers: sampled Dongyang, Shuangxi and Fenning select wet rice after upland rice is unsuitable, but retain extensive management unless the narrow lowland refinement qualifies. This requires historical field-system and terrain scrutiny; already-provisioned Chinese provinces should not receive an automatic regional boost.
- Andes: sampled highland cells can have zero modeled potato and maize yields despite reconstructed cultivation. The existing cold-field analogue addresses only a narrow setting.
- Current maxima expand existing crop/practice combinations, not every future crop, rotation or technology. Equal-area normalization is also a deliberate game abstraction that must be distinguished from a physical-data error.

HYDE cropland includes arable fallow and is not automatically harvested area. Historical land allocations depend on population and are related evidence, not independent population validation. Definitions were checked against the [HYDE methodology](https://doi.org/10.5194/essd-9-927-2017). No blanket removal of fallow or cropland multiplication was adopted.

## Reproduction and validation

Run `uv run ha1300 locations`, `uv run python scripts/validate_locations.py`, and `uv run pytest -q` from the repository. There are 109 passing tests with six existing Rasterio pending-deprecation warnings, complete values for all 20,893 ownable locations, and passing viewer checks.

The main map links to `artifacts/locations/rural_pressure.html`. Companion location, province, region and before/after CSVs and `rural_pressure.json` bind results to the input fingerprint and rank/baseline hashes. The before-state is archived locally in `data/processed/rural_round_before`.

No game export or deployment. The 1,000-unit equal-area base floor and 0.25–5 multiplier bounds remain unchanged. This is a completed diagnostic/correction round, not a completed rural-capacity repair.
