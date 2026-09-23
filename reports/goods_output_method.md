# Goods output rows: constrained method (2026-09-23)

`worldbuilder goods-fit` writes one output modifier per (good, attribute class). The constructor puts the
rows on the class definitions (climate, topography, vegetation injects; fertility, soil, coast and lake
static modifiers). Since 2026-09-23 there is no per-good base modifier in the mod: the raw-material bonus
(`pp_rgo_bonus_<good>`, +20 %, re-applied when the raw material changes) is the base at the RGO, and the
fit's level is folded into the climate rows.

## Why the old rows were inconsistent

Measured on the 2026-09-20 fit (method `ols`, still selectable in `configs/goods_output_fit.json`):

| Problem | Evidence | Effect in game |
|---|---|---|
| Irrigated potential everywhere | The V2 score takes the irrigated (LILM) branch wherever it wins; 99 % of viable arid locations were scored irrigated, with the same score with or without a river. | Deserts were the best land for fiber crops (+44 % partial), silk (+48 %), chili, cotton, incense. |
| Sugar beet | Beet wins 55 % of sugar's viable cells; it is a 19th-century sugar crop. | Central Europe was the best sugar land. |
| Rank-stretched target | Each good's scores were spread uniformly over -0.5..+0.5 by rank. | Small real differences became large rows (tea 0.22 -> 0.17 at very high fertility became -15 %). |
| Hard relevance and magnitude cut | Rows existed only with >= 5 RGOs in the class and abs >= 0.10; everything else went into a per-good intercept. | Steps like fruit high 0 / very high +9 %; intercepts from +0.20 (fruit) to -0.32 (fiber) that the rows only made sense with. |
| No direction rules | Per-good least squares on correlated classes. | 572 rows break the sign table below (wheat +13 % in tropical climates, sugar +6 % continental, tea +2 % desert, cotton +15 % arid). |

## Method

- **Target:** the V2 labor-output score on its own log scale. The rain-fed score is lifted towards the
  irrigated score only by the location's historical irrigated share, using the fertility grade's
  weight (HID 1900, saturating at 10 %). Rain-fed tables and a cane-only sugar table come from V2
  sandboxes (`scripts/goods_efficiency_variants.py`, manifests in `data/raw/goods_efficiency_rainfed`
  and `data/raw/goods_efficiency_overrides`). In arid and hot-steppe climates the mean score falls from
  0.87 to 0.47 for fiber crops, 0.77 to 0.28 for cotton, 0.73 to 0.36 for silk and 0.42 to 0.08 for rice.
- **Rows:** climate rows are absolute (every location has one climate, so they carry the good's level).
  Every other attribute is relative to its reference class. The fit is a weighted ridge least squares
  on all viable locations (RGOs weighted 3, ridge of 20 location-equivalents), and rows under 0.05 are
  dropped and the rest refitted. All 25 goods get rows; coffee and cloves had none before.
- **Priors (`configs/goods_output_priors.json`):** each crop gets home, marginal and unsuitable
  climates, and a sign per class, from agronomy and pre-modern geography (evidence text per good).
  Home climates rank at or above marginal ones, and marginal ones at or above unsuitable ones.
  Unsuitable climates sit at most -0.20 and at least 0.20 below every home climate. Fertility never
  falls with a better class. Farmland never lowers a crop (timber excepted). The game's "arctic" class
  is mostly the Tibetan plateau and the Andean puna, so highland crops are marginal there, not ruled
  out.
- **Level:** after the fit, one shift of all of a good's climate rows puts its mean viable RGO (floor
  applied) at 0. The average RGO of every good therefore gets exactly the raw-material bonus, and the
  attributes spread output around it.
- **Checks:** `check_rows` fails the build on any break of the sign table or the climate order.
  `priors_overruled.csv` lists every row where the priors moved the unconstrained data by 0.1 or more
  or flipped its sign (58 rows, each an agronomic call, e.g. tea at very high fertility -0.14 -> 0,
  cocoa in cool highland "oceanic" +0.20 -> -0.20).

## Result (2026-09-23)

| | Old rows | New rows |
|---|---:|---:|
| Breaks of the sign table / climate order | 572 | 0 |
| R² on the water-realistic score, all viable locations (old: fixed rules; new: region-held-out) | 0.26 | 0.46 |
| R² at RGO locations (new: region-held-out) | 0.38 | 0.42 |
| Rows | 226 | 649 (climate rows now carry the level, 13.8 per class on average) |
| Mean static RGO output incl. the +20 % bonus | 0.25 (0.27 after the base modifier was removed) | 0.19 |

Weak spots: the region-held-out R² at RGOs is negative for goods with few, regionally clustered RGOs
(cocoa, coffee, potato, cloves, tea): the attributes cannot see what makes Soconusco, Yemen or the
Andes special. Saffron has 41 % of its vanilla RGOs on land the data calls unviable (floor). The fiber
basket is jute-dominated, so temperate flax and hemp land (continental Europe) reads -20 %.
