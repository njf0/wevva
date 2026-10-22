# Task 0031: Tropical storm viewport framing

## Status

Planned — implementation deferred to a fresh chat

## Context

Task 0030 placed the existing large tropical track scope in the Dashboard's
lower detail row while retaining the same scope in the dedicated Tropical
Systems workspace. Both surfaces already render provider-supplied forecast
fixes and cones over the checked-in Natural Earth land layer.

The underlying geography is sound, but the final viewport framing is not.
Long, narrow storm geometries expose the problem most clearly. An eastern
Pacific track can sit in a relatively small central band with avoidable empty
ocean around it while useful Mexican geography lies just outside the chosen
extent. A wide North Atlantic system can similarly occupy too little of a tall
pane.

This is a viewport-selection problem, not permission to distort the map.
Dashboard and Tropical Systems must use the same framing engine and differ only
because their allocated canvas dimensions differ.

## Current evidence

The relevant path is deliberately small:

- `build_storm_scope_geometry()` in `wevva/widgets/tropical_track.py` derives
  projected bounds from the complete useful track plus official cone, applies
  five-percent padding, and retains a minimum regional span.
- `GeographicCanvas` in `wevva/widgets/geographic_scope.py` expands those bounds
  symmetrically to the terminal's 2x4 Braille raster aspect.
- `_build_scope_frame()` then projects visible Natural Earth land, cone, and
  storm positions, and applies a final raster-centering translation using the
  visible land, cone, and position layers.
- `LargeTropicalStormTrackScope` is already shared by the Dashboard tropical
  detail and the dedicated Tropical Systems screen. That reuse point should be
  preserved rather than adding Dashboard-specific crop or scale behavior.

The attempted adjustments establish useful negative requirements:

- increasing geographic padding merely zooms farther out;
- reducing padding trims only the symmetric inset and does not choose better
  surrounding context;
- mapping the raw bounds independently onto both canvas axes fills the pane but
  visibly warps land and cone geometry;
- a cover-style crop preserves aspect but can discard the current position,
  forecast fixes, or cone edges and gives Dashboard behavior different from
  Tropical Systems; and
- post-render centering can move pixels but cannot reveal useful geography that
  was excluded from the projected viewport.

## Problem

The current symmetric aspect fit treats the unused cross-axis extent as two
equal margins. That is geometrically safe but often geographically poor. For a
tall Vance-like eastern Pacific track, valuable context is east toward Mexico,
while an equal western allocation mostly adds open ocean. The result looks
under-filled even though the renderer has technically consumed the complete
canvas.

The framing decision also exists in two stages: geographic bounds are fitted
first, then visible raster content is translated. This makes the selected
viewport harder to reason about and risks disagreement between projected land,
place eligibility, markers, and callouts.

## Desired outcome

Every large tropical map should:

- preserve the geographic aspect ratio with one uniform scale;
- retain the complete useful provider track and complete official cone;
- keep a small, visible safety margin around the limiting track/cone edges;
- fill the allocated viewport by expanding the other geographic axis to the
  exact Braille-canvas aspect;
- position that additional extent where it reveals the most useful nearby
  geographic context instead of always dividing it symmetrically;
- show more of Mexico for a Vance-like eastern Pacific track when the available
  cross-axis extent permits it;
- produce one final viewport used consistently by land, cone, fixes, city
  eligibility, native labels, and callout placement; and
- use precisely the same framing policy in Dashboard and Tropical Systems.

For a tall track, the required north/south bounds plus small top/bottom margins
normally determine scale. The extra east/west extent should then be positioned
within the range that still contains the complete padded storm geometry. For a
wide track, the equivalent rule applies with small left/right margins and
context-aware north/south positioning.

## Scope

### One final geographic viewport

- Separate the required storm bounds from the final canvas-shaped viewport.
  Required bounds are the union of every retained forecast position and every
  official cone coordinate, with one small geographic inset.
- Expand, never contract, the required bounds to the output raster aspect. Do
  not crop required track or cone geometry.
- Permit translation only along the axis enlarged by aspect fitting, and only
  within the interval that keeps the complete padded required bounds visible.
- Select the translation before projecting/rendering layers. Do not repair a
  poor viewport afterward with non-geographic pixel scaling or a second raster
  offset.
- Ensure the final viewport is the source of truth for visible Natural Earth
  polygons, eligible populated places, fix cells, cone cells, and native
  callouts.

### Useful context placement

- Use existing checked-in Natural Earth land and populated-place data only.
  This task adds no provider request, external GIS dependency, or new data
  asset.
- Prefer a small deterministic framing rule over a generalized map camera.
  Candidate approaches should be evaluated against the representative cases
  before implementation. A bounded set of candidate translations scored by
  visible land/context is acceptable; an unconstrained optimizer is not.
- Never use issuer country or configured weather location as invented storm
  geography. Context must come from actual nearby projected land/places.
- Preserve dateline wrapping and open-ocean honesty. Some storms genuinely
  have little nearby land; the algorithm must not pan far enough to compromise
  the storm margin merely to find a coastline.
- Keep place ranking and the existing three-label limit separate from viewport
  choice. The viewport may consider existing context data, but label collision
  results must not feed back into camera position and cause unstable reflow.

### Shared rendering path

- Keep Dashboard and Tropical Systems on `LargeTropicalStormTrackScope` and the
  same `_native_scope_frame()`/geographic-canvas path.
- Do not add a Dashboard-only `crop_to_fill`, stretch, zoom, or alternate
  renderer flag.
- Canvas width and height may naturally yield different final extents on the
  two screens, but identical dimensions and storm data must produce identical
  viewport bounds and placements.
- Resize remains presentation-only and deterministic. It must not fetch storm
  systems, products, weather, or geography.

### Margin and callout behavior

- Define the small storm safety margin in projected/geographic bounds rather
  than terminal pixels. Confirm that it remains visually useful across the
  supported pane sizes.
- Do not let a label's text width enlarge the meteorological viewport. Existing
  directional callout placement should choose the other side or its marker-only
  fallback when a label cannot fit.
- Required fix and cone coordinates must remain inside the final viewport
  before raster rounding. Tests should tolerate the expected final-cell
  rounding but not silent clipping.

## Non-goals

- Changing tropical-system retrieval, canonical grouping, product caches, or
  refresh timing.
- Redesigning tabs, products, storm colours, labels, or callout interaction.
- Adding map pan/zoom controls or a general-purpose camera framework.
- Showing issuer-country geography when it is not geographically near the
  storm.
- Choosing different framing rules for Dashboard and Tropical Systems.
- Stretching longitude and latitude independently.
- Cropping the supplied track or official cone merely to make the raster look
  busy.
- Filling genuine open ocean with decorative or invented geography.

## Relevant code

- `wevva/geography.py`
  - `GeographicViewport`
  - `viewport_from_lonlat()`
  - `project_visible_polygons()`
  - longitude wrapping helpers
- `wevva/widgets/geographic_scope.py`
  - `GeographicCanvas`
  - `GeographicCanvas.frame()` and its centering offset
- `wevva/widgets/tropical_track.py`
  - `build_storm_scope_geometry()`
  - `_build_scope_frame()` / `_native_scope_frame()`
  - `LargeTropicalStormTrackScope`
  - visible-place and native-callout placement
- `wevva/screens/dashboard_screen.py`
  - `DashboardTropicalPanel`
- `wevva/screens/tropical_systems_screen.py`
  - the dedicated large track pane
- `tests/test_geography.py`
- `tests/test_tropical_track.py`
- `tests/test_dashboard_screen.py`
- `tests/test_tropical_systems_screen.py`
- `docs/architecture.md`

## Proposed slices

### Slice A — characterize the current framing

Add pure representative fixtures for:

- a tall eastern Pacific Vance-like track with Mexico on the useful context
  side;
- a wide North Atlantic Josephine-like track;
- a short or near-square track where the existing minimum context span matters;
- an official cone materially wider than its centre line; and
- a dateline-crossing open-ocean track.

Record required geometry bounds, output canvas aspect, current fitted viewport,
and which nearby land/place anchors are visible. These tests should demonstrate
the framing defect without depending on live providers or screenshot pixels.

### Slice B — one aspect-correct viewport decision

Implement one pure framing step which expands required storm bounds to the
canvas aspect and selects a legal cross-axis translation using the smallest
deterministic useful-context rule supported by Slice A's evidence. Remove any
storm-specific reliance on post-render centering once the final viewport owns
that decision.

### Slice C — shared native integration

Route both Dashboard and Tropical Systems through the same final viewport.
Ensure backdrop projection, fix/cone placement, city eligibility, and callouts
all consume it. Retain current immutable-frame caching with final viewport and
canvas dimensions represented in the cache key.

### Slice D — responsive qualification

Exercise the representative fixtures in both surfaces at compact, ordinary,
and very large pane dimensions. Tune only the small margin and bounded context
choice if evidence requires it; do not introduce per-screen heuristics.

## Acceptance criteria

- Coastlines, cones, and tracks retain correct proportions at every tested
  size; there is no independent x/y scaling.
- Every retained forecast position and every official cone coordinate lies
  inside the final viewport with the agreed small margin on the limiting axis.
- The final viewport exactly matches the 2x4 Braille canvas aspect and therefore
  occupies the complete pane without letterboxing or a second stretch.
- A Vance-like tall eastern Pacific fixture shows materially more useful
  Mexican geography than the current symmetric fit while keeping the complete
  track and cone.
- A Josephine-like wide fixture keeps the full east/west track and cone with
  small left/right margins and assigns its vertical surplus to useful context
  where available.
- Open-ocean and dateline cases remain geographically honest and stable.
- Dashboard and Tropical Systems produce the same viewport for the same storm
  and canvas dimensions; neither has a crop/stretch override.
- Land, cone, fixes, visible-place candidates, and callouts agree on the same
  viewport after initial render and resize.
- Repeated reflow at unchanged dimensions is stable and continues to reuse the
  immutable backdrop cache.
- No resize, tab change, hover, focus, or viewport computation performs network
  I/O.

## Verification

Use focused deterministic checks during the slices:

```bash
uv run python -m unittest tests.test_geography tests.test_tropical_track
uv run python -m unittest \
  tests.test_dashboard_screen \
  tests.test_tropical_systems_screen
uv run python -m compileall -q wevva
```

Manual qualification should compare Dashboard and Tropical Systems for the
same live or captured source observation at several pane sizes. Record the
terminal dimensions when assessing framing. Do not claim provider availability,
font geometry, or visual quality from deterministic tests alone.

## Decisions for the next chat

- Preserve the full supplied track and cone; improve context by positioning
  expanded viewport extent, not by cropping meteorological data.
- Preserve one uniform projection scale. A pane that looks fuller because the
  map was stretched is a regression.
- Keep the implementation proportionate: one pure framing rule, the existing
  geographic data, and the existing shared renderer should be sufficient.
- Treat the current Vance/Mexico and Josephine screenshots as visual evidence,
  while keeping regression fixtures synthetic and deterministic.
