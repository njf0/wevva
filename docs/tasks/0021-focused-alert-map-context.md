# Task 0021: Hierarchical focused-alert map labels

## Status

Proposed — problem and boundaries recorded; implementation not started

## Depends on

Task 0020 Slice E is complete. It supplies selected-alert viewport fitting,
provider geometry rendering, retained unprojected geography, responsive label
budgets, collision placement, and a checked-in Natural Earth 1:10m focused
place layer. This task enriches only the contextual labels within the supplied
effective viewport.

Task 0024 may later replace that automatic viewport with a bounded effective
viewport produced by pan and zoom controls. Task 0021 owns the label policy for
either form of viewport—including scale-adaptive density—but does not own the
controls, viewport state, scale bar, or polygon-rendering performance.

Task 0034 now treats this label work as its first gate. Establish whether
country-scoped, hierarchy-aware labels solve the motivating context failures
before changing the base-map fill, boundaries, or warning texture. Task 0021
does not depend on Task 0034's rendering experiments.

Task 0020's settlement weather interaction consumes a stable place identity
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

The opposite failure is now demonstrated as well. `docs/assets/name-bug.png`,
`docs/assets/name-bug-2.png`, and the France `CoastalEvent` capture show far too
many names: UK local authorities, Swiss cantons, neighbouring-country regions,
and foreign cities surround a France alert; departments and provinces from
nearly every neighbouring country surround Brazil. Long names eventually run
together because the current placement policy preserves every administrative
label after collision-free positions are exhausted.

Natural Earth's settlement `ADM1NAME` field is not a consistent visual level.
It yields states in Brazil, cantons in Switzerland, legacy regions in France,
and counties, cities, or unitary authorities in the UK. Treating every distinct
value as an equivalent Admin-1 annotation produces neither a stable hierarchy
nor useful local context.

Observed examples include a Rio Puerco flood warning near Bernardo, New Mexico,
and Alaskan marine advisories around named capes and coastal waters. The map is
already zoomed correctly in these cases; the empty appearance is a label-data
coverage problem, not a viewport or projection failure.

## Problem

- Natural Earth 1:10m is not a comprehensive settlement gazetteer.
- Administrative labels are incorrectly coupled to settlement presence.
- Focused candidates are currently global, so settlements and political labels
  outside the Alerts Centre's selected country can dominate a coastal or border
  viewport even though their land is not part of the country map.
- One settlement metadata field is being treated as a globally equivalent
  administrative tier despite material differences between national systems
  and stale source names.
- The existing “retain every administrative label” fallback permits text to
  overlap and concatenate when there is no remaining row, making a nominally
  descriptive map harder to read.
- Administrative labels are placed before settlement callouts and can consume
  most useful cells without a category budget or name de-duplication.
- Candidate and display budgets are fixed rather than responding to the
  geographic scale of the effective viewport.
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
- independent country-scoped administrative records with explicit hierarchy,
  selecting one useful political depth for the current geographic scale rather
  than drawing every available level or assuming Admin-1 means the same thing
  everywhere;
- balanced category budgets, stable ranking, name de-duplication, and strict
  collision handling so a dense administrative tier cannot erase settlements
  or concatenate long labels; and
- only if terrestrial improvements leave a demonstrated need, a deliberately
  small set of named contextual features such as bays, capes, channels,
  islands, rivers, and lakes.

The result follows one global data and ranking path. It does not treat US
states, counties, NWS zones, or US settlements as a special presentation tier.
Provider geometry remains the sole authority for the warning footprint.

Candidate and display density may increase conservatively as the effective
viewport zooms closer, whether that viewport comes from the automatic alert fit
or Task 0024's manual navigation. Geographic scale and the source hierarchy
choose the eligible administrative depth; terminal dimensions and collision
space determine how many eligible labels actually fit. Use one global policy
over explicit levels and density rather than a table of country-specific UI
exceptions.

This remains an offline label lookup for a supplied viewport, not a general map
engine.

## Firm architectural boundary

In scope:

- build-time ingestion and reduction of an openly licensed gazetteer;
- one compact versioned resource containing only fields needed for labels;
- a small local viewport query, preferably over country/grid buckets rather
  than scanning or materializing an unrestricted source dump per selection;
- hard country filtering for political and settlement labels on a
  country-alert map, with any later country-neutral marine/physical exception
  explicitly modelled rather than inherited from a global query;
- explicit administrative level/parent identity and deterministic selection
  of one useful depth for the current view;
- stable category-aware ranking and existing Textual collision placement;
- deterministic scale-adaptive candidate/display budgets, category quotas,
  cross-category de-duplication, and collision-free omission for contextual
  labels;
- settlement activation compatibility with Task 0020 Slices F and G;
- source, version/date, licence, attribution, and reproducible build notes; and
- deterministic fixture tests with no network dependency.

Out of scope:

- slippy-map tiles, roads, buildings, addresses, parcels, or land-use layers;
- user-controlled pan or zoom, arbitrary map browsing, navigation history,
  viewport state, controls, or scale bars; Task 0021 may consume Task 0024's
  effective viewport but never implements its navigation;
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
administrative level and stable parent chain where applicable
Admin-1 / Admin-2 codes and display names where available
feature category / feature code
population or source rank
```

Administrative records must be independent candidates, not names copied from a
surviving settlement. Preserve source-declared levels and parent identities so
the runtime policy can compare tiers without assuming that a country's most
useful visible unit is always Admin-1. A source-supplied concise name may be
retained when it is authoritative; do not invent abbreviations by truncating
political names.

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

## Runtime query, ranking, and density

The effective viewport comes from Task 0020's automatic alert fit or, when
available, Task 0024's bounded manual override. Query a modest halo around it
so nearby context can remain visible when a warning polygon narrowly misses a
settlement. Longitude wrapping must retain the existing antimeridian behavior.
For a country-alert map, filter settlement and administrative candidates to the
selected country before ranking. A viewport crossing a border does not by
itself make the other country's cities relevant.

Keep label categories independent:

1. **Administrative context:** obtain labels from dedicated hierarchical
   records or label points, never indirectly from whichever settlements
   survived ranking. Evaluate available levels independently and choose one
   principal depth for the render. Prefer a deeper level as the geographic span
   contracts, but fall back to a coarser level when the deeper tier is absent,
   too dense, or cannot supply a useful number of separated labels. Rank label
   points inside the selected provider geometry first, then by distance,
   source importance, and stable identity. Administrative labels remain
   passive, italic, marker-free, and may be omitted; they must never overlap or
   concatenate merely to make every candidate visible.
2. **Settlements:** prioritize points inside selected provider geometry, then
   visible or halo points outside it within the selected country. Within those
   groups rank administrative seats, population/source importance, distance to
   the geometry or viewport centre, and stable name/id tie-breakers. The
   responsive/collision budget still limits what can be rendered.
3. **Physical context:** add only after a fixture demonstrates that settlement
   and administrative coverage cannot ground the map. Prefer a short allowlist
   of useful feature codes and a stricter display budget. These labels are
   passive and visually subordinate to settlements and warning geometry.

Use separate category quotas over one shared occupied-cell set. Reserve room
for a small number of high-value administrative anchors and inside-warning
settlements before admitting additional members of either category; no
category may consume the complete map merely because its source is dense.
De-duplicate normalized visible names across categories when nearby labels
would be ambiguous—for example, prefer a marked city callout over a coincident
state label with the same name. Try source-supplied concise names or alternate
positions for long labels; omit a lower-priority label when it still cannot fit
instead of truncating it into an ambiguous fragment or placing it over another
name.

Define a small number of stable density bands from the effective viewport's
geographic span relative to the automatic fit. Closer bands may select a deeper
administrative tier, consider more settlements, admit lower-ranked source
records, and raise the display budget; the shared Task 0023 collision planner
or a compatible passive-label planner still decides what fits. Zooming out
must reduce clutter. Sparse source coverage remains sparse rather than being
filled with invented or remote labels.

Settlement widgets should receive source-neutral records. A settlement must
still have a stable key, name, region, and coordinates for the current-weather
tooltip and full Weather-screen navigation; changing label datasets must not
change activation semantics.

## Provider-area fallback

Provider `area_names` remain useful navigation and document metadata but are
not automatically trustworthy geographic label points. Do not parse arbitrary
warning prose or place an area name at an invented coordinate.

If a later warning-library contract exposes individually named affected-zone
geometries, those names may be placed using their own real geometry through a
provider-neutral model. That is an optional upstream enhancement, not a reason
to add NWS-specific zone fetching or name/geometry guessing in Wevva.

## Implementation slices

### Slice A — label-policy fixtures and pure hierarchy selection

- Add source-neutral fixture candidates for France, the UK, Brazil, the US, a
  small country, a dense border, a rural alert, and an antimeridian viewport.
- Reproduce the failure modes in `docs/assets/name-bug.png`,
  `docs/assets/name-bug-2.png`, and the France `CoastalEvent` capture: foreign
  labels, mixed administrative meanings, category monopolization, duplicated
  names, and concatenated long labels.
- Add pure country filtering, administrative-depth selection, category quotas,
  shared collision/omission, and cross-category name de-duplication before
  changing the packaged dataset.
- Establish useful label-count/spacing targets from compact and wide maps. Keep
  exact thresholds local to the pure policy and covered by boundary tests.

### Slice B — audit and compact artifact prototype

- Add a reproducible, development-only GeoNames builder or extend the existing
  geography build tooling without adding runtime download behavior.
- Prototype the minimal settlement plus independent hierarchical administrative
  schema, preserving country, explicit level, and stable parents. Record count,
  compressed size, load time, memory, and representative query timings.
- Verify licensing and add attribution/provenance before committing generated
  data.
- Exercise rural, dense urban, country-border, antimeridian, tiny-island, and
  marine fixture extents plus the France/UK/Brazil hierarchy cases. Stop here
  if the artifact cost is disproportionate or the source cannot express useful
  independent administrative levels.

### Slice C — hierarchical administrative and dense settlement labels

- Add a source-neutral focused-place model and bounded viewport query.
- Use the dense source only for selected-alert views; keep Natural Earth for
  whole-country and other existing maps.
- Replace settlement-derived region annotations with the independent
  country-scoped hierarchy and selected-depth policy from Slice A.
- Preserve inside-geometry priority, deterministic ranking, balanced category
  quotas, collision-free omission, and no-network resize/selection behavior.
- Add pure scale-band and candidate/display-budget policy that accepts an
  effective viewport without depending on Task 0024's controls or widget state.
- Keep Task 0020's existing Natural Earth layer as a safe fallback when the new
  resource cannot load.

### Slice D — optional named physical context

- Proceed only if named marine/rural fixtures remain ungrounded after Slices B
  and C.
- Select a narrow, documented global feature-code allowlist and measure its
  incremental artifact/runtime cost before integration.
- Use a separate, subordinate label budget; do not add feature geometry or turn
  the map into a general topographic viewer.

## Acceptance criteria

- Task 0021 does not create or mutate the alert viewport and does not change
  polygon rendering; it consumes the effective viewport supplied by Task 0020
  or Task 0024.
- Country-alert political and settlement labels are restricted to the selected
  country. The France fixtures do not show Brighton and Hove, UK local
  authorities, Belgian neighbours, or Swiss cantons; the Brazil fixture does
  not surround the map with other countries' departments or provinces.
- Focused terrestrial fixtures which were blank under Natural Earth show useful
  nearby settlements, including small communities where source data exists.
- Administrative context does not depend on the presence or visibility of a
  settlement. One deterministic useful depth is chosen from the available
  hierarchy; the UK, France, Brazil, US, and small-country fixtures need no
  country-specific presentation branches.
- Administrative labels contain no marker dots and are not selectable.
- No two visible labels overlap or concatenate. An unplaceable lower-priority
  administrative label is omitted rather than falling back onto occupied text.
- Category quotas preserve both high-value administrative context and
  settlements when candidates for both can fit. Duplicate nearby names across
  categories are resolved deterministically.
- Long political names use an authoritative concise form when supplied or are
  omitted when they cannot fit; they are not arbitrarily truncated into an
  ambiguous map label.
- US and rest-of-world fixtures follow the same level-aware category and
  ranking rules.
- Country-border and wrapped-longitude viewports return stable relevant labels
  without admitting political or settlement context solely because it lies on
  the other side of the border.
- Closer effective viewports can admit additional suitable labels and wider
  views reduce clutter, with deterministic results independent of whether the
  viewport was produced automatically or by Task 0024.
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
marine/coastal extent, plus France/UK/Brazil administrative hierarchy, a dense
urban viewport, a multi-region country border, and the antimeridian. Assert
country filtering, stable depth/order, category quotas, non-overlap,
de-duplication, marker-free administrative labels, source-neutral settlement
keys, fallback behavior, packaged-resource presence, and zero network work.

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
- Task 0024's effective-viewport consumer boundary

## Source references

- Natural Earth 1:10m populated places:
  <https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-populated-places/>
- GeoNames downloadable gazetteer, schema, extract descriptions, and licence:
  <https://download.geonames.org/export/dump/>
- Creative Commons Attribution 4.0 licence used by the GeoNames export:
  <https://creativecommons.org/licenses/by/4.0/>

## Decisions and handoff notes

- The screenshots motivating this task show correctly focused automatic alert
  viewports. Do not implement viewport fitting or navigation here; consume the
  effective viewport supplied by Task 0020/0024. Task 0034 may separately
  revisit automatic framing after this label policy is evaluated.
- Natural Earth remains the appropriate low-cost country/base-map source. Its
  selective place coverage is not a failed Slice E implementation.
- The current focused implementation loads
  `natural_earth_10m_populated_places.json.gz`, ranks points inside the selected
  polygon first, retains at most 32 candidates, and lets the responsive map
  budget display at most eight settlement callouts.
- Current Admin-1 labels are computed by grouping the `region_name` attached to
  every visible detailed settlement before the 32-place truncation. That is the
  coupling Slice C should replace. The field's meaning and freshness are not
  sufficiently consistent to define the displayed administrative depth.
- The old decision to retain every region label and allow overlap after
  collision placement is exhausted is revoked. The `name-bug` fixtures show
  that clean omission and balanced category budgets preserve more information
  than concatenated exhaustive labels.
- The selected country is a hard relevance boundary for political and
  settlement labels. Optional country-neutral marine or physical names require
  an explicit later rule tied to real coordinates; they do not reopen the
  global candidate flood.
- No current-alert request, selected-alert change, or terminal resize should
  perform network work for map labels.
- GeoNames is the leading candidate, not an irrevocable dependency. Slice B
  must establish that its compact artifact has acceptable cost and coverage.
- The stopping rule is explicit: this task ends with useful contextual labels
  and density policy for a supplied warning viewport. It does not own viewport
  interaction or general-purpose mapping.
