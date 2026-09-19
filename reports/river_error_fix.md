# River-load error repair — 17 September 2026

The failing session's log contained 3,792 lines. River parsing accounted for
3,616: 1,204 malformed-affluent clumps, 2 other malformed-affluent errors, and
2,410 unprocessed/source-not-found errors across two loads. The exporter placed
red markers on degree-three junctions instead of tributary endpoints one pixel
before them. Native reference: 1,286 red markers, all degree two.

The corrected exporter retains the physical network and five size classes,
places red markers before joins, reserves junction spacing and verifies directed
segment connectivity over the entire 690,099-pixel raster before writing it.
There are 2,170 source/mainstem trees and 4,442 tributary connections.

Compatibility fixes remove undefined references to unexported mangrove/saltmarsh
classes, supply required custom-topography modifiers, retain existing setup
resources and buildings under the changed representative geography, and include
the generated river PNG in the main mod. The temporary River Exporter diagnostic
addon was removed from the playset; its diagnostic modifier warnings are not
part of World Builder. Existing DLC/backend, audio, government and starting
building-limit messages are separate from the map-parser failures; gameplay
balance was not changed to suppress those messages.

The user requested offline validation only. The repaired build has NOT been
launched in EU5; a new campaign/restart is the remaining engine confirmation.
The preserved failing log is in artifacts/runtime_validation/failed_river_load.log.

Final checks: 248 tests passed; 25,470 custom geography references checked with
zero undefined references; 113 deployed files verified byte-for-byte. All five
width palette entries have nonzero pixels. Runtime confirmation remains pending.
