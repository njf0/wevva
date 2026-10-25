# Task 0029: Unified weather dashboard

## Status

Complete — Slices A–H implemented; Task 0030 owns the agreed functional-overview follow-up

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
- Which alerts has Wevva discovered recently across supported countries while
  the application has been running?

Simply embedding the existing screens would duplicate large widgets, fetch
lifecycles, focus models, and maps. Multiple competing maps would also leave
too little space for any of them to be useful.

## Desired outcome

Add a persistent dashboard built around one large world map. A narrow forecast
workspace sits to its left and a recent-alert feed to its right. The map
combines selectable temperature locations with accent-coloured,
labelled tropical systems. Selecting a recent alert places one animated,
severity-coloured marker at a representative point for its geometry rather
than opening a second map.

The dashboard is a summary and navigation surface. Activating a place, storm,
or alert opens the existing workspace that owns that object.

```text
┌ Location forecast ┬──── World weather and storms ─────┬ Recent alerts ────┐
│ current conditions│ London 12°       Tropical Storm  │ Severe Flood      │
│ hourly forecast ↕ │                    Melissa       │ France · 8m ago   │
│                   │ New York 17°                     │                    │
│ compact daily     │              Tokyo 21°           │ Minor Wind        │
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
- Treat 120×30 as the minimum baseline for the simultaneous three-column
  dashboard. This is a content threshold in terminal cells, not merely a
  width-to-height ratio: both dimensions must be available.
- Use a three-area baseline layout: narrow location forecast, flexible world
  map, and narrow recent-alert feed.
- Collapse the areas into stable tabs or one-at-a-time panes when the terminal
  is narrower than 120 columns or shorter than 30 rows. An 80×24 terminal is a
  fallback/smoke target, not a requirement to show the complete dashboard at
  once.
- Derive the left rail from a slightly narrower form of the ordinary Weather
  layout, omitting its location map because the dashboard's central map owns
  that role.
- Give the left rail a fixed current-conditions summary, a flexible internally
  scrollable vertical hourly forecast, and a compact daily forecast. Each
  hourly row carries hour, abbreviated condition, temperature, precipitation
  chance and amount, wind speed, gust, and direction without requiring
  horizontal scrolling.
- Spend large-screen surplus on both side rails instead of allowing the map to
  absorb it all. On very wide, tall terminals, cap the central map near its
  known projection aspect and leave the lower centre unclaimed until a later
  slice supplies real content for it.
- Keep loaded forecast snapshots and saved-location summaries application-owned
  for the active or map-selected place. Loading a dashboard preview must not
  silently adopt that place as the application's active Weather location. The
  Dashboard screen owns only focus, selection, preview identity, and pane state;
  it must not read data back out of another screen.
- Show the active location and saved locations as selectable temperature
  callouts on the central world map.
- Overlay one label per canonical tropical system, formatted with the existing
  tropical display wording such as `Tropical Storm Melissa` and coloured with
  the theme accent.
- Give selected features, tropical systems, the active location, and ordinary
  saved locations explicit descending placement priorities.
- Expose individual tropical source observations through a tooltip or owning
  workspace rather than synthesizing conflicting tracks or meteorology.
- Build a recent-alert feed from successful complete-country observations.
  Order it by Wevva's first-observed timestamp and label that meaning honestly
  rather than presenting it as provider issue time.
- Add one application-owned bulletin coordinator which, while Wevva is open,
  refreshes priority countries promptly and rolls through every country
  advertised by the installed warning-source registry over a much longer
  interval. Dashboard mount, resume, resize, or tab changes must not own or
  restart that work.
- Derive the priority set from the active location, selected dashboard place or
  alert, saved locations, and a bounded history of recent Alerts Centre use.
  Refresh those countries ahead of the rolling background queue without
  starving the rest of the registry. Retained catalogues populate the feed
  immediately but do not all become priority refresh keys.
- Bound and deduplicate bulletin work through the application-owned services.
  Use low concurrency, stagger requests, add jitter and failure backoff, and
  permit at most one in-flight complete-country refresh for a normalized
  country/language key. Cap the priority lane and rotate overflow keys through
  the ordinary queue rather than allowing a large saved set to create a burst.
- Populate the bulletin from retained catalogues immediately. Only a successful
  complete-country refresh may replace a catalogue or advance its observation
  baseline; failure retains the last usable result.
- Keep the first release to currently valid alerts. The bulletin is not a
  durable archive of expired or resolved warnings.
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
- Polling after Wevva exits or installing an operating-system background
  service, daemon, scheduled job, or notification agent.
- Launching an unbounded simultaneous all-country sweep, including from a hard
  `r` refresh.
- Introducing a general-purpose background-job framework for this one bounded
  application service.
- Retaining a historical archive of expired or resolved alerts.
- Treating first-observed time as authoritative provider issue time.
- Drawing every tropical track and cone simultaneously on the world overview.
- Merging conflicting tropical source observations into invented consensus
  meteorology.
- Sending an alert marker to Weather for its geometric centre. Marine,
  disconnected, and broad alert areas do not define a useful forecast place.
- Introducing a full GIS dependency solely to choose an alert marker cell.
- Making the dashboard the mandatory startup screen in the first release.
- Adding permanent or decorative animation.
- Forcing current, hourly, daily, world map, and alert feed into one view below
  the 120×30 baseline; compact layouts may expose them through separate panes.

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
- `wevva/services/alert_bulletin.py`
- `wevva/services/country_alerts.py`
- `wevva/services/warning_cache.py`
- `wevva/services/tropical.py`
- `wevva/widgets/world_locations_map.py`
- `wevva/widgets/weather_summary.py`
- `wevva/widgets/hourly_forecast.py`
- `wevva/widgets/daily_summary.py`
- `wevva/widgets/daily_forecast.py`
- `wevva/widgets/country_alerts_map.py`
- `wevva/widgets/tropical_track.py`
- `wevva/widgets/weather_alerts.py`
- `wevva/wevva.tcss`
- `tests/test_screen_lifecycle.py`
- `tests/test_world_locations_map.py`
- `tests/test_tropical_systems_screen.py`
- `tests/test_alerts_centre_map.py`
- `tests/test_alerts_centre_integration.py`
- `tests/test_alert_bulletin.py`
- `docs/architecture.md`
- `docs/responsive-layout.md`

## Interaction model

### Places and current weather

- Focusing or hovering a place previews its existing summary without changing
  the application's active forecast location.
- Click, Enter, and Space follow one native-label message path. The first
  primary action commits selection; repeating the primary action on the
  selected place activates it.
- Selecting a place updates the left forecast rail. Previously loaded current,
  hourly, and daily models appear immediately; a missing snapshot uses one
  application-owned preview loader/cache with cancellation and stale-result
  guards. Selection alone does not mutate the active Weather location.
- Activating the selected place opens its complete Weather forecast.
- Returning to the dashboard restores the selected place and map focus where
  it remains available.

### Tropical systems

- Each canonical system receives one accent-coloured label and one
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
- Feed rows deduplicate cross-country copies by `(source, alert ID)`. Use the
  earliest local first-observed time among current catalogue copies; deep-link
  through the country attached to that observation, breaking exact ties by
  normalized country code.

### Destination semantics

- Place or temperature label → Weather.
- Tropical-system label → Tropical Systems.
- Alert feed action or selected alert marker → Alerts Centre.

The object type, rather than its coordinates, determines the destination.

### Navigation and return

- Weather exposes `b` to open the one installed Dashboard screen. Dashboard
  exposes `w` and a visible footer action to return to the existing Weather
  screen; Escape remains available to clear alert selection.
- Activating a place adopts it as the active location and returns to the
  existing Weather screen rather than pushing another Weather instance.
- Tropical Systems and Alerts Centre open above Dashboard. Returning from
  either reveals the same Dashboard instance with its selection, pane, and map
  focus restored where the referenced object remains available.

## Bulletin refresh policy

The bulletin coordinator is an application service, not a Dashboard timer. It
starts after the ordinary initial forecast and active-location warning work has
settled, hydrates retained catalogues first, and continues while Wevva remains
open. Suspending or never opening Dashboard does not suspend discovery.

Use two scheduling lanes:

- refresh active, selected, saved, and recently used country keys on the
  existing approximately fifteen-minute freshness cadence, subject to a
  configured priority cap; and
- stagger the remaining supported-country keys across a target cycle of about
  two hours, with at most two country refreshes in flight, jitter, retry
  backoff, and fair rotation.

The target cadence is advisory rather than a promise when providers are slow or
unavailable. A later cycle must not overlap unfinished work from the previous
one. Language changes invalidate the old scheduling keys and rebuild the queue
for the new effective warning language without running both queues indefinitely.

A hard `r` refresh remains deliberately local. On Dashboard it may bypass cache
for the deduplicated active-location country, selected-place country, and
selected-alert country only, capped at those three keys. It does not force all
saved countries, restart the rolling cycle, or launch a global sweep. Repeated
hard refreshes coalesce with an in-flight refresh for the same key, and the
ordinary rolling worker resumes from its prior position afterward.

Task 0028's cache remains disposable rather than authoritative, but its current
global 32-entry limit cannot hold the supported-country working set. Give
complete-country catalogues and reusable point-candidate products separate
bounded retention policies. Country-catalogue retention must cover the current
registry for the effective language with modest headroom, and the cache must
provide a public way to enumerate retained catalogue keys for warm startup.
Likewise, revise the bounded observation-journal policy so one complete global
cycle cannot immediately discard identities that still back current feed rows.
Do not turn either store into an unbounded warning archive.

## Approach

### Slice A — interactive walking skeleton

Deliver a user-facing dashboard immediately rather than postponing the screen
until its data integrations are complete. Add the installed persistent screen,
navigation path, layout-budget helper, three stable panel boundaries, and wide
three-column plus compact tabbed behavior. Introduce the dashboard-specific
mixed-feature map composition now, populated only with active and saved places;
later slices add overlays to this same widget rather than replacing it.

Compute the layout from the usable screen area after header, footer, and stage
padding, then allocate gutters within that area. At the 120×30 viewport
checkpoint, use roughly 34 columns for the forecast rail, 48 for the map, 30
for alerts, and two two-column gutters. This revises the Slice A starting point
by four cells after the vertical-hourly visual checkpoint demonstrated that
the compact columns needed breathing room.

Populate this first slice from existing application state: show the active
location's current summary in the left rail and the active/saved temperature
locations on the central world map. Place focus and selection must already work
through the shared primary-action path, selection must update the left summary,
and repeating the primary action must open Weather. Show
purposeful hourly, daily, tropical-system, and recent-alert placeholders so
their eventual dimensions and hierarchy can be judged in the complete
composition.

Use production screen/widget boundaries and deterministic fixtures rather than
a disposable mock-up. Slice A introduces no new provider request: missing data
uses an honest empty/loading state, and resizing changes presentation only. End
the slice with a manual visual checkpoint at representative wide and compact
sizes before committing to the remaining panel proportions.

### Slice B — selected-location forecast and hourly rail

Add the application-owned selected-location forecast preview/cache and render
current conditions plus a flexible, internally scrollable narrow hourly
forecast using the configured units. Keep fetching and caching out of map
labels, preserve selection without changing the active Weather location, and
retain the reviewed Slice A proportions unless real data demonstrates a
problem. The large-screen visual checkpoint demonstrated that fixed narrow
rails and a horizontal hourly table waste the available geometry, so grow both
rails from the 120×30 baseline, use the vertical hourly rows specified above,
and apply the aspect-aware map cap only on very wide, tall terminals.

### Slice C — compact daily forecast and weather-rail completion

Add the compact daily forecast beneath the flexible hourly region, reusing the
existing daily model and presentation rules where their width assumptions fit.
Coordinate focus and scrolling so hourly navigation does not move or obscure
current conditions and daily context. Qualify the complete three-part rail at
the 120×30 baseline, then define deliberate reductions for medium, compact, and
short panes without adding a second location map.

The implemented budget shows three future days at the 120×30 baseline and up
to six on tall wide dashboards. Medium and compact panes retain two or more
days while shortening the current block; a short pane retains one daily row
and a small internally scrollable hourly viewport. Redundant open-Weather hints
are hidden outside the simultaneous layout. These are presentation reductions
on the same widgets and cached models, not separate forecast trees or requests.

### Slice D — tropical overlay and deep links

Add canonical system anchors and shared formatted labels to the world map.
Integrate them with the common placement planner and deterministic priority
rules. Add rich hover/focus context and open the existing Tropical workspace at
the chosen system/source without duplicating its detailed track view.

The implemented overlay selects one exact valid-centre observation per
canonical system by classification strength, newest issue time, then source
and ID. Locations and storms share the existing callout planner with selected
features first, then storms, the active location, and ordinary saved places.
The accent-coloured, classification-first formatter is shared with Tropical
Systems. Dashboard loads only the canonical application cache; focus
context exposes the chosen observation, while activation carries stable storm
and source/ID intent into the owning workspace without loading tracks or
products on the overview.

### Slice E — session bulletin coordinator

Add the application-owned two-lane scheduler, per-key in-flight coalescing,
controlled hard-refresh path, warm catalogue discovery, cache-retention changes,
and revised bounded observation policy described above. It runs independently
of Dashboard lifecycle, stops when Wevva exits, and exposes stable cached
bulletin state for consumers. Exercise it with deterministic clocks and fake
loaders before connecting the feed. Alerts Centre may join an already-running
country refresh with indeterminate progress, but it must not launch duplicate
provider work merely to obtain measured progress. Document the coordinator's
lifecycle and ownership in `docs/architecture.md`.

Implemented as `AlertBulletinCoordinator`, started only after ordinary
active-location warning work settles and stopped with the application. Its
capped priority lane and fair rolling lane share two refresh slots, exponential
failure backoff, and `CountryAlertsService` key-level coalescing. Retained
catalogues hydrate stable snapshots before provider work; warning products now
have separate retention limits and the bounded observation journal prefers
identities still present in current country snapshots. Dashboard hard refresh
targets only the deduplicated active, selected-place, and selected-alert
countries, capped at those three keys.

### Slice F — recent-alert feed

Consume the coordinator's complete-country catalogues and first-observed
journal. Build current non-expired ordering, cross-country identity
deduplication, stable rows, fixed preview, and the Alerts Centre deep link.
Cache hits populate the feed immediately; completed background refreshes update
it through generation-guarded application state rather than screen-owned
fetches.

Implemented with immutable bulletin rows derived by the coordinator: expired
alerts are removed, `(source, alert ID)` copies are collapsed onto the country
with the earliest persisted observation, and rows are ordered newest discovery
first with stable identity-derived option IDs. The Dashboard rail provides one
selection, fixed preview, honest `First found by Wevva` timing, and an explicit
open action. Generation-numbered application callbacks update it without
screen-owned requests. Alerts Centre accepts a pending country/identity and
applies it only after that country's guarded catalogue load. Marker preview and
animation remain isolated to Slice G.

### Slice G — alert marker and bounded attention animation

Add shared representative-point selection for Polygon and MultiPolygon alert
geometry, including disconnected parts and dateline normalization. Overlay the
single selected marker above every ordinary label, add transient hover preview,
and implement a cancellable short pulse without a permanent timer. Cover row
replacement, toggle-off, Escape, marker activation, geometry-less alerts, and
screen exit/return.

Implemented with one top-layer `DashboardAlertMarker`, shared deterministic
Polygon/MultiPolygon representative-point selection, and the same transient
pointer/keyboard preview pattern used by Alerts Centre. A committed selection
replaces rather than accumulates marker state, toggling or Escape clears it,
geometry-less alerts remain unmarked, and marker activation uses the existing
country/identity deep link. The pulse is one short cancellable task; selection
replacement and Dashboard suspension cancel it, while resume restores only the
steady selected marker.

### Slice H — deliberate behavior and appearance fine-tuning

Reserve a final integration slice rather than treating polish as incidental.
Exercise realistic dense location labels, multiple simultaneous tropical
systems, long storm names, rapid alert selection, overlapping markers, empty
feeds, geometry-less alerts, different themes, emoji on/off, the 120×30 full-
dashboard baseline, smaller fallback panes, and very wide displays.

Tune only with the combined dashboard visible:

- side-rail widths and minimum central-map area;
- current/hourly/daily height allocation, hourly scroll affordance, and compact
  daily density;
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

- Slice A alone exposes a navigable production dashboard with real current or
  cached location data, selectable map places, Weather activation, visible
  hourly/daily/tropical/alert placeholders, and no new network path.
- The Slice A visual checkpoint covers at least one wide and one compact size;
  later slices build into those reviewed boundaries rather than revealing the
  complete composition only at the end.
- A wide terminal presents current weather, one dominant world map, and recent
  alerts simultaneously without either side rail crowding the map.
- At 120×30, the full three-column dashboard is meaningful: the left rail shows
  current conditions, a usable scrollable hourly region, and compact daily
  context while the centre retains a useful world map.
- Below 120×30, responsive panes preserve access without claiming that all
  dashboard content remains simultaneously useful; 80×24 is smoke-tested only
  as a fallback layout.
- Compact and short terminals retain complete access through stable tabs or
  panes without mounting duplicate dashboard trees.
- Location temperatures and tropical systems coexist on one projection with
  deterministic collision priority and focus order.
- Tropical labels use existing classification wording and the theme accent,
  and activation reaches the intended system/source in the Tropical workspace.
- Selecting a location updates the left weather panel; activating it opens the
  complete forecast.
- Dashboard selection can load or reuse a forecast preview without changing
  the Weather screen's active location until activation.
- Weather's `b` action opens the installed Dashboard. Dashboard's `w` action
  returns to the existing Weather screen, while place activation adopts that
  location without pushing a duplicate Weather instance.
- Focus and hover remain transient. Click, Enter, and Space share one message
  path: the first primary action selects a place and repeating it activates the
  selected place.
- Retained catalogues populate the alert feed before provider work completes,
  and the feed contains only currently valid alerts.
- While Wevva is open, priority countries refresh promptly and every supported
  country receives fair service through the staggered rolling queue without an
  overlapping all-country burst.
- Dashboard mount, resize, tab switching, suspension, and return neither start
  nor restart the bulletin coordinator.
- A hard `r` refresh affects no more than the deduplicated active, selected-place,
  and selected-alert country keys; repeated requests coalesce and never expand
  into a global sweep.
- Bulletin work stops at application exit. No process, daemon, or scheduled job
  continues polling afterward.
- Separate bounded cache retention prevents a global catalogue cycle from
  evicting reusable active-location warning products solely because they share
  one global entry limit.
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
deep-link stale guards, first-observed ordering, priority and rolling bulletin
scheduling, hard-refresh caps and coalescing, cache retention and warm discovery,
failure backoff, clean application shutdown, cache hits, compact tabs, focus
restoration, and resize-without-fetch behavior.

```bash
uv run python -m unittest tests.test_screen_lifecycle tests.test_world_locations_map
uv run python -m unittest tests.test_tropical_systems_screen tests.test_alerts_centre_map
uv run python -m unittest tests.test_alerts_centre_integration tests.test_warning_cache
uv run python -m unittest tests.test_alert_bulletin
uv run python -m unittest discover -s tests
uv run python -m compileall -q wevva
```

Manually exercise 120×30 as the minimum full-dashboard baseline, plus 80×24 and
100×30 fallback layouts, 140×40, and a very wide terminal in multiple built-in
themes, with emoji enabled and disabled. Use fixture-heavy maps as well as live
cached data. Provider latency, terminal colour rendering, and animation
perception still require explicit manual qualification.

## Decisions and notes

- One central geographic surface is preferable to separate world, tropical,
  and selected-alert maps.
- Stable feed rows plus one preview are preferable to many `Collapsible`
  widgets whose heights and focus positions change independently.
- Tropical labels use the theme accent; warning severities remain a separate
  colour vocabulary.
- Alert representative points are navigational attention markers, not claims
  that the full affected area is point-like.
- Brief selection animation is functional attention guidance. Continuous
  motion is not.
- Existing workspaces remain the authoritative detailed views, which keeps the
  dashboard useful without making it another monolithic application.
- The full simultaneous dashboard begins at 120×30. Smaller terminals remain
  supported through responsive panes, not increasingly compressed typography
  or unusably small map and forecast regions.
- Background bulletin discovery runs only during an open Wevva session. The
  first release shows currently valid alerts rather than keeping a warning
  history after alerts expire or disappear.
- Local first-observed time means when a successful Wevva catalogue refresh
  first discovered an identity. It remains distinct from provider issue time,
  and its precision is bounded by the rolling refresh cadence.
- Hard refresh is a targeted cache bypass, not permission to fan out over the
  full warning-source registry.

## Outcome

Implemented through Slices A–H with one installed Dashboard tree, the shared
world projection/callout planner, application-owned forecast and tropical
caches, and the session-owned alert bulletin coordinator. The final integration
pass retained the reviewed rail and map proportions. It tightened alert rows to
two deterministic lines at the current rail width, kept the fixed preview's
condition and area to one line each, added a non-geographic selection chevron,
made the footer's original `r` action explicit as `Refresh alerts`, restored focus to the
originating alert row/button/marker after a deep-link return, and rebuilds only
cached theme/emoji-sensitive Dashboard content when appearance changes.

Later Dashboard integration work superseded that original binding: `r` now
refreshes the selected forecast, point-matched alerts, and tropical systems,
while the bulletin remains wholly on its application-owned background cadence.

The final fixture-heavy visual matrix covered 80×24 and 100×30 fallback panes,
the 120×30 simultaneous baseline, 140×40, and 250×70. It used fifteen weather
locations, four simultaneous tropical systems including long names, six alerts
including long labels and overlapping geography, both `textual-dark` and
`textual-light`, and emoji enabled and disabled. Focused interaction checks
additionally covered empty and geometry-less feeds, rapid alert replacement,
pulse cancellation/completion, Escape and repeated selection, marker
activation, screen exit/return, compact tab reuse, and very-wide map capping.

Deliberately rejected variants were further baseline rail growth, vertically
shifted world callouts, wrapping storm labels, expandable alert cards, full
warning polygons on the world overview, an approximate geometry-less marker,
continuous animation, and placeholder content below the aspect-capped map.
Those either reduced the central overview, weakened geographic meaning, added
visual churn, or duplicated an owning workspace. Live-provider latency,
terminal-specific font/emoji rendering, and subjective pulse visibility remain
manual qualifications outside deterministic fixtures.
