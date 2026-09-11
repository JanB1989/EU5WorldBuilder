# Historical Agriculture 1300

A reproducible global agricultural-productivity research model on the native GAEZ 5-arc-minute grid. It estimates conditional crop yields around 1300, food energy and labour, with a complete food-system classification and experimental non-crop extensions. The main results are lower, upper and estimated historical food-energy equivalents in people per used hectare. It does **not** estimate cultivated hectares or total cell population capacity.

The global pipeline is implemented and produces maps and evaluated diagnostics. Historical acceptance is reported separately from engineering success; inferred crop systems and management positions must not be mistaken for observations.

## Run

```bash
uv sync --group dev
uv run ha1300 --help
uv run ha1300 acquire
uv run ha1300 run
uv run pytest -q
```

The source archive `data/raw/seshat.zip` is preserved from the existing research cache, or downloaded from its pinned OSF file if absent; its URL and member checksums are in `evidence/seshat_provenance.json`. Acquisition pins and verifies the archive, RESOLVE ecological polygons (CC-BY-4.0), and 54 GAEZ rasters and snapshots the available supporting documents. Unavailable documents are recorded explicitly.

Stages are `audit`, `evidence`, `calibrate`, `assign`, `food-assign`, `calculate`, `compare`, `food-calculate`, `validate`, and `maps`. Every stage accepts `--config configs/reconstruction.json` and `--output artifacts/reconstruction`. Run the complete pipeline after changing inputs. Standalone stages reject stale configurations or altered prerequisite artifacts.

## Inspect the results

- [Main findings: food systems, three people/ha maps, Seshat graph](artifacts/reconstruction/index.html)
- [Food-system method and non-crop limitations](reports/food_system_method.md)
- [Food coverage and numerical basis](artifacts/reconstruction/food_validation.json)
- [Evidence and validation report](artifacts/reconstruction/REPORT.md)
- [Seshat comparisons](artifacts/reconstruction/benchmark_comparison.csv)
- [Independent historical wheat check](artifacts/reconstruction/independent_holdouts.json)
- [Regional distributions](artifacts/reconstruction/regional_distributions.csv)
- [Coverage and gaps](artifacts/reconstruction/coverage.json)
- [Ecoregion-to-historical-system ledger](artifacts/reconstruction/ecoregion_ledger.json)
- [Source/code/configuration/output fingerprints](artifacts/reconstruction/manifest.json)

All GeoTIFFs remain on the original GAEZ grid. Paired maps use common scales, with the display percentile limit documented in the plotting code; the underlying values are not clipped.

## Model contract

1. **Inputs:** YXX is dry-product yield on the best occurring suitability class within a cell. It is not a whole-cell mean or a current-cropland observation. All three water/input scenarios are retained.
2. **Scaling:** crop-family parameters must enclose all comparable Seshat anchor intervals. The smallest required change from the frozen reference factors is applied globally to each crop family; average-score tradeoffs cannot excuse an outside anchor. Crop/scenario-specific cultivar and management adjustments are independently configurable. The shared factor remains a composite historical correction; its cultivar and management contributions are not independently identified. Annual cropping is applied separately.
3. **Upper scenario:** select the larger adjusted high-input rainfed or irrigated yield in each cell, then aggregate. Irrigated values are conditional on water delivery; a historical water-supply feasibility map has not been established.
4. **Crop assignment:** dated regional availability and staple preferences take precedence over modeled productivity. The next viable historically listed crop is retained as an alternative. Historical systems are assigned to RESOLVE 2017 ecological polygons, distinguishing floodplains, uplands and dry plains. Their boundaries are physical stratification, not observed 1300 crop-history polygons or cultivated-area masks. Unmatched coastline cells remain unresolved.
5. **Food:** convert dry product to the configured moisture/product form, then calculate gross edible energy and separately deduct seed and losses. Rotation time and crop frequency are applied once. Annual scenario comparisons hold the assigned rotation constant.
6. **Labour:** use recorded crop/system analogues, never derive labour from yield. Later traditional systems are explicitly distinguished from medieval evidence. Seasonal bottlenecks remain unresolved.
7. **Position:** published Seshat model estimates are compared after a documented, uncertain anchor-denominator conversion. Out-of-range estimates stay out of range. All Seshat cases are calibration anchors, including the former geographic holdouts; English wheat remains an independent source check. Shared global management positions are inferred priors; population is never a fitting input.

## Edit assumptions

- `configs/food_systems.json`: food requirement, livelihood rules, pinned FORGE source and experimental livestock transfer.
- `configs/reconstruction.json`: crop conversions, scenario adjustments, calibration search ranges, management and sensitivity assumptions.
- `configs/regions.json`: ordered regional crop rules, evidence and uncertainty.
- `configs/sources.json`: source URLs, families and roles.
- `evidence/independent_holdouts.json`: independent historical comparisons excluded from calibration.
- `evidence/benchmarks_1300.csv`: generated Seshat comparisons; regenerate rather than editing to change outcomes.

The original selection-only experiment remains available through `ha1300 fetch` and `ha1300 scale`, with `configs/scaling.json` and `reports/first-pass.md` preserved. It is superseded as the main reconstruction pipeline, not deleted.

## Boundaries

Modern climate and soil are retained as environmental proxies. Missing evidence, unsuitable modeled crops, non-cropping livelihood inferences and unresolved regional assignments have different raster codes. Several indigenous staples have no adequate crop representation. A plausible envelope alone does not validate global historical yields, irrigation feasibility or a management-efficiency ranking.

No EU5 modifiers, buildings, cultivation-area allocation, population fitting, game export or deployment are included. Generated rasters and downloaded sources remain ignored; source licenses must be checked before redistributing cached material.

The food mask is a conditional reconstruction, not a complete historical observation. Non-crop numbers are research transfers: FORGE modern-environment outputs for terrestrial foraging and a provisional grazer-biomass-to-livestock conversion. They are not accepted historical minimum/maximum values. Fishing is identified but aquatic food is excluded from terrestrial per-hectare outputs. Missing numeric results remain explicit.
