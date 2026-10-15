# Task 0025: Screen-by-screen performance audit

## Status

In progress — Slice A baseline and audit harness complete on 15 October 2026;
production optimisation slices B–G have not started

## Context

Wevva has grown from one forecast view into several persistent, data-rich
Textual workspaces. Each main screen now has a different performance shape:

- startup and search are dominated by application construction, geocoding, and
  the first transition into weather;
- the weather screen coordinates the densest responsive layout and several
  asynchronous enrichment paths;
- the Alerts Centre combines potentially large provider results, filtering,
  document rendering, polygon projection, and settlement forecasts;
- the tropical workspace combines lazy provider products, track geometry, and
  responsive panes; and
- the saved-locations world map combines a global raster, native labels, and
  staggered summary updates.

Useful local optimisations already exist, including forecast and warning
caches, stable mounted widgets, stale-result guards, merged alert layers,
duplicate-polygon rejection, and shared map-callout placement. They were added
for concrete paths rather than from one comparable whole-application audit.

This task provides that audit. It is organized by user-visible screen so each
slice can be measured, changed, verified, and stopped independently.

## Problem

- There is no common baseline for screen entry, warm re-entry, content update,
  resize, selection, or exit.
- Provider and network latency can obscure avoidable local CPU, projection,
  layout, render, and allocation costs.
- Textual invalidation or widget lifecycle work can be repeated without being
  obvious from the final frame.
- Cross-screen caches and background tasks improve responsiveness but can also
  retain stale work, duplicate transformations, or make re-entry behavior hard
  to reason about.
- A broad instruction to “optimise the app” could encourage speculative caches,
  premature abstractions, fragile timing assertions, or rewrites whose cost is
  larger than their benefit.

## Desired outcome

Produce a reproducible performance record for every main screen, identify its
measured local bottlenecks, and make only small optimisations supported by that
evidence. Each slice records:

1. the scenarios and fixtures measured;
2. deterministic work counts where they are available;
3. indicative before/after timings and memory observations on the same machine;
4. the change made, or an explicit finding that no worthwhile change exists;
5. opportunities to delete or consolidate production code while preserving
   behavior; and
6. the functional and lifecycle checks which remained green.

The final application should perform less redundant work during ordinary use
and should be simpler where the same behavior can be expressed with less code,
state, and custom machinery. It must not change its visual design, provider
semantics, public API, or responsive behavior. This is an audit with bounded
fixes, not a performance framework or a promise of universal latency on every
machine and live service.

## Coordination with other tasks

- Task 0021 owns denser alert-map context, its data/query design, and
  scale-adaptive label density. Task 0025 may measure those paths once present
  but must not implement that feature.
- Task 0024 owns interactive alert-map viewport controls, scale rendering, and
  performance specifically caused by repeated navigation. Task 0025 owns the
  existing Alerts Centre entry, loading, filtering, selection, and transition
  audit. If 0024 is implemented first, its navigation benchmark remains in
  0024 rather than being duplicated here.
- Task 0023's shared callout planner is complete. This task may profile its
  callers but must not replace the planner with a general map engine.
- Any finding already owned by another active task is recorded and handed to
  that task rather than fixed twice.

## Scope

- Application startup and the main Search, Weather, Alerts Centre, Tropical
  Systems, and World Locations screen paths.
- Services, widgets, caches, projections, formatters, and background-task
  lifecycle when exercised by those screen paths.
- Cold entry, warm re-entry, representative content updates, selection changes,
  resize bursts, and exit/return transitions.
- Standard-library profiling and measurement tools, Textual mounted tests, and
  small deterministic benchmark fixtures.
- Removing repeated calculation, rendering, parsing, projection, sorting,
  mounting, query work, or obsolete async work where measurement establishes a
  useful benefit.
- A screen-by-screen complexity and deletion audit covering duplicated paths,
  obsolete fallbacks, redundant state, unnecessary custom machinery, and
  abstractions which cost more than the duplication they replace.
- Small cache or indexing changes only when ownership, invalidation, size, and
  stale-result behavior can be stated and tested clearly.
- Reporting production and test-code changes separately for each slice so a
  runtime reduction is not hidden by necessary regression coverage.
- Documentation of negative findings where the current implementation is
  already proportionate.

## Non-goals

- Visual redesign, new features, new provider data, or behavior changes.
- Replacing Textual, changing public Python API contracts, or reorganizing the
  application around a new domain/framework layer.
- A generic rendering engine, generic map framework, event bus, or universal
  cache abstraction.
- Optimising live-provider response time which Wevva does not control.
- Adding third-party profilers or telemetry to the runtime package.
- Persistent analytics, background reporting, or collection of user data.
- Fragile wall-clock assertions in the regression suite.
- Micro-optimising simple code without repeatable evidence of meaningful work.
- Combining unrelated cleanup, formatting, typing, dependency upgrades, or
  feature-task implementation with an optimisation slice.
- Treating lower source-line count, fewer function calls, or greater cache use
  as an improvement without an observed user-path benefit.
- Code golf, compressed formatting, weakened names, merged responsibilities, or
  removed safeguards merely to improve a line-count total.
- Removing user-visible behavior during this audit. A disproportionately costly
  low-value feature may be documented as a candidate, but dropping it requires
  a separate explicit decision.

## Measurement contract

### Separate waiting from local work

Use deterministic fake loaders for comparative screen measurements. Record live
requests only as optional observations and separate provider wait from the
local work before, between, and after callbacks. Do not claim an application
optimisation from a faster network sample.

### Prefer structural evidence

Instrument expensive boundaries where possible: loader invocations, worker
creation/cancellation, layout passes, widget mounts, raster/projection calls,
candidate counts, formatting/table rebuilds, and cache hits. Tests should
assert these bounded counts or state transitions rather than elapsed time.

Use `time.perf_counter()`, `cProfile`, and `tracemalloc` for investigation when
useful. Run warmups and repeated samples, report a median or range, and record
Python, Textual, terminal dimensions, fixture size, machine, and whether the
path was cold or warm. Indicative timings belong in the task handoff, not as
portable pass/fail thresholds.

### Optimisation threshold

Make a production change only when at least one of the following is true:

- a repeatable profile identifies a material hot path;
- deterministic instrumentation proves duplicated or obsolete expensive work;
- a user-visible pause or input backlog maps to a bounded local cause; or
- the change removes retained tasks/data or unbounded growth with a clear
  lifecycle benefit.

Every optimisation must remain smaller and easier to reason about than the work
it removes. A slice may correctly end with measurements and no code change.

### Complexity and deletion contract

Treat implementation simplicity as another form of efficiency. Every screen
slice must answer these questions explicitly:

1. Can duplicated, obsolete, or unreachable paths be deleted?
2. Can the same behavior use fewer states, workers, caches, adapters, or custom
   widgets?
3. Is a low-value edge feature responsible for disproportionate implementation
   or lifecycle complexity?
4. Did production code decrease, remain neutral, or grow, and was that result
   justified by the measured user-path benefit?

Prefer deletion and direct code over adding a cache, abstraction, or parallel
fast path when both solve the measured problem. New shared code must replace
enough existing machinery to reduce total conceptual complexity; do not leave
the old implementations alongside it.

Capture the touched production and test line counts at the beginning and end of
each slice and report them separately. These counts are diagnostic rather than
targets: do not compress formatting, combine responsibilities, weaken tests, or
remove defensive behavior to manufacture a reduction. There is no blanket
“50% fewer lines” acceptance threshold.

When an apparently small feature owns a large amount of code, record exactly
which behavior, safeguards, and tests it entails. Preserve it during Task 0025;
any proposal to trade that behavior for a materially simpler application needs
an explicit follow-up decision rather than being hidden inside optimisation.

### Preserve representative fixtures

Cover compact `80x24` and representative wider/taller layouts. Use ordinary and
stress fixtures—for example 24 hourly columns, several alerts, a large US alert
collection, multiple tropical observations/products, and many saved locations—
without presenting the stress case as typical usage.

## Implementation slices

### Slice A — baseline and audit harness

- Define a small scenario matrix and common reporting format for cold entry,
  warm re-entry, update, selection, resize burst, and exit.
- Add only the fixture helpers or separately runnable benchmark tooling needed
  to compare paths consistently. Keep audit instrumentation out of production
  runtime unless it is an inexpensive generally useful boundary.
- Capture a pre-change baseline for every later slice before optimising any of
  them.
- Add the four complexity/deletion questions and separate production/test code
  counts to the common slice report.
- Identify shared expensive boundaries, but defer extraction or caching until
  a screen slice demonstrates the need.

### Slice B — startup and Search screen

- Measure application construction and mount with and without an initial
  location, opening/closing Search, typing and replacing result sets, and
  selecting a place.
- Separate import/application setup, local result rendering, geocoder wait, and
  the handoff into the first weather refresh.
- Inspect result-widget churn, obsolete search tasks, repeated place conversion,
  and duplicate startup work.
- Audit whether startup/search state, task ownership, and conversion paths can
  be reduced or consolidated without changing the two startup modes.
- Preserve request cancellation, keyboard/mouse selection, CLI-provided
  location behavior, and the no-location startup path.

### Slice C — Weather screen

- Measure cold and cached forecast application, `WeatherUpdated`, alert progress
  and completion, hourly/day selection, one-second time updates, location-map
  temperature enrichment, and representative resize bursts.
- Inspect repeated layout-budget calculation, unnecessary widget refresh or
  table reconstruction, formatting of unchanged models, map reflow, sidebar
  updates, and background warning coordination.
- Audit duplicated presentation branches, reactive state, timers, workers, and
  cache handoffs for deletion or simpler ownership.
- Preserve the stable-widget responsive design, forecast/warning cache
  contracts, explicit-refresh behavior, stale-generation safeguards, and the
  complete `80x24` presentation.
- Confirm that layout, selection, and timer paths do not introduce network or
  packaged-resource work.

### Slice D — Alerts Centre

- Measure first open, warm `w → g → w → g` re-entry, country load/progress,
  country switch, filter/sort application, alert selection, detail rendering,
  settlement selection, hourly expansion, resize, and return to Weather.
- Separate provider retrieval and per-alert enrichment from local ordering,
  identity tracking, list construction, polygon projection/rasterization,
  callout placement, and document formatting.
- Use both shared-zone and mostly-unique-polygon fixtures, including a large US
  collection. Verify that coalesced layers and duplicate-polygon rejection stay
  effective.
- Audit list/filter/modal duplication, selection state, progress state, map
  intermediates, and country/hourly task ownership for simplification.
- Preserve progress semantics, current-country state, `NEW` snapshots, selected
  list highlighting, stale-request protection, geometry truth, and hourly
  forecast lifecycle.
- Hand navigation-specific work to Task 0024 and detail-source/query work to
  Task 0021.

### Slice E — Tropical Systems screen

- Measure cold and cached open, system/source/product tab changes, lazy product
  loading, observation selection, track/cone rendering, centre-weather loading,
  resize bursts, refresh, and return to Weather.
- Inspect repeated canonical-group ordering, summary/document rebuilding,
  geometry projection, label placement, and stale product/centre-weather work.
- Audit the three-level selection state, loader/task ownership, and responsive
  presentation branches for equivalent behavior through less machinery.
- Preserve untouched source observations, lazy product cache identity,
  classification ordering, source attribution, provider geometry, compact
  layout behavior, and refresh semantics.

### Slice F — World Locations screen

- Measure cold and repeated open, initial focus, keyboard/mouse movement,
  staggered summary updates, resize bursts, location activation, and return to
  Weather across small and stress-sized saved-location sets.
- Inspect global-raster reuse, repeated projection/collision work, label-widget
  churn, summary formatting, and interactions with app-owned saved-weather
  tasks.
- Audit whether map/screen state and summary propagation duplicate ownership
  already present in the application.
- Preserve stable focus, deterministic placement, current-location styling,
  late summary delivery, and the ordinary weather refresh after activation.

### Slice G — cross-screen lifecycle and consolidation

- Exercise repeated Weather/Search, `w/g/w`, `w/t/w`, and `w/m/w` transitions,
  including transitions while loaders are pending and after cache expiry.
- Check timers, workers, retained screen references, cache growth, stale
  callbacks, focus restoration, and memory after repeated entry/exit cycles.
- Move a fix into shared code only when at least two completed screen slices
  demonstrate the same expensive operation and the extraction reduces total
  complexity.
- Review the completed per-screen deletion findings together. Remove newly
  proven shared duplication, but do not force unlike screen lifecycles through
  one abstraction merely to reduce their individual line counts.
- Compare the final scenario matrix with Slice A, record gains and negative
  findings, run the complete suite, and leave unrelated opportunities as named
  follow-up tasks rather than widening this one.

## Acceptance criteria

- Every main screen has a recorded cold/warm scenario baseline and a completed
  screen-specific audit, even when no production change is justified.
- Every screen slice answers the four complexity/deletion questions and reports
  touched production and test-code changes separately.
- Each production optimisation names the measured bottleneck, reports
  comparable before/after evidence, and has deterministic regression coverage
  for its work or lifecycle invariant.
- Provider wait is reported separately from local screen work; no result claims
  to improve an external service.
- Repeated screen transitions leave no growing set of obsolete tasks, timers,
  mounted widgets, cached entries outside documented bounds, or stale callbacks.
- Resize and selection bursts do not accumulate unbounded obsolete work.
- Existing caches retain their documented keys, expiry, refresh bypass, and
  stale-generation behavior unless a tested change is explicitly justified.
- No resize, focus, filter, tab, or selection-only path adds network access or
  reloads packaged geographic data.
- Responsive layouts, focus, selection, colours, provider documents, warning
  progress, geometry, and compact-mode behavior remain unchanged.
- Public sync/async APIs and CLI behavior remain compatible.
- Production-code growth is justified by a measured benefit; code reductions
  preserve named behavior and safeguards rather than relying on compression or
  weaker coverage.
- No user-visible feature is removed without a separate explicit decision.
- The final handoff distinguishes production improvements, measurement-only
  findings, simplifications, disproportionately costly feature candidates,
  external/provider limits, and deferred opportunities.
- Audit support code remains small and runnable; runtime telemetry and fragile
  timing assertions are absent.

## Relevant code

- `wevva/app.py`
- `wevva/controller.py`
- `wevva/screens/search_screen.py`
- `wevva/screens/weather_screen.py`
- `wevva/screens/alerts_centre_screen.py`
- `wevva/screens/tropical_systems_screen.py`
- `wevva/screens/world_locations_screen.py`
- `wevva/services/`
- `wevva/widgets/`
- `wevva/layout.py`
- `wevva/tropical_layout.py`
- `wevva/alerts_centre_layout.py`
- `wevva/geography.py`
- `tests/`
- `tools/`
- `docs/architecture.md`
- Tasks 0021, 0023, and 0024

## Verification

Run focused tests after each slice and the complete suite at the end:

```bash
uv run python -m compileall -q wevva
uv run python -m unittest tests.test_responsive_weather_screen
uv run python -m unittest tests.test_warning_cache tests.test_warning_textual_smoke
uv run python -m unittest tests.test_alerts_centre_service tests.test_alerts_centre_screen
uv run python -m unittest tests.test_alerts_centre_map tests.test_alerts_centre_integration
uv run python -m unittest tests.test_tropical_systems_screen tests.test_tropical_track
uv run python -m unittest tests.test_world_locations_map
uv run python -m unittest discover -s tests
```

Run deterministic benchmark scenarios before and after each production change
on the same machine and environment. Manually inspect `80x24` and at least one
wide layout for screen entry, repeated transitions, rapid resize, focus,
keyboard/mouse activation, pending-loader exit, and warm re-entry. Live-service
checks are optional and must be labelled as such.

## Decisions and notes

- Screen slices are the unit of delivery and may be completed independently
  after Slice A.
- Performance and simplicity are co-equal audit dimensions. Neither elapsed
  time nor source-line count is sufficient evidence by itself.
- Services and widgets are audited inside the screen path which owns their
  user-visible cost; this task does not create separate open-ended “backend” or
  “widget” cleanup slices.
- Search is included with startup because its critical path ends at the first
  Weather screen refresh.
- Help, settings, author, air-quality help, and alert-detail modals are inspected
  only through their owning screen or the final lifecycle slice unless evidence
  justifies a separate follow-up.
- Optimisation work stops when remaining time is provider wait, ordinary
  Textual cost, below repeatable measurement, or requires a disproportionate
  architectural rewrite.

## Outcome

### Slice A — baseline and audit harness

Slice A adds one checkout-only script, `tools/benchmark_screens.py`. It mounts
the real screens with Textual's test driver, reuses existing deterministic test
fixtures, substitutes immediate provider loaders, and emits JSON containing
median/range timings plus optional Python allocation peaks. It does not add
runtime telemetry, a dependency, a portable timing assertion, or production
code.

Run the timing baseline from the repository root:

```bash
UV_CACHE_DIR=/tmp/wevva-uv-cache uv run python tools/benchmark_screens.py
```

The default is one discarded complete warm-up followed by three recorded
runs. The script clears Wevva's packaged-geography and projection caches before
each run so that `cold_entry` consistently means the first screen mount in a
fresh application session. It does not attempt to clear Textual's internal
class or stylesheet caches. Import time and interpreter startup remain outside
the screen numbers and belong to Slice B.

Observe per-scenario Python allocation peaks separately; the traced timings
are intentionally not used as latency baselines:

```bash
UV_CACHE_DIR=/tmp/wevva-uv-cache uv run python tools/benchmark_screens.py \
  --warmup 0 --repeat 1 --tracemalloc
```

For investigation rather than routine comparison, wrap one non-warm-up run in
`cProfile`:

```bash
UV_CACHE_DIR=/tmp/wevva-uv-cache uv run python -m cProfile \
  -o /tmp/wevva-screen-baseline.prof \
  tools/benchmark_screens.py --warmup 0 --repeat 1
```

#### Common scenario matrix

Each later screen slice should select the applicable cells below, use the same
ordinary fixture before adding a clearly labelled stress fixture, and keep
provider wait outside the recorded local interval.

| Path | Cold entry | Warm re-entry | Local update | Selection | Resize burst | Exit/return |
|---|---|---|---|---|---|---|
| Startup/Search | construct with no location, mount initial modal | open a fresh second modal | 10 results; replace 100 with 10 | one-result Enter and list activation | `80x24 → 140x45 → 100x30 → 180x55` | dismiss; separately measure first-Weather handoff |
| Weather | mount stable empty screen, then apply the 72-hour bundle | return to the persistent screen; cached forecast apply | forecast, warning completion, one-second display tick, saved-summary delivery | hour and day | same four-size burst | leave/return with and without background work |
| Alerts Centre | first installed-screen open and six-alert local load | resume the same installed screen | progress, filter/sort, country result and hourly result | alert and settlement | same four-size burst | return to Weather, including pending loaders |
| Tropical Systems | fresh screen with two systems/three observations | fresh screen backed by application caches | systems, products and centre weather | system, source and product | same four-size burst | return to Weather, including pending loaders |
| World Locations | fresh screen with three locations | fresh reconstruction from in-memory summaries | staggered summary delivery | eight-step focus burst and activation | same four-size burst | return to Weather |

Stress additions for their owning slices are 100 search results, repeated
Weather updates and richer warning states, shared-zone and mostly-unique large
alert sets, multiple tropical products/geometries, and many saved locations.
Slice A does not present those stress sizes as ordinary use. Task 0024
continues to own
repeated alert-map navigation, and Task 0021 continues to own denser alert-map
context/query work.

#### Common slice report

Every later slice should add one compact record with:

1. checkout revision and dirty-state note; Python, Textual, platform and
   terminal sizes;
2. fixture sizes, cold/warm state, warm-up/sample counts and excluded provider
   wait;
3. median and range for local wall time, an optional separately traced peak
   allocation, and deterministic work counts at the expensive boundaries;
4. the measured hotspot or an explicit negative finding;
5. before/after results on the same machine when production changed;
6. answers to the four deletion/complexity questions below;
7. separate production, test, audit-tool and documentation line deltas; and
8. focused lifecycle checks, full-suite result, manual terminal checks, and
   anything not exercised.

No wall-clock value becomes a test threshold.

#### Recorded environment and fixtures

The baseline was captured from the working tree at `884cc7b` plus the existing
uncommitted Task 0021/0024 Alerts Centre work. That dirty-state note matters:
later comparisons must use the same code or explicitly record the intervening
change.

- CPython 3.13.0, Textual 8.0.0.
- macOS 26.7.1, `x86_64` execution environment.
- Terminal sizes: `80x24`, `100x30`, `140x45`, and `180x55`.
- One complete warm-up, then three timing samples.
- Provider wait: excluded. All forecast, warning, product, centre-weather, and
  temperature loaders used immediate deterministic fixtures.
- Ordinary fixtures: 10 search results; 72 hourly and 7 daily points with two
  warnings; six alerts sharing two provider polygons; two tropical systems
  containing three source observations; and three saved locations.
- Each resize burst contains four terminal sizes. Textual settling, layout,
  styling, compositing, and render work is included.
- Application construction itself was small once imports were present: no
  location 4.6 ms [3.9–5.2], with a location and three saved locations 3.9 ms
  [3.4–4.4]. Fresh-interpreter import cost remains for Slice B.

#### Pre-change timing and allocation baseline

Times are milliseconds and show `median [minimum–maximum]`. They are
comparative mounted-test observations, not promises for an interactive
terminal. Allocation is the largest relevant per-scenario Python peak from a
separate single `tracemalloc` pass without warm-up; it is not retained memory.

| Screen/path | Cold entry | Warm re-entry | Representative update/selection | Four-resize burst | Exit/return | Peak allocation observation |
|---|---:|---:|---:|---:|---:|---:|
| Search | 99 [95–108] | 75 [74–79] fresh modal | 10 results: 24 [23–25]; 100→10: 26 [25–27] | 253 [240–334] | 14 [13–14] | cold entry 2.2 MiB; 100→10 replacement 0.1 MiB |
| Weather | 353 [349–358] | persistent return is included in the workspace exits below | 72-hour forecast apply: 2,287 [2,231–2,398] | 1,958 [1,950–1,994] | workspace-return medians 252–268 | forecast apply 29.8 MiB |
| Alerts Centre | 1,231 [936–1,327] | 208 [208–209] persistent resume | alert selection: 396 [381–416] | 3,154 [3,096–3,241] | 252 [245–277] | cold entry 26.3 MiB; selection 14.2 MiB; warm resume 0.5 MiB |
| Tropical Systems | 758 [752–965] | 475 [462–496] cached data/new screen | source selection: 408 [405–459] | 2,128 [2,126–2,194] | 268 [260–271] | cold entry 17.5 MiB; warm re-entry 9.8 MiB |
| World Locations | 709 [695–722] | 536 [523–554] fresh screen | eight focus moves: 84 [48–87] | 1,923 [1,908–2,253] | 256 [254–275] | cold entry 18.4 MiB; warm re-entry 8.1 MiB |

The warm Alerts result is a useful negative finding: retaining the installed
screen avoids nearly all first-entry allocation and most first-entry time.
Tropical and World warm paths still construct fresh screen/widget trees, so
their in-memory data caches do not remove presentation construction.

#### Profiled local hotspots and negative findings

The one-run `cProfile` investigation deliberately uses no provider work. Its
absolute times include profiler overhead; call counts and relative ownership
are the useful evidence.

- Textual invalidation is the broadest cost: stylesheet application accounted
  for 9.34 s cumulative, render/compositor work 10.99 s, and layout refresh
  12.73 s in the profiled complete scenario set. Later slices should reduce
  application-triggered invalidation, not attempt to optimise Textual itself.
- Geographic raster filling is the clearest production hotspot:
  `GeographicCanvas.fill_polygons()` ran 58 times for 3.08 s cumulative and
  `_filled_ring()` handled 10,005 rings for 3.02 s.
- World-map reflow ran six times for 2.49 s cumulative; building its frames
  consumed 2.19 s. Eight focus changes took only about 50 ms unprofiled, so
  selection is not the World screen's problem.
- Tropical visible-world projection ran five times for 2.00 s; track reflow
  ran eight times for 1.29 s. Source selection is expensive because it changes
  track geometry and presentation, not because it waits for products.
- Alerts map reflow ran six times for 1.77 s and raster rendering ran six times
  for 1.31 s. Alert selection itself rebuilds the focused geometry by design;
  later work must preserve geometry truth and Task 0021/0024 boundaries.
- `WeatherScreen._apply_layout()` ran 103 times for 1.17 s cumulative, while
  the 98 pure `weather_layout_for()` calls together took about 10 ms. The
  candidate is repeated application/style work, not the pure allocator.
- Packaged-resource parsing was bounded and cached: map-unit parsing took about
  51 ms, dense populated-place parsing about 108 ms, and neither appeared on
  selection-only paths. No new resource cache is justified by Slice A.
- Search result reconstruction was small (about 26 ms unprofiled for the
  100→10 replacement), and the one-second Weather time updates totalled about
  119 ms across 40 profiled callbacks. Neither is currently a material hotspot.
- Shared callout planning, sorting, filter predicates, and the pure responsive
  allocators did not rank as hotspots. Slice A therefore adds no cache or
  abstraction around them.

#### Complexity overview

The ownership totals below are physical lines in the primary screen-specific
modules named by this task. They exclude shared `app.py`, shared geography,
models, and unrelated tests, so they are scale indicators rather than claims of
exclusive ownership. Branch counts are simple AST counts of `if`, loop,
`try`, and `match` nodes in the screen module.

| Screen | Owned production lines | Primary related test lines | Screen methods / branches / assigned state | Lifecycle shape |
|---|---:|---:|---:|---|
| Search | 485 | 80 | 4 / 2 / 0 | fresh modal; debounce timer and result cache live in `SearchDialog` |
| Weather | 5,577 | 2,696 | 34 / 32 / 33 | one persistent screen, one map task, one one-second timer, many stable child widgets |
| Alerts Centre | 3,064 | 2,176 | 56 / 82 / 48 across two classes | installed persistent screen, country and hourly tasks, generations, filters, selection and caches |
| Tropical Systems | 3,351 | 2,061 | 28 / 107 / 28 | fresh screen, four task-creation sites, three-level selection and several per-screen result maps |
| World Locations | 514 | 277 | 10 / 1 / 4 | fresh screen; deferred reflow and native label ownership live in the map widget |

Alerts and Tropical have the highest state/branch density. Weather has the
largest total presentation footprint and highest observed transient
allocation. World is small in source but expensive per entry because a global
raster is fundamental to the feature. Search is proportionate and lacks a
measured local bottleneck.

#### Deletion and disproportionate-feature audit

These are candidates for later slices, not authorisation to remove behavior.

**Startup/Search**

1. `SearchResultsList.clear_all()` has no in-tree caller and is a deletion
   candidate after checking whether this widget method is treated as an
   external compatibility surface.
2. The current fresh modal, one debounce timer, result mapping, and country
   filter are already a small ownership model; no extra cache is warranted.
3. Country filtering causes full result replacement, but the 100→10 path is
   only about 26 ms, so it is not disproportionately costly.
4. Slice A production/test delta: `+0/+0`; no change is justified yet.

**Weather**

1. The legacy standalone `set_compact()` controls in the location, astronomy,
   and air-quality widgets have no in-tree callers. They are deletion
   candidates only after their standalone compatibility intent is resolved.
2. Repeated layout application is the measured simplification target. Slice C
   should count callback scheduling and unchanged widget/style writes before
   adding memoization or coalescing.
3. The country map and full responsive context matrix are costly auxiliary
   surfaces, but this baseline does not show that either is low value or safe
   to remove. They remain features, not hidden optimisation targets.
4. Slice A production/test delta: `+0/+0`; pure allocator caching would be
   unsupported by the profile.

**Alerts Centre**

1. No unreachable production path is proven. Existing document presentation
   already reuses the Weather alert-details component; do not recreate a
   second shared abstraction.
2. Country/progress, filter/sort, alert, settlement/hourly, responsive-tab, and
   pending-preference state all coexist in one screen. Slice D should first
   count which transitions actually require map/list/document reconstruction;
   the stale-generation and cancellation state is not optional duplication.
3. Settlement hourly expansion is a disproportionate-feature candidate: it
   owns a 301-line widget, dedicated tests, cache/generation/task state, unit
   invalidation, and responsive retained-height behavior. Preserve it during
   this task; simplifying or removing it needs an explicit product decision.
4. Slice A production/test delta: `+0/+0`. Persistent warm re-entry is already
   effective and should not be rewritten.

**Tropical Systems**

1. The apparently TUI-detached nearby-system service helpers are documented
   API compatibility paths and are not deletion candidates merely because the
   dedicated screen does not call them. No unreachable screen branch is
   proven.
2. System/source/product indices, remembered selections, product tasks, centre
   weather tasks, caches, and error maps are the densest ownership area. Slice
   E should test whether equivalent maps can share lifecycle without weakening
   stale-result guards.
3. Centre weather is a disproportionate-feature candidate: a 290-line widget
   plus coordinate-keyed task/cache/error handling supports one auxiliary
   panel. Preserve it unless a separate explicit decision values simplicity
   over that behavior.
4. Slice A production/test delta: `+0/+0`. A general map engine or new shared
   cache is not justified.

**World Locations**

1. No dead path is evident. The screen is deliberately thin and delegates
   label/reflow behavior to one widget.
2. Locations and summaries are copied through application, Weather sidebar,
   screen, and map ownership. Slice F should measure retained references and
   late updates before deciding whether one copy can be removed.
3. The whole separate world-map feature is the strongest explicit
   disproportionate-cost candidate: 514 production lines and 277 related test
   lines support a fresh screen whose three-location cold entry peaks near
   18.4 MiB. Preserve it during Task 0025; removal or replacement needs an
   explicit product decision.
4. Slice A production/test delta: `+0/+0`; focus movement is already cheap, so
   native-label interaction should remain intact.

#### Recommended remaining slice order

1. **Slice B — Startup/Search.** Close the direct mounted-test coverage gap,
   separate interpreter/import/application construction from Search, and
   likely finish with a negative finding or tiny deletion.
2. **Slice C — Weather.** It has the largest allocation peak and evidence of
   repeated layout application; measure stable-widget updates before changing
   any responsive behavior.
3. **Slice F — World Locations.** Its small ownership boundary isolates the
   strongest raster/re-entry hotspot and can establish whether frame reuse is
   safe without inventing shared machinery.
4. **Slice E — Tropical Systems.** Reuse the measurement knowledge from World,
   but require its own evidence for viewport/projection reuse and selection
   lifecycle simplification.
5. **Slice D — Alerts Centre.** It has the largest resize time, but it is also
   the highest-risk state machine and overlaps active Tasks 0021 and 0024.
   Audit it after those paths settle; do not fold navigation or denser-context
   work into Task 0025.
6. **Slice G — cross-screen lifecycle.** Only after two or more completed
   slices prove the same operation should shared consolidation be considered.

This order is evidence-driven rather than severity-driven: the Alerts Centre
is expensive, but changing it while its owning feature tasks are active would
make the baseline incomparable and increase lifecycle risk.

#### Slice A change accounting

- Production: `+0/-0` lines.
- Tests: `+0/-0` lines; no elapsed-time assertion was added.
- Audit tooling: `+423/-0` lines in one separately runnable script; no
  package/runtime import.
- Documentation: `+306/-0` lines relative to the Slice A starting file for this
  recorded baseline and common reporting contract.
- Production optimisations, behavior changes, dependency changes, caches, and
  abstractions: none.

Verification completed on 15 October 2026:

```text
uv run python -m py_compile tools/benchmark_screens.py       passed
uv run python -m compileall -q wevva                        passed
uv run python -m unittest discover -s tests                 314 passed
tools/benchmark_screens.py (1 warm-up + 3 samples)           passed
tools/benchmark_screens.py --warmup 0 --repeat 1 --tracemalloc
                                                               passed
```

The suite emitted asyncio slow-task diagnostics during the mounted Textual
tests but no failures. No live provider, interactive terminal, font, colour,
emoji, or manual mouse check was performed; Slice A makes no claim about those
external/manual conditions.
