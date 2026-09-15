# Vegetation around 1300: source audit and proposed game classes

Research date: 2026-09-14. This document records the initial research proposal. The user subsequently selected the broader candidate set; see [implemented set and validation](vegetation_1300_implementation.md) for the current 16-value prototype, occupancy exclusions and dated-source limitations. The initial ten-value recommendation below is superseded.

## Recommendation

Keep the existing Vegetation attribute and its seven vanilla values. Add Scrubland, Savanna and Tundra as the initial candidates, for ten visible values. Start with the cached 5-arcminute SAGE potential natural vegetation (PNV), apply historical land-use constraints from the cached LUH2 year-1300 states and HYDE cropland, and check regional openness against pollen evidence. Preserve source fractions and uncertainty before deriving one representative location class. This is a proposed reconstruction method, not an already validated 1300 map.

The geography should distinguish current cover from underlying natural vegetation internally. A farmland label records a historically cultivated landscape; it must not independently award the productivity already supplied by starting clearing buildings.

## Verified existing inputs

The installed vanilla definition contains desert, sparse, grasslands, farmland, woods, forest and jungle. Confirmed using the test builder's block reader; definition SHA256: b4d4c4b0f19741426b8b147fee1f92db35e0c4f969c7cd6c50959c056c075eb9.

Local files inspected:

- data/raw/location_inputs/pnv.nc: 2160 by 4320, 5 arcminutes; accompanying pnv_README inspected.
- data/raw/location_inputs/luh1300.npz: 720 by 1440, 0.25 degrees, primary/secondary forest and non-forest, five cropland categories, managed pasture, rangeland, urban; year 1300.
- data/raw/location_inputs/hyde/cropland.nc and total_irrigated.nc.
- data/raw/ecoregions/Ecoregions2017.zip: ecological boundary context is already cached.
- data/raw/location_inputs/landcover_provenance.json: source identities and imported-cache hashes.

## Source assessment

### SAGE potential natural vegetation: practical baseline, already cached

[Publisher and download](https://sage.nelson.wisc.edu/data-and-models/datasets/global-potential-vegetation-dataset/).

The 5-arcminute product distinguishes 15 classes, including eight forest/woodland types, savanna, grassland/steppe, dense/open shrubland, tundra, desert, and polar desert/rock/ice. Its local README describes a modern land-cover starting point, substitution of vegetation-model estimates in heavily cultivated/poorly represented areas, and climate rules.

It is a counterfactual natural-vegetation estimate, not observed 1300 cover. It combines forest and woodland within its forest classes and does not directly supply canopy density. The README says wetlands were excluded from the upland classification; do not use it alone for wetland vegetation.

### LUH2 v2h + HYDE: historical human modification

[LUH2 data](https://luh.umd.edu/data.shtml), [method definitions](https://www.luh.umd.edu/faq.shtml), [HYDE methodology](https://essd.copernicus.org/articles/9/927/2017/).

LUH2 offers annual historical states for 850–2015 at 0.25 degrees, including cropland, grazing land, primary and secondary natural vegetation. The year-1300 slice is already local. Its forest/non-forest division is a first-order estimate based on potential forest land, not measured canopy closure. Secondary vegetation means disturbance/recovery history since the simulation baseline; it does not mean open woodland.

HYDE combines historical population estimates and spatial allocation rules. It separates cropland and kinds of grazing, including unconverted rangeland. Grazing land must not all become cleared fields. LUH2 depends on HYDE, so the two are not independent validation. Use their dated land-use estimates explicitly as assumptions about human modification, without fitting to EU5 population.

### REVEALS: pollen-based checks, not a complete world map

[Europe](https://essd.copernicus.org/articles/14/1581/2022/), [European data](https://doi.org/10.1594/PANGAEA.937075).

European reconstructions use 1128 pollen records on a 1-degree grid, with plant cover estimates, uncertainty and temporal windows. Use regional forest/open-land patterns as an evidence-based check; coverage and confidence vary.

[China](https://essd.copernicus.org/articles/15/95/2023/essd-15-95-2023.html).

Temperate/northern subtropical China has 94 pollen records supporting 75 one-degree cells. The window 0.7–0.35 ka BP corresponds to approximately 1250–1600 CE, encompassing 1300 but not isolating it. Many cells share grouped estimates. Open land is not automatically cropland; missing taxa and bare-ground/cropland limitations matter. Apply published standard errors and compare at the source's actual spatial support.

### KK10: sensitivity to historical land use

[Dataset](https://doi.pangaea.de/10.1594/PANGAEA.871369).

Global annual reconstruction from 8000 BP to 1850 CE at 5 arcminutes. The published variable is total land-use fraction, not separate forest, scrub and crop cover. Useful as an alternative human-impact scenario, not a replacement vegetation classifier or independent observation. CC BY 3.0; archive about 17.3 GB. Not acquired in this task.

### Pongratz: directly dated global vegetation, restricted-use candidate

[Data and complete legend](https://www.wdc-climate.de/ui/entry?acronym=RECON_LAND_COVER_800-1992).

Annual global maps from 800 to 1992 at 0.5 degrees, with 11 natural vegetation and three agricultural types. Includes 1300 and uncertainty bounds before 1700. Early agricultural allocation is population-based. The catalog states scientific use only; do not make this a production/export dependency without suitable permission or clarified terms. Its uncertainty bounds are extremes for individual years, not coherent alternative time series. Metadata checked; data not acquired.

### Regional and finer-resolution supplements

[LANDFIRE Biophysical Settings](https://www.landfire.gov/vegetation/bps) models vegetation before Euro-American settlement with disturbance regimes. It can help check North American prairie/woodland patterns, but is not specifically a 1300 reconstruction or a global product.

[Hengl/OpenLandMap potential biomes](https://doi.org/10.5281/zenodo.3526619) provide a finer 250 m modeled alternative based on pollen/biome reference data and recent climate. Higher pixel resolution does not establish greater historical accuracy. The published [method](https://pmc.ncbi.nlm.nih.gov/articles/PMC6109375/) reports substantial biome-class uncertainty; evaluate before replacing the cached baseline. Not acquired.

## Proposed player-facing values

| Value | Status | Intended meaning |
|---|---|---|
| Desert | Retain | Predominantly bare desert |
| Sparse | Retain | Thin, discontinuous vegetation |
| Grasslands | Retain | Grass/herb-dominated open cover |
| Farmland | Retain | Predominantly cultivated historical landscape |
| Woods | Retain/refine | Open wooded landscape or woodland mosaic |
| Forest | Retain/refine | Predominantly forested landscape |
| Jungle | Retain/refine | Tropical humid forest |
| Scrubland | Add | Shrub-dominated cover |
| Savanna | Add | Grass-dominated landscape with scattered trees |
| Tundra | Add | Arctic/alpine low vegetation |

Do not multiply forest classes into all combinations of climate, tree species and density yet. Keep those source distinctions internally. Wetland topography and peat soil remain available; a separate marsh/mangrove vegetation value would require a demonstrated modelling need and a suitable historical reconstruction.

## Construction and validation rules

1. Retain natural vegetation types and historical land-use fractions separately on the fine grid.
2. Reconcile historical cultivated/open/wooded shares with PNV and ecological boundaries. Constrain downscaling to preserve parent-cell fractions; fine pixels are inferred placement, not newly observed historical detail.
3. Distinguish pasture conversion from grazing of natural vegetation. Do not subtract every land-use share from forest or treat secondary forest as scrub.
4. Preserve current-cover and potential-cover descriptors so later building limits can reference remaining woody cover without losing the history of existing clearing.
5. Aggregate fractional mixtures to EU5 geometry only at the end; assign one UI class with confidence and runner-up class. Do not restore physical-area scaling to the equal-area capacity model.
6. Test thresholds and disagreements in Scandinavia/Russia, France, the Mediterranean, India, East China, African savannas, Amazonia and North American prairie/forest margins. Pollen constrains regional openness, not each EU5 boundary.
7. Complete all ownable locations with documented fallback rules. Distinguish missing inputs from truly sparse or bare vegetation.
8. GAEZ then helps assess agricultural suitability of clearing; it is not evidence that a forest existed in 1300. Fertile forest and infertile forest should remain distinguishable through soil/climate, without relabelling vegetation to force a capacity target.

We have sufficient data to construct and evaluate a global 1300 approximation. The strongest supported additions are the three broad missing vegetation formations. Exact historical woodland density, fine placement of cleared parcels and wetland boundaries remain inferred and should be reported as such.
