# Improvement audit 01 — findings and decisions

Completed 2026-09-13. Candidate fingerprint: `70de690f885d3b7624a495f2f22c51d1b5dfd08a48dab5d178487d1bddb487f8`.

The multiplier-bounds change was pushed separately as `0517ef7`. This audit retains all four primary values and every capacity total in both representations exactly as serialized before the audit. Equal-area remains the working game model. No balance adjustment is adopted on the strength of component attribution alone.

## What is now measured

Every one of 20,893 ownable locations has starting and remaining clearing, management and irrigation components, physical land/service diagnostics and a rainfed management-headroom diagnostic. They use the existing native-grid calculation and exact overlap weights. The map shows these components in its collapsed breakdown. The global, regional and provincial tables use the same values.

Clearing receives the low-input return net of displaced livelihoods, management receives the increment to the assigned rainfed system, and irrigation receives the incremental water benefit. The ordering allocates interactions once. Both low and managed yields retain the same assigned rotation, so the management column is not the entire historical benefit of rotations, knowledge or infrastructure. Baseline-access management remains embedded in the preserved base. Negative management components occur in 170 ownable locations and remain visible. Independently rounded float32 source rasters leave at most 0.025 people of residual per location in equal-area units; separate rounding accounts record these within source precision.

## Findings

| Region | Evidence in this candidate | Consequence |
|---|---|---|
| Egypt | 2.308 million of 2.325 million starting improvement support is irrigation. Physical serviced area increases from about 280,134 to 282,231 ha at maximum, despite cropped area increasing from 535,031 to 761,099 ha. | The bottleneck is water service in this geometry/seasonal allocation, not a low multiplier alone. Audit Nile land registration, seasonal demand, storage and command constraints before increasing maxima. These hectares describe the modeled game footprint, not a verified historical Egyptian total. |
| Indochina | Of 111.862 million remaining support, 110.693 million is cultivation expansion at assigned management, and 1.170 million is irrigation. Physical cropped area expands from 3.26 to 47.14 million ha. | The broad PNV/relief clearing allowance is the first maximum constraint to replace with crop/terrain suitability evidence. More irrigation productivity will not solve this result. |
| France | Starting components: 12.473 million clearing, 58.959 million management, about 0.001 million irrigation; base 2.302 million. The physical-area counterpart has 34.086 million total support, versus 73.735 million after the chosen equal-area normalization. Modeled added dry cropland averages about 1.945 net people per physical hectare. | Large management share alone does not establish an excessive historical yield. Separate equal-area scaling and inherited cultivation from actual yield error. Keep equal-area as requested; do not cut management merely to fit population. |
| Southern versus eastern China | Candidate-area-weighted active rotation fractions are 0.375 versus 0.572. Existing Southwest Chinese uplands rules use extensive management/fallow, including ecological units containing wet-rice alternatives. | The management/fallow assignment remains the first targeted historical-evidence audit. Broad ecological classification is not sufficient evidence for relabeling all southern China. |
| Mongolia | Base 3.466 million of 3.484 million starting support (99.5%); about 80% of modeled physical area is assigned a pastoral food system. | Starting structure meets the desired pastoral pattern. Remaining support still grows by 2.524 million, so the assumption that steppe has little agricultural expansion is not established and needs its own feasibility check. |

## Important correction to maximum interpretation

The existing maximum adds clearing and irrigation with crop, input position and rotation fixed. It does not activate further management improvements, drainage or terraces as independent mechanisms. These effects may be embedded in existing land/productivity, but are unquantified separately. The output must not be described as a complete maximum over every future technology.

The same audit also shows why the current multiplier is not a universal improvement-return estimate: 20 ownable locations have a multiplier of at least four and effectively no remaining support. This is not inherently an error (the modeled opportunity can already be used), but productivity and remaining opportunity must stay separate.

## Next changes supported by this diagnosis

1. Resolve Indochina's existing clearing-feasibility prior with crop-specific suitability and terrain constraints, while retaining dated starting cultivation and frozen base support.
2. Trace Egypt's seasonal water allocation and mapped cultivated/served footprint before changing water coefficients or adding storage.
3. Refine southern Chinese cultivation/rotation assignments using evidence that distinguishes valley/paddy systems from upland analogues.
4. Reassess France only after distinguishing agricultural yield from equal-area representation and inherited cultivation. Its population ratio is not a fitting target.

No global productivity buff, arbitrary maximum increase, new fishing contribution or change to the 0.25–5 multiplier bounds was introduced.

## Reproduction and validation

- `uv run ha1300 locations`
- `uv run python scripts/validate_locations.py`
- `uv run pytest -q`

Results: 96 tests passed, six existing Rasterio deprecation warnings, strict delivery validation passed, all ownable component accounts complete. Before/after comparison confirms every serialized primary value and capacity unchanged. Viewer interaction is checked with the generated JavaScript in the existing mocked canvas test, not through a live browser. Generated outputs include `IMPROVEMENTS.md`, `improvement_components_equal_area.csv`, `improvement_focus_cases.csv`, `improvement_{province,region,macro_region}_audit.csv`, and `improvement_audit.json`. The latter and the main manifest bind this evidence to the candidate fingerprint.

This completes the diagnostic iteration; it does not certify the global historical balance.
