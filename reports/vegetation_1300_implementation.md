# Global vegetation prototype, 1300

Implemented 2026-09-14 in HistoricalAgriculture1300 and Land Clearance Geography Test.

## Scope and result

All 20,893 game-defined ownable locations have a complete vegetation assignment. All seven original vegetation values remain available. Nine additional native values pass the preselected minimum of 25 ownable locations. No population, capacity or building-level fitting was used.

The source model retains 18 fractional classes. Mangroves (22 dominant ownable locations) and saltmarsh (2) are retained in the CSV as components and candidate labels, but map to Swamp and Marsh in the native UI. The threshold is a game-classification choice, not a claim these ecosystems are globally unimportant. Their narrow coastal extent often does not dominate an entire EU5 location.

## Data and construction

- SAGE potential natural vegetation, 5 arcminutes: 15 formations, including dense/open shrubland, savanna, tundra and forest formations. The cached README documents its DISCover/model reconstruction. This is a modern counterfactual, not observed 1300 vegetation. Source: https://sage.nelson.wisc.edu/data-and-models/datasets/global-potential-vegetation-dataset/
- HYDE **3.4**, dated 1300: cropland in square kilometres divided by spherical grid-cell area. This local source differs from the HYDE 3.2 lineage used by LUH2; the products are related, not independent corroboration. Version and units are checked during preparation.
- LUH2 v2h, 1300, quarter-degree primary/secondary forest and grazing fractions. Forest rangeland and managed pasture contribute cleared/open land; grazing natural nonforest does not create additional clearance. Secondary forest is not reclassified as woodland merely because it is secondary. Source: https://luh.umd.edu/faq.shtml
- GLWD v2, 15 arcseconds, approximately 1990–2020: separate fractional forested/nonforested wetlands, peatlands, mangrove and saltmarsh layers. Rice paddies, open water and ephemeral wetland categories are not relabelled as natural marsh. Native 20-by-20 reduction preserves fractional percentages; source overviews are disabled. CC BY 4.0. Source: https://www.hydrosheds.org/glwd-details
- Wetland-loss reconstruction, 1700–2020, half-degree ensemble mean: use the difference between its own 1700 and 2020 remaining-natural-wetland estimates. Do not subtract fine GLWD cells from a coarse 1700 value. Additional wet ground is allocated within each half-degree cell using wet/flood-setting evidence and remaining non-crop/non-pasture land. Its source-cell budget is conserved subject to that available-land cap. The inferred forest/open split follows surviving local wetlands or the natural forest formation. Source metadata and attribution are cached in data/raw/water_management/wetloss.json.

Modern GLWD wetland fractions are conditional on mapped land near coastlines. The historical loss quantity is a fraction of the complete half-degree geographical cell; it is allocated within the same grid and capped by the land-use budget. Coastal geometry and source masks remain an approximation.

The 1700 proxy cannot prove that a wetland existed in 1300. Natural formations and wetland types are modern approximations; pollen datasets were researched but have not been used as independent validation. No historical precision beyond the source resolution is claimed.

## Classification

Historical crop and converted pasture fractions take priority. Remaining wet fractions and upland natural formations fill the rest without double counting. A LUH forest-landscape fraction below 0.65 identifies an open wooded mosaic within forest formations, rather than measured canopy closure. Farmland becomes the representative class at a 0.35 location share; wet vegetation takes precedence at a combined 0.30 share. Otherwise the largest component wins. These are shared game-classification thresholds, with sensitivity reported, not measured biome boundaries.

The native 5-minute fractions are retained until the final registered EU5-location overlap aggregation. Source gaps use a consistent nearest natural-land donor across all component fractions and are flagged by source coverage. Non-ownable land outside the settlement geometry retains its native vegetation; water remains explicitly water.

## Engineering and uncertainty

The focused suite has 19 passing checks, including source-budget conservation, no double counting, distinct formation mappings, nested native template preservation, parent-effect inheritance, soil/fertility regression and guarded sync.

The global audit checks all ownable locations independently against game default.map, fractional conservation, exported template parity, all nine DDS icons and native-parent mechanical parity. Validation and regional counts are in artifacts/vegetation. All files are bound to source/config/code hashes.

1,189 ownable locations have less than 80% direct natural-source coverage. 8,758 are flagged low confidence from missing coverage, substantial inferred restored wetland, or a mixed landscape with no component exceeding 50%. Wetland-threshold sensitivity is material: changing 0.30 to 0.40 changes 1,129 candidate classifications. This prototype is complete and reviewable, not a precise historical vegetation survey.

## Game integration

Use the EXISTING Geography > Vegetation map mode. New values are actual native vegetation definitions, so the existing attribute icon, native tooltip and blue Vegetation concept link are retained. Existing values keep their mechanical definitions; only their map colors are aligned with the report. New values inherit a documented vanilla parent. No new balancing effects, capacity fitting or monthly processing were added.

Custom art is generated against the original EU5 icon reference and converted through the existing chroma-key/RGBA/DDS pipeline. Icons are 64px. Native *_big.dds files are wide scenery strips, not square icons: those retain appropriate parent scenery. Sparse formations use the native plains strip.

The four Swedish clearing tests remain explicit template overrides (Norrtalje, Tierp, Heby, Enkoping); the exported ledger contains modeled and applied values. Limits remain 2/5/4/7. Soil and Fertility remain intact.

Exact-key vanilla scripts do not automatically recognize new types as their parents. This is the isolated geography test mod, not a balanced compatibility release. Restart the game and begin a new campaign to load the changed templates. Running-game rendering is a user verification step; build and file parity do not prove engine rendering.

## Reproduce

```
uv run ha1300 vegetation
uv run pytest tests/test_vegetation.py tests/test_geography_test.py tests/test_soil_types.py tests/test_fertility.py -q
uv run ha1300 geography-test --build-only
uv run python scripts/audit_vegetation.py
uv run ha1300 geography-test
```

The final command builds and syncs only the configured Land Clearance Geography Test folder. No constructor live deployment or Git push is part of this change.

## Active ownable-location distribution

| Vegetation | Locations | Native mechanical parent |
|---|---:|---|
| Desert | 891 | desert |
| Sparse | 54 | sparse |
| Grasslands | 2,459 | grasslands |
| Farmland | 931 | farmland |
| Woods | 136 | woods |
| Forest | 1,682 | forest |
| Jungle | 1,806 | jungle |
| Scrubland | 1,214 | sparse |
| Thicket | 929 | woods |
| Savanna | 2,127 | grasslands |
| Tundra | 353 | sparse |
| Coniferous Forest | 1,893 | forest |
| Mixed Forest | 2,064 | forest |
| Dry Forest | 870 | woods |
| Marsh | 2,241 | grasslands |
| Swamp | 1,243 | forest |


## In-game colour correction

The initial in-game check exposed black map and legend colors. error.log explicitly rejected normalized decimal RGB tokens in common/named_colors/ha1300_vegetation.txt. EU5 requires integer 0–255 RGB channels here. The exporter now emits integer channels, with a regression check and compiled-palette audit for all16 active types. The original clearing-test color already used a native valid entry. No vegetation assignments or effects changed in this fix. A full game restart is needed to reload named colors; visual confirmation remains an in-game check.


## Retired clearing-trial attributes

The artificial Forest — Clearing Test and Continental — Clearing Test values, their bonuses, icons, trial building and four location overrides are no longer emitted by the shipped config. Sync removes their previously managed files. Norrtalje, Tierp, Heby and Enkoping now receive their modeled vegetation and native climate/topography. The older trial descriptions above document history, not the current build. Restart EU5 and start a new campaign after removing these template types.
