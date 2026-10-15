# Task 0023: Shared map callout placement

## Status

Complete

## Context

Wevva has one shared low-level geographic stack: checked-in Natural Earth
resources and projection helpers in `wevva/geography.py`, followed by the
layered Braille raster in `wevva/widgets/geographic_scope.py`. The main weather
location map, saved-locations world map, Alerts Centre map, tropical track, and
warning-area scope all build on that stack.

The higher-level native callouts are less consistent. The weather location map
and tropical track use `place_directional_callout()`, while the world map and
Alerts Centre retain nearly identical private placement loops. Each interactive
map separately manages candidate priority, projected-anchor reservation,
occupied cells, left/right direction, fallback behavior, and placement result
types.

The weather location map exposed the consequence: Glasgow and Edinburgh
projected to the same terminal row, but placing Glasgow's label first caused
Edinburgh's complete callout, including its marker, to move vertically. The
weather map now protects future anchors, puts Glasgow's label to the left, and
forbids vertical displacement of native callouts. That correction is local;
the world, Alerts Centre, and tropical city paths can still move a marker away
from its projected row.

## Problem

- A marker embedded in a native label is no longer geographically truthful if
  collision handling moves the complete widget to another row.
- The world and Alerts Centre maps duplicate the directional placement
  algorithm instead of receiving fixes made in `map_callouts.py`.
- The weather map's projected-anchor reservation and priority fallback are
  implemented in its widget reflow rather than expressed as a reusable policy.
- Tropical fixes, tropical cities, saved locations, forecast cities, and alert
  settlements need different fallback and avoidance behavior, but currently
  encode those differences in whole bespoke loops.
- Adding a general `MapWidget` or GIS-style layer framework would be
  disproportionate. Geometry selection, ranking, rendering, messages, and
  interaction semantics are intentionally different between the surfaces.

## Desired outcome

Add one small, pure multi-callout placement planner on top of the existing
directional primitive. Interactive map widgets supply ranked callout candidates
and an explicit placement policy; the planner returns deterministic placements
without knowing about weather, warnings, saved locations, or tropical systems.

For every native callout whose marker is part of its text, a successful
placement keeps that marker on its projected terminal cell. The planner uses
left/right direction, projected-anchor reservation, priority, and documented
fallback behavior rather than silently changing the marker's latitude.

The maps remain separate domain widgets. This task consolidates terminal-cell
placement only.

The implementation should produce a net reduction in production mapping code.
The point of the shared planner is to delete duplicated placement machinery,
not add an abstraction alongside the existing copies.

## Scope

- Extend `wevva/widgets/map_callouts.py` with a source-neutral candidate and
  result contract, or an equivalently small pure function, for placing a ranked
  collection of directional callouts.
- Preserve every candidate's projected anchor while evaluating the space used
  by labels which have already been placed and anchors which remain to be
  placed.
- Prefer a layout in which both the current candidate and lower-priority
  anchors survive. If that is impossible, retain the higher-priority candidate
  rather than allowing a lower-priority reserved anchor to hide it.
- Support the existing left/right forms with the marker at the geographic end:
  `• Label` and `Label •`.
- Make vertical displacement an explicit policy. It must be disabled whenever
  the marker is embedded in the moved widget. It may remain available only for
  marker-free text or when a separately rendered marker remains fixed at the
  anchor.
- Retain an optional preferred-avoidance set for tropical cone cells. Avoidance
  influences label choice but does not make the geographic anchor invalid.
- Retain explicit caller-owned fallback behavior, including tropical forecast
  fixes collapsing to an exact marker and lower-priority labels being omitted
  when neither direction fits.
- Migrate `LocationMap`, `WorldLocationsMap`, `CountryAlertsMap`, and the native
  callouts in `TropicalStormTrackScope` to the shared planner.
- Remove the world and Alerts Centre private copies of directional callout
  placement after equivalent behavior is covered by tests.
- Keep stable mounted Textual label widgets and recompute only their display,
  direction, and offsets on resize or content changes.
- Update architecture documentation to describe the shared callout policy once
  implementation is complete.

## Non-goals

- A common base class for every map widget.
- Changes to Natural Earth resources, Task 0021's proposed dense gazetteer, or
  any map-data build process.
- New projections, pan/zoom controls, map tiles, spatial indexing, or a general
  GIS API.
- Changes to country-component selection, alert viewport fitting, tropical
  track/cone extraction, city ranking, label budgets, temperatures, or network
  requests.
- Unifying map-specific messages or navigation. Weather cities continue to
  emit `PlaceSelected`, saved locations continue to emit
  `SavedLocationSelected`, and Alerts Centre settlements retain their local
  selection flow.
- Converting passive warning-area labels or Alerts Centre administrative labels
  into interactive callouts. Their markers are already rendered separately or
  intentionally absent.
- Guaranteeing that every candidate label is visible in a terminal too small
  to contain it.

## Relevant code

- `wevva/widgets/map_callouts.py`
- `wevva/widgets/location_map.py`
- `wevva/widgets/world_locations_map.py`
- `wevva/widgets/country_alerts_map.py`
- `wevva/widgets/tropical_track.py`
- `wevva/widgets/warning_area.py` for the passive/single-marker contrast
- `wevva/widgets/geographic_scope.py`
- `tests/test_location_map.py`
- `tests/test_world_locations_map.py`
- `tests/test_alerts_centre_map.py`
- `tests/test_tropical_track.py`
- `docs/architecture.md`

## Approach

### Slice A — pure placement contract

- Specify candidates by stable key, projected cell, rendered width, priority
  order, and any optional avoidance cells needed by the caller.
- Return only terminal placement facts: key, column, row, width, and marker
  direction. Keep Textual widgets, colours, and domain models out of the
  planner.
- Place higher-priority candidates deterministically. First try while protecting
  remaining anchors; if no direction fits, retry without allowing a
  lower-priority reservation to displace the current candidate.
- Reserve all occupied cells from successful placements and verify that the
  marker endpoint equals the supplied anchor.
- Cover same-row neighbours, edge-facing labels, identical/adjacent anchors,
  overlong labels, crowded canvases, avoidance sets, and stable repeated output
  with pure unit tests.

### Slice B — location, world, and Alerts Centre maps

- Move the weather location map's current multi-candidate logic into the shared
  planner without regressing the Glasgow/Edinburgh fixture.
- Replace the saved-locations world map's private `_place_callout()` while
  preserving location order, focus, activation, temperatures, and resize
  behavior.
- Replace the Alerts Centre settlement `_place_callout()` while preserving
  responsive label budgets, passive region-label priority, settlement identity,
  and hourly-forecast activation.
- Do not fold passive `_plain_label_placement()` into directional marker
  placement unless a small marker-free policy expresses it cleanly.

### Slice C — tropical native callouts

- Place provider-supplied fixes before cities and continue reserving every fix
  anchor.
- Keep a fix at its exact projected cell when its text cannot fit by using the
  existing marker-only fallback.
- Place interactive city labels through the common planner while retaining cone
  avoidance and the existing three-label budget.
- Confirm that provider fixes, cone geometry, and city activation remain
  unchanged; this task owns placement, not tropical interpretation.

## Acceptance criteria

- `LocationMap`, `WorldLocationsMap`, `CountryAlertsMap`, and
  `TropicalStormTrackScope` use the shared multi-callout planner for native
  directional callouts.
- The world and Alerts Centre copies of directional placement are removed.
- Production Python lines across the touched map/callout modules decrease in
  aggregate from the pre-task baseline. Report production and test diff totals
  separately; do not obtain the reduction by compressing formatting, weakening
  tests, or combining unrelated cleanup.
- For every successful native callout placement, its marker endpoint matches
  the candidate's projected canvas cell. A label collision never changes the
  marker row.
- The compact UK weather-map fixture renders Glasgow as `Glasgow … •` and
  Edinburgh as `• Edinburgh …` on their shared projected row.
- Neighbouring saved locations and Alerts Centre settlements choose opposite
  directions or omit a lower-priority label rather than moving either marker
  vertically.
- Tropical forecast fixes never cover another fix anchor; crowded labelled
  fixes collapse to their exact marker and city labels retain cone-avoidance
  behavior.
- Placement is deterministic across repeated runs and terminal resizes with
  unchanged dimensions.
- Existing map-specific ranking, limits, colours, focus, click/keyboard
  activation, selection messages, and asynchronous loading behavior remain
  unchanged.
- `WarningAreaScope` continues to render the forecast marker at its exact
  projected cell; it need not adopt native callout planning.
- No map placement or resize path performs new file or network work.

## Verification

```bash
uv run python -m compileall -q wevva
uv run python -m unittest tests.test_location_map
uv run python -m unittest tests.test_world_locations_map
uv run python -m unittest tests.test_alerts_centre_map
uv run python -m unittest tests.test_tropical_track
uv run python -m unittest tests.test_responsive_weather_screen
uv run python -m unittest discover -s tests
```

Manually inspect representative compact and wide layouts for:

- the Glasgow/Edinburgh and Cardiff/London pairs on the weather map;
- nearby or same-cell saved locations on the world map;
- a dense selected-alert viewport with passive region labels;
- a tropical track with multiple labelled fixes and a nearby city; and
- focus, hover, click, Enter, and Space behavior after resize.

## Decisions and notes

- Geographic data, projection, and Braille rasterization are already shared and
  are not the architectural problem addressed here.
- Exact markers take priority over label direction and over retaining every
  lower-priority label.
- Net production SLOC is an explicit design constraint. Prefer extending the
  small existing primitive and deleting private loops over introducing a new
  class hierarchy or parallel orchestration layer.
- Vertical label movement is safe only when the marker is rendered separately.
  The planner must make that distinction explicit rather than infer it from a
  widget type.
- Task 0021 may later change focused-alert label candidates, but should be able
  to supply them to this source-neutral placement contract without changing the
  planner.

## Outcome

Implemented a source-neutral ranked callout planner in
`wevva/widgets/map_callouts.py` and migrated the weather location, saved-world,
Alerts Centre, and tropical native callouts to it. Embedded markers now remain
on their projected rows; lower-priority anchors influence direction before the
planner falls back to retaining a higher-priority label. Tropical fixes use the
same planner with exact-marker fallback and non-yielding fix-anchor protection,
while tropical cities retain preferred cone avoidance. The duplicate world and
Alerts Centre placement loops were removed, and pure plus mounted regressions
cover the shared policy and map-specific marker positions.
