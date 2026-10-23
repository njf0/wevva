# Task 0032: Dashboard mechanics audit

## Status

In progress — Slices A-D complete

## Context

Task 0025 completed a measured screen-by-screen performance and complexity
audit before the Dashboard existed. Tasks 0029 and 0030 subsequently added the
persistent Dashboard, its application-owned preview paths, the all-country
alert bulletin, and in-place location, tropical-system, and selected-alert
readers.

The resulting feature is intentionally broad. Its main screen now contains
2,339 physical lines, in addition to 1,173 lines in its three Dashboard-specific
forecast/map widgets, 128 lines in its pure layout allocator, and 543 lines in
the bulletin coordinator. Size alone is not a defect: much of this code
preserves genuinely different selection, loading, cache, and stale-result
contracts. It does mean that the Dashboard should receive the same measured
performance, deletion, and lifecycle review that the older screens received in
Task 0025 before feature work is considered closed.

Recent fixes provide concrete reasons for the review. Background bulletin
delivery reached a partially detached Dashboard tree; an unchanged alert could
replay its `NEW` attention state; and changing forecast location could briefly
resurface the previous location's mounted warning panel. Those faults are
fixed, but each involved interactions between persistent screen state,
asynchronous completion, and presentation state rather than an isolated
formatter.

## Problem

- The Task 0025 benchmark and repeated-transition matrix do not cover the
  Dashboard, because it was added later.
- `DashboardScreen` coordinates forecast, point-warning, canonical-system,
  tropical-product, settlement-preview, bulletin, timer, responsive-pane, and
  return-focus state. There is no comparable record of which state is
  essential, duplicated, retained too long, or doing repeated local work.
- Dashboard concepts intentionally resemble the Weather, World Locations,
  Tropical Systems, and Alerts Centre workspaces. Some reuse is already at the
  right boundary, while other similar mechanics may have drifted into parallel
  screen-owned implementations.
- Persistent mount/resume behavior can repeat label synchronization, table
  reconstruction, map geometry work, and document rendering even when the
  application-owned snapshot has not changed.
- A broad request to consolidate the Dashboard could easily produce a generic
  pane, request, cache, or screen abstraction which is larger and harder to
  reason about than the direct code it replaces.

## Desired outcome

Produce a reproducible Dashboard performance and lifecycle record, then make
only bounded changes supported by structural or measured evidence. The final
Dashboard should do less redundant work, retain no unnecessary unbounded
presentation state, and share data or presentation behavior with specialist
screens only where one owner genuinely serves both.

The audit must preserve the functional-overview interaction model, current
visual design, responsive budgets, cache semantics, provider truth, and stale-
result safeguards. A correct outcome may retain apparently similar code where
the full screens and Dashboard have different lifecycle or interaction needs.

## Audit contract

Follow Task 0025's measurement and complexity rules:

- use deterministic loaders and keep provider wait outside local timings;
- prefer work counts—fetches, task creation/cancellation, table rebuilds, map
  view/frame builds, label synchronization, tab replacement, and document
  rendering—over fragile elapsed-time claims;
- record indicative timings only on the same machine and environment, with
  warm-up and sample counts;
- make a production change only for a repeatable hot path, proven duplicate
  expensive work, a user-visible lifecycle fault, unbounded retained state, or
  a clear deletion with no behavior loss;
- report production, test, audit-tool, and documentation line deltas
  separately; and
- do not treat fewer lines or a new shared class as an improvement unless total
  conceptual complexity falls.

For every slice answer:

1. Can duplicated, obsolete, or unreachable paths be deleted?
2. Can the same behavior use fewer states, tasks, caches, rebuilds, or custom
   widgets?
3. Does a low-value behavior own disproportionate complexity?
4. Would sharing with a specialist screen actually reduce total ownership, or
   merely hide two different lifecycles behind one abstraction?

## Scope

- Dashboard startup, first forecast completion, cold and warm entry, resume,
  suspension, appearance changes, resize bursts, and return to Weather.
- Cached and uncached place selection; rapid replacement; hourly selection;
  saved-summary promotion; point-warning completion; and point-warning expiry.
- Canonical-system discovery, storm selection, cached and uncached product
  completion, stale canonical refresh, replacement failure, and rapid storm
  changes.
- Bulletin snapshots with no row change, relative-time-only change, `NEW`
  changes, selection removal, incoming-marker animation, selected-alert map and
  document changes, and settlement preview/selection.
- Compact pane changes at `80x24` and `100x30`, simultaneous layouts at
  `120x30`, `140x40`, and a very wide/tall size, plus the existing four-size
  Task 0025 resize burst.
- Repeated Dashboard/Weather, Dashboard/Tropical Systems, and
  Dashboard/Alerts Centre transitions, including completion while suspended
  and final application teardown.
- Production deletion and consolidation inside Dashboard paths and the small
  shared boundaries they already consume.

## Existing reuse to preserve unless evidence disproves it

- `Wevva` owns complete forecast snapshots, in-flight forecast coalescing,
  saved-location summaries, canonical systems, tropical products, the country
  Alerts service, and the bulletin coordinator. Dashboard widgets must not
  acquire provider or durable-cache ownership.
- `DashboardWorldMap` subclasses `WorldLocationsMap` at its narrow label,
  candidate-ordering, and interaction hooks. The shared world projection,
  backdrop cache, directional callout planner, temperature labels, and stable
  native widgets remain the useful common boundary.
- The location rail reuses `CurrentConditions`, `DailySummaryTable`, and
  `ContextBar`. Its vertical hourly table is deliberately Dashboard-specific
  because the Weather screen's horizontal hour/day navigation solves a
  different geometry and interaction problem.
- Dashboard and Tropical Systems share `LargeTropicalStormTrackScope` and the
  pure helpers in `widgets/tropical_products.py`. They should not share a
  Screen, selection controller, or product-task owner merely because both show
  tabs.
- Dashboard and Alerts Centre share `CountryAlertsMap`, settlement messages
  and tooltip formatting, `alert_renderable()`, country-alert identities, and
  the application loader. They should not embed or reach into the persistent
  Alerts Centre screen.
- Dashboard location warnings reuse Weather's warning panel presentation, but
  intentionally use the complete-country catalogue plus a fresh native point
  query. Weather's progress-bearing reusable-candidate path has a different
  cache namespace and refresh contract and must not be silently substituted.
- Task 0031 owns tropical track/cone viewport framing and the shared storm-map
  framing engine. This audit may count calls into it but must not alter its
  projection or framing behavior.

## Evidence-backed candidates to investigate

These are hypotheses for measurement, not pre-approved refactors.

### Forecast and shared weather presentation

- `ContextBar.update_forecast()` assigns four reactive values in sequence.
  Once prior data exists, its watchers can update child widgets against
  intermediate old/new combinations before the final display. Both Weather
  and Dashboard use this path, so a single explicit snapshot application may
  remove real shared work without adding a new abstraction.
- `DashboardForecastPanel.set_layout()` reapplies current-condition and context
  layouts whenever any field in the outer Dashboard budget changes, including
  wide-size changes whose forecast density is unchanged. Count child layout
  applications before adding a local equality guard.
- Forecast selection correctly reuses the application cache. Keep screen
  generation state only where it prevents a late result from replacing a new
  selection; do not add a second result cache.
- Location warning state is separate from the forecast cache by design. Audit
  mount/remove churn and same-location refresh behavior, but retain immediate
  clearing on a different location and stale-result rejection.

### World map and saved-summary propagation

- `sync_from_app()` sends locations, units, active selection, committed
  selection, and tropical systems through several setters on every resume.
  Reflow scheduling is already coalesced, but label synchronization and state
  writes may still repeat. Count `_sync_label_widgets()`, callout planning, and
  `_reflow()` before changing setter behavior.
- `DashboardWorldMap.set_active_location()` and
  `set_selected_tropical()` schedule placement work even when their keys are
  unchanged. Small identity guards are justified only if resume or bulletin
  scenarios demonstrate repeated work.
- Do not merge World Locations and Dashboard screen lifecycles. The former is
  a transient navigation surface; the latter is an installed mixed-feature
  overview. Their existing common map widget is the intended integration.

### Tropical detail

- The Dashboard and Tropical Systems workspace both manage tabs and rendered
  product bodies, but they differ in source navigation, centre weather,
  summary, error memory, refresh behavior, and responsive topology. Measure
  duplicated rendering and task work before considering any extraction beyond
  the existing pure product helpers.
- The Dashboard world map's `set_tropical_loading()` and
  `set_tropical_error()` hooks are empty remnants from the former map-overlay
  status design. If no compatibility or test caller needs them, delete the
  calls and methods.
- Verify that reselecting a fresh storm does not clear/rebuild tabs or start a
  waiter, while stale refresh preserves the current reader and performs one
  coalesced canonical and product request.

### Bulletin and selected-alert detail

- Every accepted bulletin generation currently rebuilds `OptionList` rows and
  calls `DashboardAlertDetailPanel.show_alert()`. For an unchanged selected
  row, that calls `CountryAlertsMap.update_country()`, which rebuilds selected
  geometry and polygon layers. Measure unchanged and unrelated-country
  bulletin updates and skip only presentation proven identical; appearance
  refresh must remain explicit and correct.
- `_flashed_new_alert_identities` grows for the lifetime of the installed
  Dashboard and also prevents a genuinely absent-then-rediscovered identity
  from ever flashing again. A bounded current-`NEW` snapshot may express the
  intended no-replay rule more accurately, but requires regression coverage
  for unchanged generations, badge clearing, resume, and rediscovery.
- The incoming-marker widget pool retains the largest batch ever seen. Compare
  that retained peak with the bulletin's actual row bounds before deciding
  whether widgets should be removed after a pulse.
- Alerts Centre owns a short-lived settlement-weather cache, while Dashboard
  uses the same application loader but repeats requests after each hover. Since
  both consume the same coordinate/unit response, evaluate moving the bounded
  cache and in-flight coalescing to `Wevva.load_alert_place_weather()`. Do so
  only if it deletes the Alerts Centre cache path and serves both callers; do
  not create a generic cache framework.
- Retain the Dashboard's guarded delivery during partial mount/unmount. Any
  simplification must preserve the fixed background-callback failure case.

### File and state organization

- The 2,339-line screen contains four substantial panel classes as well as the
  screen coordinator. Moving classes between files is not itself a runtime or
  complexity improvement. Split only if a completed slice identifies a
  coherent reusable owner or if it materially clarifies lifecycle state while
  reducing imports and cross-class access.
- Forecast, point-warning, tropical-discovery, tropical-product,
  stale-tropical-refresh, settlement-preview, bulletin, and timer state have
  different invalidation rules. Do not replace them with a generic request
  manager or generation object unless two completed slices prove identical
  ownership and the replacement deletes more machinery than it adds.

## Non-goals

- Visual redesign, new data, new tabs, provider changes, or new Dashboard
  interactions.
- Task 0031 storm viewport/framing work.
- Merging the Dashboard with Weather, World Locations, Tropical Systems, or
  Alerts Centre, or making those screens thin wrappers around Dashboard
  panels.
- A generic dashboard model, pane protocol, request coordinator, event bus,
  cache hierarchy, map framework, or screen superclass.
- Removing stale-generation, cancellation, hidden-screen, partial-tree, cache-
  expiry, or hard-refresh safeguards to reduce line count.
- Optimising network/provider latency or adding runtime telemetry and
  dependencies.
- Rewriting correct formatters, colour scales, map projections, or forecast
  models for stylistic consistency.
- Treating module splitting, fewer methods, or lower physical line count as a
  result without less work or clearer ownership.

## Approach

### Slice A — baseline and structural instrumentation

Extend the checkout-only Task 0025 harness with deterministic Dashboard
scenarios. Record cold startup, warm resume, cached and uncached place
selection, same/new location warning completion, summary delivery, unchanged
and changed bulletin delivery, storm/product selection, compact/wide resize,
and exit/return. Add temporary or test-only counters at the expensive
boundaries; do not add runtime telemetry.

Capture initial production/test/audit-tool line counts and a lifecycle-state
inventory. This slice makes no production optimization unless it discovers an
independent correctness fault.

### Slice B — location forecast and Weather integration

Audit `DashboardForecastPanel`, hourly/daily adapters, `ContextBar`, forecast
cache handoff, selected-hour propagation, and point warnings. Remove repeated
snapshot/layout application only where counts prove it. Preserve the vertical
hourly adapter and the distinct Weather warning-fetch contract.

Depends on Slice A. It may change a shared Weather widget only when both
Dashboard and Weather benefit and focused coverage proves both paths.

### Slice C — world map and saved-location integration

Measure Dashboard mount/resume, saved-summary updates, selection-only changes,
appearance refresh, and resize. Audit repeated label synchronization, callout
planning, backdrop use, state setters, focus restoration, and application
fan-out to Weather/Dashboard/World Locations. Keep the existing base-map
subclass boundary unless evidence shows it causes duplicate expensive work.

Depends on Slice A and can otherwise proceed independently of Slice B.

### Slice D — tropical detail and workspace integration

Measure discovery, fresh reselection, cached and uncached products, rapid
selection, stale canonical refresh, failed refresh, product-tab changes,
resize, and Dashboard/Tropical transitions. Delete obsolete overlay hooks and
consolidate only presentation work genuinely shared with the specialist
workspace. Leave viewport framing to Task 0031.

Depends on Slice A; use Task 0031's final framing implementation if it lands
first without absorbing that task.

### Slice E — bulletin, selected alert, and Alerts Centre integration

Measure no-change and changed bulletin delivery, list-label refresh, selection
retention/removal, map/document rebuilds, `NEW` transitions, incoming pulses,
settlement previews, and deep-link return. Bound retained presentation state,
avoid unchanged geometry/document work, and place settlement-preview caching
at one shared owner only if doing so deletes parallel ownership.

Depends on Slice A. Service-level bulletin semantics remain independent of
Dashboard presentation and must retain their first-baseline behavior.

### Slice F — cross-screen lifecycle and consolidation

Exercise repeated Dashboard/Weather, Dashboard/Tropical, and Dashboard/Alerts
cycles with pending and expired work. Check timers, tasks, widget pools,
installed-screen references, caches, focus restoration, and teardown. Review
all completed slice findings together and extract shared code only when at
least two slices show the same ownership and the extraction reduces total
complexity.

Compare the final scenario matrix with Slice A, run the focused suite and one
complete suite, and record negative findings and deferred product decisions.

## Acceptance criteria

- Dashboard cold/warm, update, selection, resize, pending-work, and
  exit/return scenarios have a reproducible deterministic record with provider
  wait excluded.
- Expensive local boundaries have before/after structural counts for every
  production optimization; no result relies only on a noisy timing change.
- Cached resume and unchanged bulletin work do not rebuild forecast tables,
  labels, alert geometry, or documents without a stated presentation reason.
- Repeated navigation leaves one installed Dashboard, one paused/resumed time
  timer, no obsolete waiter or settlement-preview task, and no unintended
  growth in presentation-only sets or widget pools.
- Forecast, warning, tropical, product, and bulletin cache keys, TTLs,
  coalescing, explicit-refresh behavior, and stale-result guards remain as
  documented unless a tested change is explicitly justified.
- Dashboard and specialist screens share data, widgets, and pure renderers at
  clear boundaries without embedding screens or acquiring each other's
  lifecycle state.
- Resize, focus, hover, tab, appearance, and selection-only paths do not add
  provider or packaged-resource work.
- `80x24`, `100x30`, `120x30`, `140x40`, and a very wide/tall layout retain one
  stable widget tree, current focus/selection semantics, and existing visual
  behavior.
- Task 0031 remains the sole owner of storm viewport framing.
- Every slice reports negative findings and separate production, test,
  audit-tool, and documentation deltas. No speculative framework or dependency
  is added.

## Relevant code

- `wevva/app.py`
- `wevva/dashboard_layout.py`
- `wevva/screens/dashboard_screen.py`
- `wevva/screens/weather_screen.py`
- `wevva/screens/world_locations_screen.py`
- `wevva/screens/tropical_systems_screen.py`
- `wevva/screens/alerts_centre_screen.py`
- `wevva/services/alert_bulletin.py`
- `wevva/services/alerts.py`
- `wevva/services/country_alerts.py`
- `wevva/widgets/context_bar.py`
- `wevva/widgets/dashboard_hourly_forecast.py`
- `wevva/widgets/dashboard_daily_forecast.py`
- `wevva/widgets/dashboard_world_map.py`
- `wevva/widgets/world_locations_map.py`
- `wevva/widgets/tropical_products.py`
- `wevva/widgets/tropical_track.py`
- `wevva/widgets/country_alerts_map.py`
- `wevva/widgets/weather_alerts.py`
- `tools/benchmark_screens.py`
- `tests/test_dashboard_layout.py`
- `tests/test_dashboard_screen.py`
- `tests/test_alert_bulletin.py`
- `tests/test_screen_lifecycle.py`
- Tasks 0025, 0029, 0030, and 0031

## Verification

Use focused checks during each slice and one complete run after Slice F:

```bash
UV_CACHE_DIR=/tmp/wevva-uv-cache uv run python tools/benchmark_screens.py
UV_CACHE_DIR=/tmp/wevva-uv-cache uv run python -m unittest \
  tests.test_dashboard_layout tests.test_dashboard_screen
UV_CACHE_DIR=/tmp/wevva-uv-cache uv run python -m unittest \
  tests.test_alert_bulletin tests.test_alerts_centre_map
UV_CACHE_DIR=/tmp/wevva-uv-cache uv run python -m unittest \
  tests.test_tropical_systems_screen tests.test_forecast_cache
UV_CACHE_DIR=/tmp/wevva-uv-cache uv run python -m unittest \
  tests.test_screen_lifecycle
UV_CACHE_DIR=/tmp/wevva-uv-cache uv run python -m compileall -q wevva
UV_CACHE_DIR=/tmp/wevva-uv-cache uv run python -m unittest discover -s tests
```

Manual checks should cover one ordinary colour terminal at `80x24`, `120x30`,
and a very wide/tall size. Live-provider behavior, terminal colour/font/Braille
rendering, and subjective animation cadence must not be claimed from mounted
tests alone.

## Decisions and notes

- This is the post-0030 Dashboard equivalent of Task 0025, not an extension of
  completed Task 0025.
- The audit begins from the current clean tree after the stale location-warning
  fix.
- The default decision is to retain existing reuse boundaries. Consolidation
  needs evidence that it reduces both work and ownership.
- Specialist screens remain first-class workspaces. “Smoothing integration”
  means common application data/cache ownership and shared focused widgets or
  pure renderers, not forcing unlike screen orchestration through one class.
- The useful 95-percent standard from Task 0030 remains in force: honest empty
  or unavailable states are preferable to large abstractions for rare edge
  cases.

## Outcome

### Slice A — baseline and structural instrumentation

Slice A began at `161f39c` with only this task sheet and its audit-tool changes
uncommitted. Production and regression-test code were unchanged. The existing
Task 0025 harness now has a `--scope dashboard` mode and includes the Dashboard
in its default complete matrix. The older workspace fixture explicitly selects
`start_on_dashboard=False`; without that adjustment it no longer measured its
documented Weather-first sequence after Task 0030 made Dashboard startup the
application default.

The Dashboard fixture uses three saved locations, a 72-hour/seven-day forecast,
two canonical systems containing three source observations, representative
official products, one polygon alert, immediate point-warning lookup, and a
controlled forecast gate. It exercises cold entry, warm resume, cached and
uncached place selection, three summary deliveries, storm/product selection,
initial and unchanged bulletin delivery, selected-alert rendering, forty time
updates, the common four-size resize burst, and five Weather/Dashboard cycles.
Provider wait is excluded. Checkout-only wrappers count forecast/table/context
application, map label synchronization and reflow, alert list/detail/geometry
updates, tropical track application, and provider-loader calls.

Run the focused matrix with:

```bash
UV_CACHE_DIR=/tmp/wevva-uv-cache uv run python tools/benchmark_screens.py \
  --scope dashboard
```

The recorded baseline used CPython 3.13.0, Textual 8.0.0, macOS 26.7.1 x86_64,
one discarded complete warm-up, and three samples. Times are milliseconds and
show `median [minimum–maximum]`; they include mounted Textual settling and are
comparative observations rather than application promises.

| Dashboard scenario | Local time | Structural baseline |
|---|---:|---|
| cold entry | 1,654 [1,490–1,705] | one forecast and one warning request; two snapshot applications, four hourly rebuilds, two label synchronizations and two world reflows |
| cached resume | 443 [408–448] | one snapshot/hourly application, bulletin list/detail update, label synchronization and world reflow |
| cached place selection | 82 [82–135] | one snapshot/hourly/context application and one point-warning request |
| uncached selection start | 42 [42–45] | one forecast and one point-warning request |
| uncached selection completion | 210 [171–227] | two snapshot applications, three hourly rebuilds and one world reflow |
| three saved-summary updates | 74 [71–88] | one selected-forecast/hourly reapplication and one coalesced world reflow |
| tropical selection/products | 377 [338–383] | one product request, one system application, two track updates and one world reflow |
| first one-row bulletin delivery | 89 [82–95] | one list and empty-detail update; no alert geometry yet |
| selected alert | 354 [352–360] | one detail and selected-country geometry rebuild plus one world reflow |
| unchanged bulletin delivery | 149 [138–157] | one list, detail and selected-country geometry rebuild despite identical input |
| forty time updates | 92 [89–107] | no forecast, table, context-snapshot, map or provider boundary crossed |
| four-size resize burst | 3,347 [3,122–3,430] | four layout applications/world reflows, six daily rebuilds and two hourly rebuilds |
| five Weather/Dashboard cycles | 2,567 [2,415–2,573] | five snapshot/hourly applications, label synchronizations and world reflows |

A separate one-pass `tracemalloc` observation found about 53.9 MiB transient
Python allocation for cold entry, 8.9 MiB for five resume cycles, 7.3 MiB for
selected-alert rendering, 4.2 MiB for the resize burst, 3.6 MiB for tropical
selection, 3.4 MiB for one cached resume, and 2.0 MiB for an unchanged
bulletin delivery. Traced timings are deliberately not used as latency
baselines, and these values are not retained-process-memory claims.

#### Structural findings and slice routing

- Forecast completion enters the application summary fan-out after its cache
  is populated. `DashboardScreen.update_weather_summary()` then sees the
  displayed location and reapplies that same cached forecast before
  `_load_forecast()` resumes and applies it again. This explains the two
  snapshot applications on cold and uncached completion and routes to Slice B.
- An ordinary saved-summary update for the currently displayed location also
  reapplies the complete forecast even though only the world callout changed.
  The three-update fixture therefore performs one avoidable forecast/hourly
  rebuild. The shared summary fan-out remains correct; its Dashboard consumer
  should stop reading the unchanged forecast again. This straddles Slices B/C.
- Warm resume unconditionally resynchronizes unchanged saved labels and
  reapplies the cached forecast and empty/unchanged bulletin. Five cycles prove
  five of each operation. Slice C owns label/reflow work; Slices B and E own
  their respective presentation no-ops.
- An unchanged selected bulletin row reconstructs its one-alert country view
  and polygon layers. This is direct expensive-work evidence for Slice E, not
  a proposal to cache arbitrary maps.
- Four distinct resizes correctly require four Dashboard budgets and four
  world reflows. Six daily-table rebuilds show an additional resize/layout
  interaction for Slice B to inspect. The two hourly rebuilds indicate that its
  existing fitted-width equality check is already effective.
- Tropical selection issues exactly one product request. Its two track updates
  correspond to immediate source geometry followed by product-enriched
  geometry, which is required behavior rather than proven duplication. Slice D
  should retain this unless its more detailed scenarios show otherwise.
- Forty clock/astronomy refreshes cross none of the instrumented snapshot,
  table, map, or provider boundaries. The one-second timer is proportionate.
- The `ContextBar` hypothesis is not supported: it updates once per actual
  snapshot application rather than once per reactive assignment. No shared
  reactive rewrite is justified.

#### Complexity and deletion record

1. The two empty Dashboard world-map tropical status hooks remain a concrete
   deletion candidate for Slice D. No other unreachable production path was
   established in Slice A.
2. Duplicate snapshot, resume, and bulletin presentation work can likely be
   removed with local identity/state checks. No extra cache or generic task
   manager is indicated.
3. No user-visible low-value feature is yet proven disproportionately costly.
   Selected-alert geometry is substantial, but the issue measured here is
   rebuilding it for unchanged input, not rendering it when selected.
4. Existing specialist-screen reuse remains at the right level. The baseline
   shows no reason to merge Screens, product readers, or request lifecycles.

#### Slice A accounting and verification

- Production: `+0/-0` lines.
- Tests: `+0/-0` lines; the harness uses the existing deterministic fixtures
  and asserts its lifecycle invariants directly.
- Audit tooling: `+390/-10` lines in `tools/benchmark_screens.py`, including
  the Dashboard fixture, structural counters, focused-scope option, and the
  explicit historical Weather-first fixture setting.
- Documentation: this task definition and Slice A record.
- Dependencies, runtime telemetry, public API, provider behavior, screen
  behavior, cache semantics, and Task 0031 framing: unchanged.

The focused one-warm-up/three-sample baseline, a separate allocation pass, and
one complete no-warm-up historical-plus-Dashboard matrix all completed. The
benchmark module compiles and `git diff --check` passes. No live provider,
interactive terminal, font, colour, Braille-glyph, emoji, or manual mouse check
was performed in this measurement-only slice.

### Slice B — location forecast and Weather integration

Slice B kept the existing ownership boundary: `Wevva` still owns forecast
snapshots and summary fan-out, Weather retains its warning-fetch contract, and
the Dashboard's vertical hourly/daily adapters remain presentation-only. No
shared screen, cache, request manager, or formatter abstraction was added.

Three measured duplicates were removed locally:

- `DashboardScreen.update_weather_summary()` now updates only the world-map
  summary it was given. It no longer reads and reapplies the selected complete
  forecast. This removes the second snapshot application after an uncached
  forecast completes and removes forecast work from ordinary saved-summary
  delivery.
- `DashboardForecastPanel` records the rendered location values and identities
  of the current/hourly/daily models. Reconciliation with the same cached
  snapshot on resume preserves the existing rendered tables and selected hour.
  Appearance refresh explicitly forces rebuilding because its Rich content is
  theme- and emoji-sensitive; loading, error, and location-only states clear
  the identity.
- The Dashboard hourly and daily adapters defer same-frame model/size layout
  requests through one `call_after_refresh` callback. This coalesces the parent
  budget and child resize messages without changing fitted widths, row counts,
  standard daily formatting, or responsive breakpoints.

The comparable one-warm-up/three-sample pass used the same environment and
fixtures as Slice A. Structural counts are the primary result: cold entry and
uncached completion fell from two snapshot applications to one; the vertical
hourly table fell from four to one rebuild on cold entry and from three to one
on uncached completion; three summary updates fell from one forecast/hourly
application to none; cached resume and five Weather/Dashboard cycles perform no
hourly, daily, or context rebuild; and four real resize budgets fell from six
daily rebuilds to four. Cached place selection correctly remains one snapshot,
hourly, and context application.

Indicative medians were 1,741 ms for cold entry, 466 ms for cached resume,
202 ms for uncached completion, 45 ms for three summary updates, 3,556 ms for
the four-size resize burst, and 2,788 ms for five navigation cycles. Against
the Slice A medians, summary delivery improved from 74 ms and uncached
completion from 210 ms; several broader lifecycle timings varied upward by
roughly five to nine percent despite their eliminated table work. Those paths
remain dominated by map, bulletin, and Textual lifecycle work assigned to later
slices, so Slice B claims the repeatable structural reduction rather than a
general latency win.

#### Slice B accounting and verification

- Production: `+49/-17` lines across the Dashboard screen and its two narrow
  forecast adapters; one obsolete displayed-location field and its fan-out
  branch were deleted.
- Tests: `+36/-9` lines in focused mounted regressions covering one render on
  uncached completion, summary-only map delivery, no hourly rebuild on cached
  resume, preserved selection, and one daily rebuild for one resize.
- Audit tooling and dependencies: unchanged from Slice A.
- Public API, provider calls, cache lifetime, stale-result safeguards,
  point-warning behavior, responsive layout, and visible interaction behavior:
  unchanged.

The three focused mounted regressions pass, as does a one-pass structural
matrix after the final hourly coalescing change. `compileall` and
`git diff --check` also pass. No live provider, interactive terminal, colour,
font, emoji, or manual mouse check was performed.

### Slice C — world map and saved-location integration

Slice C retained `WorldLocationsMap` as the shared map/callout owner and kept
`DashboardWorldMap` as its interaction-specific subclass. The existing
projected-land and bounded frame caches were already correctly reused; no new
map cache, projection layer, or generic screen abstraction was warranted.

The measured redundant work was removed at the existing input boundaries:

- `WorldLocationsMap.set_locations()` snapshots the mutable location values
  and rendered summary values it last received. Identical resume input now
  updates stored references without synchronizing widgets or planning
  callouts. A narrow `force` option is used only by Dashboard appearance
  refresh so theme-sensitive labels and the land backdrop are still rebuilt.
- Active location, selected location, selected tropical system, and canonical
  tropical-system setters now return when their effective key or ordered input
  is unchanged. Actual place selection still reapplies selection classes, and
  active/storm changes still reflow because they change callout priority.
- Individual weather-summary delivery updates its label but schedules a map
  reflow only when the rendered cell width changes. Temperature-unit changes
  use the same rule. The callout planner depends on width and position, not
  text colour or the numeric value itself.
- A map now ignores summaries for locations outside its owned location set.
  Previously, the active Weather location could enter the Dashboard map's
  internal summary dictionary even when it was not saved; the first resume
  then removed that stray entry and falsely treated the map as changed.
- Remount initialization now preserves already-retained labels and frames.
  Missing labels or a missing frame still take the normal initialization path;
  resize and forced appearance refresh remain authoritative invalidations.

The benchmark added explicit selection-only and appearance-refresh scenarios
plus a label-state counter. In the comparable one-warm-up/three-sample pass,
cached resume and five Weather/Dashboard cycles performed zero location-label
synchronizations, selection-state applications, or world reflows. The Slice A
baseline performed one label synchronization and reflow per resume/cycle.
Three same-width summary updates now cross no counted forecast or map boundary,
down from one forecast/hourly rebuild in Slice A and one remaining world reflow
after Slice B. Two real selection changes perform exactly two class-state
applications and no reflow. Appearance refresh deliberately performs one label
synchronization, one state application, and one reflow; four real resizes still
perform four reflows.

Indicative medians were 1,598 ms for cold entry, 409 ms for cached resume,
43 ms for three summary updates, 39 ms for two selection-only changes, 126 ms
for appearance refresh, and 2,419 ms for five navigation cycles. Resume and
cycle medians were below Slice B's 466 ms and 2,788 ms observations, while the
resize burst varied upward. Structural counts remain the claimed result.

#### Slice C accounting and verification

- Production: `+86/-11` lines across the shared world map, Dashboard subclass,
  and one forced appearance-refresh call. Most additions are small input-state
  snapshots and guards; no new owner or dependency was introduced.
- Tests: `+100/-17` lines across the mounted Dashboard and world-map suites,
  covering unchanged resume, same-width and width-changing summaries,
  non-owned summary rejection, selection preservation, and forced appearance
  refresh.
- Audit tooling: `+27/-0` lines for the selection/appearance scenarios and
  label-state counter.
- Public API, provider requests, application summary cache, saved-location
  ordering, map projection, callout policy, resize behavior, focus behavior,
  visual output, and specialist-screen ownership: unchanged.

Five focused mounted regressions, all nine shared world-map tests, and the
final three-sample Dashboard matrix pass. `compileall` and `git diff --check`
also pass. No live provider, interactive terminal, colour, font, emoji, or
manual mouse check was performed.

### Slice D — tropical detail and workspace integration

Slice D retained the intentionally different screen coordinators. `Wevva`
continues to own the canonical-system and issued-observation product caches;
the Dashboard and Tropical Systems workspace continue to share
`LargeTropicalStormTrackScope`, product-tab specifications, forecast summary,
and product widget construction. Their remaining selection and loading state
has different ownership and refresh behavior, so moving it behind a common
controller would add indirection without deleting either lifecycle.

Two bounded production changes were supported by the audit:

- The empty `DashboardWorldMap.set_tropical_loading()` and
  `set_tropical_error()` hooks and their callers were deleted. Discovery and
  errors are owned visibly by the lower tropical detail panel; the world map
  retains its existing geography while work is pending.
- `DashboardTropicalPanel` now remembers its last overview/error state and
  skips an identical state application. Warm Dashboard resume no longer
  rebuilds the unchanged prompt. Entering a selected system explicitly leaves
  that overview state, so real selection and later empty/error states still
  render normally.

The audit harness now distinguishes application-cache hits from calls through
the application loader and counts overview-state and product-body rendering.
It adds fresh reselection, product-tab change, and Dashboard/Tropical workspace
round-trip scenarios. The comparable pass used the same CPython 3.13.0,
Textual 8.0.0, macOS x86_64 environment as the earlier slices, with one
discarded warm-up and three samples:

| Tropical scenario | Local time | Structural result |
|---|---:|---|
| initial storm/product selection | 420 [381–460] ms | one provider product request, one system application, two track updates, one selection-state application and one world reflow |
| fresh cached reselection | 26 [26–57] ms | no counted work |
| product-tab change | 131 [112–160] ms | exactly one product render |
| Dashboard/Tropical round trip | 959 [926–1,178] ms | no provider product request; two track updates plus ordinary Dashboard resume reconciliation |

The two initial and round-trip track updates are required source-first and
cached-product-enriched presentations, not duplicate provider or geometry
work. The round trip reuses the exact app-owned issued-observation product
entry. The existing resize matrix likewise retains its stable widget tree,
active source/product tabs, and cached responses across compact and split
topologies without new provider calls.

Mounted regressions now cover cold discovery status, exact source/product
selection, fresh reselection, rapid replacement, successful stale refresh,
failed stale refresh, and warm Dashboard return. A failed stale refresh leaves
the prior reader, title, tabs, map selection, and products visible and clears
both loading indicators. Focused specialist checks cover lazy application
product caching, retained source/product selection, native discovery/product
loading states, responsive topology changes, and in-place refresh.

#### Slice D negative findings and accounting

1. No additional obsolete tropical path was found after removing the two
   empty overlay hooks.
2. Fresh reselection already uses zero new tasks, cache reads that reach a
   provider, tab rebuilds, or map work; its existing identity guard should be
   retained.
3. Source-first then product-enriched track rendering is useful feedback while
   lazy products load and does not issue duplicate provider work.
4. Sharing screen-level selection, loading, or task state would combine unlike
   lifecycles. The existing shared track widget and pure product helpers remain
   the smaller integration boundary.

- Production: `+12/-9` lines across the Dashboard panel/coordinator and world
  map. No application cache or specialist-screen production code changed.
- Tests: `+130/-1` lines in mounted Dashboard regressions, including discovery
  and failed stale-refresh coverage plus the unchanged-return assertion.
- Audit tooling: `+68/-2` lines for cache-aware fixture loading, three focused
  scenarios, and two presentation counters.
- Dependencies, public API, cache TTL/key semantics, cancellation and stale-
  result guards, visual interaction, and provider behavior: unchanged.
- Task 0031 viewport projection and framing: untouched.

Six focused Dashboard regressions, seven specialist workspace/cache/layout
checks, the one-warm-up/three-sample Dashboard matrix, `compileall`, and
`git diff --check` pass. No live provider, interactive terminal, colour, font,
emoji, Braille-glyph, or manual mouse check was performed.
