# Task 0021: Dense focused-alert map context

## Status

Proposed — problem and boundaries recorded; implementation not started

## Depends on

Task 0020 Slice E is complete. It supplies selected-alert viewport fitting,
provider geometry rendering, retained unprojected geography, responsive label
budgets, collision placement, and a checked-in Natural Earth 1:10m focused
place layer. This task enriches only the contextual labels within that existing
viewport.

Slices F and G of Task 0020 are complete. Their settlement selection and
hourly-forecast work consume a stable place identity
and coordinates rather than depending on Natural-Earth-specific rank fields;
preserve that boundary when replacing the candidate source.

## Context

Selected polygonal alerts correctly fit the map around their complete provider
geometry. Natural Earth's 1:10m populated-place layer nevertheless remains a
selective cartographic dataset: the checked-in compact artifact contains 7,342
places worldwide. It includes major cities, many administrative capitals, and
only a sampling of smaller towns.

This is sufficient for country maps and many regional warnings, but visibly
sparse for small rural polygons, narrow river corridors, remote islands, and
coastal or marine warnings. The current Admin-1 annotations are also derived
from the region metadata of visible Natural Earth settlement points. A region
therefore receives no label when the viewport happens to contain no such point.

Observed examples include a Rio Puerco flood warning near Bernardo, New Mexico,
and Alaskan marine advisories around named capes and coastal waters. The map is
already zoomed correctly in these cases; the empty appearance is a label-data
coverage problem, not a viewport or projection failure.

## Problem

- Natural Earth 1:10m is not a comprehensive settlement gazetteer.
- Administrative labels are incorrectly coupled to settlement presence.
- Offshore alerts may truthfully contain no settlement at all and need named
  physical or marine context rather than increasingly obscure towns.
- Loading a full global gazetteer at runtime, querying a live geocoder for each
  selection, or accumulating provider-specific fixes would add disproportionate
  complexity to a personal terminal weather application.
- Task 0020 should not become an open-ended map-engine project merely because
  its completed alert-focused viewport reveals gaps in the base label source.

## Desired outcome

Alert-focused maps use a compact, checked-in, offline gazetteer to find useful
labels within and immediately around the already-computed viewport:

- substantially denser cities, towns, villages, and administrative seats;
- independent global first- and second-order administrative labels where the
  source provides them; and
- only if terrestrial improvements leave a demonstrated need, a deliberately
  small set of named contextual features such as bays, capes, channels,
  islands, rivers, and lakes.

The result follows one global data and ranking path. It does not treat US
states, counties, NWS zones, or US settlements as a special presentation tier.
Provider geometry remains the sole authority for the warning footprint.

This remains a static label lookup for an existing viewport, not a general map
engine.

## Firm architectural boundary

In scope:

- build-time ingestion and reduction of an openly licensed gazetteer;
- one compact versioned resource containing only fields needed for labels;
- a small local viewport query, preferably over country/grid buckets rather
  than scanning or materializing an unrestricted source dump per selection;
- stable category-aware ranking and existing Textual collision placement;
- settlement activation compatibility with Task 0020 Slices F and G;
- source, version/date, licence, attribution, and reproducible build notes; and
- deterministic fixture tests with no network dependency.

Out of scope:

- slippy-map tiles, roads, buildings, addresses, parcels, or land-use layers;
- user-controlled pan or zoom, arbitrary map browsing, or navigation history;
- new projections, map servers, spatial databases, or a general GIS API;
- drawing new administrative, hydrological, or transport boundary geometry;
- reverse geocoding or live GeoNames/OpenStreetMap calls during application use;
- downloading data during package installation or first launch;
- exhaustive display of every candidate when terminal cells cannot contain it;
- perfect cartographic label placement;
- provider-specific UI branches or an NWS-only county/zone mode; and
- interpreting a nearby label as evidence that the warning applies there.

If implementation begins to require any of these excluded capabilities, stop
and reconsider the task rather than growing the abstraction.

## Candidate data contract

Use GeoNames as the first candidate for the dense offline gazetteer. At the time
this task was written, its documented `cities500` extract contains roughly
185,000 cities with population above 500 plus administrative seats down to
PPLA4. GeoNames also publishes global Admin-1 and Admin-2 code/name tables and
classifies records into administrative, populated-place, hydrographic, terrain,
undersea, and other feature groups.

Do not ship the upstream archive unchanged. A reproducible builder should emit
only a compact schema such as:

```text
stable source id
display name
longitude / latitude
country code
Admin-1 / Admin-2 codes and display names where available
feature category / feature code
population or source rank
```

Keep coordinate precision appropriate for terminal label placement. Omit
alternate-name collections, timezone, elevation, modification history, and
other unused columns. Sort deterministically and compress with reproducible
metadata, following the existing Natural Earth resource builders.

Before adoption, measure and record:

- source record counts and licence/attribution requirements;
- compact uncompressed and compressed artifact sizes;
- import/decompression time and retained Python memory;
- focused viewport query time for representative dense and sparse regions; and
- actual coverage of the motivating rural and marine fixtures.

The measurement decides whether `cities500` is acceptable or whether a smaller
population threshold/extract is warranted. Do not commit the full GeoNames
`allCountries` archive.

## Runtime query and ranking

The focused viewport continues to come from Task 0020. Query a modest halo
around it so nearby context can remain visible when a warning polygon narrowly
misses a settlement or crosses a border. Longitude wrapping must retain the
existing antimeridian behavior.

Keep label categories independent:

1. **Administrative context:** obtain Admin-1/Admin-2 labels from dedicated
   administrative records or label points, never indirectly from whichever
   settlements survived ranking. Retain every distinct administrative area in
   the queried focused extent; labels remain passive, italic, marker-free, and
   may overlap rather than be silently omitted.
2. **Settlements:** prioritize points inside selected provider geometry, then
   visible or halo points outside it. Within those groups rank administrative
   seats, population/source importance, distance to the geometry or viewport
   centre, and stable name/id tie-breakers. The responsive/collision budget
   still limits what can be rendered.
3. **Physical context:** add only after a fixture demonstrates that settlement
   and administrative coverage cannot ground the map. Prefer a short allowlist
   of useful feature codes and a stricter display budget. These labels are
   passive and visually subordinate to settlements and warning geometry.

The query may return candidates across national borders because those labels
can explain a focused alert's location. Country codes remain useful for
identity, localized naming, and tie-breaking, not as a hard viewport filter.

Settlement widgets should receive source-neutral records. A future selected
settlement must still have a stable key, name, and coordinates for the hourly
forecast flow; changing label datasets must not change the application's main
weather location.

## Provider-area fallback

Provider `area_names` remain useful navigation and document metadata but are
not automatically trustworthy geographic label points. Do not parse arbitrary
warning prose or place an area name at an invented coordinate.

If a later warning-library contract exposes individually named affected-zone
geometries, those names may be placed using their own real geometry through a
provider-neutral model. That is an optional upstream enhancement, not a reason
to add NWS-specific zone fetching or name/geometry guessing in Wevva.

## Implementation slices

### Slice A — audit and compact artifact prototype

- Add a reproducible, development-only GeoNames builder or extend the existing
  geography build tooling without adding runtime download behavior.
- Prototype the minimal settlement schema from `cities500` and record count,
  compressed size, load time, memory, and representative query timings.
- Verify licensing and add attribution/provenance before committing generated
  data.
- Exercise rural, dense urban, cross-border, antimeridian, tiny-island, and
  marine fixture extents. Stop here if the artifact cost is disproportionate.

### Slice B — dense focused settlements

- Add a source-neutral focused-place model and bounded viewport query.
- Use the dense source only for selected-alert views; keep Natural Earth for
  whole-country and other existing maps.
- Preserve inside-geometry priority, deterministic ranking, collision limits,
  and no-network resize/selection behavior.
- Keep Task 0020's existing Natural Earth layer as a safe fallback when the new
  resource cannot load.

### Slice C — independent administrative labels

- Add global Admin-1 and Admin-2 label records independently of settlements.
- Render every distinct administrative area represented in the focused query
  extent with the existing passive, italic, marker-free treatment.
- Apply the same source and hierarchy rules worldwide, with no special US
  county tier.
- Remove the current derivation of region annotations from settlement metadata
  after equivalent or better deterministic coverage is verified.

### Slice D — optional named physical context

- Proceed only if named marine/rural fixtures remain ungrounded after Slices B
  and C.
- Select a narrow, documented global feature-code allowlist and measure its
  incremental artifact/runtime cost before integration.
- Use a separate, subordinate label budget; do not add feature geometry or turn
  the map into a general topographic viewer.

## Acceptance criteria

- The alert viewport and polygon rendering are unchanged from Task 0020.
- Focused terrestrial fixtures which were blank under Natural Earth show useful
  nearby settlements, including small communities where source data exists.
- Admin-1/Admin-2 context does not depend on the presence or visibility of a
  settlement and does not omit one area merely because an alert spans several.
- Administrative labels contain no marker dots and are not selectable.
- US and rest-of-world fixtures follow the same category and ranking rules.
- Cross-border and wrapped-longitude viewports return stable relevant labels.
- A map resize performs no file reload, rebuild, or network request.
- Country maps and unrelated location/world maps retain their existing compact
  Natural Earth behavior and performance.
- Corrupt or absent dense data falls back safely without suppressing land or
  alert geometry.
- The wheel and source distribution contain the intended compact resource,
  licence, attribution, and provenance, but no upstream source archive.
- Measured package size, decompression time, retained memory, and query latency
  are documented before the data source is accepted.
- Marine/physical labels are not implemented unless Slices B and C leave a
  demonstrated fixture gap.

## Verification

All automated tests use checked-in compact fixtures or the final generated
resource; they never download GeoNames or call a geocoder.

```bash
uv run python -m compileall -q wevva
uv run python -m unittest tests.test_geography
uv run python -m unittest tests.test_alerts_centre_map
uv run python -m unittest discover -s tests
uv build
```

Add focused tests for the motivating New Mexico river corridor and an Alaskan
marine/coastal extent, plus a dense urban viewport, a multi-region border, a
cross-country border, and the antimeridian. Assert stable ordering, category
budgets, marker-free administrative labels, source-neutral settlement keys,
fallback behavior, packaged-resource presence, and zero network work.

Manual verification remains necessary for whether the resulting labels are
actually legible and geographically useful at representative terminal sizes.
Record the tested viewport, displayed labels, terminal dimensions, artifact
size, load time, and retained memory; do not describe a single fixture as
proof of exhaustive global coverage.

## Relevant code

- `wevva/widgets/country_alerts_map.py`
- `wevva/geography.py`
- `tools/build_natural_earth_places.py` as a reproducibility pattern
- `wevva/data/README.md`
- `docs/architecture.md`
- `docs/development.md`
- `tests/test_alerts_centre_map.py`
- `tests/test_geography.py`
- Task 0020 Slices E, F, and G

## Source references

- Natural Earth 1:10m populated places:
  <https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-populated-places/>
- GeoNames downloadable gazetteer, schema, extract descriptions, and licence:
  <https://download.geonames.org/export/dump/>
- Creative Commons Attribution 4.0 licence used by the GeoNames export:
  <https://creativecommons.org/licenses/by/4.0/>

## Decisions and handoff notes

- The screenshots motivating this task show correctly focused alert viewports;
  do not reopen viewport fitting without separate evidence.
- Natural Earth remains the appropriate low-cost country/base-map source. Its
  selective place coverage is not a failed Slice E implementation.
- The current focused implementation loads
  `natural_earth_10m_populated_places.json.gz`, ranks points inside the selected
  polygon first, retains at most 32 candidates, and lets the responsive map
  budget display at most eight settlement callouts.
- Current Admin-1 labels are computed by grouping the `region_name` attached to
  every visible detailed settlement before the 32-place truncation. That is the
  coupling Slice C should replace.
- Existing region labels deliberately fall back to their preferred row rather
  than being hidden when collision placement is exhausted; overlap is preferred
  to silently omitting administrative context.
- No current-alert request, selected-alert change, or terminal resize should
  perform network work for map labels.
- GeoNames is the leading candidate, not an irrevocable dependency. Slice A
  must establish that its compact artifact has acceptable cost and coverage.
- The stopping rule is explicit: this task ends with useful static labels for
  an existing warning viewport. It does not own general-purpose mapping.
