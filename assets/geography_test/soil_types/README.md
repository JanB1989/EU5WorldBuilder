# Soil geography icons

Six original, built-in image_gen illustrations: Sand, Loam, Silt, Clay, Peat,
Stony. Visual reference: vanilla EU5's small geography icons, with parchment-toned
hand-painted relief, dark outlines and a compact isolated silhouette.

`generation.json` records the complete per-icon prompts and original/prepared
hashes. `originals/` preserves selected tool outputs. Four outputs needed an
image_gen background edit because their first render painted a checkerboard;
their selected outputs use the same flat magenta production background as the
Constructor building-art workflow. Loam and Stony already had real alpha.

Reproduce preparation:

```
uv run python scripts/prepare_soil_icons.py
uv run ha1300 geography-test
```

Preparation keys the prescribed background, removes insignificant alpha dust,
fits the silhouette within a 448px square and saves a transparent 512px PNG.
The builder follows the building pipeline's RGBA-to-Pillow-DDS convention, but
uses the native geography texture size of 64px and map-mode size of 128px.
The UI draws the geography icon at 30px. `preview.png` shows 128px and 30px samples.

The location strip and tooltip resolve the icon from the existing soil-type
variable through customizable localization. The map-mode button uses Loam as a
general soil symbol. No classification, gameplay effects or soil assignments are
changed by these assets.
