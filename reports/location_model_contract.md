# Complete EU5 location model contract

## Shared game-calibration pass — 2026-09-13

The user authorized a substantial recalibration, including a shared game layer
where geographical and crop-system corrections alone could not resolve the
majority of starting shortfalls. The delivered four values remain game-effective
units. They now distinguish uncalibrated physical food support from game capacity.
Population is evaluated globally and by region after calculation; no population,
rank, owner or location-specific target enters the formula. This supersedes a
requirement that game capacity numerically equal the raw physical food estimate.

Historical cultivated footprint and existing agricultural-system classifications
set a bounded starting-inheritance scenario within the simultaneous physical
maximum. A shared monotone concave support conversion compresses the low tail in
game units, including the base. It preserves zeros, ordering and sufficiently
high source values. All crop yields, physical land and river budgets remain
recorded independently. The location multiplier remains bounded to 0.25–5.
The previous 1,000-unit minimum-base allowance is retained against the raw
baseline, so conversion cannot remove an existing allowance and reduce support.

Passing the rural-shortfall game target is separate from historical acceptance
and downstream food/population simulation validation. Remaining rural cases are
listed individually and are not automatically treated as justified exceptions.
No building implementation or live deployment is included.

Status: scope agreed 2026-09-12; first complete inferred iteration implemented. Historical balance remains provisional. See `location_iteration_01_method.md` and generated delivery checks.

This contract supersedes earlier requirements that excluded cultivated support and EU5 location output, required separate food/water/labour deliverables, or made building implementation a prerequisite. The current objective is one complete location dataset and map owned by HistoricalAgriculture1300.

## Four primary outputs

Primary maps compare population-capacity contributions: multiply every base or
improvement amount by the location multiplier before colouring or comparing
locations. Raw effective units remain in detailed ledgers for building balancing.
Within-location composition percentages remain valid because the multiplier is
shared; regional/global contribution totals must sum the multiplied values.

For every location in an explicitly versioned EU5 location inventory:

- B = `base_effective_cropland`, finite and nonnegative.
- M = `capacity_multiplier`, finite and strictly positive, expressed as the full factor.
- I_start = `starting_improvement_effective_cropland`, finite and nonnegative.
- I_max = `maximum_improvement_effective_cropland`, finite and at least I_start.

Derived values are inert capacity M*B, starting improvement capacity M*I_start, starting capacity M*(B+I_start), maximum capacity M*(B+I_max), and remaining improvement opportunity I_max-I_start.

I_max is the total achievable improvement contribution including inherited improvements; it is not an additional allowance on top of I_start. It is conditional on a documented technology and resource scenario. Several alternative maxima may be studied, but each delivered iteration must select and label one complete central scenario.

Starting population may appear in the map with source/date metadata and fill ratios. It is contextual evidence, not a formula input, fitting target, or automatic floor. Capacity zero is permitted when supported; population/capacity is then explicitly undefined rather than an infinite numeric output.

## Complete means complete

A completed iteration must contain each location exactly once, all four finite primary values, all derived accounting values, and mapped geometry or an explicitly recorded inventory exception for a non-spatial entity. Invalid geometry, unmatched spatial locations, missing values and duplicated identifiers fail completion; they cannot be dropped from the denominator.

Uncertain evidence is handled with explicit estimates from shared rules or documented analogues. Each estimate retains confidence, provenance, uncertainty and inference reason. Missing evidence must not silently become zero. A zero requires a meaningful interpretation, such as no feasible additional improvement under the specified scenario. Diagnostic or intermediate artifacts may be incomplete but must not be presented as a finished iteration.

Completeness and scientific confidence are separate: a fully populated estimate may have low confidence, and a complete map is not proof of historical accuracy. Do not call the scientific model accepted solely because its coverage checks pass.

## Fine-grid calculation, final aggregation

1. Pin and verify source rasters, geometry, units, dates, historical interpretations and configurations within this repo's acquisition/provenance system.
2. Reuse existing GAEZ, historical-yield/Seshat, crop/livelihood, HYDE/land-cover, terrain and hydrology evidence. Existing derived tables are comparison material until their assumptions and lineage are verified.
3. Estimate baseline, starting and feasible improved support on the finest defensible common working grid. Avoid upsampling claims: coarse historical evidence remains coarse evidence even when applied on the GAEZ grid.
4. Preserve physical hectares, yields and water budgets separately from effective-cropland accounting. Do not add overlapping clearing, irrigation and drainage benefits repeatedly. Natural flooding belongs in the no-infrastructure baseline where applicable.
5. Aggregate physical and support quantities by actual cell/location overlap only at the final location stage. Retain any within-cell suitability or land-share assumptions. Do not substitute centroid samples where overlap aggregation is available.
6. Translate aggregated support into B, M, I_start and I_max under one documented normalization, checking that derived support is conserved. Averaging cell multipliers and independently summing cropland must not silently change total capacity.
7. Produce the complete location data and one concise location-map interface, with evidence/uncertainty accessible without turning diagnostics into competing deliverables.

## Identification and feasibility

The four numbers are not uniquely identified by support totals. M and the absolute units require a shared normalization; arbitrary inverse rescaling by location must not masquerade as measured hectares or evidence of improvement productivity.

Shared river supplies and overlapping land claims must be reconciled before declaring a simultaneous maximum. An independent maximum for each location that spends the same water several times is not a valid world scenario.

Keep intervention-specific physical accounting internally where needed to avoid overlap. Do not require building types, fixed bonuses, numbers of levels, construction costs or game-script limits in this iteration. These will later be derived from the complete starting and maximum improvement targets.

Starting-date evidence and maximum-scenario technology must be explicitly dated. Modern climate, soils and infrastructure data are proxies where used, not observations of conditions around 1300. Historical population is never used to compensate for missing food production or land evidence.

## Repo ownership

This repo owns the source/configuration-to-map pipeline. Existing external caches may be read once or imported without modifying them. Pin and record their source identity, license, checksums, units, date and transformations, and provide a repo-owned acquisition/import route. Required geometry and location inventory must be versioned inputs with provenance. No final runtime dependence on a sibling project's code, generated capacity assignment or hard-coded cache path.

Preserve existing uncommitted work and evidence. Prior experiments can be archived and clearly superseded; do not delete them merely to simplify the main interface. Required supporting calculations remain inside the repo, focused on the location deliverable.

## Acceptance of an iteration

- Exact inventory coverage, valid map joins, unique identifiers and finite required values.
- Nonnegative B and I_start; positive M; I_max >= I_start.
- Starting/maximum/support/remaining-opportunity identities reconcile within documented output precision.
- Physical land and basin-water accounts reconcile; uncertain inferred access is labelled.
- Source/configuration/code/geometry fingerprints bind the dataset, validation report and displayed map.
- Every location has provenance or an explicit shared inference rule for all four values.
- One reproducible command builds the complete dataset and map without a sibling model runtime.
- Tests cover meaningful grid-to-location aggregation, overlap, unit conversion, normalization, budget and completeness failures.
- Final reporting distinguishes numerical/engineering passes from historical support and uncertain assumptions.

No iteration is finished with only selected regions or only a subset of the four values. Regional pilots are intermediate checks that inform the complete global run.

## Bounded game multiplier comparison — 2026-09-13

Use equal-area as the working game representation; the actual-area output remains a shelved comparison. Bound the full multiplier to **0.25–5** at final location normalization. Values inside the range stay unchanged. Divide each support component by the bounded multiplier to obtain its effective absolute units. This preserves inert, starting-improvement, starting-total and maximum capacities, and therefore population/capacity ratios. Fine-grid physical land, water and food estimates do not change.

These bounds are a game-design normalization, not new historical yield evidence or a repair to crop/management rankings. The unbounded reference multiplier and bound status remain in the ledger. `multiplier_comparison.json`, `multiplier_comparison.csv` and `multiplier_regions.csv` compare with the previous 0.01-floor normalization. A fixed improvement unit now contributes between 0.25 and 5 capacity: a 20-fold extreme range. Building counts and limits must later reproduce the rescaled improvement targets.

Reproduce with `uv run ha1300 locations`, then `uv run python scripts/validate_locations.py` and `uv run pytest -q`.

## Authorized rural game-balance exception — 2026-09-14

The user approved the proposed final 150% rural-fill ceiling. In the equal-area
game calculation only, add `max(P / 1.5 - S, 0)` to ownable rural/unranked
locations. Add the same capacity to base, starting and maximum totals, dividing
by the existing multiplier for base units. Keep remaining improvement capacity
and every historical improvement type unchanged. Preserve pre-allowance values
and a separate allowance ledger. Urban/nonownable locations are excluded.

This explicitly supersedes population independence for this final game allowance
only. It does not change physical land, water, yields, or historical assignments,
and must never be presented as evidence for those quantities. Food/population
simulation acceptance is separate from passing this game-map pressure ceiling.

## People-denominated targets — 2026-09-19

The game model fits **flat capacity from location attributes plus flat capacity
from conditional buildings, multiplied by development**. Its targets are
therefore plain people per location, written by `capacity_targets.py`:

- `capacity_targets_equal_area.csv` (and `_physical.csv`): `natural_capacity`
  (land before represented improvements), `starting_capacity`,
  `maximum_capacity`, `starting_improvement_capacity`, `remaining_capacity`,
  with `reference_people_per_effective_ha` as a diagnostic. No population column.
- `improvement_ledger_equal_area.csv`: one disjoint partition of improvement
  capacity for the start and for the maximum over clearing, management,
  water supply, paddy control, flood bunds, field drainage and polders. The
  typed values sum exactly to starting minus natural and maximum minus natural.
  Transfers, sensitivity bounds and unit columns live in
  `improvement_ledger_diagnostics_equal_area.csv`.

This supersedes the four-value B/M/I interface, the 0.25–5 multiplier bound as
a game quantity, the 1,000-unit minimum base land and the rural game-balance
allowance. The base/multiplier split is still computed and bounded, but only
as a diagnostic normalization; the unit floor is set to zero; the population
based allowance is retired (`rural_balance_diagnostic`, off by default, may
report what it would have added but is never applied).

Fill is calibrated with one global, population-free knob: `game_scale` and
`exponent` of the shared support conversion. `scripts/calibrate_fill.py`
recomputes candidates from the native-grid rasters and evaluates them against
`fill_targets` (settled Old-World rural median fill, rural over-capacity share)
in `FILL.md` / `fill_evaluation.json`. Population enters only that evaluation.
Urban food-importing cities are reported separately and handled later.

### Inheritance activation retired — 2026-09-19

The starting scenario no longer inherits a share of the remaining potential
(`maximum_opportunity_activation` = 0 for every farm-system class). Starting
improvements, and therefore starting building levels, represent evidenced
1300 works only. Before this change 43% of starting improvement capacity was
activated potential, which gave many sparsely populated locations high
starting building levels close to their maximum. The maximum scenario is
unchanged, so the room between start and maximum widens accordingly.

### Grazing land in development — 2026-09-19

`locations_equal_area.csv` gains `grazing_area_ha`: LUH 1300 managed pasture plus
rangeland in physical hectares, capped so cultivated plus grazing never exceeds
a cell (`historical_grazing_fraction.tif`). Only the total is read; HYDE's
pasture/rangeland split is population-density based and stays out. The column
is a land-use quantity for the development target and the (disabled) pastoral
building; it does not enter any capacity target. `pastoral_area_ha` is the
older livelihood-type diagnostic (steppe systems only) and is unchanged.

Development now measures used land, cultivated plus grazing weighted by an
explicit per-climate equivalence (`configs/development.json`), and counts
drainage and polder works as management per used hectare. Wet and upland
pasture economies that cultivation alone scored as unused land (the Dutch coast
at 4-6, Frisia, Ireland, the Alps) are the motivation; arable heartlands are
unaffected, open range in dry and cold climates counts little.

### Development no longer multiplies capacity — 2026-09-20

`capacity_percent_per_point` is 0 in every config. Population capacity is one flat
number, farmland: attribute flats plus improvement buildings, minus commercial farm
buildings. Development enters only the building cap equations as the linear term
`add = { value = development multiply = γ }`, so intensification arrives as extra
improvement levels rather than as a percentage. Development itself is the game's
own starting value (`data/raw/vanilla/start_development_1337.csv`); the derived
land-use formula remains as a diagnostic (`source.kind = derived`). Targets and ledger
units are people directly.
