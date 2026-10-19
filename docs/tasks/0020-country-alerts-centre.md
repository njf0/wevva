# Task 0020: Country alerts centre

## Status

Slices A through G and the post-implementation UI refinements are implemented.
Task 0021 separately owns denser focused-map labels; the Natural Earth context
completed in Slice E remains this task's baseline. Task 0020 is complete.

## Context

The weather screen answers a local question: which warnings apply to the
selected forecast coordinate? Its warning cache and native point-query path are
deliberately optimized for that question. Task 0019 improves the local alert
reader but should remain a modal rather than grow into a country browser.

A separate alerts centre can answer a different question: which active alerts
are available for a country, where are their issued polygons, and what do their
full provider documents say? The application already has most of the visual
primitives: country geometry, ranked Natural Earth cities, compact current
weather formatting, semantic alert colours, full provider prose, and Braille
polygon rendering.

## Problem

- There is no country-level warning discovery surface.
- Local weather alerts omit warnings which do not apply to the selected point,
  so they cannot populate a national list or map.
- Long provider headlines are unsuitable as dense navigation labels.
- The existing `WarningAreaScope` is built around one forecast coordinate and
  one alert; a country overview needs the entire selected country, multiple
  warnings, ranked cities, and an independently selected warning.
- Country selection, alert search, asynchronous loading, caching, and stale
  result protection need an explicit boundary rather than being folded into the
  weather screen.
- Some sources are native point-query providers and may not offer an exhaustive
  national catalogue. The UI must not imply completeness the provider API does
  not supply.

## Desired outcome

A dedicated `Alerts Centre` screen presents a country picker and searchable
alert list on the left, a square-ish country map in the middle, and the selected
alert's complete document on the right. Selecting an alert fits the map to its
real provider geometry, updates the document, and chooses useful settlements
from that focused area. Settlement labels contain names only. Hovering one
shows compact current conditions; activating one opens its complete forecast
on the Weather screen. Returning with `g` restores the Alerts Centre context.

The screen is a persistent workspace, not a modal. It has its own loading,
empty, partial-provider, and error states, while leaving the weather screen's
local alert refresh untouched.

## Wide composition

```text
┌─ Alert navigation ─┬─ Country warning map ─┬─ Selected alert ─┐
│ Country select     │                       │ full provider     │
│ Filter button      │ country outline       │ document          │
│ Sort select        │ warning polygons      │ independently     │
│ severity/event/    │ focused settlements   │ scrollable        │
│ short area list    │ hover weather preview│                    │
│                    │                       │ official link      │
└────────────────────┴──────────────────────┴──────────────────┘
```

The bordered navigation, map, and document regions have two columns of space
between them. The navigation rail is wide enough for its two-line labels, while
the map still receives the remaining width and aims for a square-ish geographic
viewport without forcing the whole page to scroll.

## Responsive topology

Use a pure row/column budget rather than one desktop breakpoint.

- **Wide:** three columns as shown above.
- **Medium:** keep alert navigation on the left; stack map and document in the
  right workspace when enough height exists.
- **80x24:** keep the country picker/filter/list at a restrained left width and
  use native `Map` / `Details` tabs for the right pane, showing one useful peer
  at a time. Selection and scroll state survive tab changes.
- **Below the supported baseline:** collapse to one pane at a time rather than
  clip all three columns or introduce full-page scrolling.

Only the alert list and provider document scroll vertically. The country map
and screen itself do not.

## Country picker and alert search

Use a Textual `Select` populated with supported countries. Its native
type-to-search behavior provides quick keyboard selection without permanently
occupying space with a second country list.

Country choices must come from an authoritative public warning-source coverage
contract, joined to Wevva's ISO country names. Prefer a small
`wevva-warnings` API such as `list_supported_alert_countries()` if projecting
`list_sources(kind='alert')` would miss global/dynamic coverage. Do not hard-code
a second country/provider registry in Wevva.

Default to the active weather location's country when it is supported;
otherwise use the last in-session selection or the first supported option. A
country change cancels or supersedes the prior request and clears no newer
result.

A primary `Filter alerts` button opens a small modal containing the text filter,
a severity filter populated only with severities in the selected country's
loaded alerts, and the `Severity`/`New first` ordering select. Apply/Enter
commits all three, Clear removes the text and severity filters while retaining
the selected ordering, and Cancel/Escape retains the previous values. Search
text across:

- normalized condition/event;
- headline;
- `area_names`;
- provider/source name; and
- urgency/certainty when present.

Filtering never issues a network request. Preserve the selected alert if it
still matches; otherwise clear selection and restore the country overview or
show a clear empty-filter state. Loading a country's alerts likewise leaves the
list unselected until the user chooses a warning; a refresh may preserve a
still-present explicit selection.

## Alert list labels and ordering

Each navigation row is a concise two-line label:

```text
Severe Flood
Northern counties

Moderate Thunderstorm
Accra and Tema
```

- Reuse `alert_condition_name(...)` and semantic severity colour.
- Put bold semantic-colour severity and regular condition on the first line,
  without separator dots.
- Put normalized provider `area_names` on the second line, hard-limit the label
  to 24 characters, and retain rendered-width ellipsis as a second guard.
- Fall back to a provider-supplied display geography/source label when area
  names are absent.
- Never derive a location label by parsing arbitrary warning prose.
- Sort strongest severity first, then the most immediate onset/expiry, then a
  stable condition/area/id tie-breaker.
- Offer `Severity` and `New first` local sort modes in the filter modal. Newly observed identities
  retain their underlying severity order within the latter mode.
- Mark identities added since the preceding successful fresh country/language
  fetch with a compact `NEW` badge on the primary background. Cache hits retain
  that refresh result; the following fresh fetch replaces it.
- Use reverse focus/selection treatment without discarding severity colour.

## Country alert data boundary

Add a dedicated asynchronous service around the public country query, for
example `get_alerts_for_country(..., active_only=True)`. Keep it separate from
the weather screen's `_alert_cache`:

- that cache intentionally contains reusable candidates for later point
  matching and excludes native point-query results;
- the centre needs the broadest country catalogue a provider makes available;
  and
- selecting a country must not affect local warning applicability or refresh
  generations.

Use a separate session-only country cache with an explicit TTL, cancellation,
and country/language generation guards. Persist only the latest successful
identity snapshot per country/language so new alerts can be recognized across
application runs. The first fetch establishes a baseline, failed fetches do not
advance it, and this snapshot is not an alert-content history. Reuse provider
progress callbacks internally without showing per-source counts or producing a
toast per source or document. Filter expired/inactive alerts and deduplicate
through the warning library's public model/query behavior. Do not silently
manufacture national completeness by sampling points.

The current warning-library country contract returns normalized `Alert`
objects, not lightweight summaries. Batch-native providers may satisfy that in
one request, while linked-CAP providers such as Meteoalarm and DWD fetch every
linked document and the Environment Agency fetches each warning-area polygon.
Those requests supply active times, severity, area labels, prose, and map
geometry. Lazy selected-alert retrieval therefore requires a new public
summary/detail contract in `wevva-warnings`; it cannot be deferred solely in
this screen without losing list and map data.

## Country map

Create a separate `CountryAlertsMap`; do not stretch the point-oriented
`WarningAreaScope` into a multi-alert workspace.

The map uses the same layered Textual pattern as the location maps:

- before an alert with polygonal geometry is selected, the complete selected
  country/map-unit land geometry is the Braille base and viewport;
- selecting an alert with valid `Polygon` or `MultiPolygon` geometry fits a new
  viewport around the complete selected geometry with small padding, preserving
  disconnected parts rather than silently choosing one component;
- very small or degenerate bounds receive a deterministic minimum span so the
  projection remains stable and retains useful surrounding context;
- selecting a geometry-less alert falls back to the whole-country viewport;
- non-selected active warning polygons use restrained/dim severity fills or
  outlines where they overlap the active viewport;
- the selected alert polygon uses its full semantic severity colour;
- alerts without polygons remain in the list/document but do not gain inferred
  shapes;
- focused land and alert projections are recomputed from retained source
  geometry, while a terminal resize only refits the established viewport and
  never performs network work;
- ranked settlements are native directional callouts containing only a marker
  and place name, for example `• Berlin` or `Berlin •`;
- labels use normal theme text rather than temperature-derived colour, and the
  selected/focused settlement uses ordinary hover/focus/reverse treatment;
- hovering a settlement requests a compact current-weather preview; mouse
  click, Enter, or Space emits an Alerts-Centre-specific activation message
  which the screen converts into ordinary Weather-screen navigation.

The whole-country fallback remains geographically truthful, including
disconnected map-unit components. An alert-focused view may naturally exclude
remote country components because its explicit purpose is to fit the selected
provider geometry, not to imply that the country itself has changed.

Select settlement candidates again whenever the alert viewport changes. Use the
complete checked-in Natural Earth place set rather than the original four-place
country cap. Rank places inside the selected alert geometry before other places
inside the visible viewport, then use stable Natural Earth rank, population,
and name tie-breakers. Let the responsive budget and collision placement choose
a useful number of visible labels: compact maps remain deliberately sparse,
while a large focused map may admit more than four. If no place lies inside the
warning polygon, nearby visible country settlements may still provide context.
No settlement selection or resize may trigger a batch current-temperature
request.

In an alert-focused viewport, add passive italic Admin-1 context labels for
every Natural Earth state, province, region, canton, or equivalent represented
by the visible detailed settlement points. These labels contain names only—no
marker dots—and use the same rule worldwide without a US-specific county tier.
They are not restricted to areas named by the warning or to regions containing
the selected polygon: nearby visible regions help ground the alert. Place them
before interactive settlement callouts so settlements yield around the context
labels; retain every region label even when an unusually dense viewport forces
overlap. Region labels are context only and are never selectable.

Alert-focused zoom depends only on normalized alert geometry. It therefore
works for any provider today and benefits automatically from later
`wevva-warnings` improvements such as resolving NWS `affectedZones`; it must not
contain provider-specific geometry logic in Wevva.

## Settlement weather preview and navigation

Hovering a visible settlement is a lightweight inspection surface; activating
it navigates to the application's complete Weather screen.

- Lazily request only current conditions after a short hover delay. Do not
  fetch weather for every displayed settlement or in response to resize.
- Render a compact, non-interactive Rich tooltip containing place/region,
  condition, temperature, rain, wind, units, and a full-forecast hint. Loading
  and retryable-unavailable states occupy the same tooltip.
- Cache successful responses briefly by rounded coordinates and temperature,
  wind, and precipitation units. Rapid hover changes use cancellation plus a
  generation guard so an older response cannot update another label.
- Unit changes invalidate the preview cache and reset visible label tooltips;
  theme changes rerender through normal semantic Rich styles.
- Click, Enter, or Space converts the source-neutral settlement into ordinary
  location metadata and opens its full Weather-screen forecast. The persistent
  Alerts Centre retains country, selected alert, filters, map viewport, and
  document state so `g` returns to the same context.
- The preview must not change map allocation or require an additional forecast
  widget. Failure leaves the map, alert list, and document intact.

## Selected alert document

Reuse the alert document presentation from Task 0019:

- authoritative provider prose via `alert_renderable(...)`;
- independent vertical scrolling;
- official-source link;
- selected semantic border/title colour where a frame is used; and
- no nested `Alert Details` border.

Selection from the list updates document and polygon atomically. Preserve the
selected alert by stable `(source, id)` identity across local filtering,
responsive topology changes, and a refresh when it remains present.

## Loading, empty, and failure states

- Before a request, the list region says `Select a country to view alerts`.
  While a country request is active, a centred progress bar replaces the
  list/empty state without transient provider-count text. It is indeterminate
  while fetching a provider's warning catalogue, then shows document/geometry
  completion and a percentage when the provider exposes a measurable total.
- A successful empty result says `No active alerts`, centred in the list area.
- A local text filter with no matches has a distinct `No matching alerts`
  state and does not clear the loaded country data.
- Partial provider failure keeps successful alerts and identifies unavailable
  sources if the public warning API exposes that status.
- Complete failure uses an inline retryable state; it does not navigate away or
  flood notifications.
- Settlement-preview loading/failure stays in its tooltip and cannot replace
  the alert-list progress or error state.
- Alerts without geometry or prose, settlements without current-weather data,
  and documents without official links degrade independently.

## Scope

- Dedicated alerts-centre screen and launcher action.
- Authoritative type-searchable country select.
- Country-level alert fetch/cache/progress path.
- Locally searchable concise alert list.
- Country-wide fallback map with selected-alert geometry fitting and contextual
  multi-alert layers.
- Dynamically ranked, interactive settlement labels without current
  temperatures.
- Cached, stale-safe current-weather tooltips and full Weather-screen
  navigation for settlements.
- Passive Natural Earth Admin-1 labels for every region represented in the
  focused viewport, independent of provider area descriptions.
- Reused full alert document reader.
- Responsive wide, medium, and 80x24 topologies.

## Non-goals

- Replacing the weather screen's point-applicable alerts or warning cache.
- Claiming exhaustive national coverage where a provider exposes point queries
  only.
- Scraping location names from provider prose.
- Inferring warning polygons from area names or unresolved geocodes in the UI
  layer.
- Persistent alert-content history, push notifications, acknowledgement
  workflows, or user-defined alert subscriptions.
- User-controlled map pan/zoom, selectable projections, or custom spatial
  keyboard navigation; viewport changes are driven only by alert selection.
- Hourly/daily forecast tables, air quality, or a persistent weather panel
  inside the Alerts Centre; current conditions exist only in transient
  settlement tooltips.
- Treating a derived area label or settlement as authoritative evidence of an
  alert's applicability; provider geometry remains authoritative.
- New warning providers or provider-specific UI branches.
- Exhaustive local settlement, administrative-area, or physical-feature
  coverage. Task 0021 may replace the focused label candidates with a denser
  offline gazetteer without changing this screen's map or alert contracts.

## Implementation slices

### Slice A — data contract and navigation shell

- Complete: confirmed the existing public `list_sources(kind='alert')` primary
  and additional country metadata exactly describes the countries routed by
  `get_alerts_for_country()`, so no second registry or warning-library change
  is needed.
- Complete: added the isolated async country service, fifteen-minute session
  cache, provider progress, cancellation, and country-generation stale guards.
- Complete, then refined: built the country select, local alert filter, concise
  severity/condition/area list, inline loading/empty/failure states, and reused
  full provider document reader with fixture-driven tests.
- Deliberately deferred: application launcher ownership and integration remain
  in Slice D; the Slice A screen exists as an independently testable workspace.

### Slice B — country map

- Complete: added complete map-unit geometry, including disconnected country
  components, with dim severity context for every provider-issued polygon and
  full semantic emphasis for the selected alert. Alerts without polygons remain
  in the list/document and receive no inferred shape.
- Complete: alert selection updates polygon emphasis without rebuilding country
  geometry or native city widgets.
- Complete: added ranked, capped, direction-aware native city callouts and one
  lightweight batch temperature request. Results have a brief coordinate/unit
  cache; failure retains geography and city names, and resize never refetches.

### Slice C — map context and responsive budget

- Complete, then refined: city context is capped at four ranked places and the
  separate current-weather inspection card was removed to maximise map space.
- Complete: added a pure responsive allocator and tested wide three-column,
  medium stacked-workspace, 80x24 tabbed-right-pane, and below-baseline
  one-pane modes. The same mounted panes preserve selection and scroll state.

### Slice D — application integration

- Complete: added the weather-screen `g` launcher and help/README guidance
  without displacing the local `i` warning-details action.
- Complete: the application owns one isolated country-alert service and one
  reusable Alerts Centre screen, preserving session caches across visits.
- Complete, then refined: `r` bypasses the country cache; `w` returns to
  weather; and live unit, language, theme, and emoji settings are applied to
  the existing workspace.

### Post-implementation UI refinement

- Complete: replaced the country input/list pair with one native `Select`,
  moved the text and severity alert filters and alert ordering select behind a
  primary `Filter alerts` button and modal, and removed provider-count and coverage-copy clutter from
  the navigation pane.
- Complete: warning rows now use a bold coloured severity plus regular
  condition on line one and one 24-character ellipsized provider-area line
  below it.
- Complete: removed the outer workspace border and current-weather card; the
  three primary rounded panes now consume the available area, with narrower
  navigation/document panes and a country viewport padded by only two percent.
- Complete: map labels are capped at four ranked capital/major-city candidates,
  leaving dim context polygons and the full-colour selected polygon dominant.
- Complete: warning fills use the readable semantic text colour over sea and a
  deliberately darker shade from the same semantic family only where warning
  and land raster pixels intersect, keeping coastlines legible without changing
  provider geometry or implying a different severity.
- Complete: wide navigation and detail rails have equal widths, the three
  wide-layout panes have two-column hatched gutters, loading uses the list
  region's progress bar, and the unselected document prompt is centred in its
  pane.
- Complete: compact layouts use one-row country/filter controls and two map
  city labels; territories routed through a shared national provider begin
  with their country name in the local filter.
- Complete: selected-alert details put the familiar local active-time line
  immediately below the headline.
- Complete: alert rows use the same muted separators as saved-location lists.
- Complete: pointer hover and focused keyboard highlighting transiently show a
  row's visible polygon at full severity without selecting, zooming, or
  replacing the detail document; leaving the list restores normal emphasis.
- Complete: activating the selected alert again clears its selection and
  returns the map and detail pane to their full-country overview states.
- Complete: added `Severity` and `New first` local sorting plus primary-backed
  `NEW` badges based on the preceding successful country/language snapshot.

### Slice E — alert-focused viewport and geographic context

- Complete: retain unprojected country, alert, and place geometry so selecting a
  polygonal alert can deterministically fit a padded viewport around the whole
  selected geometry; use the country viewport when geometry is absent or
  invalid.
- Complete: project overlapping non-selected alerts into the focused view and
  keep the selected polygon at full semantic emphasis without network work.
- Complete: rank settlements from the complete checked-in place set, prioritise
  points inside the selected geometry, and derive a collision-safe label budget
  from map dimensions rather than a fixed country-wide four-city cap.
- Complete: replace the 1:50m place subset with Natural Earth's complete 1:10m
  place layer so tightly focused alerts can use scale-rank 5–10 towns and small
  settlements rather than falling back to distant major cities.
- Complete: add passive, marker-free italic Admin-1 labels from Natural Earth
  metadata for every region represented in the focused viewport. Provider area
  descriptions do not supply map labels, multi-region alerts retain every
  region, and the same state/province/region rule applies worldwide.
- Complete within the Slice E data boundary: the focused label source is
  Natural Earth's complete 1:10m populated-place layer (7,342 records). Sparse
  rural, river-corridor, and marine alerts may therefore have little or no
  labelled context. Task 0021 records the separate denser-gazetteer problem;
  expanding it is not unfinished Slice E work.
- Verified: pure tests cover country fallback, single and
  disconnected selected polygons, tiny bounds, wrapped longitudes, place
  ranking inside/outside the selected geometry, label-budget stability, and
  multi-region label provenance. No weather request belongs in this slice.

### Slice F — interactive settlements and hourly data lifecycle (superseded)

- Complete: removed temperature text/colour and the Alerts Centre's batch city
  temperature loader/cache while leaving other location-map temperature users
  unchanged.
- Complete: made visible settlement labels mouse- and keyboard-activatable via a
  dedicated message that does not navigate away or update the primary weather
  location.
- Complete: added a minimal hourly-only Open-Meteo loader/model path with the
  user's configured units, plus a short coordinate/unit cache, cancellation,
  generation guards, explicit-refresh behavior, and independent inline
  loading/failure state.
- Complete: clear the selected settlement on country/alert changes and refetch a
  visible selection after relevant unit changes. Theme changes remain local
  rerenders.
- Verified: fixture tests cover click/Enter/Space activation,
  focus retention, cache hit/expiry, rapid-city stale results, country/alert
  invalidation, unit changes, retry, and failure that leaves the map intact.

This slice records the original implementation. The later settlement UX
revision below replaced its hourly-loader and local-selection behavior.

### Slice G — fixed hourly strip and responsive integration (superseded)

- Complete: introduced `AlertPlaceHourlyForecast`, sharing the main hourly
  forecast's formatting utilities while deliberately omitting tabs, cursor,
  scroll position, and horizontal scrolling.
- Complete: show only the consecutive hours that fit the full width, budget
  complete value/bar rows in priority order, and title the frame for the
  selected settlement.
- Complete: extended `alerts_centre_layout_for(...)` to allocate a hidden-or-bounded
  forecast peer at no more than one quarter of the Map workspace height and to
  provide the focused settlement-label budget. The map gets all height while
  no usable forecast peer is visible.
- Complete: preserve alert/document/settlement state across Map/Details tab
  changes and resize without issuing new requests; recompute only projection,
  collision placement, fitted columns, and complete visible rows.
- Complete: use a centred loading indicator rather than loading copy. The first
  settlement request uses the minimum peer, while later city-to-city requests
  retain the established forecast height within the current quarter-height
  ceiling so the map does not jump during replacement.
- Verified: rendered 80x24, 100x30, 140x40, 180x50, and very-wide
  tests assert the quarter-height ceiling, no page or hourly scrolling, exact
  complete-row admission, fitted hour counts, hidden insufficient-height state,
  and zero resize-triggered network requests.

This slice records the original implementation. Its dedicated hourly widget,
service path, layout budget, and tests were removed by the following revision.

### Post-completion settlement UX revision

- Complete: settlement hover now requests compact current conditions after a
  short delay and renders condition, temperature, rain, and wind in a Rich
  tooltip with loading and unavailable states.
- Complete: successful previews use a brief coordinate/all-unit cache; rapid
  hover changes, country/alert changes, and navigation cancel or
  supersede stale results. Resize performs no weather work.
- Complete: click, Enter, or Space now opens the settlement's full forecast on
  the Weather screen. The reusable Alerts Centre preserves its country,
  selected alert, filters, and map/document context for the next `g` return.
- Complete: removed the fixed hourly strip and its hourly-only Open-Meteo,
  service, layout, widget, and test paths, returning all map-workspace height to
  the map at every terminal size.
- Verified: deterministic tests exercise native hover, cache hit/expiry,
  all-unit keys, stale/cancelled results, retry, alert invalidation, activation,
  Weather-screen navigation, and context-preserving return.

Task 0019 should land first so this screen reuses one alert document component.

## Relevant code

- `wevva/widgets/weather_alerts.py`
- `wevva/widgets/warning_area.py`
- `wevva/widgets/location_map.py`
- `wevva/widgets/country_alerts_map.py`
- `wevva/widgets/geographic_scope.py`
- `wevva/alerts_centre_layout.py`
- `wevva/screens/alerts_centre_screen.py`
- `wevva/services/alerts.py`
- `wevva/services/weather.py` and `wevva/openmeteo.py`
- `wevva/geography.py` and `tools/build_natural_earth_places.py` for the
  completed Slice E Natural Earth baseline; see Task 0021 before expanding the
  focused label dataset
- `wevva/utils/country_codes.py`
- `wevva/app.py`
- sibling `wevva-warnings` public source/query APIs

## Acceptance criteria

- The country `Select` is type-searchable, keyboard accessible, and contains only
  countries supported by the authoritative warning-source contract.
- Changing country cannot apply an older request's list or polygons to the new
  selection.
- The loaded list contains active country alerts from the available configured
  feeds, deduplicated and strongest-first.
- The sort select defaults to `Severity`; `New first` moves only identities
  newly observed by the latest fresh fetch ahead of that stable ordering.
- The first successful fetch establishes a baseline, later added identities
  receive a `NEW` badge, cache hits retain it, and the next successful fresh
  fetch clears it when the identities are unchanged.
- Search is immediate/local and matches severity, condition, location,
  headline, and source metadata.
- List rows use a severity/condition first line and a cropped area second line.
- Loading or changing country populates the list without selecting its first
  alert, so the map and detail pane retain their country-overview prompts until
  explicit selection.
- Selecting an alert updates full text and map emphasis together by stable
  identity.
- Activating the selected alert again clears it, removes the committed list
  highlight, restores the country viewport, and shows the detail prompt.
- Hovering or keyboard-highlighting a list row temporarily gives its visible
  polygon full semantic emphasis without changing selection or viewport.
- Alerts without geometry remain fully readable and never receive an inferred
  polygon.
- With no usable selected geometry, the map retains the whole country. With
  usable selected geometry, it fits that entire geometry with bounded padding
  and retains overlapping alerts as dim context.
- Focused settlement candidates prioritize points inside the selected alert;
  their visible count follows map dimensions and collision constraints rather
  than a fixed cap.
- Settlement labels contain no temperature text or temperature-derived colour,
  are operable by mouse and keyboard, and expose compact current conditions on
  hover without changing map layout.
- Focused maps show passive italic Natural Earth Admin-1 names for every region
  represented in the viewport, without marker dots or provider-text parsing.
- Hovering a settlement starts at most one stale-safe current-weather request;
  successful previews are cached by coordinates and all display units.
- Activating a settlement opens its full Weather-screen forecast. Returning
  with `g` restores the prior Alerts Centre country and workspace context.
- Settlement-preview failure does not suppress the map, alert list, or
  document.
- Wide terminals use the three-pane composition; 80x24 uses alert navigation
  plus Map/Details workspace tabs with no full-page vertical scrolling.
- Alert-list and document selection state survive resize and pane switching;
  resize changes no alert or weather request count.
- Local weather-screen alert fetching and caching remain behaviorally and
  structurally independent.

## Verification

Deterministic tests should use country fixtures rather than live providers:

```bash
uv run python -m compileall -q wevva
uv run python -m unittest tests.test_alerts_centre_service
uv run python -m unittest tests.test_alerts_centre_map
uv run python -m unittest tests.test_alerts_centre_screen
uv run python -m unittest tests.test_warning_cache
uv run python -m unittest discover -s tests
```

Cover country switching races, cache hit/expiry, partial and total failures,
empty country/filter states, alerts with and without geometry/area names,
severity ordering, whole-country/disconnected geography, selected-geometry
viewport fitting, focused settlement ranking, settlement activation, weather-
preview cache/stale/failure behavior, and rendered 80x24, 100x30, 140x40,
180x50, and
very-wide topologies. Exercise alert loading, stale, successful-empty,
filtered-empty, partial-provider, total failure, and settlement-preview
loading/failure states at representative compact and wide sizes. Assert that
resize initiates neither country-alert nor settlement-weather requests.

Manual checks remain necessary for live provider coverage, long localized
country and region names, very large or very small alert geometry, dense
settlement clusters, Braille density, hover/focus colours, terminal fonts, and
official links. Record which country feeds and settlement previews were
actually exercised; do not claim national completeness from a small sample.

## Decisions and notes

- This is an alerts workspace, not a larger weather-warning modal.
- Country-level results get their own cache and generation; the point-alert
  cache remains untouched.
- Search/filter state is local presentation state and never refetches.
- Alert selection alone controls automatic map fitting; there is no independent
  pan/zoom state to reconcile.
- Settlement hover is local Alerts Centre state; activation intentionally
  changes the primary weather location and opens the complete Weather screen.
- Current-weather previews have their own cache and request generation; they do
  not enter the main forecast/controller or air-quality paths.
- Provider source metadata, not Wevva conditionals, determines supported
  countries and coverage limitations.
- Task 0019 supplies the reusable selected-document presentation.
- The initial country-wide map favours geographic truth over inset-map
  complexity for disconnected territories.
- Slice E is complete despite Natural Earth's intentionally selective place
  coverage. Task 0021 is the handoff for denser contextual labels and must not
  expand this task into a general mapping subsystem.
