# Native river-size export

This diagnostic mod injects a separate numeric marker into each native
`river_flowing_through_1` through `river_flowing_through_5` static modifier.
At game start it records all five active marker values, their maximum level,
river presence, lake adjacency, location size, and schema version 2.
It does not change the original gameplay effects.

Deploy this folder to a separate River Exporter mod and enable only that mod.
Start an observer game with EU5's `-debug_mode` launch option and save at the
start date. Debug mode produces a readable text save. The currently available
Rakaly fallback behind the existing savegame tool rejects EU5 1.3.11 binary
saves with `invalid header`; it must not be treated as a successful decode.

Acquisition uses the existing `eu5gameparser` save reader through the constructor
utility (run in its existing uv environment):

```sh
uv run python tools/export_river_attributes.py /path/to/diagnostic.eu5 /path/to/HistoricalAgriculture1300/data/raw/river_attributes/export.json
```

Then, in this repository:

```sh
uv run ha1300 river-import
uv run pytest -q tests/test_river_attributes.py
```

The model-side import consumes the acquired JSON independently. Outputs are
`artifacts/rivers/locations.csv`, `locations.parquet`, and `report.json`.
Original game data and saves remain local; do not redistribute them.

## First verified export: EU5 1.3.11, 1337.4.1

All 28,573 game zones have schema and size values, including all 20,893 ownable
locations. Every river location has exactly one active size modifier. Presence
matches positive size in every zone. No missing records were filled with zero.

| Native level | Ownable locations |
| --- | ---: |
| 0 — No river | 10,410 |
| 1 — Small river | 7,872 |
| 2 — Minor river | 0 |
| 3 — River | 971 |
| 4 — Major river | 0 |
| 5 — Great river | 1,640 |

The game defines all five positive levels and its native tooltip pairs
`HasRiverSizeN` with `river_flowing_through_N`. **Five supported levels does not
establish that all five occur on the installed map.** This export observed only
1, 3 and 5. Keep 2 and 4 as valid categories with zero observed counts; do not
renumber or interpolate them. This establishes active modifier categories, not
the engine's undocumented bitmap-to-size algorithm. Direct in-game comparison
of a claimed level-2/4 location would be needed to resolve any discrepancy.

Example native effects: London 1, Cologne 3, Cairo 3, Paris 5, Enkoping 0.
The bitmap's palette index is not a river level. See the reproducible bitmap
audit below for the observed mapping and its important junction-marker anomaly.

The current attribute fit has not been silently replaced or rerun.

## Bitmap audit (installed 1.3.11 map)

Run in HistoricalAgriculture1300:

```sh
uv run python tools/audit_river_bitmap.py --map-dir '/mnt/c/Games/steamapps/common/Europa Universalis V/game/in_game/map_data'
```

Outputs: `artifacts/rivers/bitmap_audit/locations.csv` and `report.json`.
The report hashes both bitmaps and the native location export. The audit rejects
previously untested palette entries instead of extrapolating a width formula.

For the entries actually used in the installed indexed `rivers.png`, maximum
mapped value inside each `locations.png` polygon predicts native effects as follows:

| Palette index | RGB | Observed contribution to native level |
| --- | --- | ---: |
| 0 | 0,255,0 | No positive contribution by itself |
| 4 | 0,200,255 | 1 |
| 5 | 0,150,255 | 1 |
| 11 | 0,0,100 | 3 |
| 15 | 24,206,0 | 5 |
| 1 (red connection marker) | 255,0,0 | 5 |
| 2 (yellow connection marker) | 255,252,0 | 5 |
| 254 / 255 | Background | 0 |

This is an empirical reconstruction, not engine source code. The mapping of
unused width entries was subsequently established by the palette experiment below.

Width pixels alone match 27,728 / 28,573 zones. Including red/yellow markers as
level 5 matches **28,564 / 28,573 (99.9685%)**, with just two ownable exceptions.
Every location containing either connection-marker colour has native level 5.
These markers promote 836 zones (759 ownable) above the maximum width-only
prediction. Paris and Stora Tuna have width-only level 1 but native level 5;
Perm has width-only 3 but native 5. London is 1 and Cologne/Cairo are 3, without
connection markers in their polygons.

The nine remaining exceptions each contain one width-4 terminal pixel and
have native level zero. Ignoring inland endpoints with at most one orthogonal
river neighbour, while retaining endpoints next to background-water pixels,
matches 28,572 / 28,573 zones. Sholakkorgan is the remaining exception. This
endpoint treatment is explicitly an exploratory hypothesis, not a verified
general engine algorithm. Buffering river widths into neighbouring polygons
was also tried (1–4 pixels) and worsened the width-only match.

The connection-marker association is exceptionally strong evidence that the
native category is affected by river network markers, not just physical width.
It could reflect special handling or a bug; this audit does not establish the
internal cause. Do not describe native level 5 as measured discharge or use it
as an unquestioned physical water-access variable. Native exported levels stay
authoritative for reproducing game effects; width-only values stay diagnostic.

## Controlled palette experiment: all five native levels confirmed

On 2026-09-17, EU5 1.3.11 produced native levels 2 and 4 from previously unused
width colours. One game launch and one fresh observer save tested all 13 width
indices simultaneously. No engine defines or native river effects were changed.

| Palette index | RGB | Native level | Junction-free test locations | Agreement |
| ---: | --- | ---: | ---: | ---: |
| 3 | 0,225,255 | 1 | 788 | 100% |
| 4 | 0,200,255 | 1 | 785 | 100% |
| 5 | 0,150,255 | 1 | 758 | 100% |
| 6 | 0,100,255 | **2** | 802 | 100% |
| 7 | 0,0,255 | **2** | 818 | 100% |
| 8 | 0,0,225 | **2** | 780 | 100% |
| 9 | 0,0,200 | 3 | 806 | 100% |
| 10 | 0,0,150 | 3 | 786 | 100% |
| 11 | 0,0,100 | 3 | 801 | 100% |
| 12 | 0,85,0 | **4** | 816 | 100% |
| 13 | 0,125,0 | **4** | 778 | 100% |
| 14 | 0,158,0 | **4** | 810 | 100% |
| 15 | 24,206,0 | 5 | 781 | 100% |

Use these entries in an indexed PNG with the original palette preserved.
The experiment does not determine whether arbitrary RGB images or rearranged
palettes would behave identically. For simple future generation, index 7
(pure blue) gives level 2 and index 13 (dark green) gives level 4.

### Method and checks

`tools/build_river_palette_test.py` assigns each location one of indices 3–15,
recolours its existing width pixels, and builds a separate diagnostic mod.
River paths, source markers, red/yellow connection markers, background pixels,
dimensions and the complete palette are preserved. The script verifies these
invariants and records source/output hashes in the experiment manifest.

The exporter measures the five native modifier categories independently and
writes a separate experiment marker to distinguish the test save from vanilla.
`tools/analyze_river_palette_test.py` verifies all 28,573 records, schema,
experiment marker and agreement between native flags and exported maximum level.
There were zero stacked native flags. The 10,309 clean cases require at least
three width pixels, no connection markers, and positive baseline river presence.
All clean cases agree with the table. In particular, **2,400 cases confirm
level 2 and 2,404 confirm level 4**.

All 1,032 locations containing connection markers still exported level 5,
regardless of their assigned width colour. Changing width alone therefore
cannot guarantee a lower native level at junction locations. This result
confirms native river categories, not navigability or proximity behavior.

Generated results live in `artifacts/rivers/palette_test/`: `manifest.json`,
`assignments.csv`, `export.json`, `results.json`, `results.csv`, and
`palette_level_counts.csv`. A compact reusable mapping is checked in as
`tools/river_exporter/verified_palette.json`.

Save: `SP_Observer_1337_04_01_c1af8be6-dd19-4203-b747-55a825d79893.eu5`.
SHA256: `52e478fadae7e78f3653e9cf4fe835c8c39609590a94ebf5f64a1c11d4a2f56e`.
Original installed game files were untouched; the original playsets file was
restored byte-for-byte after closing the test game.

### Reproduce

```sh
# In HistoricalAgriculture1300; builds the diagnostic mod but does not activate it.
uv run python tools/build_river_palette_test.py --map-dir '/mnt/c/Games/steamapps/common/Europa Universalis V/game/in_game/map_data'
# Activate only the generated River Palette Test mod, launch with -debug_mode,
# start a fresh observer game, and save once. From the Constructor checkout:
uv run python tools/export_river_attributes.py '<absolute plaintext save path>' '/home/jan/development/HistoricalAgriculture1300/artifacts/rivers/palette_test/export.json'
# Back in HistoricalAgriculture1300:
uv run python tools/analyze_river_palette_test.py --export artifacts/rivers/palette_test/export.json
```
