# Navigation from researched reaches — 26 September 2026

The navigable river channels no longer come from a modern-discharge screen. A physical screen could not tell sea-going
ships from river boats, missed tidal ports and left most channels stranded: of 16 historical inland sea ports only 3
were reachable from the sea, 616 channel groups existed and only 433 of 2,406 tiles reached the open sea.

## Evidence

`configs/navigation_reaches/*.json` (one file per world region) record for 74 rivers the head of sea-going navigation,
the head of river-craft cargo navigation, navigable branches, obstacles, confidence and sources; 48 more rivers were
considered and left out with a reason. Heads are EU5 location tags. Rivers neither map draws (the IJssel) and canals
(the Grand Canal) run straight through their listed stops.

## Geometry and states (`navigation_reaches.py`, `worldbuilder navigation`)

* Each head is traced along vanilla's river line to the open sea (the drawn export river where vanilla has none), river
  pixels first and lakes only where no river reaches the sea; a path that misses its sea head goes through it. Paths are
  four-connected and touch the sea. Pixels no farther from the sea than the sea head form the sea reach.
* Obstacles: falls and cataracts are barriers (impassable tiles), every other obstacle is improvable (passable at a
  cost, the site of lock works); the rest is navigable.
* The channel is cut 2 px wide through land, and as a strip through lakes and wasteland on the route (lakes stay lakes,
  their shores keep lake adjacency). Small pieces join the neighbouring tile. A land connection the channel cuts gets
  an explicit crossing, straight or through a tile both banks border; three reviewed cuts are accepted
  (`raster.accepted_cut_adjacencies`), any other fails the checks. Drawn river lines within 3 px of a channel are
  cleared; every land location keeps at least the river level of the export's level table.

## Result

822 tiles (768 navigable, 48 improvable, 2 barrier), 732 connected to the open sea, 84 channel groups. 68 of 74 rivers
are fully sea-connected; the others are the inland middle Niger (by design), the Ob (its mouth is an impassable
arctic sea zone), the James and the Mekong (a few percent each). Inland sea ports reachable from the sea: 11 of 16
(missing: Norwich and Yangzhou, not researched as reaches; Deventer/Zwolle now connected; Guangzhou's port is Panyu).

River levels: the export's level table is unchanged; in game 30 locations gain a level (27 from 0 to 1) because their
only river pixel used to be a source marker or was overwritten by an earlier channel, so the game now matches the
level the capacity fit uses. Coastal status, ports, crossings and market-access routes change for about 2,100
locations; channel banks are coastal in game.

Not verified in the game: channel strips through lakes and wasteland, crossings through a shared tile, and barrier
tiles.
