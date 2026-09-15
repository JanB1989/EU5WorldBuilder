# Fertility attribute — first global test iteration

Five values: **Very low, Low, Moderate, High, Very high**. Fertility is a chemical-soil proxy; Soil Type remains a separate physical category. Climate, drainage, irrigation, soil depth, texture labels, population and crop output do not enter this score. This is a complete game classification with explicit uncertainty, not an independently validated historical fertility reconstruction.

## Evidence and scope

The inputs are [FAO/IIASA HWSD2](https://www.fao.org/land-water/resources/tools/databases/hwsd/en) D1 topsoil (0–20 cm) chemistry and the native 30-arcsecond mapping-unit raster. The cached archives, database, component cache, geometry, configuration and code are fingerprinted in `artifacts/fertility/manifest.json`.

The [HWSD field interpretation](https://www.fao.org/fileadmin/templates/nr/documents/HWSD/HWSD_Documentation.pdf), pp. 13–15, informs acidity, nutrient retention and base-saturation thresholds. Base saturation correlates with pH; it is not an independent extra reward. [FAO's soil-quality framework](https://www.fao.org/soils-portal/data-hub/soil-maps-and-databases/harmonized-world-soil-database-v12/soil-qualities-description/en/) separates nutrient supply and retention from other limitations.

Modern chemistry cannot recover pristine or 1300 conditions. Liming, erosion, fertilization and land use can affect these measurements. This iteration avoids directly using nitrogen, organic carbon or modern crop yields as a claimed natural-fertility reward, but CEC and pH can still reflect management. Fertility is not statistical independence from texture, nor the same as yield or agricultural suitability. Phosphorus availability and crop-specific responses are not resolved here.

## Shared classification

The exact scores, caps and grade boundaries below are project choices inspired by that evidence, not official FAO fertility grades or a reproduction of GAEZ SQ1/SQ2.

* CEC (cmol/kg) uses breakpoints 4, 10, 20 and 40 to give scores 1–5.
* pH uses breakpoints 4.5, 5.5, 7.2 and 8.5, with scores 1, 3, 5, 4 and 1. The middle band is most favourable; more alkalinity is not automatically better.
* Base saturation (%) uses breakpoints 20 and 50, with scores 1, 3 and 5. Values above 80 receive no further reward.
* Availability is the lower of the pH and base-saturation scores. Retention is the CEC score.
* The combined score is `0.5 × min(availability, retention) + 0.5 × mean(availability, retention)`.
* Salinity (dS/m) at 4, 8 and 16 caps this score at 3, 2 and 1. Exchangeable sodium at 15% and 30%, and aluminium saturation at 50% and 80%, cap it at 2 and 1. These caps are broad game approximations; tolerances vary by crop.
* Bins are lower-bound inclusive. Round component scores to the nearest grade, with half steps upward.

Classify each soil component first. Preserve its mapped percentage in each HWSD unit, then sample that raster at four quadrature points per registered game pixel. Latitude-weighted contributions accumulate to locations. The location grade is the rounded mean of component-grade shares, not the grade of the largest component. Neither population nor location area alters a chemistry grade.

Components with wholly missing chemistry remain missing: their land is recorded as uncovered evidence, not scored as zero or a global average. Partial chemistry gaps use same-WRB-group medians, then a global field median, with flags. No partial imputation was needed in the current source. Locations with no usable evidence inherit the nearest mapped location, recording the donor and distance. Low coverage and mixed grades are explicit uncertainty flags.

## Current coverage

| Grade | Ownable locations |
|---|---:|
| Very low | 42 |
| Low | 1,983 |
| Moderate | 10,874 |
| High | 7,877 |
| Very high | 117 |

All 20,893 ownable locations have a grade. 7 use nearest-location estimates; 326 have less than 50% sampled chemistry coverage. Coverage is not equivalent to scientific confidence. Urban/bare components often lack chemistry, so nearby measured soil has more influence there. Remote non-ownable ice land can inherit distant soil evidence; other native attributes still determine whether it is habitable.

## Reproduction and game use

```
uv run ha1300 fertility
uv run pytest -q tests/test_fertility.py tests/test_soil_types.py tests/test_geography_test.py
uv run ha1300 geography-test
```

Outputs: `artifacts/fertility/locations.csv`, `component_chemistry.parquet`, `soil_type_crosscheck.csv`, `fertility.png` and `manifest.json`. The data retain component-grade shares, continuous location grade, evidence coverage, inferred donors and confidence flags.

The isolated **Land Clearance Geography Test** now exposes Fertility after Soil Type in the compact location strip. The header shows the grade, a blue Fertility concept link and its map-mode button. Its map is under Geography alongside Soil Type. Five custom painted plant icons show progressively stronger growth for the five grades. Their appearance changes no gameplay coefficients.

Fully restart EU5, then start a **new campaign**: concepts load on startup, while location variables are initialized on campaign creation. The shared startup hook sets both soil attributes once. It adds no monthly processing and no fertility-based food/capacity modifier. Five scripted predicates are available for later building rules. Existing four-location clearing limits are unchanged.

Engineering checks cover chemistry ordering, salt constraints, no-data handling, area-weighted mixtures, complete ownable coverage, correct concept links, one shared startup hook, and deployed file parity. Actual in-game rendering remains a user engine check. There is no population-based fitting or claim that chemical fertility alone explains historical agricultural productivity.
