# Task 0030: Functional dashboard overview

## Status

Complete — Slices A-F implemented

## Context

Task 0029 established the persistent Dashboard, responsive three-area layout,
application-owned forecast previews, mixed world-map labels, tropical-system
discovery, and the session-owned all-country alert bulletin. Its first release
deliberately treated the Dashboard as a summary and navigation surface.

The reviewed large-terminal layout has enough room to be more useful in place.
The agreed direction is now a functional overview: selecting a place, storm, or
warning should reveal the useful forecast or source detail in the Dashboard,
while the existing Weather, Tropical Systems, and Alerts Centre screens remain
available as complete specialist workspaces.

This is a presentation and composition follow-up. It does not justify a new
data framework, a second cache hierarchy, or eager fetching of every detailed
storm and warning product.

## Problem

The current Dashboard still carries several navigation-first compromises:

- map hover temporarily replaces useful persistent forecast state;
- repeated place activation and alert controls primarily send the user to
  another screen;
- the aspect-capped map leaves useful lower-centre space empty on large
  terminals;
- forecast rows duplicate some standard Weather formatting while omitting the
  Weather screen's current-condition instruments and context tables;
- tropical context is repeated both as a tooltip and as text over the map;
- the alert rail has a fixed preview and open button instead of using the
  selected-alert area requested below the map;
- bulletin deduplication can attach a shared-feed US alert to a territory such
  as American Samoa merely because that catalogue copy won the timestamp/code
  tie; and
- the bulletin does not expose the existing latest-refresh `NEW` information.

Several visual details also work against the intended dense, list-like
dashboard: rounded nested borders, insufficient separation between major
regions, underlined map state, and an overly quick alert-marker pulse.

## Desired outcome

The Dashboard is a fully functional overview at suitable terminal sizes:

- the left rail contains selected-location current, hourly, daily, astronomy,
  location, and air-quality data from one application-owned forecast snapshot;
- the world map remains the dominant surface and hover/focus only highlights
  features;
- a lower central deck shows selected tropical-system and selected-alert
  details side by side, with only data-backed tabs;
- selecting features updates those Dashboard regions without automatically
  opening another screen;
- background bulletin discovery, existing forecast and tropical caches, stale
  result guards, and bounded refresh behavior remain intact; and
- the result stays proportionate to a personal Textual application. Prefer
  direct reuse and small presentation adapters over a generalized dashboard
  framework.

## Scope

### Overall layout and visual separation

- Retain one stable Dashboard widget tree and the existing 120x30 threshold for
  showing the outer forecast/map/alerts regions simultaneously.
- Add one-cell gutters which reveal the stage's existing hatch between the
  forecast rail, centre column, alert rail, world map, and lower detail panes.
  Do not add decorative hatch inside tables or maps.
- Change the centre from one full-height map to a vertical stack when a useful
  detail deck fits: the aspect-aware world map above and a lower row containing
  tropical details on the left and alert details on the right.
- Use the lower row at the 120x30 simultaneous baseline only if both the map and
  the detail panes meet explicit minimum heights. At smaller or unusually short
  sizes, expose the same map/tropical/alert-detail widgets through the existing
  responsive pane tabs rather than mounting duplicates or crushing all four
  surfaces together.
- Derive the map and lower-row heights in `DashboardLayoutBudget`; do not infer
  them from live child sizes or data availability.

### Location forecast rail

- Remove the role line (`Active weather`, `Selected place`, and `Preview`) and
  the `Again opens Weather.` hint.
- Centre a compact `name` plus `country` heading. Do not include administrative
  regions. Fall back to coordinates only when the locality name is absent.
- Reuse `CurrentConditions` for the three standard Temperature,
  Precipitation, and Wind instruments. Hide its fourth detail table in this
  presentation, lay the three instruments out evenly, and override their
  borders only inside the Dashboard. Do not duplicate their formatting logic.
- Remove rounded borders from hourly, daily, and context sections. Separate
  the heading, current instruments, hourly forecast, daily forecast, Sun &
  Moon, Location Data, and Air Quality with consistent one-line top separators
  in one muted colour and without embedded border titles.
- Keep the hourly view vertical and internally scrollable, with no header and
  no day abbreviation. Each row contains:

  ```text
  HH:MM  Cond  <temp><unit>  <chance>%  <speed><unit> <dir> <arrow>
  ```

  Values and their units retain the existing temperature/rain/wind/condition
  colours; inter-column space remains unstyled. Feels-like temperature,
  precipitation amount, and gusts remain in the current instruments rather
  than being repeated in every hourly row. Preserve the space between a wind
  direction label and its arrow.
- Replace the Dashboard-specific daily cell formatting with the standard
  `DailySummaryTable` formatting. At the expanded rail width, give rain chance,
  precipitation amount, wind speed, gust, and direction separate columns with
  explicit inter-column room. Narrower rails retain the standard complete
  compact field groups rather than introducing horizontal scrolling. Keep its
  header hidden and retain only the Dashboard's row-count budget.
- Stack `AstronomyInfo`, `LocationInfo`, and `AirQualityWidget` below daily data
  without borders. Use their existing row-density controls and omit lower-
  priority rows when height is insufficient; do not horizontally scroll them.
- Make `ContextBar` honor its `location_metadata` state rather than always
  reading `app.location`, then give it a small explicit forecast-update entry
  point which its existing `WeatherUpdated` handler and the Dashboard can both
  call. The AQI hour continues to follow the highlighted hourly row.
- Continue to use `dashboard_forecast_snapshot()` and its approximately
  fifteen-minute application cache. No location request starts on hover,
  focus, resize, or a context-table update.

### World-map interaction and presentation

- Show saved-location labels only. A distinct active Weather location can
  remain the default forecast-rail subject, but must not be added to the world
  map merely because it is current or selected.
- Remove underlining from active, selected, focused, and hovered Dashboard map
  labels. Persistent selection and pointer/keyboard focus use reverse styling;
  the active unselected location may remain bold.
- Hover/focus highlights a location label only. It must not change the forecast
  rail or initiate a forecast load.
- Click, Enter, and Space select a location and show/reuse its Dashboard
  forecast. Repeating the action leaves it selected; it does not activate
  Weather. The existing `w` action remains the explicit route to Weather.
- Reserve the selected alert-marker cell during world-callout planning. When a
  place label would cover it, prefer the valid callout on the opposite side of
  that place's own anchor; preserve the planner's ordinary collision fallback
  when neither side fits.

### Tropical systems

- Remove the map's persistent `N active tropical systems`, loading/error
  narration, and the top-left copy of the focused storm context. Empty/loading
  state belongs in the lower tropical pane, not over geographic data.
- Keep a native tooltip on each storm label, formatted only as:

  ```text
  <classification> <name>
  Movement <movement>
  Wind <wind>
  ```

  `Movement` and `Wind` are dim; their values are not. Omit a complete line if
  its value is missing. Do not append source or issue-time text here.
- Keep every Dashboard map storm label and its bullet in the theme accent.
  Remove underline from selected storm labels and use reverse styling.
- Restore the Tropical Systems workspace tab treatment independently: the
  classification is classification/severity-coloured and the name is plain.
  Do not make the shared map formatter control workspace tabs.
- Selecting a storm keeps its exact canonical-system/source-observation anchor
  and populates the lower-left pane. The first tab is Track and Cone, rendered
  by `LargeTropicalStormTrackScope`. Remaining tabs come from the existing
  `_product_tab_specs`/`TropicalProduct` data, such as Forecast, Public
  Advisory, or Forecast Discussion when the provider supplies them.
- Reuse `app.load_tropical_products()` and its per-observation cache and
  in-flight coalescing. A product request starts only after committed storm
  selection, never for every map label or on hover. Use generation checks so a
  late result cannot replace a newer selection.
- Keep one selected source observation; do not merge tracks, cones, products,
  or meteorology from competing issuers.
- When a storm is selected, use its name and the theme accent for the lower
  pane's border title and border. Selecting a relevant city inside its track
  map updates the Dashboard forecast rail without opening Weather.

### Selected alert detail

- Selecting a recent-alert row populates the lower-right pane and retains the
  single world-map alert marker. Remove the rail's fixed preview and `Open
  alert` button. The selected OptionList style is sufficient; remove the
  synthetic leading chevron and its reserved padding.
- The first available detail tab is Map, using `CountryAlertsMap` with the
  selected alert as its sole alert and the alert identity selected. This reuses
  polygon fitting, dateline handling, packaged relevant-city selection, map
  labels, and the existing optional settlement-weather path.
- Add one Alert tab after Map. Reuse the Alerts Centre's complete
  `alert_renderable(..., include_timing=True)` presentation so headline,
  active timing, description, instruction, and any official link read as one
  coherent document rather than separate fragments. Alerts with sparse source
  fields retain the renderer's honest fallback content.
- Alert selection itself requires no new provider request because bulletin
  rows carry the complete cached `Alert`. Settlement current weather remains
  user-triggered and uses `app.load_alert_place_weather()`.
- Use the selected alert's condition and severity colour for the lower pane's
  border title and border. Selecting a relevant city inside its map updates
  the Dashboard forecast rail without opening Weather.
- Escape may clear the selected alert and lower alert pane. Opening Alerts
  Centre remains available through the application's existing explicit
  navigation, not through a duplicate per-row button.

### Bulletin correctness and `NEW` state

- Treat the first successful fetch for an uncached country/language catalogue
  as hidden baseline population, not as a discovery event or bulletin content.
  Store its identities with empty visible and new sets. Only alerts first seen
  on a later successful refresh of that same catalogue enter the bulletin and
  qualify as `NEW`. Once admitted, they remain visible while present in later
  successful catalogues, although their `NEW` state clears on their next
  successful refresh or when a newer non-empty discovery arrives elsewhere.
  Only that latest discovered set retains badges. This prevents an initially
  discovered provider feed from dumping all of its existing warnings into the
  bulletin.
- Distinguish “no successful baseline yet” from “the successful baseline was
  empty.” If the first successful fetch legitimately contains no alerts, a
  warning appearing on the next successful lap is new. Failed or cancelled
  fetches neither establish a baseline nor advance/clear the prior successful
  comparison point.
- Extend a successful `BulletinCatalogue` snapshot with identities absent from
  that coordinator key's previous successful catalogue. Keep this comparison
  at the bulletin boundary: an independent Alerts Centre refresh must not
  consume the bulletin's next-lap discovery state. Hydrate only catalogue
  cache entries still inside `CountryAlertsService`'s fifteen-minute freshness
  window. Fresh hydrated catalogues are valid comparison baselines and begin
  with empty visible and new sets; their next successful live refresh may
  identify additions, but their current alerts never become startup bulletin
  rows. Older provisional/retained entries remain hidden; that country's first
  successful live refresh establishes a hidden baseline, and only later
  additions enter the bulletin.
- Add an immutable `is_new` value to each derived `BulletinAlert`. It reflects
  the latest non-empty bulletin discovery and is replaced globally when a
  newer set arrives, or cleared by that country's next successful refresh. A
  no-change refresh elsewhere does not make the badge disappear immediately.
  It is not a durable unread system and does not add acknowledgement
  persistence.
- Prefix newly fetched feed rows with the Alerts Centre's dark-background-text
  on primary-colour `NEW` badge, without applying that background to the
  remaining condition, country, or time text.
- Correct shared-feed country attribution before row rendering. Move the
  provider-neutral alert search text out of `alerts_centre_screen.py` so both
  the default territory filter and bulletin attribution use the same fields.
  For duplicate identities:

  1. prefer an additional territory whose normalized country name actually
     matches the alert's event/headline/areas/source search text;
  2. otherwise prefer the warning source's declared primary country; and
  3. only then use first-observed time and country code as deterministic
     fallbacks.

  This prevents an ordinary US shared-feed alert from being labelled American
  Samoa while retaining correct attribution for an alert that explicitly
  names American Samoa, Guam, or another shared-feed territory.
- Slow the existing four-phase selection pulse from 0.12 seconds to 0.24
  seconds per phase. It remains finite, cancellable, and timer-free afterward.

## Non-goals

- Replacing or removing the Weather, World Locations, Tropical Systems, or
  Alerts Centre screens.
- Creating generic pane, tab, data-source, caching, or background-job
  frameworks for this one composition.
- Eagerly loading detailed products for every tropical system, city weather
  for every selected alert, or forecasts for hover/focus targets.
- Adding unread counters, acknowledgement state, notification persistence, or
  an expired-alert archive to `NEW`.
- Combining tropical products across sources or inventing fields which the
  provider did not supply.
- Adding another all-country refresh path or widening hard `r` beyond Task
  0029's bounded local countries.
- Rewriting the existing alert polygon renderer, map projection, callout
  planner, forecast models, or colour scales.
- Guaranteeing that every detail pane remains simultaneously visible below the
  established responsive thresholds.

## Relevant code and concrete reuse points

- `wevva/screens/dashboard_screen.py`
  - persistent Dashboard state, forecast selection, alert rail, and layout;
  - remove hover-driven forecast preview and open-button/chevron paths;
  - own lower-pane selection generations, not provider caches.
- `wevva/dashboard_layout.py`
  - extend the pure budget with map/detail heights and context row counts.
- `wevva/widgets/current_conditions.py`, `weather_widget.py`, and
  `precip_info.py`
  - reuse the three standard current-condition instruments with Dashboard-only
    border/layout overrides.
- `wevva/widgets/dashboard_hourly_forecast.py`
  - retain the vertical table; change Rich cell composition and hide headers.
- `wevva/widgets/daily_summary.py`
  - replace duplicate Dashboard daily formatting with the standard combined
    field cells.
- `wevva/widgets/context_bar.py`, `location_info.py`, `astronomy_info.py`, and
  `air_quality.py`
  - reuse the three compact context tables after fixing explicit-location
    input and applying Dashboard-only border/separator styling.
- `wevva/widgets/dashboard_world_map.py` and `map_callouts.py`
  - simplify hover/state styling, remove tropical overlay narration, reserve
    the alert marker during label placement, and retain one projection.
- `wevva/widgets/tropical_track.py`, `widgets/tropical_systems.py`, and
  `screens/tropical_systems_screen.py`
  - reuse the track/cone reader and product rendering while separating map and
    workspace-tab label semantics.
- `wevva/widgets/country_alerts_map.py` and `widgets/weather_alerts.py`
  - reuse selected-alert geometry/cities and promote only the small warning
    timing/text renderers needed by the detail tabs.
- `wevva/services/alert_bulletin.py` and `services/country_alerts.py`
  - attach latest-refresh new identities and fix shared-feed attribution at the
    snapshot boundary.
- `wevva/app.py`
  - retain `dashboard_forecast_snapshot`, forecast preview loading,
    `load_tropical_products`, bulletin ownership, and alert-place weather as the
    only fetch/cache boundaries.
- `tests/test_dashboard_layout.py`, `tests/test_dashboard_screen.py`,
  `tests/test_alert_bulletin.py`, `tests/test_tropical_systems_screen.py`, and
  `tests/test_alerts_centre_map.py`
  - extend the focused deterministic coverage rather than adding a parallel
    integration harness.

## Missing boundaries to add

Only four small boundaries are required before composing the new view:

1. `ContextBar` needs an explicit selected-location/forecast update method;
   its current `_update_display()` incorrectly assigns `self.app.location` even
   though it already stores `location_metadata`.
2. Tropical product tab specs and product-to-renderable conversion currently
   live as private `TropicalSystemsScreen` methods/functions. Promote those two
   presentation helpers so the Dashboard can consume the same products without
   mounting or reaching into a Screen.
3. Warning timing/body renderers and normalized alert search text are private
   to screen/widget implementations. Promote only these pure helpers for the
   selected-alert tabs and shared-feed attribution.
4. Bulletin catalogues need refresh-scoped new identities and a deterministic
   source/territory attribution helper. Keep this inside the bulletin/country-
   alert service boundary; presentation must not guess countries.

No general dashboard data model, pane protocol, repository layer, event bus, or
new cache is warranted.

## Approach and slice dependencies

### Slice A — layout, hatching, and committed-selection behavior

Reshape the centre into the aspect-aware map plus persistent lower detail row,
add hatched gutters, extend the pure responsive budget, and remove hover-driven
forecast changes and repeated-click navigation. Mount honest empty tropical and
alert detail panes. This establishes the final widget ownership and responsive
topology before detailed readers are added.

Depends on Task 0029 only. Later slices depend on this stable composition.

Implemented with one centre-column tree containing the aspect-aware world map
and two persistent detail-panel boundaries. The 120x30 budget assigns 14 map
rows, one hatched gutter, and 11 detail rows; compact presentations expose Map,
Tropical, Selected Alert, and Recent Alerts as distinct tabs over the same
mounted widgets. Place hover/focus is now visual-only, repeated selection stays
in Dashboard, and storm selection records the exact canonical/source anchor
without opening Tropical Systems or loading products. Both detail regions show
selection-aware empty states ready for their later reader slices.

### Slice B — complete location forecast rail

Replace the current summary with the three reused current instruments; revise
hourly Rich cells; replace Dashboard daily formatting with
`DailySummaryTable`; add borderless separated context tables; and fix
`ContextBar`'s explicit-location boundary. Preserve forecast cache and stale-
selection guards.

Depends on Slice A's rail height budgets. It is otherwise independent of the
two lower detail readers.

Implemented by reusing `CurrentConditions`, `DailySummaryTable`, and
`ContextBar` over the selected place's existing application-owned forecast
snapshot. The Dashboard keeps only one custom vertical hourly adapter; its
five Rich cells show full time, condition, temperature, rain chance, and
wind/direction, with units sharing value colour and no repeated feels-like,
amount, or gust fields. It does not expose a horizontal scroll path. The
heading is name plus country only, and hourly selection updates both the
standard current instruments and AQI.
The hourly viewport grows only to its 24 real rows, so daily and context data
follow it directly and surplus height remains below the complete stack.
Expanded rails switch the standard daily table to separate rain, amount, wind,
gust, and direction columns; compact rails keep its combined standard groups.
All inner sections use untitled, consistently coloured top separators.
The pure layout budget omits context cards in compact/medium modes, shows one
row per card at the 120x30 baseline, and expands their existing density at
taller sizes. `ContextBar` now accepts an explicit location, while the Weather
screen continues through the same update boundary.

### Slice C — tropical selection and detail reader

Simplify map storm tooltip/state, separate workspace tab colouring from map
colouring, promote the narrow product presentation helpers, and populate Track
and Cone plus available product tabs through the existing application cache.

Depends on Slice A's lower-left pane and selection ownership. It does not
depend on alert work.

Implemented with a persistent `Track and Cone` tab backed by
`LargeTropicalStormTrackScope` and content-backed official-product tabs. A
committed source observation renders its own geometry immediately, then joins
`Wevva.load_tropical_products()`; Dashboard selection generations prevent late
results from replacing a newer storm. Product-tab selection and safe product
widget conversion now live in one small shared presentation module used by
both Dashboard and Tropical Systems. The world map no longer paints storm
status or focused-tooltip copies over geography, and its native tooltip is
limited to title, movement, and wind. Map labels remain fully accent-coloured,
while Tropical Systems tabs again colour only the classification.

### Slice D — selected-alert reader and rail simplification

Remove preview/open controls and chevron padding, mount the one-alert
`CountryAlertsMap`, and pair it with one complete alert-document tab using the
Alerts Centre renderer.

Depends on Slice A's lower-right pane. It can proceed independently of Slice C.

Implemented with a single-alert `CountryAlertsMap` and one persistent document
body behind Map and Alert tabs. The Alert tab directly reuses the Alerts
Centre's complete headline/timing/provider-prose renderer. Bulletin selection
supplies the complete cached `Alert`; it starts no warning-provider request.
Alert-map city tooltips share one formatter while Dashboard hover weather
remains delayed, cancellable, and loaded through
`Wevva.load_alert_place_weather()`. The rail relies on the native `OptionList`
selection treatment, with no fixed preview, open button, synthetic chevron, or
reserved indentation. Geometry-less warnings retain the honest country-map
fallback and do not acquire invented warning polygons.

### Slice E — bulletin attribution, `NEW`, and map collision polish

Establish an explicit successful-fetch baseline for each country/language
catalogue, attach refresh-scoped new identities only from the second successful
uncached fetch onward, implement source/territory attribution, render `NEW`,
slow the pulse, and reserve the alert marker during world callout placement.
This slice changes existing bulletin/map behavior only after the new
selected-alert presentation is stable.

Depends on Slice D's final alert-row shape. Attribution and `NEW` should first
be covered with service-level tests before visual integration. Those tests must
cover a non-empty first fetch producing no `NEW`, a later added identity
becoming `NEW`, a successfully empty baseline, fresh-catalogue startup, stale
retained data staying hidden, and failed refreshes preserving the last
successful comparison point.

Implemented by storing refresh-scoped new identities and the independently
visible bulletin identities on each immutable `BulletinCatalogue`, then
deriving immutable `BulletinAlert.is_new` rows after country attribution. An
uncached first success always establishes a hidden baseline with empty visible
and new sets; a successfully empty catalogue still establishes that baseline,
failed refreshes retain the prior successful snapshot, and the next unchanged
success clears that country's former `NEW` state without removing still-active
admitted rows. A non-empty discovery also clears older badges from every other
catalogue before marking only its newly arrived identities.
Cross-country duplicates now
prefer an explicitly named additional territory, then the warning source's
primary country, before the existing observation-time/code fallback. Dashboard
rows render only the `NEW` token as dark text on the primary colour, matching
Alerts Centre. Startup hydration now admits only fresh, non-provisional
country catalogues; older retained entries remain hidden and the first live
success replaces them as a hidden baseline. The selected marker cell is
passed through the callout planner's existing preferred-avoidance input, and
its finite four-phase pulse now uses 0.24-second phases.

### Slice F — responsive and combined-view qualification

Exercise the complete layout at 80x24, 100x30, 120x30, 140x40, and a very wide
terminal; verify keyboard order, theme/emoji variants, long units, missing
provider fields, rapid selection, stale product results, geometry-less alerts,
shared US/territory feeds, and empty states. Tune only explicit budgets,
separator density, and tab truncation discovered here.

Depends on Slices B-E. It must not grow into unrelated cleanup or new provider
features.

Completed without changing the production layout budgets. Deterministic
coverage now qualifies the stable widget tree at 80x24, 100x30, 120x30,
140x40, and 250x70; the mounted resize path crosses compact, medium, and wide
presentations while preserving the same five region widgets. It also covers
pane and map-feature keyboard order, honest empty states, supported long unit
labels with separately styled values, and late place-forecast results in
addition to the existing late tropical-product, missing-field,
geometry-less-alert, theme/emoji, and shared-feed cases. The explicit
map/detail minima and separator density remained usable, so qualification did
not justify another breakpoint, tab abstraction, or provider-specific branch.

## Likely risks

- The complete left rail may not fit at 120x30. Row budgets must reduce context
  fields and daily days before shrinking current instruments or making tables
  horizontally scrollable.
- A map that preserves projection aspect can leave too little lower-pane height
  at mid-sized terminals. The pure budget must choose map-only/tabbed fallback,
  not render two unusable half-panes.
- Reusing whole Screens would duplicate bindings, lifecycle, and fetch state.
  Reuse their widgets and pure renderers only.
- Tropical product tasks and forecast preview tasks can finish after selection
  changes. Existing app coalescing prevents duplicate I/O, but Dashboard-level
  generation guards are still required before rendering results.
- `CountryAlertsMap` is designed for a full country collection. Passing only
  the selected alert must be checked for geometry-less alerts and sensible
  relevant-city scope without weakening the full Alerts Centre path.
- Shared warning feeds need semantic attribution, not alphabetical tie breaks.
  Tests must cover both an ordinary continental-US alert and a genuine named
  territory alert so the fix does not simply force every shared identity to
  `US`.
- Rich styling assembled as one string can accidentally colour punctuation and
  units. Hourly cells and `NEW` labels should be constructed from explicit
  `Text.append()` spans.
- An empty alert tuple cannot by itself indicate whether bulletin discovery has
  run successfully. Baseline readiness must be explicit so an uncached first
  fetch and a previously fetched empty provider result are not conflated.
- Hiding borders removes two rows of implicit layout chrome. Separator and
  DataTable heights must be budgeted explicitly to avoid clipped last rows.

## Acceptance criteria

- Large dashboards show hatched gutters and the requested four-region grid:
  forecast rail, map over two centre columns, tropical detail, selected-alert
  detail, and recent-alert rail.
- Responsive layouts retain one widget tree and usable access to all regions;
  no resize or tab switch starts a network request.
- Location hover/focus changes emphasis only. Committed selection updates the
  forecast rail, and repeated selection does not open Weather.
- World-map place callouts are saved locations only; lower tropical/alert map
  city selections also update the rail in place.
- The forecast heading shows centred name and country without admin regions.
- Current conditions use the standard three digit-style instruments without
  borders; hourly, daily, astronomy, location, and AQI sections are borderless
  and separated by untitled lines in one colour.
- Hourly and daily content and styling match the formats specified in Scope,
  including full hourly times, coloured units, spaced wind arrows, and the
  expanded daily table's separate value columns. Zebra rows retain a clear,
  opaque background step.
- The location context and AQI belong to the Dashboard-selected place, not
  accidentally to `app.location`; AQI follows the highlighted hour.
- No tropical status/context prose is painted over the world map. Storm
  tooltips have only the agreed title, movement, and wind lines.
- Dashboard storm labels and bullets use accent; Tropical Systems workspace
  tabs colour classification but leave the name plain.
- A committed storm selection shows track/cone immediately when available and
  lazily reuses cached official products without stale-selection replacement.
- Alert rows have no fixed preview, open button, chevron, or extra selection
  padding. Selection populates Map and one complete Alerts Centre-style Alert
  document tab.
- Selected-alert Map reuses polygon/city behavior and geometry-less alerts
  remain honest rather than acquiring invented geometry.
- Ordinary US shared-feed alerts are labelled United States, while explicitly
  territory-matched alerts retain the correct territory.
- Only identities introduced between a catalogue's last two successful
  snapshots show the primary-colour `NEW` badge, and a later non-empty
  discovery replaces all earlier badges. An uncached first successful
  fetch establishes a hidden baseline and contributes no rows. Only
  still-fresh startup catalogues may act as comparison baselines, and they too
  remain hidden. Older retained catalogues remain hidden, their first live
  replacement becomes the hidden baseline, and only later additions are
  admitted.
- Place labels avoid the selected alert marker when an opposite-side valid
  callout exists.
- The slower marker pulse remains finite and is cancelled on replacement,
  clear, suspension, or unmount.
- Existing full Weather, Tropical Systems, Alerts Centre, bulletin scheduling,
  hard-refresh caps, and application cache behavior remain intact.

## Verification

Use focused tests while implementing each slice, then one combined run at the
end rather than repeatedly running the full suite:

```bash
uv run python -m unittest tests.test_dashboard_layout tests.test_dashboard_screen
uv run python -m unittest tests.test_alert_bulletin tests.test_alerts_centre_map
uv run python -m unittest tests.test_tropical_systems_screen tests.test_forecast_cache
uv run python -m compileall -q wevva
uv run python -m unittest discover -s tests
```

Manual qualification should cover the sizes and cases in Slice F. Live
provider availability, terminal colours/fonts, subjective separator density,
and pulse cadence must not be claimed from deterministic tests alone.

## Decisions and notes

- This task intentionally supersedes Task 0029's navigation-first interaction
  model and its non-goals against a selected-alert map/document in the
  Dashboard. It does not supersede the cache, scheduler, or specialist-screen
  ownership decisions.
- “Fully functional overview” means useful selected-object inspection in place,
  not complete duplication of every control in the owning screens.
- Selection is the only detail-fetch trigger. Hover and focus are visual only.
- Provider-backed tabs are conditional. Empty Public Advisory, Forecast
  Discussion, timing, or instruction placeholders are less useful than simply
  omitting unavailable tabs.
- `NEW` means found by comparison with the previous successful country
  snapshot, not unread by the user and not necessarily newly issued by the
  provider. More precisely, it means absent from that catalogue's last
  successful baseline, present in its latest successful refresh, and part of
  the bulletin's most recent non-empty discovery set. Initial uncached
  population is neither `NEW` nor visible bulletin content.
- Separator lines and stage hatch replace nested rounded boxes. Major outer
  regions may retain their existing frame titles where they aid orientation.
- The implementation target is the useful 95 percent with direct reuse and
  explicit state. Edge cases should fail to honest empty/unavailable content,
  not motivate speculative abstraction.

## Outcome

The Dashboard is now a functional, cache-aware overview rather than a set of
screen shortcuts. Its single responsive widget tree provides the complete
selected-location forecast, an interaction-safe world map, lazy exact-source
tropical details, selected-alert maps and documents, and a correctly
attributed session bulletin with refresh-scoped `NEW` state. Compact terminals
retain each region through ordered pane tabs, and large terminals expose the
combined map/detail composition without duplicating fetch or selection state.
