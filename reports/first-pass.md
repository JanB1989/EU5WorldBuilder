# First pass: what is established and what is not

## Established

The local prototype separates input acquisition, configurable crop/scenario transformations and historical evidence. It uses YXX rather than YCX to avoid choosing current cropland as the denominator. Exact YXX land-unit aggregation and yield mass/annual conventions still require product-level confirmation.

Seshat supplies selection ratios for 1300 relative to 2000 of 0.5 for wheat, approximately 0.727 for maize and 0.769 for rice. The diagnostic configuration transfers only these ratios, keeping the modern scenario differences. This is deliberately NOT the proposed full historical envelope. Other crops are explicitly unresolved.

## Research findings

GAEZ Module V distinguishes attainable yields from sustainable annual-production tabulations where fallow is applied. Therefore a guessed second fallow multiplier is not justified. Confirm the selected raster's denominator before calorie and Seshat comparisons.

Source: https://github.com/un-fao/gaezv5/wiki/07.-Module-V-(Integration-of-climatic-and-edaphic-evaluation)

A Chinese agricultural-history study of Song Jiangnan cautions that rent-based yield reconstructions depend on rent type and cropping frequency. Historical unit conversions and rice product form must be reconciled before treating these reports as modern tonnes of paddy per hectare. It is useful independent follow-up evidence, not yet a numerical calibration anchor.

Source: https://agri-history.ihns.ac.cn/scholars/gejinfang1.htm

## Required next gates

1. Verify YXX exact units, fallow and terrain/soil aggregation; do not substitute current-cropland yield.
2. Freeze independent historical yield ranges and separate endpoint transformations, including uncertainties and relevant crop availability.
3. Add dry/fresh/product conversions and source-based labour ranges; calorie functions alone do not supply those inputs.
4. Construct global crop assignment with explicit inference and non-cropping states, then evaluate coverage.
5. Compare Seshat regional estimates using verified boundaries or explicitly approximate sampling, never silently reuse incorrect map locators.

No accepted historical envelope, global crop assignment, labour map or carrying-capacity map has been produced yet.

## Scenario ordering check

The raw YXX endpoints are not always ordered. Low-positive/high-zero cells: wheat 73,491; maize 70,717; wet rice 59,920; dry rice 66,793. An additional 19 wheat and 23 maize cells have both yields positive but reversed. These figures are unweighted cell counts, not hectares. The prototype reports these rather than swapping labels or turning high-input zero into missing data.

FAO documents different soil/terrain suitability rules across water systems and input levels. This is a plausible explanation for many reversals, not a cell-by-cell attribution. A global envelope needs an explicit policy for unsupported irrigation, potentially evaluating a high-input rainfed alternative, before historical scaling can certify the upper endpoint.

Source: https://github.com/un-fao/gaezv5/wiki/06.-Module-IV-%28Agro%E2%80%90edaphic-suitability%29
