# Task 0027: Warning visibility across forecasts and saved locations

## Status

Proposed

## Context

The weather screen shows complete warning details for the active location, but
the daily forecast does not identify which forecast dates are covered. Saved
locations show current weather in a list and on the world map, but neither
surface indicates that a location has an active or upcoming warning.

The warning service already separates reusable country candidates from native
point-query sources. Reusable candidates are cached by country and language,
while native sources must be queried for each location. Saved-weather summary
requests already provide a background, generation-guarded model for updating
the list and an open world map.

## Problem

Warnings are easy to miss unless the affected location is already open, and a
warning shown on the weather screen is not connected visually to the days it
covers. Adding saved-location indicators requires background warning discovery
without duplicating country-wide provider work, delaying the main forecast, or
allowing stale results to update a location after navigation or preference
changes.

## Desired outcome

The daily forecast and both saved-location surfaces use one compact `!` badge
and one shared severity scale. The active forecast marks each date that overlaps
a warning, while the locations list and world map show the most severe warning
known for each location. Warning discovery for all surfaced locations happens
silently in the background and reuses country-level work.

## Scope

- Add shared severity ranking, most-severe selection, colour, and date-overlap
  helpers so every warning surface follows the same rules.
- Pass active-location alert updates to the existing daily forecast table.
- Prefix an affected daily date with a severity-coloured `!` without changing
  the table's column widths, row count, or overall dimensions.
- Add a severity-coloured `!` badge to the weather-summary line of affected
  rows in the saved-locations list, avoiding extra pressure on long place
  names.
- Replace a world-map callout's geographic `•` with a severity-coloured `!`
  when that location has a warning, while retaining the temperature colour for
  the callout body and keeping the marker on the projected cell.
- Fetch warnings in the background for every distinct location shown by the
  saved-location surfaces, including a distinct active location on the world
  map.
- Fetch reusable candidates once per normalized country/language cache key and
  locally match them to every location in that country.
- Query native point sources separately for every valid location.
- Preserve cancellation, generation, and coordinate checks so superseded
  background results cannot update current UI state.
- Keep successful empty and unsupported-country results cacheable; do not
  replace a last-known location indicator with an uncertain empty result after
  provider failure.
- Feed completed results into an already-open world map without rebuilding its
  label widgets or losing focus.

## Non-goals

- Showing warning headlines or complete documents directly in the locations
  list or world map.
- Changing table, sidebar, or map dimensions.
- Adding warning polygons to the world map.
- Making the background saved-location sweep drive the active weather screen's
  header subtitle or warning progress panel.
- Changing the Alerts Centre's independent cache or refresh behavior.
- Persisting warning results between application sessions.
- Treating tropical-system products as ordinary location warnings.

## Relevant code

- `wevva/app.py`
- `wevva/services/alerts.py`
- `wevva/screens/weather_screen.py`
- `wevva/screens/world_locations_screen.py`
- `wevva/widgets/daily_forecast.py`
- `wevva/widgets/daily_summary.py`
- `wevva/widgets/saved_locations.py`
- `wevva/widgets/world_locations_map.py`
- `wevva/widgets/weather_alerts.py`
- `tests/test_warning_cache.py`
- `tests/test_warning_textual_smoke.py`
- `tests/test_responsive_weather_screen.py`
- `tests/test_world_locations_map.py`

## Approach

### Shared warning presentation rules

Move the current weather-screen severity ordering and warning-widget colour
mapping behind shared pure helpers. Normalize provider labels before ranking:
`extreme`/`red`, `severe`/`orange`/`amber`, `moderate`/`yellow`,
`minor`/`green`, then `unknown` and unrecognized values. Equal-ranked alerts
use stable event/headline ordering.

Render the badge as a bold reverse-style `!` in the severity colour. Reverse
styling supplies a compact coloured background without introducing a separate
layout element. The surrounding date, place name, or temperature keeps its
existing presentation.

### Daily warning dates

`DailySummaryTable` retains the alerts separately from its forecast model and
rebuilds when either changes. For each displayed local forecast date, select
the most severe alert whose interval overlaps that calendar day in the
forecast location's IANA timezone.

Use these bounds when provider timing is incomplete:

- onset and expiry: mark every overlapping local date;
- expiry only: treat the warning as already active and mark dates through the
  expiry date;
- onset only: mark the onset date, without inventing an unknown duration;
- neither: leave daily dates unmarked while retaining the ordinary warning
  panel and location-level badge.

Compact dates become `! Fri 13` and wide dates become `! Friday 13`; both fit
inside the existing 8- and 13-cell date columns. Unaffected dates retain their
current text.

### Saved-location warning state

Keep warning results separate from `SavedLocationWeatherSummary`, because
weather and warning requests complete independently and have different failure
and cache semantics. The sidebar, modal copy, world screen, and map accept a
small per-location warning snapshot keyed by the existing `location_key()`.
The snapshot needs the ordered matched alerts, or at minimum the selected most
severe alert plus a checked timestamp; it remains session-only.

The current location's ordinary warning result updates the same saved-surface
state. A separate saved-location background generation handles the remaining
locations. Country candidate retrieval is shared by normalized
`(country_code, warning_language)` and uses the existing 30-minute cache; an
in-flight lookup should also be shared so simultaneous locations do not start
duplicate country requests. Native point lookups remain per-location and are
combined with locally matched candidates.

The active location keeps its existing foreground warning task, progress, and
header lifecycle. Background locations update only their badges. Background
work should be bounded or staggered so a long saved list cannot start an
unlimited burst of provider requests.

Refresh the background set after startup/current forecast refresh, saved-list
changes, and warning-language changes. Explicit refresh bypasses eligible
session caches. Cancellation or a changed generation, location set, language,
or coordinates prevents publication. A completed empty result clears a badge;
a failed or incomplete lookup preserves the last known snapshot.

## Acceptance criteria

- An active-location alert with published timing marks every overlapping daily
  row and no non-overlapping row.
- When multiple alerts overlap a date or location, its badge uses the most
  severe alert according to the shared ordering.
- Partial and missing timing follow the documented conservative rules.
- Daily warning badges fit both compact and wide date columns without changing
  layout budgets or table dimensions.
- Saved-location list rows show a background-coloured `!` only when a matched
  warning is known for that location.
- A warned world-map location uses `!` on its geographic anchor; an unwarned or
  unchecked location uses `•`.
- The marker severity colour and callout-body temperature colour can coexist,
  including under focus and hover treatment.
- One reusable candidate request serves all locations sharing a country and
  language during a valid cache interval.
- Native point-query sources are invoked once for each location participating
  in a background refresh.
- Warning work never delays the main forecast or saved-weather summaries.
- Stale, cancelled, failed, and preference-obsolete results do not clear or
  overwrite newer location warning state.
- An open world map accepts later warning results without replacing labels or
  losing focus.
- Existing active-warning progress, cache, force-refresh, and no-toast behavior
  remains intact.

## Verification

```bash
uv run python -m unittest tests.test_warning_cache tests.test_warning_textual_smoke
uv run python -m unittest tests.test_responsive_weather_screen tests.test_world_locations_map
uv run python -m unittest discover -s tests
uv run python -m compileall -q wevva
```

Add deterministic coverage for interval overlap across midnight and timezone
boundaries, severity ties and aliases, grouped country retrieval, per-point
native retrieval, partial provider failure, stale generations, live world-map
updates, marker anchoring, and unchanged responsive dimensions. Terminal
background colours, focus inversion, and dense real saved-location sets still
need manual checks.

## Decisions and notes

- A visible `!` plus severity colour is preferable to colour alone: it remains
  meaningful in low-colour themes and uses spare cells already present in both
  daily date widths.
- On the map, replacing `•` is preferable to adding a second glyph because the
  marker already owns the exact geographic cell and the callout planner can
  retain its existing width and anchor semantics.
- Country-wide candidates are the shared expensive unit; local matching and
  native point sources remain location-specific.
- Background saved-location progress stays silent because the existing header
  and sidebar progress describe the active forecast location.

## Outcome

To be completed when implemented.
