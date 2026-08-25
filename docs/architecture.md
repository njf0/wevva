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
             -> background alerts + global canonical/nearby tropical context
             -> WeatherAlertsUpdated
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
  result is rendered, an uncached canonical tropical refresh continues in the
  background and updates both the compact storm launcher and local alert tabs
  only if the location is still current. Its sidebar progress is indeterminate
  while global reports are fetched, then shows measured local matching
  progress; tropical reports remain ordered before ordinary alerts.
- `wevva/services/tropical.py` fetches `CanonicalTropicalSystem` groups with
  `get_canonical_tropical_systems()` and keeps them in a separate thirty-minute,
  session-only cache. Canonical groups remain identity wrappers: the dedicated
  `TropicalSystemsScreen` shows each untouched source observation separately,
  and orders groups by the strongest declared source classification without
  merging meteorology. Supplementary `TropicalProduct` values are loaded lazily
  for the selected observation and cached by source, ID, and issue time. The
  service flattens those same observations only when it calls
  `match_tropical_systems_to_point()` afresh for every selected location using
  the final Open-Meteo forecast coordinates and
  a 250 km (roughly 155 miles) radius around either the current centre or the
  supplied forecast track; supplied polygons continue to match by containment.
  It calculates local centre distances
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

The right sidebar combines an optional independently scrolling CAP detail
reader and warning-area scope with a compact Nearby Tropical Systems launcher.
It shows at most the nearest few canonical systems and deliberately contains no
maps or supplementary-product reader. The central alert tabs retain nearby
tropical entries and ordinary CAP alerts independently.

`wevva/screens/tropical_systems_screen.py` is the global storm workspace opened
with `t`. Its severity-ordered, full-classification storm selector is followed
by a source selector only for multi-observation systems. An aligned
full-width current-analysis summary table, a compact Open-Meteo
current-conditions table for the selected source centre, and persistent
track-fitted Storm Track pane occupy the wider left column; a two-cell gutter
separates the right-hand fixed
product tabs and independently scrolling document body. The storm-selection
workspace behind both columns retains the application hatch. `Overview` is
always present. Other tabs come only from lazy
`get_tropical_products()` results, with literal plain text, explicit Markdown,
and restrained tables for the structured forecast point shapes supplied by
`wevva-warnings`. The workspace is a bounded panel inside a full-height
centring stage and occupies roughly sixty percent of the terminal; at compact
widths the panel expands into a small screen inset while retaining the same
summary/conditions/track-left and document-right topology with relaxed column
minimums.
Product tabs begin directly with retrieved provider content; the UI does not
prepend a redundant product title or issued-time block.
Centre conditions use a current-only request in the application's configured
temperature, wind, and precipitation units. Results are cached by source-centre
coordinates for the screen lifetime, refresh with the tropical workspace, and
fail independently of the issuing-centre summary, products, and track. The
table also identifies Open-Meteo's returned forecast-grid coordinates so a
small grid/centre offset remains visible rather than implied away.
Canonical discovery uses an inner Textual loading overlay so the surrounding
Active Tropical Systems frame remains visible; lazy product requests use the
product body's native loading overlay. On this screen, `r` bypasses the shared
canonical and product caches, preserves the selected storm/source where still
present, and applies its refresh loading overlay only to Storm Information so
the existing track remains visible until it updates in place.

Ordinary alert descriptions and instructions are rendered as literal provider
text rather than generic Markdown. A small provider-neutral pass joins
operational hard-wrapped prose while retaining blank lines, dashed section
headings, subsection markers, and list starts. Rich/Textual then performs the
visible wrapping; list rows use hanging indentation, and source punctuation is
never treated as markup.

The storm scope combines the current position and the complete useful source
forecast horizon in one padded, track-fitted regional viewport. It clips the
checked-in global Natural Earth map-unit layer into that viewport rather than
using `DisplayGeography` to select one source country; open-ocean views
may consequently contain no land. Source geography metadata may contribute one
visible map-unit/subunit label, but it never changes the land layer or viewport;
an off-screen context is not labelled. The selected forecast location never
supplies storm-map context. The current position and regular 24-hour forecast
fixes receive visible centred dots without a connecting line. When supplied,
an official cone is a secondary-coloured Braille layer. The screen's `t` and
`c` bindings independently hide position markers and the cone; both toggles
retain the complete scope for placement so the viewport and remaining markers
do not move or clip. The warning scope instead keeps a stable whole selected
country/map-unit viewport so the warning polygon's relative coverage remains
meaningful.

The CAP prose panel and tropical product body each own their scrollbar, while
geographic scopes remain bounded inside their respective areas. Compact scope
content height comes from the padded projected viewport
and the shared 2×4 raster cell aspect, then is clamped by widget-specific minimum
and maximum heights. The dedicated storm scope instead consumes the remaining
left-pane height while retaining projection fitting. Width changes recompute
compact heights. Warning Area also uses
the same one-row top-margin convention as saved-location progress panels; the
sidebar hatch remains visible in that gap while each child panel keeps a solid
background. Warning-map raster composition can balance final visible sub-cell
margins with a translation only. Storm-map placement instead uses the complete
scope's raster layers and avoids a second visibility-dependent translation, so
toggling the cone cannot reposition or discard forecast markers.

`wevva/geography.py` owns the deliberately small shared geographic path:
Natural Earth map-unit loading and local-component selection, GeoJSON
Polygon/MultiPolygon and line extraction, local projection, and viewport
bounds. `wevva/widgets/geographic_scope.py` supplies the logical filled-polygon,
polyline, and point raster plus 2×4 Braille composition. Warning areas assign
every fully covered land/warning cell to one full `⣿` glyph, snapping internal
colour boundaries to cells while retaining partial Braille at the exterior
geographic edge. Storm forecasts instead use centred position dots over an
optional secondary-coloured Braille cone; they do not use the warning fill
policy or draw a connecting line. The storm widget adds only forecast-path
selection, its inclusive viewport policy, markers, cone, and semantic styles;
the warning widget adds the selected CAP
Polygon/MultiPolygon, stable context viewport policy, severity fill, and
location marker. This is not a general GIS or plotting framework.

The intentionally direct coupling between widgets, Textual messages, and the
forecast model objects keeps the project small. Stable widget IDs are part of
the CSS contract. The README's minimum terminal target is 186x53 for the full
layout. At launch, the saved-locations sidebar is shown from 144 columns and
the alert-details sidebar joins it at 186 columns. They collapse below those
widths on resize and restore if space returns; both can also be toggled from the
weather screen. Emoji width/rendering depends on the terminal and font.

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
