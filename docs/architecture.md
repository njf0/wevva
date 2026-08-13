# Architecture

`wevva` is a compact Textual TUI with a reusable Python API. It deliberately
uses plain modules and Textual messages rather than a separate domain layer.

## Main execution paths

```text
wevva command / python -m wevva
  -> wevva.cli:app -> _launch_wevva() -> Wevva.run()
  -> Wevva.on_mount()
     -> SearchScreen, or WeatherScreen + refresh when coordinates are known

place search -> SearchDialog -> SearchScreen -> services.geocoding.search_places()
             -> PlaceSelected -> Wevva.action_refresh()
             -> WeatherController.fetch() -> weather + air quality -> WeatherUpdated
             -> WeatherScreen -> child widgets
             -> background alerts + nearby tropical context -> WeatherAlertsUpdated
```

`wevva/cli.py` applies CLI and saved-preference choices, resolves a startup
location when needed, and constructs `wevva.app.Wevva`. The console script is
`wevva.cli:app` (`pyproject.toml`); `wevva/__main__.py` makes `python -m wevva`
equivalent.

`Wevva` owns session state: the selected `LocationMetadata`, unit/theme
settings, saved locations, refresh generations, short-lived forecast/warning
caches, and background task handles. Complete forecast results, including air
quality, are cached for fifteen minutes by requested coordinates and display
units; the explicit `r` refresh bypasses that cache.
It uses `WeatherController` for the main forecast refresh. `WeatherScreen`
receives `WeatherUpdated` messages and explicitly forwards models to its
widgets; `HourHighlighted` and `DaySelected` coordinate the selected hour/day
between widgets. Alerts are intentionally fetched after the main forecast so a
slow warning provider does not delay the weather display.

Saved-location sidebar summaries take a separate, staggered weather-only path
in `Wevva._fetch_saved_weather_summary`; they do not use the controller or
request air quality and warnings.

## Data and external boundaries

- `wevva/services/geocoding.py` calls Open-Meteo geocoding and normalizes its
  response to small dictionaries. The TUI and CLI turn these into
  `LocationMetadata`.
- `wevva/services/weather.py` delegates to `OpenMeteoForecast.fetch_all()` in
  `wevva/openmeteo.py` for complete forecasts, and makes a current-only query
  for saved-location summaries. That module defines the requested fields, API
  unit parameters, response metadata extraction, and current/hourly/daily
  model classes.
- `wevva/services/air_quality.py` calls Open-Meteo's Air Quality API. The
  controller and public API merge selected hourly series into weather data.
- `wevva/services/alerts.py` wraps `wevva-warnings`, normalizes country codes,
  filters expired alerts, and uses a thread for its async wrapper. Reusable
  country candidates are cached by the TUI and locally matched; native
  point-query sources are fetched for every selected location, then combined
  and de-duplicated. Progress for reusable candidate retrieval is forwarded to
  `WeatherAlertsProgress` messages on the Textual event loop, then rendered by
  `SavedLocationsSidebar` without reflowing the main forecast layout. The
  sidebar shows an indeterminate bar while a provider request is pending and
  switches to measured progress once the provider returns its alert count.
  Reusable country alerts and native point alerts start together. Once their
  result is rendered, an uncached raw tropical refresh continues in the
  background and updates the same tab panel only if the location is still
  current. Its sidebar progress is indeterminate while global reports are
  fetched, then shows measured local matching progress; tropical reports
  remain ordered before ordinary alerts.
- `wevva/services/tropical.py` fetches raw global reports with
  `get_tropical_systems()` and keeps them in a separate thirty-minute,
  session-only cache. It calls `match_tropical_systems_to_point()` afresh for
  every selected location using the final Open-Meteo forecast coordinates and
  a 250 km (roughly 155 miles) radius. It calculates local centre distances
  and normalises matching reports by source/ID and storm name, preferring a
  same-country issuer or otherwise the newest report. Tropical reports never
  enter the ordinary country-warning candidate cache; an empty or failed raw
  lookup simply contributes no tabs.
- `wevva/config.py` reads/writes `~/.config/wevva/config.json`, validates
  preferences, and normalizes saved/default location metadata.

The public API lives in `wevva/api.py` and is exported by `wevva/__init__.py`.
`forecast_by_coordinates()` / `forecast_by_place()` return `ForecastBundle`;
`geocode()` returns `LocationMetadata` values; alerts are separate helpers.
The `*_sync` wrappers call `asyncio.run` and deliberately reject use inside an
already-running event loop. This path builds models directly rather than using
the TUI controller, although both paths independently merge air quality.

## Presentation

`wevva/screens/weather_screen.py` composes the weather screen and owns
screen-level widget routing. Focused presentation logic is in
`wevva/widgets/`; `wevva/utils/` contains condition formatting, colour scales,
country-code lookup, and small display helpers. `wevva/wevva.tcss` supplies
global CSS; several widgets also carry local `DEFAULT_CSS` for their own
geometry.

The intentionally direct coupling between widgets, Textual messages, and the
forecast model objects keeps the project small. Stable widget IDs are part of
the CSS contract. The README's minimum terminal target is 192x53 for the full
layout, and emoji width/rendering depends on the terminal and font.

## Constraints worth preserving

- Open-Meteo responses are consumed as parallel time-series lists and parsed
  using its returned timezone. Changes to requested fields or response parsing
  affect most presentation widgets.
- Main refresh, alerts, and saved-summary requests have separate cancellation
  and generation guards. Preserve stale-result protection when changing async
  work, including warning-progress callbacks from the worker thread.
- `LocationMetadata` is built incrementally: geocoding provides identity and
  coordinates, while a forecast supplements elevation/timezone abbreviation.
- Configuration normalizes old/incomplete values and quietly falls back to
  defaults on read/write failures. Avoid breaking existing config shapes.
- Public exports and model method names are library compatibility surfaces,
  even where the TUI does not use every method.
