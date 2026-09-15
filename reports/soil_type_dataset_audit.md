# Soil type dataset audit

2026-09-14. Read-only source audit; no location assignments or game changes.

## Source actually inspected

Downloaded FAO's HWSD2_DB.zip (9,304,008 bytes), extracted HWSD2.mdb and read the lookup tables, field metadata and HWSD2_LAYERS with access-parser 0.0.6. Archive SHA256: 6c69e09137a8150f53c8a893fe3e4426d6b5cceb635c00378b54b7d64a9736c0.

Source: https://s3.eu-west-1.amazonaws.com/data.gaezdev.aws.fao.org/HWSD/HWSD2_DB.zip
Documentation: https://www.fao.org/land-water/resources/tools/databases/hwsd/en/

Cached source identity, lookup tables and record audit: data/raw/documentation/soil_audit/. The raster was not acquired in this audit. Record counts below are not area fractions or EU5 location counts. No source redistribution license is inferred from download access.

## Observations

D_TEXTURE_USDA has 13 entries: heavy clay, silty clay, light clay, silty clay loam, clay loam, silt, silt loam, sandy clay, loam, sandy clay loam, sandy loam, loamy sand and sand. This implementation splits clay into heavy/light. Only nine texture codes occur among the 58,405 D1 component records inspected; 1,289 records have no texture code. Nulls must not become infertile soil.

WRB2 identifies Histosols (HS), providing an organic-soil classification independently of the mineral texture codes. There are 881 HS topsoil component records. COARSE measures coarse fragments by volume: 57,116 D1 records have valid values; 1,750 have at least 35%, and 458 at least 40%. These counts alone do not establish global spatial importance. PHASE1/PHASE2 also identify stony, gravelly, rudic and skeletic conditions.

## Proposed game-facing types

Retain Sand, Loam, Silt, Clay, Peat and recommend one additional candidate: Stony. No depth variants and no new fertility subclasses.

A provisional broad mineral mapping is Sand = codes 11/12/13; Loam = 5/9/10; Silt = 6/7; Clay = 1/2/3/4/8. In particular sandy loam goes to Sand and clay loam to Loam: these are game simplifications, not exact equivalences. Continuous fractions must remain in the source ledger so alternative grouping can be tested.

Peat uses Histosol classification. Stony would use substantial coarse-fragment content and corroborating phase information. Neither the final threshold nor precedence in mixed organic/stony records is fixed by this audit. Do not label every shallow soil Stony. Classify components before location aggregation and preserve shares. Ice, water, unknown and modern artificial-soil classes need explicit handling; they are not additional productive soil types.

Fertility remains separate. Salinity, carbonate, volcanic properties and shrink-swell behavior are not all captured by texture plus fertility; retain source fields and only propose further visible categories if a tested gameplay distinction requires them. Do not append these overlapping descriptions casually to the same classification.

## Conclusion and limits

The database contains the fields needed to construct this six-type candidate. It does not prove that six types reproduce the target building/capacity distributions. That requires spatial mapping and held-out evaluation against the existing location targets, with source uncertainty and the deliberately simplified classification retained.
