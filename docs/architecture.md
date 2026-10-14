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

g key -> AlertsCentreScreen -> country-alert service/cache
                            -> complete map unit + provider warning polygons
                            -> selected-settlement minimal hourly request/cache

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
caches, the reusable Alerts Centre/service, and background task handles.
Complete forecast results, including air
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
  response to small dictionaries. The TUI, CLI, and public API turn these into
  `LocationMetadata` through the shared `location_metadata_from_place()`
  conversion.
- `wevva/services/weather.py` delegates to `OpenMeteoForecast.fetch_all()` in
  `wevva/openmeteo.py` for complete forecasts, and makes a current-only query
  for saved-location summaries. That module defines the requested fields, API
  unit parameters, response metadata extraction, and current/hourly/daily
  model classes. Model accessors return `None` for invalid offsets or absent
  scalar values and an empty string for absent textual condition helpers;
  malformed provider series still fail when the models are constructed.
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
  Independently of that rail, the header subtitle reads `Checking warnings…`
  for the lifetime of the warning task and then restores `Powered by
  Open-Meteo`. Warning checks do not emit toast notifications; active results
  are communicated by the warning widget.
  Reusable country alerts and native point alerts start together. Tropical
  retrieval is not part of this weather-location refresh path.
- `wevva/services/country_alerts.py` is the independent country-discovery
  boundary for the Alerts Centre. It derives supported country choices from
  the warning library's public alert-source registry, calls the broad public
  country query with active filtering, orders and deduplicates results, and
  owns a separate fifteen-minute session cache plus the latest successful
  per-country identity snapshot used for refresh-scoped `NEW` badges. It never
  reads or writes the weather screen's reusable-candidate cache.
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
the TUI controller, while both paths use the same pure air-quality series
alignment helper.

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
The land raster and labels are separate layers. Each current/city callout is a
native `LocationMapLabel` using the same `•` marker; permanent reverse styling
identifies the active forecast, while hover/focus reverses other labels. Click,
Enter, or Space sends the ordinary `PlaceSelected` message and refreshes the
weather screen in place. Responsive placement still limits the sidecar to four
cities and the wider bottom map to eight, reflowing collision-free labels after
temperature updates and resizes. A callout faces right (`• City temperature`)
or left (`City temperature •`) according to available space, keeping the marker
on the projected city cell.

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
document in one independently scrolling, unframed detail body. When the
selected warning has real polygon geometry, the same selection path adds a
bounded Warning Area peer beside the document; alerts without geometry return
the complete width to the prose. The modal's single rounded frame is centred,
uses the selected severity colour, and carries the bold centred alert-count
title. Saved locations and
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

The Alerts Centre implementation lives in
`wevva/screens/alerts_centre_screen.py`. It supplies the type-searchable
supported-country select, local metadata search, severity/new-first ordering,
a concise strongest-first warning list, inline states, stale country-request
protection, and the shared full provider-document presentation. Its
`CountryAlertsMap` centre pane
uses the complete selected map unit rather than the weather screen's local
component cluster. It renders provider-issued warning polygons as dim semantic
context with the selected warning at full severity. Warning pixels over sea use
the readable `text-*` severity colour, while pixels that truly intersect the
land raster use a darker shade from the matching semantic family
(`warning-darken-2` rather than `text-warning`, for example), preserving the
coastline without borrowing a stronger severity colour, clipping, or inferring
geometry. Geometry-less alerts remain readable without inferred shapes. Alert
selection fits the complete
selected geometry, reprojects overlapping context, and reranks settlements
locally without network work.

The Alerts Centre draws candidates from the complete, denser Natural Earth
1:10m Populated Places layer, ranks points inside selected alert geometry first,
and lets map size plus collision placement determine how many labels are shown.
Its focused view also groups the place layer's worldwide Admin-1 metadata into
plain italic state/province/region context labels. Every represented region is
retained, including nearby and multi-alert-spanning regions; provider warning
area prose is not used as map geography and the US receives no separate county
label path.
Settlement callouts contain names only and use ordinary theme text. They are
native focusable controls: click, Enter, or Space emits an Alerts-Centre-only
selection message rather than the application's global place-navigation
message. Selection starts one minimal Open-Meteo hourly request for temperature,
precipitation probability, wind speed/direction, and timezone metadata. Results
are normalized into `HourlyOpenMeteoForecast`, cached briefly by rounded
coordinates and temperature/wind units, and guarded by cancellation plus a
request generation. Country or alert changes clear the selection; relevant
unit changes refetch it; resize performs no weather work. A dedicated fixed
hourly strip below the map fills its width with up to 24 consecutive hours and
has no tabs, cursor, or scrolling. The pure responsive budget limits it to one
quarter of the Map workspace, always admits temperature and time first, then
rain and wind values, then complete corresponding bar rows. If the minimum
complete strip cannot fit, it remains hidden while retaining settlement and
forecast state; loading, empty, and retryable failure occupy the same peer when
its one-row body fits. Loading uses a centred indicator. Once a forecast strip
has been displayed, a replacement settlement request retains that established
height, capped to the current responsive allowance, rather than collapsing the
peer while data is in flight.

Country loading swaps the navigation list for an indeterminate catalogue-fetch
bar, then a percentage-bearing provider-document/geometry bar when measurable
work begins; empty and retryable states occupy that same centred region. Alert
rows use the saved-location list's muted separators. A successful fresh fetch
compares stable source/alert identities with the previous successful snapshot;
new identities receive a refresh-scoped `NEW` badge and can be sorted first.
The bounded per-country/language snapshots persist separately in
`~/.config/wevva/country-alert-observations.json`; the first fetch establishes
a baseline, cache hits retain the current badges, and the next fresh fetch
replaces them. Failed fetches never advance the snapshot. The equal-width
navigation/detail rails and map use two-column hatched gutters in wide
layouts, and 24-character area summaries are capped
before rendering so provider geography cannot consume an unbounded navigation
row. Shared-feed territories start with a country-name filter. At the compact
80x24 target, the country and filter controls collapse to one row each and the
map shows at most two ranked city labels. Selected-alert documents place their
local active-time range directly below the headline.

The warning-library country API returns complete normalized alerts: providers
whose top-level feeds contain only links must fetch their CAP documents (and
some separate geometries) before Wevva can render severity, active state,
polygons, area labels, and provider prose.

`wevva/alerts_centre_layout.py` owns the pure responsive allocation. Wide
terminals show three columns, medium terminals stack map and document beside
navigation, 80x24 uses native Map/Details tabs, and smaller terminals expose
Navigation/Map/Details one pane at a time. These modes only toggle and rearrange
the same mounted widgets, preserving selection and document scroll state. The
allocator also owns the forecast-peer height, complete hourly rows, and broad
settlement-label cap so resize changes presentation without fetching data.
`Wevva` installs this reusable workspace with Textual and opens it with `g`,
owns its independent `CountryAlertsService`, and supplies the focused hourly
loader. Pop/reopen cycles suspend and resume the live widget
tree rather than remounting a previously removed screen.
Its `r` refresh bypasses only Alerts Centre caches;
`w` returns to weather. Settings update its language, units, and theme-derived
presentation in place without merging this path into local warning refresh.

While the workspace is suspended, provider threads discard progress before
attempting to cross back into Textual's UI thread, but the in-flight request
may still populate the persistent screen and cache. Final unmount invalidates
the request generation before cancellation.

`wevva/screens/tropical_systems_screen.py` is the global storm workspace opened
with `t`. Its severity-ordered, full-classification storm selector is followed
by a source selector only for multi-observation systems. The top-level label
uses the canonical storm's strongest declared classification and semantic
severity colour, so changing sources does not restyle the storm. A pure
`wevva/tropical_layout.py` budget accounts for terminal chrome, stage padding,
frame/pane borders, tab rows, and gutters. At 80x24 the same mounted summary
and information widgets form a single stack; complete summary rows are admitted
in priority order while the map and centre weather remain hidden. Once both
column and row minima fit, the workspace becomes a balanced two-by-two
composition: centre weather above the map, and summary above the product
reader. The outer frame consumes the full stage content inside its `1 2`
padding. Resizing changes presentation only and retains storm, source, product,
document, and loading state.

Tiered Open-Meteo current conditions and the track-fitted Storm Track pane
occupy the split left column. The source summary and product reader occupy the
right, with matching top-table and lower-pane heights across the two-cell
gutter. Classification remains in the canonical storm tab rather than being
repeated in the summary, and advisory number is omitted from that compact
table. The track pane keeps land and the provider cone in a Braille
backdrop. Native direction-aware `◆ Now`/daily forecast-fix and
`• City` callouts sit above it; city hover/focus reverses the complete callout,
and click, Enter, or Space sends the ordinary `PlaceSelected` message. A city
callout first searches for collision-free cells outside the forecast cone,
then falls back to ordinary collision placement when the map is too constrained.
A minimum projected span expands short tracks to reveal nearby land and prominent
cities without cropping longer tracks or breaking dateline wrapping. The map
shows discrete provider-supplied fixes instead of joining them into a
continuous path. A fix receives a lead label only when a loaded structured
product supplies `lead_hours` at matching coordinates; vertex order and valid
timestamps do not imply a lead. Resize only reflows the existing callout
widgets and does not request products or weather. Product tabs appear only
when there is a choice, and the two
reclaimed tab rows return to the independently scrolling body. Providers with
only a discovery headline, summary, or official link show that information
directly in a compact reader instead of reserving the full column height. The
workspace behind both columns retains the application hatch. NHC and CPHC
observations with a useful discovery headline or summary receive a `Forecast`
tab; other tabs come only from lazy `get_tropical_products()` results. Product
content uses literal plain text, explicit Markdown, and restrained tables for
the structured forecast point shapes supplied by `wevva-warnings`. The
workspace fills its full-height stage. Its frame has no internal padding; the
stage supplies the only `1 2` outer inset.
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
location never supplies storm-map context. The current position and
provider-supplied forecast fixes define the complete viewport without a
connecting line. When explicit lead hours include daily boundaries, visible
forecast markers and compact labels use only the 24-hour fixes (`24h`, `48h`,
and so on); the full supplied horizon remains in scope.
When supplied, an official cone is a subdued warning-coloured Braille layer. The
track and cone layers render whenever supplied and have no separate visibility
bindings or notification state. A missing track uses the local unavailable
treatment when the budget admits that region. The warning
scope instead keeps a stable whole selected country/map-unit viewport so the
warning polygon's relative coverage remains meaningful.

The CAP prose panel and tropical product body each own their scrollbar, while
geographic scopes remain bounded inside their respective areas. Compact scope
content height comes from the padded projected viewport
and the shared 2×4 raster cell aspect, then is clamped by widget-specific minimum
and maximum heights. The dedicated storm scope instead consumes the complete
lower-left pane while retaining projection fitting. Width changes recompute
compact heights. Warning Area also uses
the same one-row top-margin convention as saved-location progress panels; the
sidebar hatch remains visible in that gap while each child panel keeps a solid
background. Warning-map raster composition can balance final visible sub-cell
margins with a translation only. Storm-map placement instead uses the complete
scope's raster layers and avoids a second visibility-dependent translation.

`wevva/geography.py` owns the deliberately small shared geographic path:
Natural Earth map-unit and populated-place loading, local-component selection,
GeoJSON Polygon/MultiPolygon and line extraction, local projection, and
viewport bounds. `wevva/widgets/geographic_scope.py` supplies the logical
filled-polygon, polyline, and point raster plus 2×4 Braille composition.
Warning areas assign every fully covered land/warning cell to one full `⣿`
glyph, snapping internal colour boundaries to cells while retaining partial
Braille at the exterior geographic edge. Storm forecasts instead use centred
position dots over an optional secondary-coloured Braille cone; they do not use
the warning fill policy or draw a connecting line. The storm widget adds only
forecast-position selection, its inclusive viewport policy, markers, cone, and
semantic styles;
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
