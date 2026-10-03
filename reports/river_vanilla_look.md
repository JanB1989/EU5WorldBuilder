# Rivers on vanilla's network — 3 October 2026

EU5 1.4 draws rivers in many more map modes, in the paper style with dark banks, and animates their flow in the
river map mode (`river_surface.shader`, the "sentinel" branch). That makes the shape of the drawing visible. Vanilla's
rivers are 693 continuous systems; 685 of them reach the sea or a lake. Ours (export plus navigation cleanup) were
5,289 pieces. Only 1,858 reached water, and 1,899 were shorter than 16 px, so they showed as faint blobs or not at
all, because the engine does not draw the first 5 px after a source. Copied vanilla pieces also ran a pixel or two
beside our own lines.

## What changes

`worldbuilder navigation` ends with a redraw (`river_vanilla_look.py`, `configs/river_navigation.json`
`vanilla_look`):

1. **Skeleton.** Every vanilla river pixel on land is the base, except in ownable locations that have no river in
   the gameplay table and along a channel. A line beside a channel is cleared, but a tributary mouth crossing the
   3 px corridor stays and touches the channel. Vanilla's distributary splits are detached (the branch starts one
   pixel off the main river).
2. **Our rivers.** Our pixels stay only where vanilla draws no river. A piece that runs mostly (80 %) within 12 px
   of a vanilla line is the same river drawn beside it and is dropped, as is a piece that leaves a vanilla line and
   comes back to it. A piece that flows into a vanilla river is bridged to it.
3. **Encoding.** Every connected river is re-encoded as one native tree. A red tributary marker makes its location
   level 5, so a tributary joins only where the location already has level 5 (or on unownable land). Elsewhere it
   ends touching the receiving river, or one pixel short of it.
4. **Levels.** Every ownable location keeps its engine river level exactly (asserted). A vanilla pixel wider than
   its location's level is capped. Level 2 is drawn at width 6, which looks like vanilla's 5. A location whose
   visible river is still below its level gets a two-pixel carrier inside the source fade-in. Widening each
   location's line to its level instead was tried and rejected: about 6,000 pinches and bulges, and in places the
   wrong river widened, where the level came from our river drawn in a different spot (Ucayali).

## Result

| | before | after | vanilla |
| --- | --- | --- | --- |
| river trees | 5,289 | 6,048 (3,045 invisible carriers) | 693 |
| visible trees reaching water | 1,858 | 2,548 | 685 |
| drawn pixels on vanilla lines | 47 % | 86 % | — |
| vanilla land river pixels drawn | 37 % | 99 % | — |
| abrupt width changes (levels 2+ apart) | 420 | 1,098 | 476 |

Locations whose visible river shows their level: 11,197 of 12,693 (before 11,874). The rest are held by carriers:
level-5 locations from a junction marker, levels 3–5 where vanilla draws the river thin, and 937 locations with no
visible river (before 773).

## Gameplay

Unchanged according to `scripts/river_gameplay_snapshot.py`: river level of every land location, coastal flags,
shore states, ports, crossings, channel network groups and all 35,763 tile-step distances. The handover tables
(capacity rows, buildings, targets, attributes, goods floor, navigation tables) are byte-identical to
2026-10-01-20050ee.

**Changed: the market-access river edges.** The engine makes a step between two neighbouring locations cheaper when
a traced river runs from one into the other (constructor `market_access.py`, rule RIVER: ×0.5 downstream, ×0.8
upstream). That rule reads the drawing's geometry. Of 8,895 river edges, 7,724 stay, 1,171 go and 2,931 are new
(mostly vanilla tributaries we did not draw). The new network is close to vanilla's own (13,415 directed edges
against vanilla's 13,670 on the mod map; old 11,176). Flow direction also agrees with vanilla on 6,237 one-way edges
and is reversed on 185; the old drawing was reversed on 676 of 3,999, mostly copied vanilla pieces whose source sat
at an arbitrary end.

Measured with the constructor's access model (pure rules, start save `pp_mkt_0d.eu5`, 13,588 owned locations):

| access to the own market | |
| --- | --- |
| mean change | −0.0002 (population-weighted −0.0006) |
| changed by more than 0.01 | 1,251 up, 1,452 down |
| changed by more than 0.05 | 231 up, 245 down |
| changed by more than 0.1 | 25 up, 13 down (Siberia, Central Asia, Sudan) |
| predicted market differs | 301 of 21,637 locations, at most 14 per market (Delhi, Tabriz, Cahokia) |

For scale, the first tick from the start save already moves 1,030 locations, and 427 locations flip between two
near-equal markets.

Not verified in game.
