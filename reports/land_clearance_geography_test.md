# Land Clearance Geography Test

Enable this mod ALONE in a test playset, restart EU5 and start a NEW 1337 game as Sweden. Geography is loaded from location templates; do not use an existing campaign. Main Prosper or Perish and other map mods must be disabled for a controlled result.

Open the following locations and find Land Clearance (Geography Test). It starts at zero levels. Hover its maximum level to inspect Base Allowance, Vegetation and Climate.

| Location | Vegetation addition | Climate addition | Expected limit |
|---|---:|---:|---:|
| norrtalje | +0 | +0 | 2 |
| tierp | +3 | +0 | 5 |
| heby | +0 | +2 | 4 |
| enkoping | +3 | +2 | 7 |

## Engine checks

- New forest/climate names, icons and tooltips render, with their extra level modifiers.
- Limits match the table; outside these four locations the test building is unavailable.
- Build one level in each: confirm its raw capacity contribution and resulting total capacity.
- Each level adds 1 game capacity unit (normally 1,000 displayed people), multiplied by the full active native relative factor. Record that factor from the local capacity tooltip; native development/rank effects may differ by location. This test does not force the agricultural model multiplier into the game.
- Build to the cap, including queued levels; verify another level cannot be built.
- Demolish one level: one slot should reopen, not change the total maximum.
- Save, reload and recheck the attributes, capacity and limits.
- Inspect error.log for ha1300 keys, missing icons, invalid modifier/types or unknown definitions.
- The new categories inherit the original forest/continental definition except for the explicit test allowance. Scripts that explicitly check the vanilla key do not automatically recognise a new subtype. This test does not implement global compatibility rewrites.

Construction has a nominal cost of 1 gold, no goods demand or staffing, and a base duration of 2 days; native modifiers may affect the displayed cost/time. Empty maintenance is deliberate.

## Status

Build/parser/unit-test and deployed byte-parity checks are engineering evidence only. Loading, construction, UI and save/reload behavior remain pending until checked in the running game.

## Rebuild and sync

`uv run ha1300 geography-test`

Build without syncing: `uv run ha1300 geography-test --build-only`

The live destination comes from ignored geography_test.local.toml. Only the dedicated test folder is managed. To uninstall, disable this mod and remove that folder.

## Engineering verification

177 project tests pass (including six new build/sync tests), with eight existing Rasterio deprecation warnings. All eight generated Clausewitz text files parse. The building and its unique maintenance method resolve through the vanilla-plus-test load order. Of 28,573 location templates, only Tierp, Heby and Enkoping change; Norrtalje is an unchanged control. Sixteen deployed files match their compiled hashes. This does not certify engine/UI behavior.

## Soil UI trial (user requested)

The user confirmed the original climate/vegetation approach works in-game. Added a custom Soil Quality icon to the existing geography strip, backed by template-assigned static modifiers. Prototype soil values: Norrtalje Poor (+0); Tierp Average (+1); Heby Good (+2); Enkoping Excellent (+3). New total limits: 2, 6, 6, 10. This is a script-owned attribute with custom UI, not a new native engine database. Generated definitions parse and 21 files were synced with byte parity. Awaiting user engine/UI observation; no broad regression run for this prototype.
