# Starting and maximum improvement distributions

Run `uv run ha1300 locations`, followed by `uv run python scripts/validate_locations.py`
and `uv run pytest -q`. The third map tab shows starting and maximum population-capacity contributions (effective improvement units × location multiplier) on one shared linear colour scale. The location panel shows these contributions with percentages underneath; raw units remain in the detailed breakdown.
`artifacts/locations/improvement_distribution_equal_area.csv` contains every map
location, including explicit ownability, starting/remaining/maximum units and shares.
Shares are fractions (0–1) in data and percentages in the map.

The three types are clearing, field management and irrigation. They follow the
existing native-grid sequential attribution: additional accessible land at low
input, the management increment, then incremental surface-water support. Their
underlying source assumptions and the shared game calibration remain in force.
These are inferred model contributions, not historical infrastructure surveys.
Drainage, terraces and groundwater cannot be independently identified from these
three components and are not represented as falsely measured separate shares.

Starting and remaining positive contributions are each normalized to their
existing effective-unit budget; maximum is the sum by type. This preserves all
four model values and guarantees each type's maximum covers its starting amount.
Only source-precision negative residues can be removed. Substantive negative
contributions or missing component evidence fail allocation. The original signed
component and rounding ledger is retained.

Positive budgets have shares summing to one. A zero budget has three explicit
zero shares and `no_improvement_budget` status; the UI displays a dash because
a percentage of zero is undefined. This applies to zero-opportunity locations
and non-ownable zones as well; no location is omitted.

Building splitting, costs, bonuses and levels remain deferred. Later subdivision
must partition these contributions, not add drainage or terraces on top of the
existing maximum. Management may require practices or advances rather than a
literal infrastructure building. Maximum remains the currently modeled crop and
management scenario, not every future technology.
