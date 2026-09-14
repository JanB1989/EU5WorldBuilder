# Complete water-management attribution

The equal-area EU5 map now distinguishes **water supply, paddy water control,
flood embankments, field drainage, and coastal drainage/reclamation**. Each has a starting
and maximum contribution for every location. All displayed contributions are
**effective improvement units × the location multiplier**, in people supported.
Maximum includes starting works. This is an attribution of our existing game
capacity estimate, not a new reconstruction of physical hectares or building counts.

## Evidence and the five mechanisms

| Map category | Physical and historical evidence | Later building counterpart |
|---|---|---|
| Water supply systems | Existing seasonal rainfed/irrigated yield differences, HYDE 1300 irrigation, river access and shared basin water budget. Keeps the previous irrigation contribution exactly. | `irrigation_systems` |
| Paddy water control | Historically assigned wet rice, terrain access and GLWD rice-paddy settings. Field bunds, levelling and controlled retention/drainage can matter even in rainfed rice. Small paddy bunds are included here, not counted again as flood embankments. | `irrigated_rice_paddies` (broaden its name to Paddy water control) |
| Flood embankments | GLWD riverine/floodplain classes and major deltas; reconstructed 1700 wetland settings near rivers. Embankments and controlled flood basins account for part of existing field preparation and management. | `bund` |
| Field drainage | Remaining inland wetland/peat/flood-prone settings after other categories are partitioned. Agricultural access and existing support bound the gain: wetland presence alone does not create farmland. | `field_drainage` |
| Coastal drainage / reclamation | Coastal wetlands and low coastal terrain with former wetland evidence or fine-resolution below-sea-level land. Enclosure and drainage are treated together, rather than each receiving the whole benefit. This is a broad reclamation analogue, not proof that Dutch-style polders existed at every assigned coast. | `polders` |

The [GLWD v2 dataset](https://www.hydrosheds.org/products/glwd) provides global
15-arcsecond fractional wetland classes. We use class fractions, not rectangular
regional overrides or the dominant-class map. Its [methods paper](https://essd.copernicus.org/articles/17/2277/2025/)
describes a contemporary composite, approximately 1990–2020. It does **not** map
medieval infrastructure. The [global wetland-loss reconstruction](https://doi.org/10.5281/zenodo.7616651)
adds a 1700 wetland-extent proxy, including settings subsequently lost to land use.
Its [paper](https://www.nature.com/articles/s41586-022-05572-6) does not reconstruct
1300. Its HYDE/GLWD dependencies are recorded as related evidence, not independent
validation of our land-use inputs.

FAO describes [basins and bunds](https://www.fao.org/4/s8684e/s8684e03.htm),
[bunded rainfed lowland rice](https://www.fao.org/4/ai408e/ai408E05.htm), and
[agricultural drainage](https://www.fao.org/4/R4082E/r4082e07.htm).
These sources support the mechanisms; they do not supply medieval global effect
percentages. Historic systems such as [Sangyuanwei](https://icid-ciid.org/award/his_details/129)
and [Kinderdijk](https://whc.unesco.org/en/list/818/) show why enclosure, conveyance,
retention and drainage need separating from additional water supply. We do not
backdate their complete later footprints or later pumping technology to 1300.

Reservoirs, qanats, aqueducts and named regional monuments are **not separate
chosen map types**. Their independently available storage/groundwater resources
are not established in the current surface-water calculation. They can later
implement a share of the supply target without creating a second water budget.

## Reproducible allocation

1. Average native GLWD percentage pixels into the matching 5-minute grid with
   source overviews disabled. Preserve coverage masks. Reconstruct 1700 wetland
   fractions from km² and their 0.5° cell area; retain that coarse resolution's
   uncertainty when assigning its 5-minute children. Small negative source
   ensemble areas are clamped to physical zero and counted in the manifest.
2. Combine overlapping contemporary and older wetness evidence with a maximum,
   not a sum. Paddy settings require historically allowed wet rice. A modern
   paddy cell cannot introduce an unavailable medieval crop.
3. Partition physical setting weights in order: paddy control, coastal
   reclamation, flood control, remaining drainage. Each next type receives only
   the unassigned share. Water supply remains the already reconciled incremental
   supply benefit, independently of this partition.
4. Reassign a share of **existing** clearing and management support, after the
   shared game conversion and before location aggregation. Coefficients are
   shared assumptions in `configs/water_management.json`, not observed fractions:

| Type | Clearing transfer at full setting | Management transfer at full setting |
|---|---:|---:|
| Paddy control | 25% | 50% |
| Flood embankments | 40% | 25% |
| Field drainage | 50% | 25% |
| Coastal drainage / reclamation | 75% | 40% |

5. Starting transfers also use the existing historically assessed farming-system
   class: extensive 0.35, rotation 0.65, managed 0.85, intensive 1.0; unknown 0.25.
   Previously researched maintained-field refinements take precedence. These are
   conservative inference weights, not dates or measured construction shares.
   The starting improvement budget itself already reflects dated land use and
   the inherited-system scenario. Population does not enter this calculation.
6. Remaining transfers use full system effectiveness, within the existing
   remaining opportunity. Maximum for every subtype is starting plus remaining,
   so no existing works disappear at the maximum. Aggregate the fine-grid
   contributions by exact EU5 overlap, then apply the same equal-area conversion.

Missing source coverage uses an explicit low-weight climate/terrain wetness
analogue, with affected shares in the ledger. A zero subtype value is a completed
model result, not a missing record. Small-island/coastline transfers follow the
existing labelled terrestrial completion. Coastal distance is an approximate
5-minute-grid screen; the 1700 reconstruction does not gain finer precision by
resampling. Native ETOPO 60-second subcells between −10 and 0 m, screened by low coastal mean elevation and distance, also identify already-reclaimed settings missing from wetland inventories. The 75 km grid-distance screen is approximate and deliberately broader than the actual coast: at high latitude, a grid step overstates east–west distance. Inland negative elevation alone is insufficient. Modern subsidence and later reclamation mean this is a dependency proxy, not the shoreline or construction footprint of 1300. No province rectangles are used.

## Conservation and uncertainty

The five subtypes sum to water management. Remaining clearing + remaining field
management + water management sum to the original improvement contribution at
each stage. Multiplier and total starting/maximum support remain unchanged; see the superseding boundary refinement below for base reclassification. No new water withdrawal or physical land is created.

The numerical division between clearing, management and water control is **inferred**.
Modern wetland geography and 1700 reconstruction cannot establish the location
and age of every medieval ditch. Half and 1.5× transfer-strength experiments show
attribution sensitivity; these are not statistical confidence intervals. Upper
sensitivity fractions saturate at each source budget, and all overlap remains
partitioned. Better historical evidence can revise this allocation without
fitting total capacity to population.

The legacy `*_irrigation_improvement_*` fields remain a compatibility alias for
**water supply only**. They must not be added to `*_water_management_improvement_*`.
Original `*_clearing_capacity` and `*_management_capacity` retain the source
ledger before reassignment; use `*_improvement_capacity` for the new displayed
breakdown. Units and shares remain available for later building balancing.

## Reproduction and delivery

From the repository root:

```sh
uv run python scripts/prepare_water_management.py
uv run ha1300 locations
uv run python scripts/validate_locations.py
uv run pytest -q
```

Open `artifacts/locations/index.html#water`. The **Improvement mix** tab shows
clearing, management and aggregate water management; the **Water management**
tab shows ten subtype maps. The overview shares one linear colour scale. All ten water subtype maps share one logarithmic scale, preserving cross-type comparison while making smaller drainage contributions visible. Paired starting/maximum maps are directly comparable. Click a location for
the same multiplied contributions and sensitivity range.

The full water ledger, global/regional totals, source hashes and coverage checks
are delivered alongside the HTML. Engineering completion means every selected
type is mapped and accounts reconcile. It does not turn these inferred causal
shares into observed medieval infrastructure inventories. Building counts,
costs, limits and game deployment remain deferred.


## Superseding boundary refinement (baseline commit 87eef4a)

The base is no longer frozen. A transfer requires all three signals: positive
baseline crop support over displaced natural livelihoods, reconstructed 1300
cultivation overlapping that baseline-access cropland, and a paddy, drainage or
coastal dependency setting. The eligible share is calculated on the native grid
and applied to the same share of the converted game baseline. Natural livelihood
support stays in base. Natural floodplain wetness alone and the hypothetical
irrigated-yield scenario cause no baseline transfer.

Dependency shares are explicitly inferred: paddy control 65%, inland drainage
50%, coastal drainage/reclamation 80% of their exclusive eligible setting.
Water supply and flood embankments receive zero base transfers. FAO's basin and
rainfed-lowland rice descriptions support the distinction between cultivated
bunded fields and naturally wet land; UNESCO's Kinderdijk account supports
maintained drainage as part of agricultural access. Neither source provides the
numerical coefficients used here. Modern subsidence remains a limitation.

The field-management transfer shares also change from 50% to 70% for paddy
control, 25% to 35% for flood control, 25% to 40% for drainage, and 40% to 60% for
coastal reclamation. Clearing transfer shares stay fixed. These are shared
attribution candidates, not population fits or a targeted global percentage.

Base transfers are clipped proportionally only at final location normalization
to preserve the existing 1,000-unit equal-area base floor. The original physical
baseline used to calculate the game's floor allowance is retained, so this
cannot create extra capacity. The same amount leaves base and enters both
starting and maximum improvements; remaining opportunity and the multiplier
stay fixed. Raw base requests, applied amounts and the pre-transfer baseline
are retained in the ledger. In the intermediate three-component ledger, the
transfer passes through management before being fully assigned to its water
subtype; it must not be counted as extra field-management support.

The half/1.5x attribution sensitivity brackets vary transfers from improvements;
they hold this base-boundary candidate fixed. They are not confidence intervals
for the historical base split. `water_boundary_comparison.csv` and
`water_boundary_validation.json` compare every location to the pushed baseline,
checking preserved capacities, unchanged remaining opportunity and exact
component transfer identities. The older inheritance audit restores these
recorded transfers before testing its original protected base/maximum values;
unexplained changes still fail.


This pass does not rebrand modeled natural livelihood support as irrigation.
Consequently, locations whose baseline is almost entirely non-crop support can
remain base-heavy. Resolving that would require reviewing the underlying
livelihood estimate/game conversion, not another transfer coefficient.
