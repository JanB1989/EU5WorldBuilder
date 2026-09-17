# EU5 World Builder

## World-data ownership

This repository, formerly HistoricalAgriculture1300, owns the evidence-based
location attributes and geographical datasets: climate/winter, vegetation,
topography, soils/fertility, river/coast/lake attributes, capacity modelling,
maps, validation and isolated geography test-mod exports. Production gameplay
integration, building balance and release deployment belong to the Constructor.
The canonical checkout is `/home/jan/development/EU5WorldBuilder`; an old-path
alias preserves existing local map links. Preserve historical source identities
and manifests rather than rewriting them to match the repository name.

## Complete location outputs

Own and build the complete EU5 location dataset and location map described in `reports/location_model_contract.md`. This contract supersedes older per-hectare-only project boundaries.

Each location needs base effective cropland, a full capacity multiplier, starting improvement effective cropland, and maximum improvement effective cropland (including starting improvements). No finished iteration may omit locations or required values. Evidence-based estimates with visible uncertainty are allowed; missing evidence is not silently zero.

Keep physical calculations on the fine grid until the final overlap-based location aggregation. Preserve hectares and water budgets separately from effective cropland. Starting population is contextual, never a fitting target for physical or historical estimates. User-authorized exception (2026-09-14): the final equal-area game output may add an explicitly recorded rural balance allowance so population/capacity is at most 1.5. Keep pre-allowance values, urban locations, physical accounts, multipliers and remaining improvement capacity unchanged. Do not describe this allowance as historical farmland or infrastructure.

Food/yield/water calculations are supporting stages, not separate project objectives. Building splitting and balancing, game export/deployment and standalone economic/labour projects are deferred.

## Ownership and preservation

Own the required code, configurations, evidence manifests, acquisition/import logic and geometry mapping here. Completed workflows must not depend on a sibling project's runtime or generated capacity model. Existing caches may be imported with hashes, licenses, source identity and transformations recorded. Never modify external caches as part of this project.

Preserve existing dirty work. Archive superseded experiments when useful; do not delete prior evidence or unrelated work for tidiness. Generated data remain ignored when appropriate; do not redistribute restricted source data.

## Validation

Use `uv run worldbuilder --help` for the CLI and `uv run pytest -q` for tests. `ha1300` remains a supported alias. Add the canonical complete location-build workflow within this CLI. Coverage, accounting and scientific confidence must be reported separately. A complete estimate with uncertainty is acceptable as an iteration; an incomplete output is not.
