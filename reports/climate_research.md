# Climate and winter geography prototype

## Decision

Keep the existing Climate attribute and its native winter-severity row. No moisture-regime attribute, separate winter chip, hidden combinations or duplicate climate labels. Eighteen climate types retain all eight original keys and add ten readable distinctions. All 30 source classes have an explicit crosswalk in `configs/climate.json`.

Winter is a fixed property of each engine climate definition, not an independently assigned location field. This iteration deliberately uses representative native game levels. It merges rare distinctions instead of claiming precise local winter simulation. Original keys retain their effects and winter levels. Consequently, the native Mediterranean `none` and Cold Arid `mild` are game conventions; they should not be read as claims that these climates never freeze or never have harsh winters. New types inherit documented parent mechanics. Steppe clones restore precipitation that their desert parents disable. Subarctic inherits Continental and does not introduce permanent winter.

## Source and historical meaning

Beck et al. (2023), *High-resolution (1 km) Köppen–Geiger maps for 1901–2099 based on constrained CMIP6 projections*, Scientific Data 10, 724. https://doi.org/10.1038/s41597-023-02549-6 ; https://www.gloh2o.org/koppen/ . CC BY 4.0.

Downloaded the linked V3 archive, Figshare article 21789074 version 2, file 61012822, MD5 `7fc2f5a15d4f5fe0ce59c9a9b502aa09`. The archive includes the publisher's numeric legend. We use only the earliest observed-climatology period, 1901–1930, at 30 arc seconds. Source archive, article metadata, SHA256 and transformations are retained locally. No projection or 1991–2020 map is substituted.

**This is an early twentieth-century geographic proxy for 1300, not a reconstructed medieval climate map.** No evidence supports simply cooling all cells by a single amount or tuning rainfall to match population, so neither is done. Broad zones are useful for a playable geography test; medieval boundaries, marginal growing climates and monsoon extent remain uncertain.

CHELSA-TraCE21k offers a real alternative for historical reconstruction: monthly temperature minima/maxima and precipitation at kilometre scale and centennial steps. https://www.chelsa-climate.org/datasets/chelsa-trace21k-centennial ; https://doi.org/10.5194/cp-19-439-2023 . We have not downloaded or classified its medieval time slice, and do not claim to have applied it. Such a replacement requires checking time coordinates, temperature/product units and precipitation biases before recomputing classifications. The game's categories and exporter do not depend on the chosen period.

## Aggregation and coverage

Each 10×10 block of 1 km input pixels becomes cosine-latitude weighted fractions for all thirty source classes on the native 5-minute analysis grid. No categorical resampling or early majority vote discards mixed climates. Existing spatial overlap weights then combine those fractions within each EU5 location. Source classes are grouped into the configured readable categories before the final winner is selected. All thirty source shares, dominant fraction and source coverage are exported.

No-data/ocean class 0 is excluded from the climate denominator. Locations with no observed land overlap retain their native climate, explicitly marked as inferred. Every ownable location still receives a value. Non-ownable zones retain native definitions. Low source coverage and highly mixed climates are flagged independently of the 1300 temporal limitation, which applies everywhere.

The smallest new class is Subpolar Oceanic (24 ownable locations), mainly cool maritime fringes. It is retained because its short growing season differs meaningfully from Oceanic; no threshold was adjusted to inflate its count.

## Scope and reproduction

`uv run ha1300 climate` builds the assignment table, map, winter map and manifest. `uv run ha1300 geography-test` builds and synchronizes only the existing isolated geography test mod. Existing soil, fertility, vegetation and topography assignments are preserved. The native Climate map mode, icon frame and linked Climate tooltip provide the interface; there is no extra UI slot or recurring event.

The capacity model and agriculture balances are not recalibrated here. Exact-key vanilla script conditions may need parent-family integration before production deployment. Engineering checks verify completeness and export correctness; only an in-game restart/new campaign verifies actual engine display.

## Maximum-winter map correction

The shipped native `winter` map uses `color_mode = winter`, a monthly refresh, and a localized description explicitly referring to winter currently experienced. It is seasonal weather, not the climate maximum. At the reported paused campaign start its legend marked black as No Winter. The geography prototype now replaces only that map definition with explicit climate-based categories, calls it Maximum Winter Severity, and uses four non-black integer RGB colours. The four climate limits and the engine weather simulation are unchanged. Native `winter_power` and all other map definitions remain intact. No new location attribute or recurring event is introduced.
