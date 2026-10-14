# Task 0018: Budget-driven tropical systems workspace

## Status

In progress — Slices A–C implemented; Slice D remains

## Context

The tropical workspace already has a sound information model: severity-ordered
canonical storm tabs, source/provider tabs, an observation summary, independent
weather near the selected centre, a fitted Braille track and cone, and lazy
official-product tabs. Those nested tabs are a particularly good fit for
canonical storms which may have several issuing-centre observations and several
products.

Its layout predates the budget-driven weather screen. It currently chooses one
wide horizontal topology around a single 217-column breakpoint, gives the outer
frame internal padding, and assumes enough room for a summary, a fixed-height
centre-weather table, a map, and a broad product reader simultaneously. At
ordinary and especially 80x24 terminal sizes this makes every region compete
for space rather than degrading by information priority.

The country and saved-location maps now establish a second useful pattern:
Braille geography is a passive raster beneath native, direction-aware Textual
callouts. City labels can be focused, hovered, and clicked without custom hit
testing. The tropical maps should use the same interaction language.

This task succeeds the layout portions of task 0014; it does not change that
task's provider, cache, or two-repository handoff boundaries.

## Problem

- The compact breakpoint is based almost entirely on width and does not budget
  rows, so it cannot make deliberate trade-offs at 80x24.
- The main workspace can retain low-priority weather and map content while the
  essential observation summary or official information becomes cramped.
- Fixed root padding spends scarce cells between the outer frame and the storm
  tabs without adding useful hierarchy.
- Providers with rich NHC/CPHC products and providers with only a short basic
  summary receive essentially the same large information pane.
- Track and place labels are painted into one Rich render and cannot use the
  native focus, hover, inversion, or selection behavior of the newer maps.
- The fitted track viewport can be so tight that an ocean track has little
  geographic context even when nearby land could fit.
- Forecast dots do not explain whether they are the current centre or an
  official forecast lead such as `12h` or `24h`.
- The `t` and `c` bindings expose track/cone layer controls which are not useful
  enough to justify footer space or UI state.
- There is no spatial overview of all active systems.

## Desired outcome

The existing hierarchy remains recognizable, but the screen allocates its real
post-header/footer rows and columns through a pure layout budget. It never needs
full-page vertical scrolling at the supported 80x24 baseline. The storm and
provider tabs remain the primary navigation; the summary and storm-information
reader are always represented; centre weather and maps appear or grow only when
complete useful presentations fit.

Selected-storm maps adopt the native callout pattern, show data-backed lead-time
labels, and provide more surrounding geographic context. A later slice adds a
full-screen overview of all active storms and tracks.

## Stable information hierarchy

The importance order is:

1. active-storm tabs;
2. source/provider tabs when the selected storm has multiple observations;
3. a minimum source-observation summary;
4. a usable, internally scrolling storm-information body;
5. additional summary rows;
6. the selected storm track and cone;
7. compact weather near the selected centre;
8. additional centre-weather rows and additional map height.

The main page itself does not scroll. Official prose and structured products
continue to scroll inside their existing body.

At wide sizes the familiar split composition remains:

```text
Canonical storm tabs
Source/provider tabs, when needed

Centre weather      | Summary
Selected storm map  | Product tabs / storm information body
```

The two columns are balanced rather than capping the map column. The frame
fills the stage inside its `1 2` padding instead of imposing an additional
maximum width or height.

At compact sizes the same mounted widgets use a single-column budget:

```text
Canonical storm tabs
Source/provider tabs, when needed
Minimum summary
Product tabs / storm information body
```

The centre-weather table and selected-storm map are hidden at the smallest
tier. They return as complete regions rather than clipped fragments when rows
permit. The outer stage retains `1 2` spacing around the rounded frame, while
the frame itself uses zero padding so the storm tabs sit directly inside its
border.

## Layout budget contract

Add a pure tropical layout calculation, separate from Textual widgets, using
the content width and height plus small availability facts:

```text
topology: compact_stack | split
frame_width
summary_rows
summary_height
centre_weather_rows
centre_weather_height
track_visible
track_height
information_tabs_visible
information_height
information_body_height
source_tabs_visible
```

Inputs may include whether there are multiple sources, a renderable track, a
centre-weather result, and one or several product choices. They must not include
provider-specific layout branches.

The calculation accounts explicitly for header/footer removal, stage padding,
the outer border, tab rows, child borders, and gutters. Replace
`COMPACT_SCREEN_WIDTH = 217` with constraints derived from the minimum useful
left pane, information pane, and gutter widths. Widgets remain mounted and
receive narrow `set_layout(...)` calls; resizing must not rebuild the screen or
lose the selected storm, source, or product.

### 80x24 target

At 80x24, including a multi-source storm, retain:

- the rounded outer frame and its external `1 2` spacing;
- horizontally navigable storm tabs;
- source tabs when more than one observation exists;
- a compact bordered summary with complete high-priority rows; and
- the storm-information frame, product tabs when meaningful, and at least a
  small internally scrolling document body.

The map and centre-weather table are deliberately omitted. If product tabs are
not meaningful, their two rows are returned to the information body. No region
may extend behind the footer and the main screen must report no vertical scroll.

After that baseline, spend rows deterministically:

1. add complete summary rows;
2. when both column and row minima fit, admit the paired two-column layout;
3. show complete centre-weather and summary rows in its top row; and
4. give all remaining rows to the aligned map and information panes.

Exact crossover dimensions are fixture-driven rather than part of the public
contract. Removing space reverses the same order.

## Widget density

### Observation summary

`TropicalStormSummary` should accept an ordered subset of complete rows. It
does not repeat classification, which is already present in the canonical
storm tab, or advisory number. The priority is:

1. source, when no source-tab row is visible;
2. centre;
3. maximum wind;
4. minimum pressure;
5. movement; and
6. last update.

When source tabs are visible, their label already communicates the issuing
centre and the table can spend that row elsewhere. Compact field labels may be
shortened, but values must never be clipped mid-unit.

### Weather near centre

`TropicalCentreWeather` should expose complete row tiers rather than its current
fixed six-row body. Row priority is condition, temperature, wind,
precipitation, surface pressure, then forecast coordinates. A failed lookup
remains a compact inline unavailable state and never suppresses the summary,
map, or products.

### Storm information

Keep the product tabs and independently scrolling body for rich issuing-centre
products. Hide the tab row when there is no choice to make. A provider with
only a headline, summary, or official link uses a compact information mode;
reclaimed rows may be offered to the map rather than leaving a mostly empty
document pane. Reapply the budget after lazy products arrive, without replacing
the selected tab or resetting the body unnecessarily.

## Storm ordering and semantic colour

Retain `sort_canonical_tropical_systems_by_severity`; strongest declared source
classification remains the canonical presentation rank and alphabetical name
is the tie-breaker. Add deterministic tests rather than introducing another
sort path.

Top-level storm labels should be stable when the user changes source tabs and
use the strongest observation's classification. Colour the classification with
the theme's semantic roles:

- `$error`: hurricane, typhoon, category classifications, and intense/severe
  tropical cyclones;
- `$warning`: severe or strong tropical storms;
- `$accent`: tropical storms, moderate tropical storms, and generic tropical
  cyclones;
- `$secondary`: tropical depressions; and
- `$primary`: disturbances, tropical lows, and unknown/unclassified systems.

The storm name retains normal foreground treatment. Selection remains the
standard Textual tab state, so severity colour does not become a second custom
selection mechanism.

## Selected-storm map

Refactor the map into the established layered pattern:

- land and cone fill remain a Braille/raster background, with the cone using a
  subdued `$text-warning` tint to distinguish uncertainty from land;
- render provider-supplied track positions as discrete fix dots rather than
  joining them into a continuous or interpolated path;
- current/forecast fixes, lead labels, and city callouts are native children
  positioned over it;
- shared directional placement may render `• City` or `City •`, always keeping
  the bullet on the projected city cell;
- city names prefer clear map cells outside the forecast cone, with ordinary
  collision-safe placement as a constrained-layout fallback;
- city hover/focus reverses the complete callout; click, Enter, and Space emit
  the ordinary `PlaceSelected` message and open that city's weather; and
- use normal Textual focus traversal only—do not add a bespoke spatial keyboard
  mode.

This surface and the later all-storm overview follow the cross-screen map
interaction contract in `docs/responsive-layout.md`. Temperature enrichment is
not added here; resize and collision reflow must therefore remain entirely
presentation-only and must not refresh tropical or centre-weather data.

Use `•` for city markers and retain a visually distinct storm-fix marker. Label
the current fix `Now`; label official forecast fixes with lead times such as
`12h` and `24h` only when that timing is explicitly supplied at matching
coordinates. When explicit daily boundaries are available, keep the complete
track in the viewport but show markers and labels only at `24h`, `48h`, and
later 24-hour intervals. Never infer time from vertex order or timestamps. At
small map sizes preserve `Now`, then the nearest official leads, hiding
lower-priority labels when collisions cannot be resolved.

The viewport still contains the complete selected track and cone, including
dateline wrapping, but gains a context floor: minimum latitudinal/longitudinal
span and padding should be large enough to reveal nearby land and prominent
cities when available. This is an expansion policy, not a crop; it must not cut
off provider geometry merely to show land. Tune the minimum span with Pacific,
Atlantic, and island fixtures.

Track and cone render whenever supplied. Remove the `t`/`c` bindings, footer
entries, and user-facing visibility state. Missing layers use the existing
inline unavailable treatment; absence alone should not create repetitive
notifications.

## All-storm overview

Add this only after the responsive detail screen and selected map are stable.
From the tropical workspace, `m` opens a dedicated full-screen overview with a
rounded border and `1 2` spacing outside it, matching the saved-locations world
map.

The overview contains:

- the checked-in Braille world land backdrop, cropped south of inhabited land
  in the same manner as the saved-locations map;
- every active system's available track and cone;
- a native callout at each current centre containing classification and name,
  coloured by the same semantic severity mapping;
- a restrained set of major-city callouts; and
- collision-aware reflow after resize.

Storm callouts are clickable/focusable and return to the detail workspace with
that storm selected. City callouts use `PlaceSelected` and open the ordinary
weather screen. If a later regional overview is added, it must use the shortest
wrapped longitude interval and a generous minimum span; the initial slice may
remain a predictable global viewport rather than adding pan and zoom.

## Interaction changes

- Keep `w` for weather, `r` for refresh, and normal tab navigation.
- Remove `t` and `c` track/cone bindings.
- Add `m` for the all-storm overview once that slice lands.
- Preserve storm, source, and product selection across resizes and refreshes.
- Keep loading overlays local to the discovery or information region which is
  actually loading.

## Implementation slices

### Slice A — budget and compact shell

- Add the pure layout budget and rendered dimension matrix.
- Remove root-internal padding and the width-only compact breakpoint.
- Implement 80x24 single-column and wider split modes.
- Remove track/cone bindings and apply stable severity ordering/colour.

### Slice B — existing-widget density

- Add summary-row and centre-weather-row tiers.
- Distinguish compact/basic information from rich product readers.
- Verify selection and loading state across budget changes.

### Slice C — selected map normalization

- Extract/reuse only the small directional callout primitive justified by the
  third map surface.
- Layer native city/fix labels over existing land/cone/track geometry.
- Add data-backed lead labels and the context-aware viewport floor.

### Slice D — all-storm overview

- Add the full-screen multi-storm map, native storm/city callouts, binding, and
  return-to-detail selection path.

Slices A and B form a useful first delivery. Slice C is independent enough to
follow without blocking 80x24 support. Slice D is intentionally last and is the
largest optional extension in this task.

## Non-goals

- New tropical providers, warning/storm association, or changes to canonical
  grouping.
- Merging or averaging source observations.
- Inventing forecast times, tracks, cones, centres, or intensity trends.
- Rewriting official provider prose or structured product data.
- User-controlled pan, zoom, map projections, or a spatial keyboard navigator.
- New city-temperature queries from tropical maps.
- Changing the ordinary weather-screen CAP warning path.

## Relevant code

- `wevva/screens/tropical_systems_screen.py`
- `wevva/widgets/tropical_summary.py`
- `wevva/widgets/tropical_centre_weather.py`
- `wevva/widgets/tropical_track.py`
- `wevva/widgets/geographic_scope.py`
- `wevva/widgets/location_map.py`
- `wevva/widgets/world_locations_map.py`
- `wevva/services/tropical.py`
- `wevva/geography.py`
- `wevva/app.py`
- `tests/test_tropical_systems_screen.py`
- `tests/test_tropical_track.py`
- a new pure-layout test module and overview-map test module

## Acceptance criteria

- At 80x24 the screen shows storm navigation, provider navigation when needed,
  a complete minimum summary, and a usable internally scrolling information
  body with no full-page vertical scrolling.
- The outer frame keeps `1 2` external spacing and has no internal gap above or
  beside the storm tabs.
- Split topology appears only when both panes retain their documented minimum
  widths; no fixed 217-column breakpoint remains.
- Summary and centre-weather rows appear and disappear only as complete rows in
  documented priority order.
- Rich US products retain the existing nested-tab reader; basic providers do
  not leave a disproportionately empty information pane.
- Storm order is strongest-first, storm-tab severity colours use the documented
  semantic roles, and selecting a provider does not restyle the canonical storm
  as if its overall severity changed.
- Track and cone are always shown when present; `t` and `c` are absent from the
  bindings and footer.
- The selected map retains complete provider geometry, shows more geographic
  context where possible, and labels current/data-backed forecast fixes without
  fabricating lead times.
- Tropical city labels are native, direction-aware, focusable/clickable, and
  use the existing weather-selection path.
- Resizing preserves the selected storm, source, product, and mounted widget
  identity.
- The all-storm overview, when Slice D lands, shows every active storm once and
  can select either a storm or a city through native Textual callouts.

## Verification

Deterministic checks should include:

```bash
uv run python -m compileall -q wevva
uv run python -m unittest tests.test_tropical_layout
uv run python -m unittest tests.test_tropical_track
uv run python -m unittest tests.test_tropical_systems_screen
uv run python -m unittest discover -s tests
```

Rendered tests should cover at least 80x24, 100x30, 140x45, and a very wide
terminal; single- and multi-source storms; track/cone availability; basic and
rich product sets; long classification/source labels; dateline tracks; and
selection persistence through resize. The same matrix should exercise local
discovery/product loading, empty discovery, failed centre weather, missing
geometry, and basic-provider states so temporary content cannot change the
screen's page-scroll contract. Assert that resize causes no provider or weather
request.

Manual terminal checks remain necessary for mouse hover/inversion, Braille and
Unicode alignment, real provider prose, and active-provider geography. When
representative live systems exist, inspect at least NHC/CPHC, a western Pacific
multi-source storm, and a basic non-US provider. Do not claim those checks when
no suitable live system is available.

## Decisions and notes

- Nested storm/source/product tabs remain the primary navigation model.
- The information reader, not the map, owns internal scrolling.
- The existing canonical severity sorter is authoritative; this task adds
  semantic display colour and stable labels rather than another ranking model.
- A source change may update source-specific summary, weather, map, and product
  content, but not the canonical storm's top-level severity label.
- The all-storm overview is valuable but must not hold the compact responsive
  screen hostage; implement it only after Slices A–C are stable.
- Any required provider-model enrichment for explicit lead hours belongs in
  `wevva-warnings` and must be recorded as a sibling task rather than inferred
  in this renderer.
- Slice C renders only discrete provider-supplied forecast positions and uses
  structured product `lead_hours` where supplied. NHC/CPHC cadence and HKO/JMA
  valid times are not converted into leads; sources without explicit lead
  hours remain unlabeled pending the sibling provider work recorded in task
  0022.
