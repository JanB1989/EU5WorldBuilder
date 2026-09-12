# Food systems and food-energy equivalents per hectare

## Contract

All values describe **one hectare used by the represented livelihood**. Cell area, cultivated extent and the fraction of land available are not used. Crop hectares cover the full rotation, including fallow. Grazing hectares represent the animal-supporting range. Foraging hectares represent terrestrial foraging range. These denominators are labelled; they must not be multiplied by total cell area to claim total support without a separate land-availability model.

A food-energy person-equivalent is 2,500 kcal/day for 365 days (912,500 kcal/year). This is a configurable reporting assumption, not an observed 1300 dietary requirement or a nutritionally complete diet. Seed, processing and crop losses are unchanged. Milk/meat conversion uses 850/1,450 kcal/kg from the FAO Mali analysis, with a separately assumed 15% handling loss.

## Food-system mask

Historical crop preferences remain first, checked against GAEZ scenarios. RESOLVE ecoregions supply physical boundaries. Explicit pastoral overrides identify core steppe, alpine and North Atlantic systems; supplementary sources document long-standing Eurasian dairying and Norse animal husbandry. African desert/grassland non-crop fallbacks use pastoral analogues. Australia and the Americas are excluded from Old World domestic-livestock transfers. Andean crop systems are preserved; camelid husbandry is not yet separately quantified.

Where no represented crop fits, broad hunting/gathering or pastoral systems are inferred from ecological realm and biome. These are conditional food-system assignments, not proof of historical occupation or dominant diet in every cell. Rock/ice and Antarctic terrestrial-zero classes are explicit. GAEZ land south of 60 S is assigned the Antarctic terrestrial-zero convention even where ice polygons leave geometry gaps; marine production remains excluded. Source-mask water proximity identifies fishing-associated foraging possibilities, not observed dependence or fish yield. Remote/unmatched land is labelled wild-food potential with uncertain local history.

Ecological shoreline mismatches may inherit the nearest ecological unit within two native cells, with an inference flag and a local GAEZ viability check before crop assignment. More distant gaps are not assigned a crop by distance. The old nearest-source-cell FORGE transfer is superseded by the climate-conditioned method below. Missing coastal source values are no longer filled before transfer.

HYDE is deliberately not used as crop or livelihood identity: its land-use allocation is not a staple map, and population-derived cultivated extent has no role in this per-hectare calculation.

## Crop productivity and the Seshat graph

The three crop maps use canonical lower, inferred historical and upper dry-product yields, converted to edible food through the same processing, seed, loss, fallow and cropping-frequency accounts. Neither cell area nor observed population enters.

The bottom graph preserves the Seshat benchmark intervals and uses each crop's energy accounting. Annualization is explicit in configs/rotations.json. Most comparisons retain their published cropping coefficient. Kansai is shown as a single rice-crop equivalent: its published multi-cropping coefficient of two is retained in the evidence, but no longer interpreted as two identical rice harvests. Winter crops remain unquantified, and the anchor's harvested-area denominator is still uncertain. All components of each comparison receive the same conversion; calibration yields are unchanged. The two already unresolved comparisons remain labelled.

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

## Replacing the 2-degree squares (2026-09-11)

The squares were a numerical sampling artifact: a single FORGE value was repeated across each 24-by-24 group of GAEZ cells. They were not historical region boundaries. The preserved checkpoint is `af63656`; its generated maps are archived in `artifacts/experiments/forge_nearest_non_crop`.

The replacement uses [WorldClim 2.1](https://www.worldclim.org/data/worldclim21.html), 1970–2000, at the native 5-arc-minute grid. BIO1 is mean temperature (degrees C), BIO12 annual precipitation (mm), BIO15 precipitation seasonality (coefficient of variation). Precipitation and its seasonality enter as log(1+x). These covariates are aggregated to the original FORGE support for source comparisons. The target uses its local climate, so desert margins and mountains need not follow source-grid squares.

At each non-crop target, up to 12 original, valid FORGE cells within 600 km contribute. Weights combine a finite spatial kernel (200 km) and standardized climate similarity. A finite kernel is important: original cells are area-support estimates, not exact point measurements that warrant bullseyes at their centres. We do not impute missing source cells, extrapolate beyond the radius, invent a regional bonus, or multiply support by cell area. All six FORGE channels use identical weights. Results are convex combinations of local values, including zeros. An isolated coarse zero can therefore be blended with positive neighbours; this is explicitly an interpolation uncertainty, not evidence that every fine hectare is productive.

Climate-strength settings 0, 0.25, 1 and 4 are compared using five deterministic 10-degree geographical folds. Zero is the spatial-only comparison. The selected shared value minimizes log-scaled FORGE reconstruction error, with coverage reported. This validates transfer of a process model, **not medieval food productivity**. It does not resolve the provisional livestock conversion, terrestrial-only fishing values, or modern-climate assumptions. Detailed cross-validation and before/after distributions are saved with the result.

A finer [natural-grassland ANPP dataset](https://zenodo.org/records/18171957) was also downloaded and inspected. Its 1/24-degree product excludes much of the Sahara, Arabia and Iceland. It is retained as a research candidate, but is not used to fill those deserts or treated as global potential grassland. A future feed-budget replacement must first resolve that coverage and verify dry-matter/product conversions. No ANPP-based numerical change has been adopted here.


## Food-rank review (2026-09-11)

The earlier estimates are preserved in `artifacts/experiments/pre_food_rank_review`. Three narrow changes replace unsupported assumptions:

1. Cassava seed loss is zero for edible roots: planting material consists of stem cuttings. The previous 5% edible-root deduction was inappropriate. Processing recovery and other losses remain unchanged. This increases cassava net calories by 1/0.95 everywhere, not selectively by region.
2. A separate temporal rotation override applies to cassava in inland Iquitos, Monte Alegre and Purus varzea ecological units (469, 482, 496). The candidate uses one active cropping year plus 1.6 fallow years, hence a 0.3846 rotation fraction instead of 0.23. The one-year duration is a conservative scenario assumption; mean fallow of 1.6 years comes from 59 modern floodplain fields in the [Fraser et al. study](https://pmc.ncbi.nlm.nih.gov/articles/PMC3430692/). Geographic and historical transfer is inferred. The recorded sensitivity range 0.15–0.65 is illustrative, not a statistical confidence interval. GAEZ yield, management position, crop identity and physical area remain unchanged. The same annualization applies to labour as well as food.
3. Kansai's graph now shows a labelled rice-only equivalent. The Seshat table says multi-cropping, not two rice harvests. Farris's medieval Japanese farming discussion includes winter wheat/barley and other crops. No second-crop yield is manufactured. The original coefficient and unresolved anchor convention remain in comparison tables.

No general yam, cassava-upland, pearl-millet, barley, rye or sorghum yield adjustment was adopted. Amazonian upland long fallows are documented, while [FAO's African farming-system review](https://www.fao.org/4/y1860e/y1860e04.htm) describes diverse crop/fallow cycles. Later African cassava intensification cannot establish a 1300 American rate. A universal root-crop boost would not follow from this evidence. Dark-earth intensification requires its own spatial evidence; tidal/coastal varzea and other floodplain types do not inherit this override.

Matched-site cereal diagnostics hold sites and annualization fixed. They are agronomic comparisons, not historical crop-availability maps. Wheat/barley differences become much smaller than differences between their assigned-region medians. Sorghum/millet scaling still lacks direct calibration, so no rank-based tuning was applied.

Reproduce the review with `uv run python scripts/review_food_ranking.py` after `uv run ha1300 run`. It writes food-rank distributions, matched-site comparisons and exact candidate-change checks. Historical acceptance remains unestablished; the narrowed rotation assumption is a transparent candidate, not a newly observed medieval productivity value.


### Explicit Seshat chart proxies

Every chart row names its crop. Yemeni Coastal Plain and Deccan retain the published wheat-based Seshat points, but use local sorghum scenario ranges because their sampled wheat envelopes are unavailable. These are labelled cross-crop energy comparisons, not repaired same-crop validation. Traditional Tihama sorghum/spate agriculture (FAO, Guidelines on Spate Irrigation) and Deccan sorghum traditions (A. K. Singh, 2014) motivate the assumptions; neither establishes exact local conditions in 1300.

The proxy uses the same approximate one-degree box, 121 sample points, the original benchmark annual cropping coefficient, and each crop's own edible-energy conversion. It requires common valid lower/upper sorghum samples. Conditional irrigation feasibility remains unverified. `benchmark_people.csv` records `assumed`, `range_crop`, provenance and `source_comparison_valid`; its `valid` field means the chart can draw a comparison. Original calibration validity and scientific acceptance are unchanged. Proxy observations are never clipped into their ranges.
