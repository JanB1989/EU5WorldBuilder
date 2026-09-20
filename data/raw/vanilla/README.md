# Game reference inputs

`start_development_1337.csv`: EU5 1.3.11 vanilla game-start development per location (`development`), the
vanilla rules of `main_menu/setup/start/14_development.txt` (base, region/area/province/location, rank,
climate/topography/vegetation, coast x harbour, river x size, road) evaluated on the vanilla location table by
`ppc worldbuilder export-development` in ProsperOrPerishConstructor on 2026-09-20. Range 0 to about 110; the
engine multiplies population capacity by 1% per point. Read by `configs/development.json`
(`source.kind = game_start`). Not derived from population.

`location_raw_material_1337.csv`: the game starting RGO (`raw_material`) per location, from the vanilla
location templates as parsed on 2026-09-20 (via the labeling pipeline base table). The game decides the
RGO; the World Builder only fits output rows where a good is the RGO.
