# River drawing snapped to vanilla — 26 September 2026

Our rivers are traced from the geographic network, so where vanilla draws the same river the two lines usually run
one to five pixels apart, and the widths differ: vanilla draws almost every river at width 4 or 5 and only large ones at
11 and 15, while the export used one width per level (4, 7, 11, 13, 15). This pass makes the drawing look like vanilla
without changing gameplay.

## What changes

* **Snapping** (`river_snap.py`, `configs/rivers.json` `export.vanilla_snap`). A routed stretch that follows a vanilla
  river within 5 px for at least 12 px is redrawn on vanilla's own pixels, joined to the rest of the branch by a pixel
  or two. A stretch is accepted only if every location keeps its routed river level, it keeps clear of every other drawn
  river and of every reference junction, and it leaves the navigation pixels alone (below).
* **Widths** (`export.width_policy = vanilla_within_level`). A river pixel takes vanilla's width index where vanilla
  draws the same level at or within 5 px of it, otherwise vanilla's usual width of the level (4, 11, 15; 6 and 12 for
  levels 2 and 4, which vanilla never draws). The level is the width band, so no level changes.
* **Lower-Thames box.** The native-geometry override used to blank its whole box to land in rivers.png; it now only
  clears the old river pixels inside it.

## Why gameplay does not change

* The export routes twice: once without snapping (the reference) and then with snapping, repeating the snapped pass
  and denying stretches around every location whose marker-aware level differs from the reference, until none does.
* Navigation cuts water tiles, ports and crossings from river pixels matched to large reaches, and smooths each pixel's
  gradient over its seven nearest river pixels. The KD-tree breaks distance ties by the whole map's pixel set, so any
  change anywhere can flip a tile state elsewhere. The export therefore also writes the reference drawing
  (`navigation_reference_rivers.png`, byte-identical to the unsnapped export) and `worldbuilder navigation` takes every
  decision from it; only the final drawn rivers come from the snapped `rivers.png`. In addition every pixel of a reach of
  at least 300 m³/s (drawn or not), a 16 px buffer and the below-threshold override locations keep the reference
  drawing, so the channels and their banks look the same as before.
* `scripts/river_gameplay_snapshot.py` records per land location the river level (engine rule: widest pixel, junction
  marker = 5, source marker = nothing), coastal flag, shore tile states, ports, crossings, channel network groups,
  tile-step distances between connected locations and land area, and diffs two exports.

## Result

| | before | after |
| --- | --- | --- |
| river pixels on a vanilla line | 32.7 % | 39.3 % |
| within 2 px of a vanilla line | 65.1 % | 66.0 % |
| width 7 (level 2) pixels | 144,980 | 0 (width 6) |
| level 1 at vanilla's width 5 | 0 | 53,860 |

723 stretches (49,186 px) snapped in three passes, 43 denied. Gameplay diff against the pre-snap export: tiles, tile
states, ports, crossings, network groups, 54,383 tile-step distances and all land areas identical; export location
levels identical. One location differs: zombodze gets river level 1. Its only river pixel used to be a green source
marker, which gives no level in the engine, while the export's level table (and the capacity fit built from it) already
counted level 1; the snapped drawing gives it a level-1 width pixel, so the game now matches the fit.

Moving the channels as well would put 47.4 % of the river pixels on vanilla's lines but re-cuts the navigation: in a
trial it changed river ports in 54 locations, 73 crossings, the shore states of 347 locations and 150 channel network
groups. That is a gameplay change and was not adopted.

Not verified in the game: the renders are drawn from the palette index, not captured from the engine.
