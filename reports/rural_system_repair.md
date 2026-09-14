# Extreme rural shortfall investigation

Baseline: location map fingerprint 201a7273c1d65580, saved byte-for-byte as
`data/processed/rural_system_before.csv`. Africa had 98 locations above starting
capacity; western India had 81. These counts include urban locations.

## Diagnosed crop defects

The northwestern Indian crop list contained only wheat/barley. Surat's sampled
cell had zero GAEZ wheat/barley yields in all three scenarios, while sorghum and
pearl millet were viable. Regional crop eligibility therefore incorrectly turned
substantial reconstructed cultivation into a non-cropping system. In Jaisalmer,
irrigated wheat suitability prevented selection of a viable rainfed millet.

The repaired location calculation retains viable original rainfed crops. If the
original cannot produce rainfed food, it selects the first viable dry crop in the
historical preference list, before falling back to irrigated-only crops. This is
not yield maximization. Water and land constraints still apply. The underlying
food-type raster remains a livelihood reconstruction, not a prohibition on
subsidiary crops; `potential_crop.tif` records the location pipeline's crop.

Historical availability sources:

- Winchell et al. (2018), archaeological evidence of sorghum and pearl millet in
  Sudan and India: https://pmc.ncbi.nlm.nih.gov/articles/PMC6394749/
- Petrie et al. (2023), different Indus farming strategies, including Gujarat
  summer cereals: https://www.cambridge.org/core/journals/antiquity/article/different-strategies-in-indus-agriculture-the-goals-and-outcomes-of-farming-choices/A155524D0EBBF3D631EEC620E9F98147
- Medieval Nile cultivation: https://knowledge.uchicago.edu/record/1009/files/MSR_IV_2000-Borsch.pdf

These support crop availability, not precise cell-level preferences or yields.
Saharan/Arabian conditional cereal candidates repair empty crop lists. An
irrigated yield is never treated as rainfed, and no river water is created.

## Evaluation contract

Compare every ownable location against the saved baseline, including counts
above 1x, 2x and 5x starting support and above maximum. Retain every extreme rural
residual explicitly; urban rank alone does not prove an import exception.
Population is reporting only. Run the canonical full model and independent
delivery validator; no isolated spreadsheet overrides or population floors.

The fixed-output inheritance and water-attribution comparisons are superseded
experiments when physical crop inputs change. Within-candidate water transfer,
component, land and water-budget conservation checks remain mandatory. Previous
experiment outputs remain in their original Git revision and cached baseline.

## Crop water correction

The original location calculation charged reference-grass ET throughout the
season and applied the worst active month's supply fraction to all annual
irrigation output. Apply FAO approximate crop-stage coefficients before net
irrigation demand; rain-derived reference ET is credited once. Initial and
ripening stages do not have the same requirements as peak growth. Millet uses
sorghum and rye uses small-grain coefficients as explicit analogues.
Source: https://www.fao.org/4/s2022e/s2022e07.htm

Use a seasonal water-weighted supply fraction with a conservative 25% weight
on the strict worst-month fraction. This prior is not a measured historical
coefficient or FAO Ky. Seasonal and stage-specific responses are supported by
https://www.fao.org/4/y3655e/y3655e04.htm ; uncertainty remains large. The
full strict alternative is saved as two sensitivity rasters. No new water,
groundwater or seasonal storage is introduced. Each reported served hectare
is now a full-demand-equivalent productive hectare, bounded by supplied water,
not surveyed irrigated land. Source irrigation acreage remains separately saved.
