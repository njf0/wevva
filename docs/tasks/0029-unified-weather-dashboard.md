# Task 0029: Unified weather dashboard

## Status

Proposed

## Context

Wevva now has focused workspaces for a location forecast, saved locations on a
world map, country alerts, and tropical systems. Each workspace can devote the
terminal to its subject, but moving among them makes it harder to retain a
single global picture.

The application already has most of the necessary data boundaries: active and
saved-location weather summaries, a shared world-map/callout foundation,
canonical tropical-system groups, country-alert catalogues, and session
caches. Task 0028 adds persistent warning products and first-observed metadata;
Task 0027 may later add warning badges to saved-location surfaces.

## Problem

There is no overview that answers all of these questions at once:

- What is the weather at the selected location?
- What are conditions at saved locations around the world?
- Which tropical systems are active and where are they?
- Which alerts have Wevva observed recently across relevant countries?

Simply embedding the existing screens would duplicate large widgets, fetch
lifecycles, focus models, and maps. Multiple competing maps would also leave
too little space for any of them to be useful.

## Desired outcome

Add a persistent dashboard built around one large world map. A compact current-
weather panel sits to its left and a recent-alert feed to its right. The map
combines selectable temperature locations with classification-coloured,
labelled tropical systems. Selecting a recent alert places one animated,
severity-coloured marker at a representative point for its geometry rather
than opening a second map.

The dashboard is a summary and navigation surface. Activating a place, storm,
or alert opens the existing workspace that owns that object.

```text
┌ Current weather ──┬──── World weather and storms ─────┬ Recent alerts ────┐
│ condition / temp  │ London 12°       Tropical Storm  │ Severe Flood      │
│ rain / wind       │                    Melissa       │ France · 8m ago   │
│ compact outlook   │ New York 17°                     │                    │
│                   │              Tokyo 21°           │ Minor Wind        │
│ Open full weather │                                  │ Japan · 14m ago   │
└───────────────────┴──────────────────────────────────┴────────────────────┘
```

## Dependencies

- Task 0023's shared map callout-placement rules remain the foundation for
  mixed map labels.
- Task 0028 supplies persistent warning entries and bounded first-observed
  metadata for the recent-alert feed.
- Task 0027 warning badges are compatible with the dashboard but do not block
  its first implementation.
- Tasks 0021 and 0024 remain owners of detailed and interactive Alerts Centre
  mapping; this dashboard does not absorb those responsibilities.

## Scope

- Add one persistent Dashboard screen with large, medium, compact, and short
  layout budgets.
- Use a three-area wide layout: narrow current weather, flexible world map, and
  narrow recent-alert feed.
- Collapse the areas into stable tabs or one-at-a-time panes when the terminal
  cannot display all three meaningfully.
- Render a compact current-weather view for the active or map-selected place,
  using the configured temperature, rain, and wind units.
- Show the active location and saved locations as selectable temperature
  callouts on the central world map.
- Overlay one label per canonical tropical system, formatted with the existing
  tropical display wording such as `Tropical Storm Melissa` and coloured with
  the existing tropical classification semantics.
- Give selected features, tropical systems, the active location, and ordinary
  saved locations explicit descending placement priorities.
- Expose individual tropical source observations through a tooltip or owning
  workspace rather than synthesizing conflicting tracks or meteorology.
- Build a recent-alert feed from successful complete-country observations for
  relevant countries. Order it by Wevva's first-observed timestamp and label
  that meaning honestly rather than presenting it as provider issue time.
- Derive relevant countries from the active location, saved locations, recent
  Alerts Centre use, and already persisted country catalogues. Do not poll
  every supported country merely because the dashboard is open.
- Bound and deduplicate background refresh work through the application-owned
  services; mounting or resizing the dashboard must not start duplicate
  provider requests.
- Keep alert rows compact and stable, with one selected alert and one fixed
  preview area rather than a list of independently expanding `Collapsible`
  widgets.
- For a selected alert with geometry, place a severity-coloured `●` at a
  deterministic representative point. Prefer an interior point from the
  largest polygon component and handle dateline wrapping through shared
  geography helpers.
- Do not imply precision for geometry-less alerts. They remain selectable in
  the feed without a marker; a later explicitly approximate country marker may
  use a visually distinct form.
- Briefly pulse a newly selected alert marker, then leave it steady in its
  severity colour. Animation must be bounded and cancelled when selection or
  screen lifecycle changes.
- Deep-link place, storm, and alert activation into their owning screens while
  retaining dashboard state for the return journey.
- Preserve keyboard-only operation, visible focus, hover previews, theme
  semantics, configured emoji behavior, and screen-reader-friendly labels.

## Non-goals

- Replacing the full Weather, World Locations, Tropical Systems, or Alerts
  Centre workspaces.
- Adding a second alert map or rendering complete warning documents in the
  dashboard.
- Polling all warning countries globally on a timer.
- Treating first-observed time as authoritative provider issue time.
- Drawing every tropical track and cone simultaneously on the world overview.
- Merging conflicting tropical source observations into invented consensus
  meteorology.
- Sending an alert marker to Weather for its geometric centre. Marine,
  disconnected, and broad alert areas do not define a useful forecast place.
- Introducing a full GIS dependency solely to choose an alert marker cell.
- Making the dashboard the mandatory startup screen in the first release.
- Adding permanent or decorative animation.

## Relevant code

- `wevva/app.py`
- `wevva/messages.py`
- `wevva/alerts_centre_layout.py`
- `wevva/geography.py`
- `wevva/screens/weather_screen.py`
- `wevva/screens/world_locations_screen.py`
- `wevva/screens/alerts_centre_screen.py`
- `wevva/screens/tropical_systems_screen.py`
- `wevva/services/alerts.py`
- `wevva/services/country_alerts.py`
- `wevva/services/tropical.py`
- `wevva/widgets/world_locations_map.py`
- `wevva/widgets/country_alerts_map.py`
- `wevva/widgets/tropical_track.py`
- `wevva/widgets/weather_alerts.py`
- `wevva/wevva.tcss`
- `tests/test_screen_lifecycle.py`
- `tests/test_world_locations_map.py`
- `tests/test_tropical_systems_screen.py`
- `tests/test_alerts_centre_map.py`
- `tests/test_alerts_centre_integration.py`
- `docs/architecture.md`
- `docs/responsive-layout.md`

## Interaction model

### Places and current weather

- Focusing or hovering a place previews its existing summary without changing
  the application's active forecast location.
- Selecting a place updates the left current-weather panel. Previously loaded
  current conditions appear immediately; missing compact conditions use one
  application-owned loader/cache with cancellation and stale-result guards.
- Activating the selected place opens its complete Weather forecast.
- Returning to the dashboard restores the selected place and map focus where
  it remains available.

### Tropical systems

- Each canonical system receives one classification-coloured label and one
  deterministic source-observation anchor; the formatter is shared with the
  Tropical Systems workspace.
- Hover or focus presents compact classification, movement, wind, source, and
  observation-time context where supplied.
- Activating a tropical label opens the Tropical Systems workspace at that
  system and source observation. It does not replace the left location-weather
  panel with a different kind of inspector.
- A selected system may receive restrained focus emphasis, but tracks and
  cones remain the detailed workspace's responsibility.

### Recent alerts

- Hovering or keyboard-highlighting a feed row may show a transient dim marker
  without committing selection or animation.
- Selecting a row records exactly one selected identity, updates the fixed
  preview, and pulses its map marker briefly.
- Selecting a different row replaces the previous marker; markers never
  accumulate as click history.
- Selecting the already-selected row again clears it and restores the ordinary
  world overview.
- Escape clears alert selection. Enter and an explicit `Open alert` action open
  Alerts Centre at the selected country and alert.
- Clicking the selected map marker also opens that alert in Alerts Centre.
- Alerts Centre accepts a pending country/identity deep link and applies it
  only after the matching catalogue is available; stale loads cannot select an
  alert for the wrong country.

### Destination semantics

- Place or temperature label → Weather.
- Tropical-system label → Tropical Systems.
- Alert feed action or selected alert marker → Alerts Centre.

The object type, rather than its coordinates, determines the destination.

## Approach

### Slice A — dashboard shell and responsive contracts

Add the installed persistent screen, navigation path, layout-budget helper,
three stable panel boundaries, empty/loading/error states, and deterministic
fixtures. Establish wide three-column and compact tabbed behavior before
connecting live data. Resizing changes presentation only and performs no
network work.

### Slice B — location weather and unified world map

Adapt the world-location map behind a dashboard-specific composition that can
accept heterogeneous overlays without inheriting full-screen lifecycle state.
Connect active/saved temperature summaries, place selection, the compact left
weather panel, and Weather deep links. Keep fetching and caching in the
application/service boundary rather than in map labels.

### Slice C — tropical overlay and deep links

Add canonical system anchors and shared formatted labels to the world map.
Integrate them with the common placement planner and deterministic priority
rules. Add rich hover/focus context and open the existing Tropical workspace at
the chosen system/source without duplicating its detailed track view.

### Slice D — recent-alert feed

Consume Task 0028's complete-country cache metadata and first-observed journal.
Build the relevant-country set, bounded refresh scheduling, recent ordering,
stable rows, fixed preview, and Alerts Centre deep link. Cache hits populate the
feed immediately; provider refreshes update it through generation-guarded
application state rather than screen-owned fetches.

### Slice E — alert marker and bounded attention animation

Add shared representative-point selection for Polygon and MultiPolygon alert
geometry, including disconnected parts and dateline normalization. Overlay the
single selected marker above every ordinary label, add transient hover preview,
and implement a cancellable short pulse without a permanent timer. Cover row
replacement, toggle-off, Escape, marker activation, geometry-less alerts, and
screen exit/return.

### Slice F — deliberate behavior and appearance fine-tuning

Reserve a final integration slice rather than treating polish as incidental.
Exercise realistic dense location labels, multiple simultaneous tropical
systems, long storm names, rapid alert selection, overlapping markers, empty
feeds, geometry-less alerts, different themes, emoji on/off, and terminal sizes
from 80×24 through very wide displays.

Tune only with the combined dashboard visible:

- side-rail widths and minimum central-map area;
- map label density and placement priority;
- tropical label wording, wrapping, colour, and collision treatment;
- alert-row density, preview height, separators, truncation, and selected state;
- marker glyph, severity contrast, pulse cadence, duration, and final state;
- hover versus persistent selection and repeated-click behavior;
- tab order, focus restoration, footer hints, and deep-link return behavior;
- loading transitions that retain usable cached content without visual churn;
- compact/short layouts where all three areas cannot remain visible;
- render cost, timers, retained widgets, and refresh responsiveness.

This slice may simplify or remove interactions that prove noisy. It must not
quietly expand into new provider queries, detailed mapping, or a second alert
viewer.

## Acceptance criteria

- A wide terminal presents current weather, one dominant world map, and recent
  alerts simultaneously without either side rail crowding the map.
- Compact and short terminals retain complete access through stable tabs or
  panes without mounting duplicate dashboard trees.
- Location temperatures and tropical systems coexist on one projection with
  deterministic collision priority and focus order.
- Tropical labels use existing classification wording and semantic colours,
  and activation reaches the intended system/source in the Tropical workspace.
- Selecting a location updates the left weather panel; activating it opens the
  complete forecast.
- The alert feed covers only relevant/cached countries and never triggers an
  all-country scan.
- Alert recency is based on persisted first observation and is labelled without
  implying an unavailable provider issue time.
- At most one alert marker is persistently visible. Re-selection clears it and
  selecting a different alert replaces it.
- A selected geometry-backed alert gets a deterministic meaningful marker;
  geometry-less alerts do not gain false precision.
- The marker pulse is noticeable but finite, uses semantic colour, and leaves
  no active timer after completion, selection change, or screen exit.
- Alert activation opens Alerts Centre at the correct country/identity even
  when its catalogue must first load.
- Dashboard mounting, resizing, tab switching, and cached return issue no
  duplicate network requests.
- Existing full-screen workspaces retain their current behavior and caches.
- The final fine-tuning slice records the tested size/theme/data matrix and any
  deliberately rejected visual or interaction variants.

## Verification

Add focused tests for the dashboard layout budget, mixed map placement,
selection state machine, representative alert points, bounded animation,
deep-link stale guards, first-observed ordering, relevant-country scheduling,
cache hits, compact tabs, focus restoration, and resize-without-fetch behavior.

```bash
uv run python -m unittest tests.test_screen_lifecycle tests.test_world_locations_map
uv run python -m unittest tests.test_tropical_systems_screen tests.test_alerts_centre_map
uv run python -m unittest tests.test_alerts_centre_integration tests.test_warning_cache
uv run python -m unittest discover -s tests
uv run python -m compileall -q wevva
```

Manually exercise at least 80×24, 100×30, 140×40, and a very wide terminal in
multiple built-in themes, with emoji enabled and disabled. Use fixture-heavy
maps as well as live cached data. Provider latency, terminal colour rendering,
and animation perception still require explicit manual qualification.

## Decisions and notes

- One central geographic surface is preferable to separate world, tropical,
  and selected-alert maps.
- Stable feed rows plus one preview are preferable to many `Collapsible`
  widgets whose heights and focus positions change independently.
- Tropical labels use tropical classification semantics; warning severities
  remain a separate colour vocabulary.
- Alert representative points are navigational attention markers, not claims
  that the full affected area is point-like.
- Brief selection animation is functional attention guidance. Continuous
  motion is not.
- Existing workspaces remain the authoritative detailed views, which keeps the
  dashboard useful without making it another monolithic application.

## Outcome

To be completed when implemented.
