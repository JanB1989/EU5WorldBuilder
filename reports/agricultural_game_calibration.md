# Broad agricultural-system calibration

The complete location map now uses a shared game calibration. Rural locations
above starting capacity fall from **6,209 to 483** (92.2% resolved), with **no new
rural shortfalls**. Rural provinces above starting capacity fall from **1,003 to
64**. This resolves the majority of the game-map mismatch. It does not establish
that the remaining cases are historically justified, nor validate population
growth or the downstream food economy.

## What changed

**Inherited improvements:** existing regional agricultural-system classifications
set maximum activation fractions of 0.2, 0.4, 0.55 and 0.7 for extensive, rotation,
managed and intensive systems. Multiply these by `h/(h+0.01)`, where `h` is the
reconstructed cultivated fraction. Uncultivated cells receive no additional
inheritance. These numerical values are shared game assignments, not surveyed
medieval infrastructure coverage. The source classifications and historical
extent remain uncertain; HYDE/LUH extent is population-informed evidence.

Activation transfers that share of each remaining clearing, management and water
contribution into the starting state. Physical land and water use stay between
the original starting and simultaneous maximum scenarios. No additional river
water, land, yield or new crop is invented. The maximum river allocation remains
a feasible upper bound for every cell's inherited use; the allocation is not
reoptimized to spend water released by partial activation.

**Game support conversion:** apply the same function to baseline, inherited
starting and maximum support on the native grid:

`G(s; r) = max(s, r × (s/r)^(1/3))`, with `G(0; r) = 0`.

The reference is 1.0 for the existing crop food-system classes and 0.1 for noncrop
classes. These are dimensional game-normalization anchors, not historical yields
or measured people per hectare. The function raises the very low support tail,
preserves order and zeros, and leaves values at or above their reference unchanged.
It does not depend on population, ownership, rank, individual locations or a
location-specific target.

The location multiplier remains exactly unchanged within 0.25–5. Converted
baseline support determines B; converted starting and maximum gains determine
I_start and I_max. The old 1,000-unit minimum-base allowance is retained against
the uncalibrated baseline. Otherwise increasing the baseline could withdraw an
existing allowance and perversely reduce total capacity.

**Base capacity changes too.** This is not solely a starting-infrastructure buff.
The original physical estimates remain in `uncalibrated_*.tif` and companion
location columns. Game capacities must not be presented as newly established
physical food-production estimates.

## Results and attribution

| Rural diagnostic | Before | Current | Weaker conversion |
|---|---:|---:|---:|
| Locations above starting capacity | 6,209 | 483 | 639 |
| Locations above maximum capacity | 1,562 | 319 | 394 |
| Provinces above starting capacity | 1,003 | 64 | 93 |
| Provinces above maximum capacity | 211 | 39 | 53 |

The weaker comparison changes only the exponent to 0.4 and reruns the full
canonical pipeline. It resolves about 90% of starting shortfalls but fails the
chosen 500-case game-coverage gate. It passes engineering validation. The chosen
candidate passes that coverage gate, unchanged-multiplier, no-reduction and
no-new-shortfall checks. Neither candidate is scientifically accepted merely
because its game-coverage counts improve.

Native-grid attribution using the canonical conversion shows:

| Applied change | Rural starting shortfalls |
|---|---:|
| Neither | 6,209 |
| Inherited improvements only | 4,051 |
| Game conversion only | 605 |
| Both | 483 |

Most of the improvement therefore comes from changing the game support scale,
not from discovering missing physical hectares. `game_calibration_attribution.json`
records this calculation and hashes of its published float32 source rasters.

| Rural region | Shortfalls before → now | Starting capacity, millions, before → now |
|---|---:|---:|
| Western India | 134 → 80 | 2.71 → 12.33 |
| Hindustan | 228 → 52 | 16.30 → 48.33 |
| Egypt | 38 → 15 | 3.31 → 5.54 |
| Nubia | 76 → 33 | 1.29 → 6.04 |
| Great Lakes | 73 → 8 | 4.96 → 19.55 |
| East China | 187 → 44 | 69.48 → 155.78 |
| South China | 164 → 5 | 14.18 → 44.64 |
| Japan | 212 → 0 | 15.06 → 69.59 |
| Indochina | 212 → 0 | 13.01 → 81.50 |
| Guinea | 251 → 0 | 1.97 → 21.49 |
| Andes | 297 → 52 | 3.33 → 20.36 |
| France | 19 → 1 | 63.33 → 89.59 |
| La Plata | 119 → 2 | 0.30 → 2.36 |

## Trade-offs and remaining cases

All-ownable starting capacity rises from **817.83 million to 2.358 billion**;
maximum capacity rises from **4.241 to 4.835 billion**. Remaining improvement
room is retained, but more support is available at the start and advantages at
the low end are compressed. No location loses starting or maximum capacity.

For the 8,192 rural locations with starting population below 5,000, median starting
capacity rises from **4,120 to 40,436**. Their 99th percentile rises from about
79,011 to 210,401. These gains are a substantial game-balance trade-off. They
must be considered when balancing free-land consumption and growth; this repo
has not simulated those effects. The population threshold is reporting only,
never a calibration branch.

The remaining 483 rural cases are individually listed in
`artifacts/locations/remaining_rural_shortfalls.csv`. Of these, 319 remain above
maximum. Bijnot, Nawakot, Mugamba, Nduga and Xianju remain major failures. They
are marked unresolved, not silently classified as import-dependent or urban.
Urban shortfalls, evaluated separately, decline from 410 to 76.

## Validation and outputs

- All 20,893 ownable locations have complete positive values; all 28,573 map
  locations are present.
- The four-value identities and signed improvement component ledgers reconcile.
- Source and inherited land/water ordering is checked before aggregation. Shared
  river budgets pass independent conservation checks.
- Source/configuration/code fingerprints and output hashes pass independent
  validation for the main and weaker candidates.
- **137 tests pass**, with eight existing Rasterio pending-deprecation warnings
  and no skips. Generated viewer click, pan/zoom and detail tests pass.
- Main map: `artifacts/locations/index.html`; full data:
  `locations_equal_area.csv`; primary interface: `location_values_equal_area.csv`.
- `game_calibration_evaluation.json`, `game_calibration_locations.csv` and
  `game_calibration_regions.csv` expose all beneficiaries, residuals and gains.

Main fingerprint:
`637f57edc6b251ab0ef818c4c3c2ab805300d4c285ce33903a469762ab83b46d`.
Weaker fingerprint:
`c4dbddfe700edf5ea94c6df0f185c3378c191cea64a9050ac856e704054d8e22`.

## Reproduction

```bash
uv run ha1300 locations
uv run python scripts/validate_locations.py
uv run pytest -q
```

For the weaker run, copy the game-calibration JSON, change
`support_conversion.exponent` to `0.4`, then point a copy of `configs/locations.json`
at that parameter file:

```bash
uv run ha1300 locations --config data/processed/game_calibration_conservative.json --output artifacts/game_calibration_conservative
uv run python scripts/validate_locations.py --config data/processed/game_calibration_conservative.json --output artifacts/game_calibration_conservative
```

The before-state CSV is `data/processed/system_calibration_before.csv`. If that
generated comparison input is absent, first run the same pipeline with
`agricultural_game_calibration` set to `null` into a separate output directory,
then copy its `locations_equal_area.csv` to that path. This regenerates the raw
before-state without a sibling repo or an old source checkout. Input data caches
and the existing acquisition manifest remain required.

No building balancing, game export, live deployment, commit or push was performed.
