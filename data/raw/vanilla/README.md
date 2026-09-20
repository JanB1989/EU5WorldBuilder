# Game reference inputs

`start_development_1337.csv`: EU5 1.3.11 starting development per location (`profile_start_development`),
the day-one savegame snapshot as exported through the ProsperOrPerishConstructor state table on
2026-09-19. Negative values are empty land and are clipped to 0 where used. Read by
`configs/development.json` (`source.kind = game_start`). Not derived from population; it is the game's own
number and is used as an input to the building cap equations only.

`location_raw_material_1337.csv`: the game starting RGO (`raw_material`) per location, from the vanilla
location templates as parsed on 2026-09-20 (via the labeling pipeline base table). The game decides the
RGO; the World Builder only fits output rows where a good is the RGO.
