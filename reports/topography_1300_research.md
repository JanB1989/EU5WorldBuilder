# Topography: four global additions

The accepted set is **Rolling Terrain, Valleys, Floodplains and Deltas**. All 22 installed EU5 topography values remain defined. No fifth class is added: the earlier extras either overlap existing terrain, are poorly observable at location scale, or add little useful distinction.

## Data actually used

| Evidence | Release and access | Use | Limits |
|---|---|---|---|
| [EcoTapestry landforms](https://doi.org/10.5281/zenodo.1464846) | Hengl 2018, v1.0; global 250m categorical raster; CC-BY-SA-4.0 | Smooth plains and low hills are candidates for Rolling Terrain | Seven-class product, not the later sixteen-class Hammond map. Modern proxy. |
| [Geomorpho90m](https://doi.org/10.1594/PANGAEA.899135) | Amatulli et al., 250m publication layer; CC-BY-4.0 | Mapped valleys plus immediately adjoining flat floors | Terrain microforms, not a historical survey or complete named-valley atlas. |
| [GFPLAIN250m](https://doi.org/10.6084/m9.figshare.6665165.v1) | Nardi et al. 2019, v1; CC-BY-4.0 | Geomorphic river floodplain footprint | Small catchments, dry environments and high latitudes are incompletely represented. Background is not proof of absence. |
| [Global delta database](https://doi.org/10.1038/s41467-020-18531-4) | Edmonds et al. 2020, Supplementary Data 1; CC-BY-4.0 | Convex hulls from five published points for 2,174 deltas | Modern delta/coastal outlines are uncertain for 1300; population columns are not used. |
| [ETOPO2022](https://www.ncei.noaa.gov/products/etopo-global-relief-model) | Cached NOAA 60 arc-second surface | Broad surrounding relief and a simplified delta elevation screen | Coarser than landform pixels; no claim to resolve narrow gorges or medieval channels. |
| [GLWD v2](https://www.hydrosheds.org/products/glwd) | Existing documented 15 arc-second riverine-settings aggregation | Supplementary positive floodplain evidence | Modern wetland settings omit many drained former floodplains. |

The Esri-hosted Improved Hammond service required a token. It is **not** a production dependency, and the seven-class public EcoTapestry product is not presented as that sixteen-class dataset.

## Representation rules

Classification remains spatial until the final existing GAEZ-to-EU5 overlap. Native 250m categorical rasters are read in strips, converted to binary feature masks and area-averaged to five arc-minute fractions. No categorical overview sampling is used. Each EU5 location retains separate feature and source-coverage fractions.

* Rolling: smooth plains/low hills with 15–180m surrounding relief; at least 50% of location overlap.
* Valleys: geomorphon valley pixels and adjoining flat pixels within four source pixels, with at least 80m surrounding relief; at least 22% floor coverage. This represents a substantial usable valley floor with surrounding slopes, rather than claiming the entire location is flat.
* Floodplains: at least 35% positive geomorphic/riverine coverage.
* Deltas: at least 35% of the published polygon footprint after the simplified ETOPO 0–100m elevation screen.

These thresholds are explicit game representation choices, not numbers measured by the cited papers. Delta > floodplain > valley > rolling is the priority when features overlap. Only ordinary ownable flatland/hills/mountains/plateau locations can be refined. Wetlands remain unchanged except where a mapped delta provides the more specific landform. Salt pans, atolls, wastelands, water and non-ownable zones remain unchanged.

No location receives a synthetic terrain type merely to fill missing source data. The named native baseline is retained in uncovered/unsupported cases. That gives a complete game mask with visible uncertainty, rather than asserting complete scientific coverage.

## Gameplay and artwork

All four new native definitions inherit flatland mechanics in the isolated geography prototype. Agricultural bonuses and building limits remain a later task. Existing native Topography tooltip, concept link and map mode serve the new values. Exact-key vanilla scripts will need an integration pass later.

Four icons were created with the built-in image generator using the installed 64px topography symbols as style reference. Prompts, originals, deterministic alpha preparation and checksums are in `assets/geography_test/topography/generation.json` and `scripts/prepare_topography_icons.py`. No opaque checkerboard reaches the DDS files.

## Reproduction and verification

`uv run ha1300 topography`

`uv run pytest tests/test_topography.py tests/test_geography_test.py tests/test_vegetation.py -q`

`uv run ha1300 geography-test`

`uv run python scripts/audit_topography.py`

The source and parameter manifests bind assignments to checksums. The generated map/assignments derived from EcoTapestry are CC-BY-SA-4.0, retaining the other source attributions. Generated data and global rasters remain ignored. Engineering validation and in-game visual verification are reported separately.
