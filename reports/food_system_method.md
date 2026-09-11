# Food systems and food-energy equivalents per hectare

## Contract

All values describe **one hectare used by the represented livelihood**. Cell area, cultivated extent and the fraction of land available are not used. Crop hectares cover the full rotation, including fallow. Grazing hectares represent the animal-supporting range. Foraging hectares represent terrestrial foraging range. These denominators are labelled; they must not be multiplied by total cell area to claim total support without a separate land-availability model.

A food-energy person-equivalent is 2,500 kcal/day for 365 days (912,500 kcal/year). This is a configurable reporting assumption, not an observed 1300 dietary requirement or a nutritionally complete diet. Seed, processing and crop losses are unchanged. Milk/meat conversion uses 850/1,450 kcal/kg from the FAO Mali analysis, with a separately assumed 15% handling loss.

## Food-system mask

Historical crop preferences remain first, checked against GAEZ scenarios. RESOLVE ecoregions supply physical boundaries. Explicit pastoral overrides identify core steppe, alpine and North Atlantic systems; supplementary sources document long-standing Eurasian dairying and Norse animal husbandry. African desert/grassland non-crop fallbacks use pastoral analogues. Australia and the Americas are excluded from Old World domestic-livestock transfers. Andean crop systems are preserved; camelid husbandry is not yet separately quantified.

Where no represented crop fits, broad hunting/gathering or pastoral systems are inferred from ecological realm and biome. These are conditional food-system assignments, not proof of historical occupation or dominant diet in every cell. Rock/ice and Antarctic terrestrial-zero classes are explicit. GAEZ land south of 60 S is assigned the Antarctic terrestrial-zero convention even where ice polygons leave geometry gaps; marine production remains excluded. Source-mask water proximity identifies fishing-associated foraging possibilities, not observed dependence or fish yield. Remote/unmatched land is labelled wild-food potential with uncertain local history.

Ecological shoreline mismatches may inherit the nearest ecological unit within two native cells, with an inference flag and a local GAEZ viability check before crop assignment. More distant gaps are not assigned a crop by distance. FORGE values are sampled from their original 2-degree cells, with at most 1.5 source-cell distances used to reconcile missing coastal values. This does not create new fine-resolution ecological information.

HYDE is deliberately not used as crop or livelihood identity: its land-use allocation is not a staple map, and population-derived cultivated extent has no role in this per-hectare calculation.

## Crop productivity and the Seshat graph

The three crop maps use canonical lower, inferred historical and upper dry-product yields, converted to edible food through the same processing, seed, loss, fallow and cropping-frequency accounts. Neither cell area nor observed population enters.

The bottom graph preserves the Seshat benchmark intervals, converted with each crop's energy accounting and the benchmark's own annual cropping coefficient. A coefficient below one is a rotation fraction; above one it is harvest frequency. Apply it once. Thus Kansai's coefficient of two is handled as two harvests, not an invalid 200% land share. Graph envelopes, observations and uncertainty intervals all receive the same conversion. The two already unresolved comparisons remain labelled; conversion does not manufacture a valid benchmark.

## Non-crop numerical estimates: experimental

[Zhu et al. 2021, FORGE](https://www.nature.com/articles/s41559-021-01548-3) provides global S0/S1/S2 model outputs and source code. These are present-day environmental process-model results, not observed historical population. The source reports human density per square metre, daily edible dry-matter intake per model person, and 9.8 MJ/kg dry matter net energy for both animal and plant food. We multiply annual mean density by annual mean intake, convert m² to hectares and MJ to kcal, and annualize. This is an approximation because covariance of daily intake and population is unavailable in the distributed annual output. Population-floor values are treated as zero food support rather than preserved as fake minimum productivity.

S2 is the reference; the S0–S2 envelope is environmental/model sensitivity. It is **not** a researched minimum/maximum technology range for 1300. No fishing is included. Fishing-associated cell values describe the terrestrial component only.

Livestock is an explicitly **provisional model transfer**: FORGE grazer biomass per grass hectare (180 kg per modeled grazer) is divided by 250 kg per tropical livestock unit. This supplies a geographically varying stocking proxy. Wild standing biomass affected by hunting is not an independently validated domestic carrying capacity. We then apply [FAO traditional pastoral](https://www.fao.org/4/t0413e/T0413E15.htm) annual product coefficients: 95/161/220 kg milk and 13.7/16.3/34.5 kg meat per livestock unit for cattle/mixed/small-ruminant analogues. They define low/reference/high product-system scenarios, not observed medieval improvements. The food-energy factors come from [FAO Mali](https://www.fao.org/4/x5531e/x5531e07.htm). Transfer outside tropical African systems, especially yak and North Atlantic farming, needs regional calibration. These numerical maps must not be described as validated pastoral productivity.

Livestock, crop and wild-food values are alternatives for the assigned hectare; they are never independently added. The lower/upper bounds do not incorporate all forage-model or livestock-transfer uncertainty. No unknown numeric value is replaced with zero; unquantified land is shown separately.

## Evidence and reproduction

Source URLs, roles and snapshots are registered in `configs/sources.json` and `data/raw/documentation`. The original FORGE ZIP is pinned in `configs/food_systems.json` and included in fingerprints. Original crop-only outputs are preserved in `artifacts/experiments/ecoregion_crop_only`.

```bash
uv run ha1300 acquire
uv run ha1300 run
uv run pytest -q --junitxml=reports/tests.xml
```

The main page contains the food-system map, three people-per-used-hectare maps and the converted Seshat graph. Additional diagnostics are collapsed. Engineering checks and historical/scientific acceptance remain separate. A complete categorical mask does not imply complete quantitative coverage or demonstrated historical accuracy.
