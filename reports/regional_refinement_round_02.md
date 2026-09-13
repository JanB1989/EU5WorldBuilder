# Regional refinement round 02

Status: complete evidence-guided comparison, not scientific acceptance of the global model. The main viewer uses the central candidate. Equal-area remains the working game model; fishing and building implementation remain excluded.

## What changed

- Southern Chinese cultivated wet-rice lowlands previously inheriting an extensive/upland system now use managed-system assumptions. Eligibility requires the selected ecoregions, elevation <=400 m, local relief <=100 m and reconstructed cropland >=1%. No new cultivated hectares or irrigation service were introduced. ICID dates Sangyuanwei construction from 1102–1110, with final enclosure in 1396: this supports historical management, not a fully completed 1396 footprint in 1300. The precise management coefficients and spatial thresholds are inferred.
- Selected North American prairie grassland/savanna cells no longer receive automatic 10–15% natural crop access. The central allowance ranges from 1.5% away from rivers towards 5% near rivers, before terrain constraints. Historical reconstructed cultivation is retained and classified as inherited improvement; this reclassification itself conserves capacity. NPS accounts support river-valley cultivation and dense prairie sod as mechanisms. The numerical access fractions are uncertain analogues, not measured medieval land use. Physical maximum cropland is unchanged.
- An altitude-based Andean maize-to-potato correction changed zero cells: viable potatoes were already represented. A subsequent narrow analogue supplies cold-adapted maintained fields in 54 source cells with reconstructed cultivation, low relief, elevation 3800–4200 m and a valid zero standard-potato upper yield. It assumes 4 t fresh potatoes per harvested hectare, alternate-year cultivation, and existing processing/loss conversions. It adds neither land nor irrigation. Modern experiments and FAO descriptions support plausibility of the system; they do not measure its 1300 yield. The regional deficit remains unresolved.

Evidence URLs, applicability and cached source hashes are recorded in `evidence/location_refinements.json`; frozen central and sensitivity assumptions are in `configs/location_refinements.json`.

## Equal-area results

Starting capacity, millions of people-equivalent game support units. Population was not used to select parameters.

| Region | Previous | Conservative | Central | Strong |
|---|---:|---:|---:|---:|
| South China | 7.245 | 10.219 | 13.681 | 14.707 |
| East China | 82.809 | 85.377 | 88.339 | 89.227 |
| Great Plains | 7.437 | 4.195 | 3.265 | 2.451 |
| Andes | 1.982 | 2.009 | 2.030 | 2.054 |

The equal-area reference remains fixed at 246651.09965447552 ha across comparisons, preventing regional adjustments from renormalizing the rest of the world. All 20,327 unrelated ownable locations retain their previous base capacity, starting/maximum capacity and multiplier within serialization precision. The regional masks touch 566 ownable locations. Base support is also preserved inside adjusted areas except the explicitly revised prairie baseline.

Central examples: Guangzhou starts at 172,489 versus 36,335 previously; Hangzhou remains 900,909. Cahokia starts at 29,892 versus 88,248, retaining maximum capacity around 589,534. Chucuito improves from 6,383 to 14,651, still far below its starting population of 114,770. These examples must not be read as historical acceptance or population floors.

The Great Plains maximum remains 65.658 million: this round changes accessible starting support, not the still uncertain maximum cultivation prior. Andean starting support of 2.030 million remains far below the snapshot population of 7.838 million. Missing historical systems and excluded food sources remain visible rather than being filled by capacity fitted to population.

## Validation

- 102 Python tests passed; six existing Rasterio pending-deprecation warnings, no skips.
- Viewer Node checks passed: selection with blocked readback, row boundaries, high-DPI, pan/zoom/drag distinction, summary/details, area switching and explicit non-ownable states.
- Strict location validation passed for central, conservative and strong candidates.
- All 20,893 ownable locations have complete finite inputs and positive support, across 28,573 map zones.
- Component accounts reconcile; missing evidence and unsuitable zeros remain distinct.
- Maximum crop-fraction raster and water-account arrays are byte-identical to the pre-round inputs. Existing water residuals remain at floating-point scale.
- Narrow eligibility, prairie reclassification conservation and fixed-reference/no-spillover rules have regression tests.

Engineering success does not establish historical accuracy. Central assumptions were frozen before their comparison; the sensitivity runs expose uncertainty rather than choosing the highest world retention. Maximum capacity still holds the current crop/rotation system fixed while adding the modeled physical opportunities.

## Reproduction

Run from `/home/jan/development/HistoricalAgriculture1300`:

```sh
uv run ha1300 locations
uv run python scripts/validate_locations.py
uv run pytest -q
```

For sensitivity runs, copy `configs/locations.json` to a candidate config, changing only `refinement_variant` to `conservative` or `strong`, then run:

```sh
uv run ha1300 locations --config data/processed/regional_round_02_conservative.json --output artifacts/regional_conservative
uv run python scripts/validate_locations.py --config data/processed/regional_round_02_conservative.json --output artifacts/regional_conservative
uv run ha1300 locations --config data/processed/regional_round_02_strong.json --output artifacts/regional_strong
uv run python scripts/validate_locations.py --config data/processed/regional_round_02_strong.json --output artifacts/regional_strong
```

Candidate configs and downloaded inputs are local reproducible artifacts. The historical before/after comparison also requires the archived `data/processed/regional_round_02_before/locations_equal_area.csv` (SHA256 `df4e6febb20f3ab4e408da2ac9d7f909a190bf9c0e2ba46d43c08c603be35eae`). Without that optional archive, values still build but the old-candidate comparison cannot be regenerated.

## Outputs and fingerprints

Main: `artifacts/locations/index.html`; comparison: `artifacts/locations/regional_comparison.html`. Companion CSV/JSON reports retain per-location differences, source masks and physical contribution accounts.

- Central: `ef4d096a51102311ff542b6ee79343de6ab82a10b675cc032a71467f61fcef73`
- Conservative: `fa34f4b20f80a4503626e231226ff6bb6d449aa6bf57bfa7905eca4ecba3787c`
- Strong: `adc968b2ac7cb7fcb28b7cbe4946c54a21ef2e5e70f8c08e8958cb7c9717934a`

No game export or live deployment was performed.
