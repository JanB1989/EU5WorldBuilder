# Crop-distribution revision: ecological geometry

The original rectangular assignment is preserved in `artifacts/experiments/rectangular_assignment/`.

## Geographic source

[RESOLVE Ecoregions 2017](https://ecoregions.world/) supplies 846 terrestrial ecoregions and an additional rock/ice category. The original WGS84 shapefile is pinned by SHA-256 in `configs/regions.json`; its license is CC-BY-4.0. It describes ecological units, not observed vegetation or crops in 1300. No modern cropland mask is used as historical cultivated extent.

Each ecological unit is assigned exactly one named historical farming-system rule. Assignments are expert-style inferences drawing on the existing historical source registry. Ecological units are not evidence that a crop or a particular management intensity occupied every part of that unit. All cells remain conditional farming scenarios, not claimed cultivation.

## Calculation

1. Rasterize the original polygon boundaries and holes at native GAEZ cell centres. Bounding boxes are used only to limit computation, never as the assignment geometry.
2. Join ECO_ID to the explicit crop-system ledger. Duplicate, missing or unknown catalogue assignments fail.
3. Apply the historical crop preference list, selecting the first crop with a positive, complete modeled scenario. Retain the next viable crop as an alternative. Do not maximize calories to pick crops.
4. Retain unmatched geometry, uncertain island occupation, unavailable crop proxies and unsuitable conditions explicitly. A GAEZ-valid cell whose centre is outside the ecological polygons is not silently assigned its nearest neighbour.
5. Recalculate the downstream calorie, labour and management scenario maps through the same pipeline.

## Substantive changes

- Yangtze lowlands retain wet rice; northern Chinese plains favour millet. Upland systems test dry rice first but retain wet rice for terrace/valley systems before falling back to millet. GAEZ dry-rice zero does not imply historical absence of rice.
- European cool/forest cereal systems, Mediterranean cereals and Central Asian cereal systems have distinct ecological support.
- Sahel millet, humid West African roots, Ethiopian highland crops and Nile/Niger floodplain systems follow ecological units.
- Mesoamerican and eastern North American maize are separated from Amazonian root systems. Andean highland tubers are distinguished from lower-elevation maize. Pampas and Patagonian controls do not acquire a modern grain-belt crop assignment.
- New Guinea root horticulture is separated from Indonesian rice systems. Uncertain remote-island occupation remains unresolved.

These distinctions improve the geographical structure; they do not independently validate crop dominance or the inherited management priors. Rice water supply, small mixed farming systems, missing indigenous crops, coastlines and local historical boundaries remain limitations.

## Reproduction and checks

```bash
uv run ha1300 acquire
uv run ha1300 run
uv run pytest -q --junitxml=reports/tests.xml
```

The gallery includes a before/after crop map with identical colour codes. The polygon test explicitly checks an L-shaped boundary and an interior hole. Named crop controls and exclusive catalogue coverage are regression-tested. All comparable Seshat enclosure constraints remain unchanged.
