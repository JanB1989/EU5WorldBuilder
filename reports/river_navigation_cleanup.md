# River navigation cleanup — September 2026

The original native maximum river level is retained on every land location. Converted water is removed from `rivers.png`; a minimal ordinary bank pixel restores a lost maximum. No duplicate gameplay modifiers are needed. This preserves the native engine interface used by river bonuses and building triggers, subject to fresh-campaign confirmation of isolated pixels. The numerical raster audit passes globally.

Physical screening is not a historical navigability survey. Modern HydroATLAS discharge and coarse DEM gradient remain proxies. Tropical thresholds are now configurable separately (mean 2,000 m³/s and low flow 250 m³/s by default). This is a conservative all-fleet conversion policy; large tropical rivers remain usable, with a more expensive baseline route profile. It does not imply that premodern people could not navigate smaller rivers with local craft.

The complete Khone Falls navigation barrier is documented by the [Mekong River Commission](https://archive.iwlearn.net/mrcmekong.org/RAK/html/1.15.3_river_navigation.html). The [World Bank Congo transport study](https://documents1.worldbank.org/curated/en/684111495448714514/pdf/WP-TradeFacilitationEnglishmainweb-PUBLIC.pdf) and [DNIT Solimões description](https://www.gov.br/dnit/pt-br/assuntos/aquaviario/antiga-daq/hidrovia-do-solimoes) support preserving extensive navigation on major tropical rivers, while allowing for barriers and seasonal/infrastructure limitations. These are physical checks, not evidence of 1300 ports or modern navigation works.

Short gaps are repaired only along existing native river pixels with qualifying endpoints in the same basin. A bounded six-pixel coastline alignment repair can reconnect a lowland river outlet to the game sea. It cannot cross lakes or wasteland. All repairs are recorded. Missing historical channels, lake interfaces, and conservative land/crossing exclusions remain limitations; no claim of full global historical route reconstruction is made.

New map ports have passable water coordinates and bank adjacency; geography templates have a configurable harbor floor while retaining better existing values. Original valid ports remain in place (one port per location). Constructor owns gameplay road costs, works hooks and the live in-game diagnostic map.

## Validated export

- tiles: 2406
- tile_states: {'navigable': 1735, 'improvable': 473, 'barrier': 198}
- edges: 7980
- crossings: 1199
- ports_changed: 2433
- preserved_river_pixels: 1702
- ocean_connected_passable_tiles: 433
- passable_components: 616
- Bounded mouth alignment repairs: 52

337 World Builder tests pass. A full restart and new campaign are required; in-engine display and isolated-pixel recognition are not covered by the raster tests.
