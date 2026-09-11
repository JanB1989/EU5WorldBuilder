# Global reconstruction implementation and evaluated results

This supersedes the selection-only first diagnostic as the main project status. The earlier experiment is preserved in `first-pass.md`, `selection-only-status.json`, `configs/scaling.json`, and the legacy CLI.

The reproducible pipeline now processes 18 crop codes and 54 GAEZ scenarios, retains every transformed crop surface, assigns regional historical staple candidates, and calculates food, labour and sensitivity outputs. It produced 1,149,836 cell estimates and 11 map figures. The grid remains native GAEZ; no EU5 geometry or population data enter the model.

## What passed

- All 19 automated regressions and the global numerical/accounting checks.
- Acquisition, raster alignment, pinned source verification, typed zero/missing handling, independent scenario factors, per-cell upper-system selection, conversion and annualization arithmetic.
- Historical crop preference precedes yield ranking. An alternative crop remains available for explicit comparisons.
- Source, configuration and code fingerprints, stage dependencies and artifact hashes prevent stale results from certifying changed inputs.
- The independent English wheat range overlaps the modeled envelope. It was excluded from parameter selection; the broad envelope means this is a limited plausibility check.

## What the historical comparison says

Of 23 Seshat cases, 18 fall inside the adjusted local envelope, three fall outside, and two remain unresolved. Middle Yellow River Valley, Kansai and Cahokia remain outside. Yemen and Deccan have no comparable positive wheat samples at the current approximate locators. These are recorded failures, not zero historical agriculture.

The initial search was limited to lower factors of 0.6–1.0. Training residuals hit that boundary, so a second frozen candidate grid added 0.15, 0.25 and 0.4. The rice upper search was widened after the Southern China Hills training comparison exceeded the earlier envelope. No per-location adjustment or population fitting was introduced. Holdouts remained excluded from selection.

Seshat normalization is material: its crop coefficient is relative to the yield-anchor date. Simply dividing every published yield by the 1300 cropping coefficient is not valid for every region. The current conversion removes the relative anchor factor under an explicit harvested-area interpretation; the report also evaluates alternative denominator conventions. These are alternative interpretations of one source, not independent observations.

## Remaining limitations

- 546 viable grid cells still lack a regional historical assignment; see the spatial gap register. The larger Assam and Caribbean gaps were addressed through dated evidence and explicit regional analogues.
- Crop rules use approximate rectangles. A crop presence inference does not establish local dominance or actual cultivated land.
- Millet transformations and several root/cereal transfers lack direct crop-specific medieval calibration. The per-crop parameter table makes inherited family assumptions visible.
- Global management positions are broad practice-based priors, not a historically validated efficiency map. Labour evidence is largely from much later traditional systems.
- Independent verification of product-level fallow conventions, exact Seshat region boundaries, historical irrigation water delivery and seasonal labour limits remains incomplete.
- Modern climate and soils are environmental proxies. An upper irrigated yield is conditional on water delivery.

These limitations prevent an accepted historical-model claim. The engineering implementation and maps are usable for research; the remaining scientific issues are itemized in the generated failure register.

## Reproduction

```bash
uv sync --group dev
uv run ha1300 acquire
uv run ha1300 run
uv run ha1300 validate
uv run pytest -q --junitxml=reports/tests.xml
```

Run fingerprint: `97e861646272961f4cb299a7fd3d15c866a5901ae3f395b4696ad517039e1b59`.

Open `artifacts/reconstruction/index.html` for maps, `REPORT.md` for evidence, `regional_distributions.csv` for statistics, `crop_parameters.csv` for scenario multipliers, and `failure_register.json` for unresolved cases. Downloaded sources and generated rasters remain local ignored artifacts; check licenses before redistribution.
