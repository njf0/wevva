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
             -> background alerts
             -> WeatherAlertsUpdated

t key -> TropicalSystemsScreen -> global canonical tropical systems + products

m key -> WorldLocationsScreen -> checked-in global map-unit geometry
                             -> cached saved-location summaries
                             -> SavedLocationSelected -> WeatherScreen + refresh
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

Saved-location summaries take a separate, staggered weather-only path in
`Wevva._fetch_saved_weather_summary`; they do not use the controller or request
air quality and warnings. Each result updates both the sidebar cache and an
open `WorldLocationsScreen`, so the spatial overview can render immediately
from cached values and accept later results without issuing its own queries.

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
  When that sidebar is absent, the app emits one informational notification at
  the start of a warning check. A completed empty check or a failed check emits
  one terminal notification; provider progress callbacks never emit their own
  notifications, and active results are communicated by the warning widget.
  Reusable country alerts and native point alerts start together. Tropical
  retrieval is not part of this weather-location refresh path.
- `wevva/services/tropical.py` fetches `CanonicalTropicalSystem` groups with
  `get_canonical_tropical_systems()` only for the dedicated tropical workspace
  and keeps them in a separate thirty-minute, session-only cache. Canonical
  groups remain identity wrappers: the dedicated
  `TropicalSystemsScreen` shows each untouched source observation separately,
  and orders groups by the strongest declared source classification without
  merging meteorology. Supplementary `TropicalProduct` values are loaded lazily
  for the selected observation and cached by source, ID, and issue time. The
  service retains standalone nearby-system helpers for API callers. Those
  flatten source observations and use `match_tropical_systems_to_point()` with
  a 250 km (roughly 155 miles) radius around either the current centre or the
  supplied forecast track; supplied polygons continue to match by containment.
  These helpers do not participate in the main TUI weather refresh.
- `wevva/config.py` reads/writes `~/.config/wevva/config.json`, validates
  preferences, and normalizes saved/default location metadata.

The public API lives in `wevva/api.py` and is exported by `wevva/__init__.py`.
`forecast_by_coordinates()` / `forecast_by_place()` return `ForecastBundle`;
`geocode()` returns `LocationMetadata` values; alerts are separate helpers.
The `*_sync` wrappers call `asyncio.run` and deliberately reject use inside an
already-running event loop. This path builds models directly rather than using
the TUI controller, although both paths independently merge air quality.

## Presentation

The implemented responsive layout language is documented in
`docs/responsive-layout.md`; its completed delivery record and acceptance
criteria are in `docs/tasks/0015-responsive-layout-redesign.md`.

`wevva/screens/weather_screen.py` composes the weather screen and owns
screen-level widget routing. Focused presentation logic is in
`wevva/widgets/`; `wevva/utils/` contains condition formatting, colour scales,
country-code lookup, and small display helpers. `wevva/wevva.tcss` supplies
global CSS; several widgets also carry local `DEFAULT_CSS` for their own
geometry.

`wevva/layout.py` is the pure allocator for the responsive weather screen.
Given the content viewport, warning presence, and available auxiliary surfaces,
it returns current-condition density and height, visible detail/hourly rows,
warning density and height, daily columns and row count, context density and
height, and modal/sidebar presentation. Its constants explicitly include
borders, tabs, padding, and gutters. `WeatherScreen` applies one result to
stable widget instances after weather updates, warning changes, sidebar
changes, and terminal resizes.

The main panel retains `1 2` padding, centres the complete visible forecast
stack vertically, and does not scroll vertically. Summary,
warning, current-condition, and hourly frames share a centred 98-cell maximum.
Current condition instruments switch between mounted `Digits`, two-line static
values, and a smallest primary-value-only line; the detail table exposes only
complete prioritized rows. Once 102 usable columns are available, its label
field grows from six to eleven cells and restores full labels such as
`Humidity`, `Visibility`, and `Cloud Cover`. Hourly day tabs retain up to 24 columns in a horizontally
scrollable `DataTable` while complete value/graph rows follow the height budget.
Narrow tables expose an explicit position thumb and keyboard hint; once all
hours fit, their compact four-cell columns remain fixed inside a centred
98-cell frame. Daily forecast rows and field groups are also complete budget
units, and the centred frame contracts to the active columns. Rain probability
and wind release their combined-value space when amount and gust gain dedicated
columns. Rain amount is ordered immediately after rain probability and before
wind. At 102 or more usable columns the daily forecast restores its original
96-cell table: full weekday and condition names, dedicated rain amount and
wind-direction fields, and gusts combined into the wind field. Its 98-cell
bordered frame then shares the other forecast widgets' maximum width. The table
appears only when at least two rows fit. At 80x24 the titled weather summary,
an active bordered warning, a hatch row after each summary, the smallest
one-line four-instrument row, and hourly condition/temperature/time fit in the
22 rows between the header and footer. Rain is added before wind as rows become
available; current conditions grow only after both value rows fit.

The country map uses the same Natural Earth map-unit, populated-place, local
projection, Braille raster, and collision-fitted label path as the other
geographic scopes. The selected location chooses a useful local component
cluster of its country: for example, Hawaii is shown without continental US.
Ranked cities are restricted to that selected land and the forecast location is
drawn and labelled in a distinct semantic colour. Up to eight ranked cities
receive current temperatures from one lightweight, non-blocking multi-location
Open-Meteo request; failed or stale enrichment leaves the base map intact.

The saved-locations world map is a separate global navigation surface opened
with `m`. It layers native, focusable `WorldLocationLabel` widgets over one
fixed Braille world raster. Absolute offsets express geographic placement, but
Textual still owns focus, hover, click handling, and activation. Collision
placement is recomputed on resize without replacing the labels, preserving
focus. Left/right moves between labels; Enter, Space, or click emits the same
`SavedLocationSelected` message as the list and returns to the ordinary weather
screen. The screen keeps the standard header/footer and places the map's single
rounded frame inside `1 2` stage padding. Its fixed viewport ends at 78°S,
retaining the Antarctic coast while assigning the southern polar cap's rows to
the inhabited world.

Weather-warning presence is a bordered focusable summary card at compact
heights. Once three additional rows are available after the standard current
instruments, it upgrades to the classic alert tabs and a two-line preview;
activating the selected preview opens that warning. Mouse activation, Enter,
or Space opens a modal where those tabs directly select the complete provider
document in one independently scrolling, unframed detail body inside the
modal's single rounded frame. Saved locations and
warning details also have modal access commands. When width and height permit,
the first 42 surplus columns move existing forecast context beside the full
102-column central canvas. Auxiliary sidebars use later surplus: one at 186
columns and both at 228 while the sidecar is active. Warning detail wins the
single auxiliary rail when both surfaces have content. In a short viewport
where the context sidecar cannot fit usefully, auxiliary rails retain their
legacy 144/186 thresholds.

When at least 14 final rows are available, location, astronomy, and air-quality
cards stack in the left half of a centred 98-cell context matrix while the
country map fills the right half. The cards grow together through two-, three-,
four-, and five-field tiers at matrix heights 14, 17, 20, and 23; the map tracks
the same height. At the supported 80-column width the inner matrix contracts to
76 cells, leaving two viable 37-cell columns. In a sufficiently tall viewport
of at least 144 columns, the same mounted widgets instead form a 40-cell
right-hand sidecar. Location and astronomy remain above a larger bounded map;
air quality is hidden in this narrow presentation and returns with the bottom
matrix. The sidecar map limits itself to four ranked city labels. Its table and
map heights are budgeted independently from the parallel forecast column.
Fields are admitted only in their documented priority order, and neither
placement introduces page scrolling.
Tropical systems are presented only in the dedicated workspace.

`wevva/screens/tropical_systems_screen.py` is the global storm workspace opened
with `t`. Its severity-ordered, full-classification storm selector is followed
by a source selector only for multi-observation systems. An aligned
full-width current-analysis summary table, a compact Open-Meteo
current-conditions table for the selected source centre, and persistent
track-fitted Storm Track pane occupy the wider left column; a two-cell gutter
separates the right-hand fixed
product tabs and independently scrolling document body. The storm-selection
workspace behind both columns retains the application hatch. NHC and CPHC
observations with a useful discovery headline or summary receive a `Forecast`
tab; other tabs come only from lazy `get_tropical_products()` results. Product
content uses literal plain text, explicit Markdown, and restrained tables for
the structured forecast point shapes supplied by `wevva-warnings`. The
workspace is a bounded panel inside a full-height
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
may consequently contain no land. Up to three collision-fitted place labels
come from Natural Earth's ranked 1:50m Populated Places layer, prioritising
regional significance and then proximity to the track. Issuer and source
geography metadata never supplies a storm-map label, so a provider's home
country cannot be mistaken for the land under a storm. The selected forecast
location never supplies storm-map context. The current position and regular
24-hour forecast fixes receive visible centred dots without a connecting line.
When supplied, an official cone is a secondary-coloured Braille layer. The
screen's `t` and `c` bindings independently hide position markers and the cone;
both toggles retain the complete scope for placement so the viewport and
remaining markers do not move or clip. A once-per-observation information
notification identifies a missing forecast track, cone, or both. The warning
scope instead keeps a stable whole selected country/map-unit viewport so the
warning polygon's relative coverage remains meaningful.

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
Natural Earth map-unit and populated-place loading, local-component selection,
GeoJSON Polygon/MultiPolygon and line extraction, local projection, and
viewport bounds. `wevva/widgets/geographic_scope.py` supplies the logical
filled-polygon, polyline, and point raster plus 2×4 Braille composition.
Warning areas assign every fully covered land/warning cell to one full `⣿`
glyph, snapping internal colour boundaries to cells while retaining partial
Braille at the exterior geographic edge. Storm forecasts instead use centred
position dots over an optional secondary-coloured Braille cone; they do not use
the warning fill policy or draw a connecting line. The storm widget adds only forecast-path
selection, its inclusive viewport policy, markers, cone, and semantic styles;
the warning widget adds the selected CAP
Polygon/MultiPolygon, stable context viewport policy, severity fill, and
location marker. This is not a general GIS or plotting framework.

The intentionally direct coupling between widgets, Textual messages, and the
forecast model objects keeps the project small. Stable widget IDs are part of
the CSS contract. The compact terminal target is 80x24. At useful wide/tall
sizes, forecast context receives the first surplus-width block; saved-location
and alert-detail sidebars follow without shrinking the full forecast canvas.
They collapse on resize and restore if space returns, while their commands open
modal fallbacks when no rail is present. Emoji width/rendering depends on the
terminal and font.

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
