# Review of inferred starting improvements

Baseline: pushed commit `aa5fa3d`, with 483 rural locations above starting
capacity. The review addresses extra inherited improvements, not sourced
cultivation, natural support, productivity or maximum opportunity.

## Diagnosis

The previous activation rule `m*h/(h+0.01)` can grant considerable expansion
from a tiny reconstructed cultivated footprint `h`. For example, an extensive
system with 0.5% cultivation activates about 6.7% of its remaining opportunity;
if that opportunity spans half the cell, the additional 3.3% of cell area is
over six times the evidence-supported cultivated extent. This is an inferred
allowance, not something established by the historical land-use reconstruction.

The new guard limits that extrapolation. Below 1% cultivation, extra crop and
water-served extent can each expand by at most the existing cultivated extent;
the restriction tapers away between 1% and 5%. It applies to extensive,
rotation-based and unknown classifications. Maintained managed/intensive systems
retain their existing scenario. The classes come from `configs/regions.json`;
they are broad evidence/inference rules, not independent local infrastructure
surveys. HYDE/LUH cultivated extent remains population-informed evidence.

No source-supported works are removed. Existing cultivated land and irrigation
remain even in very small settlements. Sparse population and unused capacity
are diagnostics, not criteria in the assignment formula. Extensive systems can
have a long agricultural history; the guard is about uncertain extrapolation
beyond represented cultivation.

## Candidate selection

Test the unrestricted baseline, a universal extent guard, then the restricted
guard with extra-extent ratios 0.5, 1 and 2. The universal rule creates adverse
changes in established agricultural systems. Use ratio 1 as the central
conservative uncertainty allowance; retain 0.5 and 2 as sensitivity cases.
Do not tune individual locations to avoid a population shortfall.

The full rebuild produces `inheritance_review.json`, a complete location
comparison, region totals and the explicit new-shortfall list. Accounting
validation checks unchanged base, multiplier, maximum and source-supported
works. Starting capacity removed is transferred to remaining opportunity.

## Reproduction

The frozen pre-review CSV is `data/processed/inheritance_review_before.csv`.
To regenerate it, run the canonical pipeline with `inheritance.extent_guard`
removed and `inheritance_review_baseline` omitted, into a separate directory;
copy that output's `locations_equal_area.csv` to the baseline path. The raw
source pack and prior comparison inputs are still required as documented in
the main model report.

```bash
uv run python scripts/review_starting_inheritance.py
uv run ha1300 locations
uv run python scripts/validate_locations.py
uv run pytest -q
```

The diagnostic runner reconstructs unrestricted activation from the same raw
native-grid support and source extents, so it also runs after the guarded map
has been built. Its float32 cache comparison can differ at raster precision
from the full pipeline. Candidate inputs and code are hashed in its report.

This is a starting-infrastructure refinement. Large natural-base allowances and
the downstream food/growth behavior remain separate unresolved balance questions.

## First complete candidate results

The full native-grid calculation moves 67.319 million game capacity from starting
improvements to remaining opportunity across 9,044 ownable locations. Starting
capacity falls from 2,357.980 to 2,290.661 million; maximum remains 4,835.386 million.
Base, multiplier, source cultivation, source irrigation and uncalibrated starting
support are unchanged.

Among rural locations with 0 < population < 5,000, 2,903 change: 29.397 million
capacity moves to future opportunity and median starting capacity falls from
40,436 to 38,875. None of these locations becomes newly over capacity. Large base
allowances still explain considerable sparse-settlement headroom.

Five rural locations elsewhere become newly over starting capacity: Launggyet,
Sikasingo, Xianyou, Yongfu and Fuan. The rural total rises from 483 to 488. One
additional urban location also crosses its starting capacity. These are explicit
unresolved costs of the shared evidence rule, not automatically accepted import
exceptions. No individual population-based carve-outs were applied.

The main changed regional totals are eastern North America (−14.3%), Great Plains
(−14.9%), Russia (−10.7%), Urals (−10.7%) and Kongo (−7.5%). These percentages refer
to starting capacity, not reconstructed physical cultivated hectares.
