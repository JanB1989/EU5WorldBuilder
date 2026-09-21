# Global river navigation

`configs/river_navigation.json` controls physical screening, historical overrides, graphical width, minimum tile size, bank preservation and road costs. Run `uv run worldbuilder navigation`, then `uv run worldbuilder geography-test --build-only --export-only`, then `uv run worldbuilder handover`. Constructor consumes the resulting checked navigation contract and owns building balance and gameplay hooks.

The clickable map is `artifacts/river_navigation/index.html`. Its adjacent manifest, tiles, edges, shores and before/after river-effect tables retain evidence, omissions, bisections, restored crossings, connectivity counts and source hashes. Generated maps and downloaded data remain untracked.

## Evidence

Modern [HydroATLAS](https://www.hydrosheds.org/hydroatlas) / [HydroRIVERS](https://www.hydrosheds.org/products/hydrorivers) discharge and [NOAA ETOPO](https://www.ncei.noaa.gov/products/etopo-global-relief-model) relief screen candidate waterways. Defaults require mean flow 500 m3/s and low flow 75 m3/s. Modern hydrology is not medieval navigability: dams, river courses, seasonality, shallow bars and vessel draft remain uncertainties. Missing or poorly registered evidence leaves native rivers. Lower Thames and existing Jiangnan canal corridors receive explicit exceptions.

The [UNESCO Grand Canal](https://whc.unesco.org/en/list/1443) and [ICOMOS evaluation](https://whc.unesco.org/document/128794) support medieval grain transport. Existing mapped southern corridors are included; this export does not invent the complete historical northern canal geometry. The [Canal Museum chronology](https://www.canalmuseum.org.uk/history/ukcanals.htm) places Britain's major canal age much later. [Delfland history](https://www.hhdelfland.nl/over-ons/historie-erfgoed/historie/) supports medieval water management.

Named physical barriers use [Victoria Falls](https://whc.unesco.org/en/list/509), [Niagara](https://www.nps.gov/places/niagara-falls.htm), [Saint Anthony Falls](https://www.nps.gov/miss/learn/historyculture/river-of-hisory-chapter-6.htm), and pre-large-dam descriptions of the [Congo](https://en.wikisource.org/wiki/1911_Encyclop%C3%A6dia_Britannica/Congo) and [Nile](https://en.wikisource.org/wiki/1911_Encyclop%C3%A6dia_Britannica/Nile). These are approximate envelopes, not an exhaustive rapids catalog.

## Geometry and configuration

Source river pixels carry reach/basin identity, discharge and relief. Adjacent selected pixels form short water tiles. Diagonal corners are stitched within the same basin for four-connected game adjacency. Whole tiles use median physical state to avoid one-pixel barriers caused by DEM noise; explicit restrictive overrides win. Width defaults to two pixels, independently of transport balance; supported widths are 1, 2, 3. Minimum water-zone area is 32 pixels, exported as an engine define. Land remains at least 100 pixels, or its original area if already smaller. Undersized channels and lake-contact pieces remain native.

Large riverbank halves retain their original land-location identity. Small fragments may join an adjacent bank within configured size and area limits. Strict single-component land preservation is available but interrupts most long routes, so the default permits a location on both banks. Lost adjacency between distinct locations is restored with explicit crossings; unsafe cases retain native rivers. New hierarchy is water-only and appended after original identities. Ports, discovery and locators follow the raster.

Graph reports distinguish ocean-connected water tiles and inland components. Physical barriers and endorheic basins justify some disconnections; map omissions also interrupt routes and are not presented as historical proof. All fleets can use passable sea zones. Permanent ocean-wasteland barriers were confirmed in the local Thames test; global engine behavior still requires a fresh campaign.

Input and output hashes gate integration. Classifier code/source changes invalidate the evidence cache; raster-code changes invalidate the overlay. `uv run pytest -q` runs the full tests.

The lower Thames has a documented geometry-only override: its verified vanilla river alignment reaches the existing Thames sea zone, while the modern-source alignment ends inland. This is configurable by pixel box and retains the physical/historical evidence separately. It does not create a permanent Thames barrier.
