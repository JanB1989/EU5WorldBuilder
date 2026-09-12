# Complete EU5 location model contract

Status: scope agreed 2026-09-12; first complete inferred iteration implemented. Historical balance remains provisional. See `location_iteration_01_method.md` and generated delivery checks.

This contract supersedes earlier requirements that excluded cultivated support and EU5 location output, required separate food/water/labour deliverables, or made building implementation a prerequisite. The current objective is one complete location dataset and map owned by HistoricalAgriculture1300.

## Four primary outputs

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
