# Task 0020: Country alerts centre

## Status

Proposed concept — data and interaction boundaries recorded; implementation not
started

## Context

The weather screen answers a local question: which warnings apply to the
selected forecast coordinate? Its warning cache and native point-query path are
deliberately optimized for that question. Task 0019 improves the local alert
reader but should remain a modal rather than grow into a country browser.

A separate alerts centre can answer a different question: which active alerts
are available for a country, where are their issued polygons, and what do their
full provider documents say? The application already has most of the visual
primitives: country geometry, ranked Natural Earth cities, batch Open-Meteo
temperature requests, semantic alert colours, full provider prose, and Braille
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
alert's complete document on the right. Selecting an alert updates its map area
and document together. Major cities appear on the map with current temperatures
and can drive a small current-weather inspection card.

The screen is a persistent workspace, not a modal. It has its own loading,
empty, partial-provider, and error states, while leaving the weather screen's
local alert refresh untouched.

## Wide composition

```text
┌─ Alert navigation ─┬─ Country warning map ─┬─ Selected alert ─┐
│ Country picker     │                       │ full provider     │
│ Alert filter       │ country outline       │ document          │
│                    │ warning polygons      │ independently    │
│ severity/event/    │ key cities + temps    │ scrollable        │
│ short area list    │                       │                    │
│                    │ compact city weather  │ official link      │
└────────────────────┴──────────────────────┴──────────────────┘
```

The left and right regions are narrow bordered peers; the map receives the
remaining width and aims for a square-ish geographic viewport without forcing
the whole page to scroll.

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
and the screen itself do not.

## Country picker and alert search

Build a Textual-native typeable picker: an `Input` filters an `OptionList` of
supported countries, while ordinary focus and Enter select an option. Avoid a
custom-painted dropdown or mouse hit testing.

Country choices must come from an authoritative public warning-source coverage
contract, joined to Wevva's ISO country names. Prefer a small
`wevva-warnings` API such as `list_supported_alert_countries()` if projecting
`list_sources(kind='alert')` would miss global/dynamic coverage. Do not hard-code
a second country/provider registry in Wevva.

Default to the active weather location's country when it is supported;
otherwise use the last in-session selection or the first supported option. A
country change cancels or supersedes the prior request and clears no newer
result.

A second `Input` filters the already loaded alerts locally. Search across:

- severity;
- normalized condition/event;
- headline;
- `area_names`;
- provider/source name; and
- urgency/certainty when present.

Filtering never issues a network request. Preserve the selected alert if it
still matches; otherwise select the first visible alert or show a clear empty
filter state.

## Alert list labels and ordering

Each navigation row is a concise single-line label:

```text
Severe · Flood · Northern counties
Moderate · Thunderstorm · Accra and Tema
```

- Reuse `alert_condition_name(...)` and semantic severity colour.
- Use the first useful one or two normalized `area_names`, then elide.
- Fall back to a provider-supplied display geography/source label when area
  names are absent.
- Never derive a location label by parsing arbitrary warning prose.
- Sort strongest severity first, then the most immediate onset/expiry, then a
  stable condition/area/id tie-breaker.
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
and country/language generation guards. Reuse provider progress callbacks in a
single local loading/progress region; do not produce a toast per source or
document. Filter expired/inactive alerts and deduplicate through the warning
library's public model/query behavior.

The screen must state when results represent the available configured feeds
rather than guarantee exhaustive national coverage. If native point-only
sources cannot enumerate a country, expose that limitation as source metadata
or a restrained inline note. Do not silently manufacture national completeness
by sampling points.

## Country map

Create a separate `CountryAlertsMap`; do not stretch the point-oriented
`WarningAreaScope` into a multi-alert workspace.

The map uses the same layered Textual pattern as the location maps:

- the complete selected country/map-unit land geometry is the Braille base;
- non-selected active warning polygons use restrained/dim severity fills or
  outlines where the renderer supports them;
- the selected alert polygon uses its full semantic severity colour;
- alerts without polygons remain in the list/document but do not gain inferred
  shapes;
- ranked major cities are native directional callouts showing current
  temperature, for example `• Berlin 16°C` or `Berlin 16°C •`;
- city focus/hover inverts the complete label; and
- alert selection changes polygon emphasis without rebuilding country geometry
  or city widgets.

The requested overview is country-wide, including disconnected map-unit
components. Countries whose remote components make the overview unusually
sparse should remain geographically truthful in the first slice; inset maps or
component selectors are a later enhancement, not an implicit crop.

Use one lightweight multi-location Open-Meteo call for the visible ranked
cities, following the current location-map enrichment path. A failed weather
request leaves city names and alert polygons intact.

Rank and cap the country's enrichment set before constructing that request,
then cache results briefly by stable place/coordinate identity. Responsive
layouts display subsets of that already enriched set: resizing and collision
reflow must not issue successively larger city requests. A country refresh or
cache expiry may refresh enrichment, but an ordinary resize may not.

Follow the cross-screen map interaction contract in
`docs/responsive-layout.md`. Severity is the alert's semantic base colour;
focus and selection reverse the complete navigation label while the selected
polygon and document frame continue to communicate severity. Test that these
states remain distinguishable rather than allowing focus colour to masquerade
as a different severity.

## Current-weather inspection

A compact card associated with the map shows condition, temperature, rain, and
wind for one inspection city. Selecting a city updates this card without
changing the selected alert. Initially choose, in order:

1. a prominent mapped city inside the selected warning polygon;
2. the nearest prominent mapped city to that polygon; or
3. the country's highest-ranked visible city when geometry is absent.

Use existing Natural Earth places and point-in-polygon helpers. Do not query a
raw polygon bounding-box centre which may fall offshore or outside a concave
warning. Opening the full weather page for the inspection city may be a
separate explicit action; map selection itself should keep the user in the
alerts workspace.

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

- Loading one country leaves the previous country clearly marked stale or
  replaces it with one local loading overlay; never mix old polygons with the
  new country title.
- A successful empty result says `No active alerts from available feeds`.
- A local text filter with no matches has a distinct `No matching alerts`
  state and does not clear the loaded country data.
- Partial provider failure keeps successful alerts and identifies unavailable
  sources if the public warning API exposes that status.
- Complete failure uses an inline retryable state; it does not navigate away or
  flood notifications.
- Alerts without geometry, prose, city weather, or official links degrade
  independently.

## Scope

- Dedicated alerts-centre screen and launcher action.
- Authoritative typeable country picker.
- Country-level alert fetch/cache/progress path.
- Locally searchable concise alert list.
- Country-wide multi-alert map with selected polygon emphasis.
- Major-city temperature labels and compact city weather inspection.
- Reused full alert document reader.
- Responsive wide, medium, and 80x24 topologies.

## Non-goals

- Replacing the weather screen's point-applicable alerts or warning cache.
- Claiming exhaustive national coverage where a provider exposes point queries
  only.
- Scraping location names from provider prose.
- Inferring warning polygons from area names or geocodes in the UI layer.
- Persistent alert history, push notifications, acknowledgement workflows, or
  user-defined alert subscriptions.
- Map pan/zoom, selectable projections, or custom spatial keyboard navigation.
- Full hourly/daily forecasts inside the alerts centre.
- New warning providers or provider-specific UI branches.

## Implementation slices

### Slice A — data contract and navigation shell

- Confirm/add public supported-country and country-alert APIs in
  `wevva-warnings`.
- Add the isolated async country service, cache, progress, and stale guards.
- Build the country picker, filter input, concise list labels, and selected
  document using fixture data.

### Slice B — country map

- Add whole-country geometry, all/selected polygon layers, and stable selection
  updates.
- Add native city labels and batch temperature enrichment.

### Slice C — weather inspection and responsive budget

- Add representative-city selection and the compact current-weather card.
- Implement/test wide three-column, medium, and 80x24 tabbed-right-pane modes.

### Slice D — application integration

- Add the launcher binding/command and help text without displacing the local
  `i` warning-details action.
- Wire refresh, return-to-weather behavior, settings/language changes, and
  final cache ownership.

Task 0019 should land first so this screen reuses one alert document component.

## Relevant code

- `wevva/widgets/weather_alerts.py`
- `wevva/widgets/warning_area.py`
- `wevva/widgets/location_map.py`
- `wevva/widgets/geographic_scope.py`
- `wevva/geography.py`
- `wevva/services/alerts.py`
- `wevva/openmeteo.py` and the existing map-temperature loader path
- `wevva/utils/country_codes.py`
- `wevva/app.py`
- a new alerts-centre screen, map widget, pure layout module, and focused tests
- sibling `wevva-warnings` public source/query APIs

## Acceptance criteria

- The country picker is typeable, keyboard accessible, and contains only
  countries supported by the authoritative warning-source contract.
- Changing country cannot apply an older request's list or polygons to the new
  selection.
- The loaded list contains active country alerts from the available configured
  feeds, deduplicated and strongest-first.
- Search is immediate/local and matches severity, condition, location,
  headline, and source metadata.
- List rows remain one line and use concise severity/condition/area labels.
- Selecting an alert updates full text and map emphasis together by stable
  identity.
- Alerts without geometry remain fully readable and never receive an inferred
  polygon.
- The country map retains the whole country, shows selected/all alert context,
  and uses native direction-aware city temperature callouts.
- City-temperature failure does not suppress the map or alert list.
- The compact weather card uses a real ranked city rather than an arbitrary
  polygon bounding-box centre.
- Wide terminals use the three-pane composition; 80x24 uses alert navigation
  plus Map/Details workspace tabs with no full-page vertical scrolling.
- Alert-list and document scroll/focus/selection state survive resize and pane
  switching.
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
severity ordering, whole-country/disconnected geography, city weather failure,
and rendered 80x24, 100x30, 140x40, 180x50, and very-wide topologies. Exercise
loading, stale, successful-empty, filtered-empty, partial-provider, and total
failure states at representative compact and wide sizes. Assert that resize
does not initiate country-alert or city-weather requests.

Manual checks remain necessary for live provider coverage, long localized
country names, very large alert sets, Braille density, hover/focus colours, and
official links. Record which country feeds were actually exercised; do not
claim national completeness from a small sample.

## Decisions and notes

- This is an alerts workspace, not a larger weather-warning modal.
- Country-level results get their own cache and generation; the point-alert
  cache remains untouched.
- Search/filter state is local presentation state and never refetches.
- Provider source metadata, not Wevva conditionals, determines supported
  countries and coverage limitations.
- Task 0019 supplies the reusable selected-document presentation.
- The initial country-wide map favours geographic truth over inset-map
  complexity for disconnected territories.
