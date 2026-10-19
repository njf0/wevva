"""Main weather screen.

Shows the primary weather grid (top bar, current conditions,
hourly forecast, daily views) with a header/footer. This keeps
the main UI self-contained as a `Screen` so the `App` can focus
on orchestration (search/help, data refresh, and screen routing).
"""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Container
from textual.events import Resize
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from wevva.alerts import Alert
from wevva.config import location_key
from wevva.geography import short_location_name
from wevva.layout import (
    AuxiliaryPresentation,
    ContextPresentation,
    DEFAULT_LAYOUT_METRICS,
    WarningDensity,
    WeatherLayoutBudget,
    auxiliary_presentations_for,
    context_sidecar_eligible,
    weather_layout_for,
)
from wevva.messages import (
    DaySelected,
    HourHighlighted,
    WeatherAlertSelected,
    WeatherAlertsProgress,
    WeatherAlertsUpdated,
    WeatherUpdated,
)
from wevva.screens.air_quality_help import AirQualityHelp
from wevva.screens.author_screen import AuthorScreen
from wevva.screens.help import HelpScreen
from wevva.widgets.air_quality import AirQualityWidget
from wevva.widgets.context_bar import ContextBar
from wevva.widgets.current_conditions import CurrentConditions
from wevva.widgets.daily_forecast import DailyForecast
from wevva.widgets.hourly_forecast import HourlyForecast
from wevva.widgets.location_map import LocationMap
from wevva.widgets.saved_locations import SavedLocationsModal, SavedLocationsSidebar
from wevva.widgets.weather_alerts import (
    WeatherAlertDetailsSidebar,
    WeatherAlertSummary,
    WeatherAlertsModal,
    WeatherAlertsPanel,
)
from wevva.widgets.weather_summary import WeatherSummary

ALERT_SEVERITY_RANK = {
    'extreme': 5,
    'severe': 4,
    'moderate': 3,
    'minor': 2,
    'unknown': 1,
    # GeoMet risk color labels.
    'red': 5,
    'orange': 4,
    'amber': 4,
    'yellow': 3,
    'green': 2,
}

CityTemperatureLoader = Callable[
    [Sequence[tuple[float, float]], str],
    Awaitable[dict[tuple[float, float], float]],
]


def alert_sort_key(alert: Alert) -> tuple[int, str, str]:
    """Sort key for displaying most severe alerts first."""
    severity = (alert.severity or '').strip().lower()
    rank = ALERT_SEVERITY_RANK.get(severity, 0)
    return (
        -rank,
        (alert.event or '').lower(),
        (alert.headline or '').lower(),
    )


class WeatherScreen(Screen[None]):
    """Primary weather UI as a full screen.

    - Composes the header, footer, and all weather widgets.
    - Handles `WeatherUpdated` and related messages locally.
    - Keeps IDs stable to preserve existing CSS selectors.
    - App bindings (q/s/r/h) work automatically via inherit_bindings=False on App.
    """

    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ('t', 'tropical_systems', 'Tropical Systems'),
        ('c', 'open_author', 'Credits'),
        ('?', 'help', 'Help'),  # Context-aware help (AQ or general)
        ('l', 'locations', 'Locations'),
        ('i', 'alert_details', 'Warning details'),
        ('g', 'alerts_centre', 'Alerts Centre'),
        ('m', 'world_map', 'World Map'),
    ]
    def __init__(
        self,
        *args,
        city_temperature_loader: CityTemperatureLoader | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._city_temperature_loader = city_temperature_loader
        self._location_map_task: asyncio.Task[None] | None = None
        self._location_map_generation = 0
        self._time_refresh_timer = None  # Track the 1-second update timer
        self._locations_sidebar_has_content = False
        self._alert_details_sidebar_has_content = False
        self._local_alert_details_has_content = False
        self._alerts: list[Alert] = []
        self._layout_budget: WeatherLayoutBudget | None = None
        self._forecast_loading = False
        self._warning_checking = False

    DEFAULT_CSS = """
    #main-panel {
        layout: vertical;
        align-horizontal: center;
        align-vertical: middle;
        content-align: left top;
        width: 100%;
        height: 100%;
        min-width: 0;
        padding: 1 2;
        overflow: hidden hidden;
        hatch: right $background-lighten-1;
    }

    #weather-workspace {
        layout: vertical;
        align-horizontal: center;
        align-vertical: middle;
        width: 100%;
        height: auto;
        min-width: 0;
        margin: 0;
        hatch: right $background-lighten-1;
    }

    #forecast-column {
        layout: vertical;
        align-horizontal: center;
        width: 100%;
        height: auto;
        min-width: 0;
        margin: 0;
        hatch: right $background-lighten-1;
    }

    #top-row {
        layout: horizontal;
        align-horizontal: center;
        align-vertical: middle;
        width: auto;
        height: auto;
        margin: 0 0 1 0;
    }

    #next-24-hours-table {
        padding: 0;
        width: 100%;
        min-width: 0;
        align-horizontal: center;
        align-vertical: middle;
        content-align: center middle;
        hatch: right $background-lighten-1;
        height: auto;
        margin: 0 0 1 0;
    }

    #daily-forecast {
        padding: 0;
        width: 100%;
        min-width: 0;
        align-horizontal: center;
        align-vertical: middle;
        content-align: center middle;
        hatch: right $background-lighten-1;
        height: auto;
        margin: 0;
    }

    #summary-row {
        layout: horizontal;
        align-horizontal: center;
        align-vertical: top;
        content-align: center middle;
        width: 100%;
        height: 4;
        margin: 0;
        hatch: right $background-lighten-1;
    }

    #warnings-row {
        layout: horizontal;
        align-horizontal: center;
        align-vertical: top;
        content-align: center middle;
        width: 100%;
        height: 4;
        hatch: right $background-lighten-1;
    }

    #current-conditions-row {
        layout: horizontal;
        align-horizontal: center;
        align-vertical: top;
        width: 100%;
        height: 7;
        margin: 0 0 1 0;
        hatch: right $background-lighten-1;
    }

    #weather-summary {
        align-horizontal: left;
        align-vertical: middle;
        content-align: center middle;
        height: 3;
        width: 100%;
    }


    #context-row {
        layout: horizontal;
        align-horizontal: center;
        align-vertical: top;
        width: 100%;
        height: 17;
        margin: 0;
        hatch: right $background-lighten-1;
    }

    #lower-row {
        layout: grid;
        grid-size: 2 1;
        grid-columns: 1fr 1fr;
        grid-gutter: 0 2;
        width: 98;
        max-width: 100%;
        height: 17;
        margin: 0;
        hatch: right $background-lighten-1;
    }

    #lower-row > ContextBar,
    #lower-row > LocationMap {
        width: 100%;
        height: 17;
        margin: 0;
    }

    #weather-warnings {
        layout: vertical;
        align-horizontal: left;
        align-vertical: middle;
        width: 100%;
        max-width: 98;
        height: 3;
        content-align: center middle;
        overflow: hidden hidden;
        hatch: right $background-lighten-1;
    }

    #credits {
        height: auto;
        width: auto;
        align-horizontal: center;
        align-vertical: middle;
        content-align: center middle;
        margin: 0 0 0 0;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose the main weather screen layout."""
        # Header
        self.header = Header(show_clock=True)
        yield self.header

        # Main panel content mirrors the prior App layout
        self.main_panel = Container(id='main-panel')
        self.saved_locations_sidebar = SavedLocationsSidebar()
        self.alert_details_sidebar = WeatherAlertDetailsSidebar()
        yield self.saved_locations_sidebar
        yield self.alert_details_sidebar

        with self.main_panel:
            # Error banner area (hidden by default)
            self.error_banner = Static('', id='error-banner')
            self.error_banner.display = False
            yield self.error_banner

            self.weather_workspace = Container(id='weather-workspace')
            with self.weather_workspace:
                self.forecast_column = Container(id='forecast-column')
                with self.forecast_column:
                    # Summary row: formatted text after top info
                    self.summary_row = Container(id='summary-row')
                    with self.summary_row:
                        self.weather_summary = WeatherSummary()
                        yield self.weather_summary

                    self.warnings_row = Container(id='warnings-row')
                    with self.warnings_row:
                        self.weather_warnings = Container(id='weather-warnings')
                        yield self.weather_warnings

                    # Current conditions: tiles + compact tables
                    self.current_weather_row = Container(id='current-conditions-row')
                    with self.current_weather_row:
                        self.current_weather = CurrentConditions(classes='current-weather')
                        yield self.current_weather

                    # Next 24 hours table (owns HourlyForecast)
                    self.next_24_hours = Container(id='next-24-hours-table')
                    with self.next_24_hours:
                        yield HourlyForecast()

                    # Daily forecast (7-day view)
                    self.daily_forecast = Container(id='daily-forecast')
                    with self.daily_forecast:
                        yield DailyForecast()

                self.context_row = Container(id='context-row')
                with self.context_row:
                    self.bottom_info_bar = Container(id='lower-row')
                    with self.bottom_info_bar:
                        self.context_bar = ContextBar()
                        yield self.context_bar
                        self.location_map = LocationMap()
                        yield self.location_map

        # Footer (credits moved to a dedicated screen)
        yield Footer()

    # Property accessors for child widgets
    @property
    def hourly_forecast(self) -> HourlyForecast:
        return self.query_one(HourlyForecast)

    def on_mount(self) -> None:
        # Hide empty content unless the initial request is already loading.
        self.main_panel.display = self._forecast_loading
        self.weather_workspace.loading = self._forecast_loading
        self._sync_activity_subtitle()
        self.warnings_row.display = False
        self.weather_warnings.display = False
        self.update_saved_locations_sidebar()

    def on_unmount(self) -> None:
        if self._location_map_task is not None:
            self._location_map_task.cancel()
            self._location_map_task = None

    def set_warning_checking(self, checking: bool) -> None:
        """Show transient warning-query activity in the header subtitle."""

        self._warning_checking = checking
        self._sync_activity_subtitle()

    def set_forecast_loading(self, loading: bool) -> None:
        """Cover stale forecast content while a new forecast is requested."""

        self._forecast_loading = loading
        if hasattr(self, 'weather_workspace'):
            if loading:
                self.main_panel.display = True
            self.weather_workspace.loading = loading
        self._sync_activity_subtitle()

    def _sync_activity_subtitle(self) -> None:
        """Render the highest-priority weather-screen activity in the header."""

        if self._forecast_loading:
            place = short_location_name(getattr(self.app, 'location', None))
            subtitle = f'Fetching forecast for {place}…'
        elif self._warning_checking:
            subtitle = 'Checking warnings…'
        else:
            subtitle = 'Powered by Open-Meteo'
        self.sub_title = subtitle
        self.app.sub_title = subtitle

    @property
    def saved_locations_sidebar_visible(self) -> bool:
        """Whether the saved-locations sidebar is currently on screen."""
        return bool(
            getattr(getattr(self, 'saved_locations_sidebar', None), 'display', False)
        )

    @property
    def alert_details_sidebar_visible(self) -> bool:
        """Whether the alert-details sidebar is currently on screen."""
        return bool(
            getattr(getattr(self, 'alert_details_sidebar', None), 'display', False)
        )

    def _sync_sidebar_visibility(self, *, viewport_height: int | None = None) -> None:
        """Derive rail visibility from available width and available content."""
        if viewport_height is None:
            viewport_height = max(1, self.size.height - 2)
        context_sidecar = context_sidecar_eligible(
            self.size.width,
            viewport_height,
            has_warnings=bool(self._alerts),
        )
        (
            _usable_width,
            locations_presentation,
            warning_presentation,
        ) = auxiliary_presentations_for(
            self.size.width,
            locations_available=self._locations_sidebar_has_content,
            warning_details_available=self._alert_details_sidebar_has_content,
            context_sidecar=context_sidecar,
        )
        if hasattr(self, 'saved_locations_sidebar'):
            self.saved_locations_sidebar.display = (
                locations_presentation is AuxiliaryPresentation.SIDEBAR
            )
        if hasattr(self, 'alert_details_sidebar'):
            self.alert_details_sidebar.display = (
                warning_presentation is AuxiliaryPresentation.SIDEBAR
            )
        if self.is_mounted:
            self.refresh_bindings()
            self.call_after_refresh(self._apply_layout)

    def on_resize(self, event: Resize) -> None:
        """Reallocate context and automatic rails when geometry changes."""
        self._sync_sidebar_visibility(viewport_height=max(1, event.size.height - 2))

    def _apply_layout(self) -> None:
        """Apply one pure budget decision to stable mounted weather widgets."""

        if not hasattr(self, 'main_panel') or not self.main_panel.is_mounted:
            return
        viewport = self.main_panel.region
        if viewport.width <= 0 or viewport.height <= 0:
            return

        budget = weather_layout_for(
            self.size.width,
            viewport.height,
            has_warnings=bool(self._alerts),
            locations_requested=self._locations_sidebar_has_content,
            warning_details_requested=self._alert_details_sidebar_has_content,
        )
        if budget == self._layout_budget:
            return
        self._layout_budget = budget
        self.summary_row.display = budget.show_summary
        self.weather_summary.set_layout(budget.usable_width)
        self.warnings_row.styles.height = (
            budget.warning_height if self._alerts else 0
        )
        self.weather_warnings.styles.height = (
            budget.warning_card_height if self._alerts else 0
        )
        if self._alerts:
            self.weather_alert_summary.display = (
                budget.warning_density is WarningDensity.SUMMARY
            )
            self.weather_alert_panel.display = (
                budget.warning_density is WarningDensity.TABBED
            )
        self.current_weather.set_layout(
            budget.current_density,
            budget.current_height,
            budget.detail_rows,
            budget.full_detail_labels,
        )
        self.current_weather_row.styles.height = budget.current_height
        self.hourly_forecast.set_layout(budget.hourly_rows)
        hourly_height = (
            DEFAULT_LAYOUT_METRICS.hourly_chrome_rows + len(budget.hourly_rows)
        )
        self.next_24_hours.styles.height = hourly_height

        daily = self.query_one(DailyForecast)
        daily.set_layout(budget.daily_columns, budget.daily_row_count)
        self.daily_forecast.display = budget.daily_row_count > 0
        self.next_24_hours.styles.margin = (
            (0, 0, 1, 0) if budget.daily_row_count else (0, 0, 0, 0)
        )
        self.daily_forecast.styles.height = (
            DEFAULT_LAYOUT_METRICS.daily_chrome_rows + budget.daily_row_count
            if budget.daily_row_count
            else 0
        )

        show_context = budget.show_context_matrix and self.location_map.available
        context_sidecar = (
            show_context
            and budget.context_presentation is ContextPresentation.SIDECAR
        )
        context_height = budget.context_height if show_context else 0
        self.context_bar.set_layout(
            row_count=budget.context_detail_rows,
            height=budget.context_table_height,
            narrow=(context_sidecar or budget.usable_width < 96),
            show_air_quality=not context_sidecar,
        )
        self.location_map.set_layout_height(
            budget.context_map_height if show_context else None,
            max_place_labels=(
                DEFAULT_LAYOUT_METRICS.context_sidecar_place_labels
                if context_sidecar
                else None
            ),
        )
        self.context_row.display = show_context
        self.bottom_info_bar.display = show_context
        self.location_map.display = show_context
        self.context_row.styles.height = context_height
        self.bottom_info_bar.styles.height = context_height

        forecast_height = budget.used_rows - DEFAULT_LAYOUT_METRICS.outer_vertical_padding
        if (
            show_context
            and budget.context_presentation is ContextPresentation.BOTTOM
        ):
            # Keep the final forecast gutter inside this column so the daily
            # table's bottom margin paints a deliberate hatch row immediately
            # above the lower context matrix.
            forecast_height -= budget.context_height
        self.forecast_column.styles.height = forecast_height

        if context_sidecar:
            self.weather_workspace.styles.layout = 'horizontal'
            self.weather_workspace.styles.width = 140
            self.weather_workspace.styles.height = max(
                forecast_height,
                budget.context_height,
            )
            self.forecast_column.styles.width = 98
            self.context_row.styles.width = 40
            self.context_row.styles.margin = (0, 0, 0, 2)
            self.bottom_info_bar.styles.width = 40
            self.bottom_info_bar.styles.max_width = 40
            self.bottom_info_bar.styles.grid_size_columns = 1
            self.bottom_info_bar.styles.grid_size_rows = 2
            self.bottom_info_bar.styles.grid_columns = ('1fr',)
            self.bottom_info_bar.styles.grid_rows = (
                budget.context_table_height,
                budget.context_map_height,
            )
            # Textual's grid resolver applies the named horizontal gutter to
            # rows and the named vertical gutter to columns. Keep the one-cell
            # visual gap on the sidecar's row axis.
            self.bottom_info_bar.styles.grid_gutter_horizontal = (
                DEFAULT_LAYOUT_METRICS.context_sidecar_gutter_rows
            )
            self.bottom_info_bar.styles.grid_gutter_vertical = 0
        else:
            self.weather_workspace.styles.layout = 'vertical'
            self.weather_workspace.styles.width = '100%'
            self.weather_workspace.styles.height = (
                forecast_height
                + (budget.context_height if show_context else 0)
            )
            self.forecast_column.styles.width = '100%'
            self.context_row.styles.width = '100%'
            self.context_row.styles.margin = 0
            self.bottom_info_bar.styles.width = 98
            self.bottom_info_bar.styles.max_width = '100%'
            self.bottom_info_bar.styles.grid_size_columns = 2
            self.bottom_info_bar.styles.grid_size_rows = 1
            self.bottom_info_bar.styles.grid_columns = ('1fr', '1fr')
            self.bottom_info_bar.styles.grid_rows = (budget.context_table_height,)
            # See the sidecar branch above: this is the visual column gap.
            self.bottom_info_bar.styles.grid_gutter_horizontal = 0
            self.bottom_info_bar.styles.grid_gutter_vertical = 2
        self.daily_forecast.styles.margin = (
            (0, 0, 1, 0)
            if (
                show_context
                and budget.context_presentation is ContextPresentation.BOTTOM
            )
            else (0, 0, 0, 0)
        )

    def update_saved_locations_sidebar(self) -> None:
        """Sync saved-location sidebar from app state."""
        if not hasattr(self, 'saved_locations_sidebar'):
            return
        locations = list(getattr(self.app, 'saved_locations', []))
        current_location = getattr(self.app, 'location', None)
        if (
            current_location is not None
            and current_location.latitude is not None
            and current_location.longitude is not None
        ):
            saved_keys = {location_key(location) for location in locations}
            if location_key(current_location) not in saved_keys:
                locations.append(current_location)
        self.saved_locations_sidebar.set_locations(locations)
        has_content = bool(locations)
        if has_content != self._locations_sidebar_has_content:
            self._layout_budget = None
        self._locations_sidebar_has_content = has_content
        self._sync_sidebar_visibility()

    def update_saved_location_weather(self, location, summary: str) -> None:
        """Update compact weather text for one saved location."""
        if not hasattr(self, 'saved_locations_sidebar'):
            return
        self.saved_locations_sidebar.update_weather_summary(location, summary)

    def saved_location_weather_summary(self, location):
        """Return the cached sidebar summary for one saved location, if any."""
        if not hasattr(self, 'saved_locations_sidebar'):
            return None
        return self.saved_locations_sidebar.weather_summary(location)

    def selected_saved_location(self):
        """Return the highlighted saved location from the sidebar."""
        active_screen = self.app.screen
        if isinstance(active_screen, SavedLocationsModal):
            return active_screen.selected_location()
        if not hasattr(self, 'saved_locations_sidebar'):
            return None
        return self.saved_locations_sidebar.selected_location()

    # --- Actions ---
    def action_open_author(self) -> None:
        """Open the Author/Credits screen."""
        self.app.push_screen(AuthorScreen())

    def action_world_map(self) -> None:
        """Open the spatial overview of sidebar locations."""

        self.app.open_world_locations_screen()

    async def action_tropical_systems(self) -> None:
        """Open the dedicated active tropical-system workspace."""
        await self.app.open_tropical_systems_screen()

    def action_alerts_centre(self) -> None:
        """Open the country-level alert discovery workspace."""

        self.app.open_alerts_centre_screen()

    def action_help(self) -> None:
        """Show help screen - air quality help if AQ widget is focused, else general help."""
        # Check if the Air Quality widget is focused
        focused = self.app.focused
        if isinstance(focused, AirQualityWidget):
            self.app.push_screen(AirQualityHelp())
        else:
            # Default help
            self.app.push_screen(HelpScreen())

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Expose auxiliary access actions only when they have content."""
        if action == 'locations':
            return self._locations_sidebar_has_content
        if action == 'alert_details':
            return self._alert_details_sidebar_has_content
        return super().check_action(action, parameters)

    def action_locations(self) -> None:
        """Focus the automatic rail or open its modal fallback."""
        if self.saved_locations_sidebar_visible:
            self.saved_locations_sidebar.locations.focus()
        else:
            self.app.push_screen(SavedLocationsModal(self.saved_locations_sidebar))

    def action_alert_details(self) -> None:
        """Focus the automatic rail or open the tabbed warning reader."""
        if self.alert_details_sidebar_visible:
            self.alert_details_sidebar.details.focus()
        elif self._alerts:
            self.app.push_screen(WeatherAlertsModal(self._alerts))

    # --- Messages ---
    async def on_weather_updated(self, event: WeatherUpdated) -> None:
        """Update all widgets with fresh weather data."""
        self.header.icon = ''
        if self.app.emoji_enabled:
            self.header.icon = event.hourly.get_condition_emoji(0)

        # Forward directly so the bubbling message isn't re-handled by this screen.
        await self.context_bar.on_weather_updated(event)
        await self.current_weather.on_weather_updated(event)
        self._refresh_location_map(event.current)
        await self.hourly_forecast.on_weather_updated(event)
        await self.weather_summary.on_weather_updated(event)

        daily = self.query_one(DailyForecast)
        await daily.on_weather_updated(event)
        await self.render_alert_panel(event.alerts)

        # Reveal main panel and clear errors on success
        main_panel = self.query_one('#main-panel')
        main_panel.display = True
        self.error_banner.update('')
        self.error_banner.display = False
        self.set_forecast_loading(False)

        # Start time refresh timer after data arrives (updates every second)
        if self._time_refresh_timer is None:
            self._time_refresh_timer = self.set_interval(1, self._refresh_time_display)

    def _refresh_location_map(self, current: object | None = None) -> None:
        """Render country context now and enrich city temperatures in the background."""
        self._layout_budget = None
        self._location_map_generation += 1
        generation = self._location_map_generation
        if self._location_map_task is not None and not self._location_map_task.done():
            self._location_map_task.cancel()
        current_temperature = None
        get_temperature = getattr(current, 'get_temperature', None)
        if callable(get_temperature):
            current_temperature = get_temperature()
        temperature_unit = getattr(self.app, 'temperature_unit', 'celsius')
        self.location_map.update_location(
            getattr(self.app, 'location', None),
            current_temperature=current_temperature,
            temperature_unit=temperature_unit,
        )
        coordinates = self.location_map.city_coordinates
        if self._city_temperature_loader is None or not coordinates:
            self._location_map_task = None
            return
        self._location_map_task = asyncio.create_task(
            self._load_location_map_temperatures(
                coordinates,
                generation,
                temperature_unit,
            )
        )

    async def _load_location_map_temperatures(
        self,
        coordinates: Sequence[tuple[float, float]],
        generation: int,
        temperature_unit: str,
    ) -> None:
        """Apply city readings only to the location generation that requested them."""
        try:
            temperatures = await self._city_temperature_loader(
                coordinates,
                temperature_unit,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            return
        if generation != self._location_map_generation or not self.location_map.is_attached:
            return
        self.location_map.update_temperatures(
            temperatures,
            temperature_unit=temperature_unit,
        )

    async def on_weather_alerts_updated(self, event: WeatherAlertsUpdated) -> None:
        """Render the weather-alert tab panel."""
        await self.render_alert_panel(event.alerts)

    def on_weather_alerts_progress(self, event: WeatherAlertsProgress) -> None:
        """Forward individual warning work to the saved-locations sidebar."""
        self.saved_locations_sidebar.update_warning_progress(event.event, event.payload)

    def on_weather_alert_selected(self, event: WeatherAlertSelected) -> None:
        """Show full text for the selected alert in the details sidebar."""
        self.alert_details_sidebar.update_alert(event.alert)
        self._local_alert_details_has_content = True
        self._sync_alert_sidebar_content()
        self._sync_sidebar_visibility()

    def _sync_alert_sidebar_content(self) -> None:
        has_content = self._local_alert_details_has_content
        if has_content != self._alert_details_sidebar_has_content:
            self._layout_budget = None
        self._alert_details_sidebar_has_content = has_content

    def _refresh_time_display(self) -> None:
        """Periodically refresh time display in context bar."""
        self.context_bar.refresh_time_display()

    async def render_alert_panel(self, alerts: list[Alert]) -> None:
        """Mount the fixed-height warning summary, or none when empty."""
        self.saved_locations_sidebar.clear_warning_progress()
        ordered_alerts = sorted(alerts, key=alert_sort_key)
        if ordered_alerts == self._alerts:
            self._sync_sidebar_visibility()
            return

        self._layout_budget = None
        await self.weather_warnings.remove_children()
        self._alerts = ordered_alerts
        if not ordered_alerts:
            self.warnings_row.display = False
            self.weather_warnings.display = False
            self._local_alert_details_has_content = False
            self._sync_alert_sidebar_content()
            self._sync_sidebar_visibility()
            return

        self.alert_details_sidebar.update_alert(ordered_alerts[0])
        self._local_alert_details_has_content = True
        self._sync_alert_sidebar_content()
        self._sync_sidebar_visibility()
        self.weather_alert_summary = WeatherAlertSummary(ordered_alerts)
        self.weather_alert_panel = WeatherAlertsPanel(ordered_alerts)
        self.weather_alert_panel.display = False
        await self.weather_warnings.mount(
            self.weather_alert_summary,
            self.weather_alert_panel,
        )
        self.warnings_row.display = True
        self.weather_warnings.display = True

    async def on_hour_highlighted(self, message: HourHighlighted) -> None:  # type: ignore[override]
        """Forward hour selection to current conditions row.

        Messages bubble up from `HourlyForecast`; invoke the sibling's handler
        directly to avoid rebroadcast loops.
        """
        await self.current_weather.on_hour_highlighted(message)
        await self.weather_summary.on_hour_highlighted(message)
        # Forward hour highlight to ContextBar (which forwards to air quality widget)
        self.context_bar.on_hour_highlighted(message.index)

    def on_day_selected(self, message: DaySelected) -> None:  # type: ignore[override]
        """Forward daily table row selection to the hourly forecast tabs."""
        # Forward to sibling widget directly (messages don't auto-broadcast laterally).
        self.hourly_forecast.on_day_selected(message)
