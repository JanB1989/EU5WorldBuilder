# Geographic river network and separate EU5 mapping

This pipeline constructs geography, not a population-capacity fit. The physical
network and game representation have separate files, stages and fingerprints.

## 1. Geographic network

Source: [HydroATLAS / RiverATLAS 1.0](https://www.hydrosheds.org/hydroatlas), CC BY 4.0.
The already imported source is `data/raw/location_inputs/hydrology/river_reaches.parquet`;
its acquisition provenance is in `evidence/location_input_manifest.json`.
No sibling repository or runtime is required.

`worldbuilder rivers --stage network` creates
`data/processed/rivers/network.parquet`: a GeoParquet dataset in OGC:CRS84
(longitude, latitude), with all **8,477,883** reaches. The source geometry,
downstream IDs, basin identity, discharge fields, catchment area, downstream
distance and endorheic flag are preserved. IDs become integers and source
game-alignment fields are removed. No game coordinates, levels or minimum-river
filter enter this dataset. Line vertices run upstream to downstream.

The adjacent manifest records raw and generated checksums, source attribution,
transformations and code fingerprint. Validation checks all IDs, complete links,
acyclicity, geometry and endpoint agreement. All 8,321,721 nonterminal links meet
exactly in the imported data. The source overview uses continuous discharge
colour, with a separately configurable display filter; this does not delete
small streams from the dataset.

This is modern modelled hydrography, not an observed map for 1300. Channel shifts,
historical engineering, reservoirs, discharge changes and navigability are not
reconstructed. The network remains a physical reference, with those limitations.

## 2. EU5 projection and raster routing

`worldbuilder rivers --stage export` reads the geographic network and
`configs/rivers.json`. It verifies that the source/network fingerprints are
current. The game installation is read from ignored `geography_test.local.toml`.
The source locations raster, inventory and fitted geographic registration are
owned input files under `data/raw/location_inputs`.

Only this stage controls:

- Minimum mean discharge to display, with downstream closure so falling discharge
  cannot arbitrarily truncate a selected river before its outlet.
- Five discharge bands and their verified native palette entries.
- The game-map projection, clipping, raster generalization and minimum visible
  branch length.
- Junction snapping radius, connectivity markers and native-level audit.

Initial bands start at **50, 150, 500, 2,000 and 8,000 m³/s**. They are editable
cartographic defaults, not claimed empirical boundaries of historical
navigability or exact equivalences to vanilla gameplay. Below-threshold reaches
retained by downstream closure use level 1. The source overview independently
displays reaches from 10 m³/s.

The exporter follows source links to form mainstems and tributaries. At each
confluence, the upstream branch with greatest mean discharge continues the
mainstem. Rendering proceeds downstream to upstream, with larger branches first.
Lines are four-connected and one pixel wide. Small self-touches are generalized
into simple paths; confluence offsets can be routed within twelve game pixels.
The original route is tried first. Only a collision or missing raster parent
triggers attempts at three, six and twelve pixels; an already valid join is kept.
The short approach path may use an additional four-pixel buffer, but the
connection itself must remain within the configured snapping radius.
Snapping cannot cross water or join an unrelated basin. A later accidental
collision stops that branch and is recorded, rather than creating a false link.
Short branches are removed only from the game bitmap, with rollback that preserves
their mainstem. All selected source reaches remain traceable through
`export_reaches.parquet` to `export_branches.csv`.

The existing separable geographic registration is approximate, especially near
coastlines and islands. River pixels landing in native sea/lake zones are clipped;
visible sections on opposite sides of lakes become separate game components.
This can also fragment a line at a mismatched coast. The report exposes water
clipping, out-of-projection branches, collision omissions and missing-parent
branches. Accounting for a source reach does **not** mean every part of that reach
successfully appears in the game bitmap.

The game map's fitted coverage is approximately 56°S–73°N. Physical data outside
this area remain in the geographic dataset. The coverage table's `continent`
column carries original source-tile codes, including `north` and `south`; these
are source partitions, not a newly derived political/continental classification.

## Junction limitation

Palette indices 0, 1 and 2 are source, joining and splitting markers. The five
chosen width entries are 4, 7, 11, 13 and 15. Prior native exports and controlled
tests established that red/yellow junction markers promote their location to
**native river level 5**, irrespective of adjacent river widths.

This exporter retains red confluences for connectivity and reports the effect.
`location_levels.csv` has the intended physical size and marker-aware prediction
as separate columns. The red-junction preview makes the affected geometry easy
to inspect. There is deliberately no supposedly harmless “remove junctions”
switch. A future alternative connection policy belongs here, not in the physical
network. RiverATLAS has one downstream link per reach; unsupported distributaries
and yellow split markers are not invented.

Sources are placed at upstream leaves, with one green marker per raster tree.
Red markers belong on the tributary pixel immediately BEFORE its receiving
mainstem, not on the three-neighbour junction centre. All 1,286 red markers in
the native bitmap have two neighbours. The original exporter violated this rule;
its otherwise acyclic trees caused malformed-affluent and missing-source errors.
Routing now reserves space around existing junctions and does not attach to
source/outlet endpoints. Nearby ambiguous connections are snapped within the
configured radius or omitted with an explicit ledger entry.

Validation removes red markers and verifies every remaining segment is a simple
path. Each red connects a tributary endpoint to a receiving segment interior;
each tributary has one receiver, and green sources start the receiving mainstems.
The complete raster must be acyclic, have exactly one source per tree, retain
all five width classes and round-trip through indexed PNG unchanged. These
checks run before writing the export. They are offline validation, not a claim
of a successful engine load.

## Outputs and use

- `artifacts/river_network/index.html`: source, intended game-size and junction views.
- `data/processed/rivers/network.parquet`: complete physical source network.
- `artifacts/river_network/export_reaches.parquet`: selected reach, branch and size table.
- `artifacts/river_network/export_branches.csv`: every selected branch and its routing outcome.
- `artifacts/river_network/location_levels.csv`: intended versus predicted native sizes.
- `artifacts/river_network/export_manifest.json`: inputs, exact settings, fingerprints and checks.
- `artifacts/river_network/mod/EU5 World Builder - Rivers/in_game/map_data/rivers.png`:
  game-sized, indexed PNG in an isolated prototype mod folder.

No production mod is overwritten or deployed by these commands. Change the
export settings and rerun only the exporter to experiment with river sizes and
pixel mapping. Use the complete GeoParquet for future physical adjustments.

## Corrected export, 17 September 2026

The export selects 396,309 reaches and draws
690,099 pixels in 11,184 locations.
There are 2,170 trees and 4,442 correctly placed tributary
markers. The source data and all five discharge thresholds remain unchanged.
See the current manifest for branch omission counts and per-location marker
promotions; these are predictions awaiting the user's engine check.

## Main mod integration and compatibility

`worldbuilder geography-test --export-only` rebuilds the main **EU5 World Builder**
mod using verified existing geography assignments and the latest river export,
then syncs it to the configured live mod folder. No separate river addon is
needed. `--build-only` suppresses syncing. Stale river configuration, exporter
code, missing encoding validation or a changed PNG prevents river deployment.

Native resource/building predicates now recognise active mapped subtypes through
their configured parent classes. Inactive candidates (mangroves and saltmarsh in
this build) are excluded. A pre-deployment check rejects undefined custom
climate, vegetation or topography references. Existing lumber resources and
explicit starting orchards, terraces, forestry and irrigation are retained even
where representative geography or river registration misses their local site.
New eligibility continues to use the geographical rules. Costs, outputs and
starting building levels are unchanged. Custom topographies also have the
required proximity modifiers and capital modifiers.

Regression coverage includes malformed red junctions, closely spaced joins,
rotation, missing/duplicate/misplaced sources, cycles, all five widths, inactive
class references, unchanged native inputs and building balance, and stale/corrupt
river deployment. The complete global bitmap passes the same native encoding
validator as the synthetic fixtures.

## Ownable-location mapping filter

The mapping configuration now enables `export.ownable_locations_only`. It uses
the game's `default.map` exclusions through the complete zone inventory, covering
non-ownable land, impassable mountains, lakes and sea zones. Clipping takes place
before routing and marker assignment. Junction snapping uses the same exclusion
mask, so it cannot add a connection back across excluded land. Land remains
land in the PNG background palette; this does not turn excluded regions into water.

The full geographic network and geographic source preview are unchanged. A river
crossing excluded terrain becomes separate visible sections in the game bitmap.
The manifest verifies zero river pixels in excluded zones alongside the existing
source, junction and directed-connectivity checks. Branch accounting separately
records projected pixels excluded on unownable land.

This filtered export has 502,304 river pixels in 10,566 ownable locations, with
3,041 tributary markers. All five sizes remain present. Four additional regression
cases cover eligibility, clipping, fragment markers and blocked junction snapping;
the full suite passes 289 tests. Engine confirmation is left to the user.
