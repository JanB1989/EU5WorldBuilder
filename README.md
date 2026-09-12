# HistoricalAgriculture1300

This repository owns the reconstruction of a **complete EU5 location capacity dataset and location map**. Fine-grid evidence and calculations are retained until the final location aggregation.

## Deliverable

Every location in the frozen EU5 location inventory must have four finite values:

| Field | Meaning |
|---|---|
| `base_effective_cropland` | Baseline effective cropland, excluding improvements represented in the improvement contribution |
| `capacity_multiplier` | Population support per effective cropland unit |
| `starting_improvement_effective_cropland` | Contribution of improvements present at the starting date |
| `maximum_improvement_effective_cropland` | Total feasible improvement contribution, **including** starting improvements |

`starting_capacity = capacity_multiplier * (base_effective_cropland + starting_improvement_effective_cropland)`

`maximum_capacity = capacity_multiplier * (base_effective_cropland + maximum_improvement_effective_cropland)`

Remaining opportunity is maximum improvements minus starting improvements. The multiplier is the full factor (2.0, not a native +100% percentage). Effective cropland units are game-model support equivalents, not claims of measured physical hectares.

The map must expose these four values, starting/maximum capacity and remaining opportunity. Starting population is contextual comparison data, never an input used to fit capacity.

Read the [model and completion contract](reports/location_model_contract.md).

## Scope

Yield, historical crops, land cover and water calculations are internal supporting stages. They serve this single location-output objective. Building types, counts, costs and implementation are deferred. Deployment, autonomous economic simulation and separate labour-research deliverables are outside the current work.

The repo must own required code, configuration, evidence records, source manifests and geometry mapping. Sources may be acquired or imported from existing caches with provenance; a completed pipeline must not require a sibling project's generated model or runtime. Large downloaded and generated files remain ignored as appropriate for their licenses and size.

## First complete iteration

The first location iteration is available at [artifacts/locations/index.html](artifacts/locations/index.html).

- All **28,573 game-map zones** have four values: 20,929 modelled land locations plus 7,644 explicitly classified nonsettlement zones with zero settlement capacity.
- [Four-value dataset](artifacts/locations/location_values.csv), [full ledger](artifacts/locations/locations.csv), [validation](artifacts/locations/validation.json), and [manifest](artifacts/locations/manifest.json).
- [Method, assumptions and reproduction](reports/location_iteration_01_method.md).

This is a complete inferred iteration, **not accepted historical balance**. Regional shortfalls, excessive frontier support and low-confidence maximum assumptions are reported for refinement. Food and water maps remain internal supporting evidence.

Existing work is preserved. The [previous research README](reports/archive/pre_location_contract_README.md) records superseded assumptions and older commands.

## Build and validate

```bash
uv sync --group dev
uv run ha1300 --help
uv run ha1300 locations
uv run python scripts/validate_locations.py
uv run pytest -q
```

`ha1300 locations` generates the complete grid-to-location dataset and map from the owned input pack and supporting grid products. See the method for acquisition/import and supporting-product rebuild commands. No building implementation or deployment is performed.
