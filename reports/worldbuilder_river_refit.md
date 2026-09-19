# World Builder rivers: additive refit

All 20,893 ownable locations. Only the current river size/presence source changes.
Other attributes, targets, coefficients bounds, solver settings and region folds match the previous vanilla-river fit. Verified from archived input hashes and configurations.

Current rivers use marker-aware predicted engine levels from the ownable-only exported PNG, including junction promotions. This is not a fresh engine save export.

| Target | Evaluation | Vanilla-river R² | New-river R² | RMSE reduction |
|---|---|---:|---:|---:|
| base_effective_cropland | full_fit | 0.226077 | 0.224494 | -0.102% |
| capacity_multiplier | full_fit | 0.365005 | 0.364876 | -0.010% |
| inert_capacity | full_fit | -0.427369 | -0.415704 | +0.409% |
| starting_capacity | full_fit | 0.721411 | 0.722284 | +0.157% |
| maximum_capacity | full_fit | 0.510075 | 0.509420 | -0.067% |
| base_effective_cropland | region_heldout | 0.009709 | 0.008640 | -0.054% |
| capacity_multiplier | region_heldout | 0.218105 | 0.219747 | +0.105% |
| inert_capacity | region_heldout | -0.607589 | -0.584154 | +0.732% |
| starting_capacity | region_heldout | 0.671017 | 0.673245 | +0.339% |
| maximum_capacity | region_heldout | 0.419819 | 0.420950 | +0.098% |

The numerical gains are small. Base land slightly worsens; held-out multiplier, inert, starting and maximum capacity improve slightly. Inert capacity from separately fitted base and multiplier still has negative R².

Starting and maximum capacity retain the actual improvement quantities. They are diagnostics of replacing base and multiplier, not complete attribute-only predictions or fitted building levels.

The current presence-only control is also rerun using NEW-map presence. Thus river_comparison.csv isolates levels versus presence within the new map; worldbuilder_river_comparison.csv compares the previous vanilla-level fit with the new-level fit.

Both absolute- and relative-error objectives were rerun. Figures above use the primary absolute-error objective. All five positive levels now receive coefficients. No targets, mod effects or game files were changed.

Reproduce: `uv run worldbuilder attribute-fit`. New map/report: `artifacts/attribute_fit/index.html`; full coefficients: `coefficients.csv`; archived baseline: `before_worldbuilder_rivers/`. Ten targeted fitting/river tests passed.
