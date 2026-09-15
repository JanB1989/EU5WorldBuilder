# Fertility icons — revision 3

Five variants of the same four-leaf seedling, generated with the built-in image-generation tool. Fertility is encoded by ordered plant size, leaf posture/fullness AND the existing map legend colours. The crop/species does not change between grades.

| Grade | Legend palette | Growth |
|---|---|---|
| Very low | Brick red, #A8403B | Stunted, small contracted and drooping leaves |
| Low | Orange, #D77D40 | Short, sparse, partly drooping |
| Moderate | Yellow ochre, #DBBF64 | Medium-sized, spreading leaves |
| High | Light green, #8BB65E | Upright, vigorous, large leaves |
| Very high | Rich green, #378B50 | Tallest, fullest broad foliage |

## Design evidence

[University of Maryland Extension](https://www.extension.umd.edu/resource/nutrient-deficiency-trees-and-shrubs) describes reduced shoot growth and leaf size as useful nutrition cues. Actual deficiency symptoms vary. Red/orange/yellow here are semantic colours matching the map legend, not a claim about universal physiological symptoms or plant age.

[W3C guidance](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html) recommends conveying distinctions through more than colour. The common species, ordered size and changing posture supply those additional cues. This does not claim that a 30px game icon alone meets every accessibility requirement.

The design was recorded before generation in `design_v3.json`. The prompt set, source filenames and checksums are recorded in `generation.json`. All five use the same earlier four-leaf seedling as their edit reference, a common soil mound/groundline and fixed square canvas. Unlike the old preparation, this revision DOES NOT enlarge every silhouette to identical bounds: the intended growth progression survives export.

## Reproduction

```
uv run python scripts/prepare_fertility_icons.py
uv run ha1300 geography-test
```

Original generated magenta production mattes remain in `originals/`. Preparation keys out that background and preserves the square registration, producing 512px RGBA masters. Existing export writes 64px DDS textures and a 128px map/concept icon. `preview.png` compares the artwork with the five legend swatches and shows the actual 30px native frames plus a magnified strip.

Earlier sets are retained in `previous_v1/` and `previous_v2/`. This is artwork only: no fertility data, class thresholds, map colours or economic modifiers change.
