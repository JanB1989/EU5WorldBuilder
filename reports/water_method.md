# Water-only reference maps

The independent report calculates no crops, yields, food or population capacity.

## Quantity

Monthly unmet demand is ET0 minus ETa, in millimetres. Annual maps sum monthly
deficits; wet-season surplus cannot erase dry-season shortage without storage.
All three maps use the same land-surface hectare denominator. Irrigation affects
the serviced fraction only. Internal area converts mm to cubic metres for shared
river budgets; there is no cultivated-area or carrying-capacity result.

## Natural baseline

WorldClim 2.1 monthly climate (1970–2000) supplies a modern proxy.
https://www.worldclim.org/data/worldclim21.html

FAO-56 reference grass defines a crop-independent standard demand:
https://www.fao.org/4/X0490E/x0490e06.htm

Penman–Monteith uses monthly mean daily inputs, kJ-to-MJ radiation conversion,
G=0, and WorldClim's 2-m wind without a 10-to-2-m correction, following the
data author's interface: https://rspatial.github.io/geodata/reference/worldclim.html

A 100 mm reference soil bucket includes snow partition at 0°C and melt at
3 mm/degree/day. An analytical annual fixed point avoids spin-up bias.
Perennial snow accumulation/no thawing month is excluded, not declared fertile.
This is a rainfall baseline; natural flooding and groundwater are not reconstructed.

## Historical irrigation

The exact cached HYDE April 2025 files provide the CF-decoded 1300 time slice.
No silent date interpolation is allowed. Cache notes label them HYDE3.5, but
embedded metadata says HYDE3.4/test netCDF. The conflicting labels and hashes
remain explicit. This is modeled historical irrigation, not an archaeological
pixel survey: https://doi.org/10.5194/essd-9-927-2017

The recorded irrigation footprint receives water for the same reference demand.
This does not claim year-round reference-grass cultivation in medieval history.
Missing historical data remains missing.

## Upper surface-irrigation scenario

RiverATLAS corridors (mean flow ≥1 m³/s) and ETOPO 60-second sub-cell elevations
screen access. Shared parameters: 10 km access taper; 6 m low lift plus 15 m
terrain-resolution allowance; relief taper with 100 m scale; 40% efficiency;
60% runoff reserve. They are adjustable screening choices, not universal
historical maxima. Existing infrastructure is retained in the envelope.

Traditional-system mechanisms are supported by:
https://www.fao.org/4/ah810e/ah810e05.htm
https://www.fao.org/4/t7202e/t7202e08.htm

These references do not establish every numerical parameter or medieval boundary.
Wells, qanats, engineered seasonal reservoirs, long canals, and basin transfers
remain outside the upper screen. The result is not a complete technological maximum.

## Shared monthly water

GRUN 1970–2000 runoff is aggregated by area into HydroBASINS level-6 catchments.
Its native 0.5° resolution is not made more precise by the 5′ display.
Only bounded (≤0.5°) nearest fill is used for coastal gaps; others remain missing.
https://doi.org/10.5194/essd-11-1655-2019
https://www.hydrosheds.org/products/hydrobasins

RiverATLAS mean discharge constrains routed runoff. If accumulated runoff exceeds
the largest mapped mean reach discharge in a basin, a transmission survival
fraction reduces it. This reconciles source models and represents natural losses
approximately; it is not observed local transmission loss. It never creates water.
https://www.hydrosheds.org/hydroatlas
https://www.ncei.noaa.gov/products/etopo-global-relief-model

Withdrawals reduce downstream supply. Existing allocations have priority over
extensions, including downstream users. Irrigation losses are not credited as
return flows. Ledgers account for runoff, withdrawals, transmission and outlet flow.

### Nile delta correction

Coastal catchments 1060034170 and 1060034270 contain delta irrigation fed by the Nile,
despite separate natural drainage polygons. Their ≤30 m land is linked to main-Nile
withdrawal node 1060034260. This changes water origin, not irrigation extent or supply.
The geometry/elevation screen is approximate; other historic canal connections
are not comprehensively reconstructed.
https://knowledge.uchicago.edu/record/1009/files/MSR_IV_2000-Borsch.pdf

## Viewer and limitations

The HTML contains three maps, annual/monthly switching, shared zoom/pan and
regional presets. Annual scale: 0–2500+ mm. Monthly scale: 0–300+ mm.
Hover values use a labelled 20′ preview; GeoTIFFs retain 5′.
Green means little water shortage, not agricultural suitability.

1300 dates management extent, not climate. Flood inundation, groundwater, drainage,
salinity, crop calendars, canal routing, historical storage and investment costs
remain unresolved. The maps are exploratory, not validated historical water access.

## Reproduction

Working directory: /home/jan/development/HistoricalAgriculture1300

    uv run python scripts/acquire_water.py
    uv run ha1300 water --config configs/water.json --output artifacts/water
    uv run python scripts/validate_water.py
    uv run pytest -q

Large existing caches are configured in configs/water.json and remain read-only.
New downloads have URLs/checksums in data/raw/water/download_manifest.json;
all reused inputs and code have hashes in artifacts/water/manifest.json.
HYDE embedded licence: CC BY 3.0; HydroBASINS: HydroSHEDS licence;
RiverATLAS and GRUN: CC BY 4.0; ETOPO: US government data; WorldClim: its site terms.
Source data are not relicensed.

Mathematical/accounting validation and historical validation are separate.

## Difference map

The fourth panel is rainfed deficit minus upper-scenario deficit, with the same
cell averaging and no change to the water model. Positive values indicate less
shortage. A separate linear scale (0–100+ mm/year; 0–20+ mm/month) makes small
improvements visible. Only display colours saturate: GeoTIFFs retain full values
and missing-input masks. It shares the other maps' period, pan and zoom controls.

The fifth panel is rainfed deficit minus estimated 1300 deficit. It uses the
same 0–100+ mm/year and 0–20+ mm/month colour scale as the upper difference
panel. It retains missing historical evidence as missing and shares all view
controls. This is a presentation addition; no water parameters are changed.
