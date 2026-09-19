# Native river levels in the additive attribute fit

Run: 2026-09-17, `uv run ha1300 attribute-fit`.

All 20,893 ownable locations are retained. The control uses the expanded
attributes with river presence; the treatment replaces presence with native
river level. Targets, constraints, losses, seed and five region-grouped folds
are identical. The rerun control reproduces the prior metrics within 1e-8.
Only config and fitting code changed among the previous run's hashed inputs;
capacity targets and environmental classifications are unchanged.

## Results

Primary objective: squared absolute error, with the existing coefficient and
global prediction bounds.

| Target | Full-map R²: presence | Full-map R²: levels | Held-out R²: presence | Held-out R²: levels |
|---|---:|---:|---:|---:|
| Base units | 0.222304 | 0.226077 | 0.004782 | 0.009709 |
| Multiplier | 0.365005 | 0.365005 | 0.218184 | 0.218105 |
| Base × multiplier | -0.394293 | -0.427369 | -0.562773 | -0.607589 |
| Starting capacity, actual improvements retained | 0.722468 | 0.721411 | 0.672498 | 0.671017 |
| Maximum capacity, actual improvements retained | 0.511517 | 0.510075 | 0.422094 | 0.419819 |

Base RMSE falls 0.243% on the full map and 0.248% on held-out regions.
Multiplier RMSE is unchanged on the full map and increases 0.005% held out.
Starting/maximum capacity RMSE increases 0.190%/0.147% on the full map and
0.226%/0.197% held out. Separately optimizing base and multiplier does not
guarantee improving their product. The total-capacity comparisons retain the
same actual improvement quantities in both variants; they are not fits of
improvement levels or complete attribute-only capacity predictions.

This small gain is not just the coefficient bounds hiding a large river signal:
unconstrained additive full-map R² changes from 0.224544 to 0.228369 for base
and 0.391316 to 0.391794 for multiplier. Relative-error fits also show no major
gain. This describes fit to current model targets, not historical accuracy or
the causal importance of rivers.

## River effects in the bounded absolute fit

| Native level | Locations | Base-unit contribution | Multiplier contribution |
|---|---:|---:|---:|
| 0 | 10,410 | -596.59 | +0.017830 |
| 1 | 7,872 | -1,215.65 | -0.017706 |
| 3 | 971 | +6,957.65 | -0.017706 |
| 5 | 1,640 | +5,502.54 | -0.017706 |

Effects are centred by training frequencies and added to a common reference
and all other attribute effects. They are conditional fitted associations,
not standalone productivity measurements. There is no imposed river ordering.

The source is the unmodified 1.3.11 observer export at 1337.4.1, save SHA256
`49cfe1a9e604de6240cc797b7cb1ef0eb765ced530d81f2bdbee137f72369b7a`.
Its presence matches the old inventory in every fitted location. Native levels
2 and 4 do not occur, so they receive no estimated coefficients. Neither the
palette experiment nor the showcase river is used. Native level 5 also reflects
connection-marker promotions; this variable is not measured discharge.

## Validation and outputs

`uv run pytest -q tests/test_attribute_fit.py tests/test_river_attributes.py`:
9 passed. New checks cover location-key alignment, missing/duplicate/invalid
river data, presence agreement, categorical level encoding and recovery of a
synthetic signal that binary presence cannot distinguish.

`artifacts/attribute_fit/river_comparison.csv` contains exact paired results.
`coefficients.csv`, `location_predictions.csv`, `regional_errors.csv`,
`report.json`, `report.md` and the existing `index.html` residual map are
regenerated. The map now exposes native river level in location attributes.
Pre-refit reports/metrics/coefficients/regional errors are retained in
`artifacts/attribute_fit/before_river_levels/`. No game values were deployed.
