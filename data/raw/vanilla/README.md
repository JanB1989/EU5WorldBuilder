# Game reference inputs

Written by `scripts/import_vanilla_start.py` (2026-10-01, EU5 1.4.0 beta), run from the constructor environment
because it reads the start save with the project's Rust/Polars save engine:

    uv run --project ../ProsperOrPerishConstructor python scripts/import_vanilla_start.py --save <vanilla 1337.4.1 save>

`start_development_1337.csv`: vanilla game-start development per location (`development`), read from the vanilla
1.4 start save `SP_Observer_1337_04_01_da189272-b6a0-4900-b013-a184fa9ec42b.eu5` (1337.4.1). Locations the save
stores no development for (unowned land, zero) are 0. Range 0 to 43. Read by `configs/development.json`
(`source.kind = game_start`). Not derived from population.

`location_raw_material_1337.csv`: the game starting RGO (`raw_material`) per location from the 1.4 location
templates (`data/raw/location_inputs/game_templates.txt`), checked against the save (identical). Includes the
new good `camels` (69 locations). The game decides the RGO; the World Builder only fits output rows.

The same run replaces `eu5_start_population`, the pop-type columns and `starting_location_rank` in
`data/raw/location_inputs/starting_population_source.csv` with the save values (contextual only). Hashes, counts
and checks: `evidence/vanilla_start_manifest.json`. The 1.3.11 copies are kept in
`artifacts/baseline_1.3.11/raw/`.
