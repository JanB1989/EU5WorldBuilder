# Location attributes for agricultural improvements

Research recommendation, 2026-09-14. This is a proposed attribute design, not a fitted classification or a change to the map/test mod.

## Recommendation

Start with six additional attribute families alongside climate, vegetation and topography: soil fertility, soil profile, accessible freshwater, river regime, floodplain extent, and natural drainage. Replace the experimental clearable-land attribute with a derived building opportunity. Retain salinity as a separate constraint where relevant; investigate groundwater separately before promising well/qanat eligibility.

Independent means distinct mechanisms with additional predictive information. Environmental properties are correlated, and their source products share inputs. Neither statistical independence nor the sufficiency of six families has been established.

## Existing work and the actual gap

The prototype already contains soil quality, water supply, floodplain extent, waterlogging and clearable land. Its Swedish assignments and food bonuses are synthetic UI/stacking tests. They are not historical classifications.

The repository already has GAEZ scenarios, WorldClim monthly climate, GRUN runoff, river reaches, HydroBASINS, ETOPO terrain, potential natural vegetation, HYDE/LUH reconstructions, GLWD v2 wetland fractions and the 1700–2020 wetland-loss reconstruction. These give us much of the foundation. The current water reference uses constant 100 mm soil storage and excludes groundwater and seasonal storage. The water-management transfer fractions and vegetation accessibility weights are explicitly inferred assumptions. They must not become independent observations when evaluating this attribute scheme.

No SoilGrids, HWSD or HydroATLAS files were identified by filename in the current raw cache during this audit. Their published documentation was researched; their global layers have not been acquired or classified in this task. A HydroATLAS technical PDF was cached for source verification.

## Proposed attributes

The example values below illustrate player-readable categories. They are not frozen numerical thresholds, and soil-profile/river-regime values are types rather than a good-to-bad ranking.

| Attribute | Separate information supplied | Candidate values | Role in building rules |
|---|---|---|---|
| Soil fertility | Nutrient limitations under the baseline farming system, excluding water and slope penalties | Poor, moderate, fertile, very fertile | Baseline support; response to nutrient-management practices |
| Soil profile | Rootable depth, stones and texture; retains these as separate continuous fields underneath | Shallow/stony, deep sandy, deep loamy, deep heavy-clay; mixed where necessary | Cultivation difficulty, tillage/traction choices, clearing benefit, soil-water storage |
| Accessible freshwater | Potential external freshwater supply and physical access before canals/pumps are constructed | Minimal, limited, substantial, abundant | Irrigation opportunity under a shared water budget; not an automatic current food bonus |
| River regime | Timing and persistence of river flow, distinct from its amount | No significant river, perennial with weak seasonality, perennial with strong seasonality, intermittent | Seasonal diversion, basin irrigation and storage prerequisites |
| Floodplain extent | Share of connected low river land, distinct from water volume | Negligible, narrow, moderate, extensive | Extent potentially served by flood embankments or basin irrigation |
| Natural drainage | Tendency to persistent saturation without artificial drainage | Freely drained, seasonally wet, poorly drained, persistently saturated | Drainage dependency and opportunity; does not imply that every wetland is profitable to drain |

Do not force every soil into the illustrative four profile types. Preserve mixed cases, peat/organic substrates and salinity flags until the classification has been tested. Keep rootable depth and texture separately available to rules; if merging them causes systematic errors, split their UI representation.

### Soil evidence

GAEZ v4 explicitly distinguishes nutrient availability, nutrient retention, rooting conditions, oxygen availability, salinity/sodicity, lime/gypsum and workability. Its suitability ratings depend on crop, input level and water system. Therefore a final GAEZ suitability score is not a crop-independent soil attribute. Use its component logic and underlying properties; use yields to check the resulting interactions. [GAEZ v4 documentation](https://gaez-v4-data.fao.org/data/documentation/GAEZ%20v4%20Model%20Documentation.pdf)

HWSD v2 supplies approximately 1 km soil mapping units, seven soil layers, rootable depth and water-capacity information. This is a practical source for substrate constraints. Version differences from the HWSD v1.2 used by GAEZ v4 need explicit recording. [FAO HWSD](https://www.fao.org/land-water/resources/tools/databases/hwsd/en)

SoilGrids supplies finer soil-property predictions, including texture, coarse fragments, pH, CEC and water content, with uncertainty quantiles. Its documentation also identifies masked areas and uneven accuracy. Use HWSD/contextual inference for gaps, not zero fertility. Modern organic carbon, nitrogen and pH must not automatically be interpreted as unmanaged 1300 fertility. [ISRIC documentation](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html)

Separating nutrient retention from initial fertility is useful internally: capacity to retain additions is not the same as having abundant nutrients initially. We should test whether it needs a separate visible attribute before adding a seventh icon.

### Water evidence

HydroATLAS supplies basin/reach attributes including modeled natural discharge and inundation information. Its technical documentation identifies WaterGAP as the discharge source. Do not use its modern reservoir volume or regulation fields as natural medieval endowments. [HydroATLAS](https://www.hydrosheds.org/hydroatlas), [technical documentation](https://data.hydrosheds.org/file/technical-documentation/HydroATLAS_TechDoc_v10_1.pdf)

MERIT Hydro provides approximately 90 m terrain-related hydrology, including height above nearest drainage. Combine river-relative elevation, routing and distance with freshwater supply to screen accessibility. HAND is not flood frequency or proof that a canal can serve the land. Its documented weaknesses include delta bifurcations and coastal land below sea level. It covers 90°N–60°S; its access and dual-license terms need recording when acquired. [MERIT Hydro](https://global-hydrodynamics.github.io/MERIT_Hydro/)

Our cached GRUN source reconstructs monthly runoff at 0.5 degrees over 1902–2014. Routed monthly sequences can inform seasonality and interannual variability, with modern-period and resolution uncertainty. Runoff is not local river discharge until routed. Monthly means cannot establish predictable annual flood peaks. Historical river evidence remains necessary for a label such as reliable annual inundation. [GRUN methods](https://essd.copernicus.org/articles/11/1655/2019/index.html)

Floodplain extent and drainage must remain separate: a periodically flooded river plain is not equivalent to permanently saturated peatland. GFPLAIN250m provides geomorphic floodplain evidence but excludes important desert/ice settings and high latitudes, and uses a river catchment-size threshold. It cannot be the sole global source, especially for the Nile. Use GLWD, terrain and river connectivity as complementary evidence with explicit inference. [GFPLAIN methods](https://pmc.ncbi.nlm.nih.gov/articles/PMC6335616/)

GLWD v2 maps water/wetland classes and within-cell fractions at 15 arcseconds for 1990–2020. Its riverine, coastal and saturated categories help distinguish settings, but modern rice paddies are managed land, not an inert natural attribute. [GLWD v2](https://www.hydrosheds.org/products/glwd), [class definitions](https://www.hydrosheds.org/glwd-details)

The cached wetland-loss reconstruction begins in 1700. It can identify later drainage and support a historical correction, but does not directly reconstruct 1300 or undo earlier drainage. [Wetland reconstruction](https://zenodo.org/records/7616651)

### Additional constraints, not mandatory new icons yet

Salinity should not disappear inside a fertility average. HWSD/GAEZ components can supply a constraint, cross-checked against FAO's modern salt-affected-soil map. Modern irrigation-induced salinity requires historical interpretation. [FAO GSASmap](https://www.fao.org/global-soil-partnership/data/global-map-of-salt-affected-soils-gsasmap/en)

WHYMAP maps aquifer productivity and recharge environments. It can support a groundwater extension, but does not establish medieval well depth, spring availability or a feasible qanat route at each location. Do not equate a productive deep aquifer with accessible 1300 irrigation. [BGR WHYMAP service](https://services.bgr.de/arcgis/rest/services/grundwasser/whymap_gwr/MapServer)

## What belongs in existing attributes or buildings

Extend climate to preserve thermal growing-season and rainfall-seasonality differences rather than adding a redundant generic agricultural-climate score. Extend topography using slope distributions, valley land and coastal elevation. Extend vegetation for woodland/scrub/grass/peat distinctions where needed. Keep soil and hydrological information separate from these labels.

Clearable land is an output of vegetation removal, cultivable soil, slope, climate and water constraints. It is not another independent natural quality. Likewise do not make high-input potential, irrigation benefit or historical development into inert geography attributes. Existing clearing, terraces, bunds, drainage and canals belong to the starting investment ledger.

Not every attribute needs a direct food modifier. Some should principally control availability, costs or limits. In particular abundant water and extensive floodplain should not automatically grant the full benefit of constructed waterworks. Existing direct productivity estimates must not receive their soil/water advantages a second time.

## How to establish that this set is enough

1. Preserve continuous component data and uncertainty on the fine grid. Derive classifications there, then aggregate to locations using shares and joint occurrences, not only a majority class.
2. Check combinations on the same land: flat land in one part plus river water in another does not prove irrigable flat land exists. Retain the joint accessible fraction behind building limits.
3. Derive transparent initial class boundaries from agricultural constraints; avoid choosing boundaries merely to reproduce current capacities.
4. Compare native-only rules with added soil, then added water/floodplain/drainage, and finally a small number of building-specific interactions. Use province-grouped and geographical holdouts and remove each family in turn to measure its additional value.
5. Evaluate starting and maximum clearing, field-management and water-management contributions separately, always absolute units multiplied by the location multiplier. Assess physical plausibility independently of agreement with the current model, whose improvement shares contain assumptions.
6. Use historically scaled GAEZ rainfed/irrigated and input scenarios to diagnose responses. The difference between irrigation gains at high and low inputs measures an interaction; do not treat those two gains as independent additive bonuses.
7. Keep all ownable locations assigned, with fallback source and uncertainty recorded. Absence of a soil/wetland record is not evidence of absence. Preserve the equal-area game convention; use fractions for geographical descriptors, without restoring a location-size capacity bonus.

The result should be a small understandable rule system, not an arbitrary maximum-capacity attribute. A flat, seasonally flooded, well-watered location can qualify for Basin Irrigation; inherited building levels distinguish an established agricultural system from an otherwise similar unbuilt frontier. Exact maxima still need the empirical fit and resource-budget checks above. This research supports the candidate mechanisms and available sources; it does not yet demonstrate that six attributes reproduce every target distribution.
