# Game reference inputs

`start_development_1337.csv`: EU5 1.3.11 starting development per location (`profile_start_development`),
the day-one savegame snapshot as exported through the ProsperOrPerishConstructor state table on
2026-09-19. Negative values are empty land and are clipped to 0 where used. Read by
`configs/development.json` (`source.kind = game_start`). Not derived from population; it is the game's own
number and is used as an input to the building cap equations only.
