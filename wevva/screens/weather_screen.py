"""Main weather screen.

Shows the primary weather grid (top bar, current conditions,
hourly forecast, daily views) with a header/footer. This keeps
the main UI self-contained as a `Screen` so the `App` can focus
on orchestration (search/help, data refresh, and screen routing).
"""

from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Container
from textual.events import Resize
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from wevva.alerts import Alert
from wevva.config import location_key
from wevva.messages import (
    DaySelected,
    HourHighlighted,
    NearbyTropicalSystemSelected,
    TropicalSystemsProgress,
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
from wevva.widgets.saved_locations import SavedLocationsSidebar
from wevva.widgets.weather_alerts import WeatherAlertDetailsSidebar, WeatherAlertsPanel
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
        ('c', 'open_author', 'Credits'),
        ('?', 'help', 'Help'),  # Context-aware help (AQ or general)
        ('l', 'show_saved_locations', 'Show locations'),
        ('l', 'hide_saved_locations', 'Hide locations'),
        ('i', 'show_alert_details', 'Show details'),
        ('i', 'hide_alert_details', 'Hide details'),
    ]

    # The main forecast content is 98 columns wide. At 144 columns the left
    # sidebar fits comfortably. With both 40-column sidebars, 186 columns
    # preserves the same two-column gutter around the 98-column main content.
    LOCATIONS_SIDEBAR_MIN_WIDTH = 144
    ALERT_DETAILS_SIDEBAR_MIN_WIDTH = 186

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._time_refresh_timer = None  # Track the 1-second update timer
        self._locations_sidebar_requested = False
        self._alert_details_sidebar_requested = False
        self._locations_sidebar_has_content = False
        self._alert_details_sidebar_has_content = False
        self._locations_sidebar_width_collapsed = False
        self._alert_details_sidebar_width_collapsed = False

    DEFAULT_CSS = """
    #main-panel {
        layout: vertical;
        align-horizontal: center;
        align-vertical: middle;
        content-align: center middle;
        overflow-y: auto;
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
        padding: 0 1;
        align-horizontal: center;
        align-vertical: middle;
        content-align: center middle;
        hatch: right $background-lighten-1;
        height: auto;
        margin: 0 0 1 0;
    }

    #daily-forecast {
        padding: 0 1;
        align-horizontal: center;
        align-vertical: middle;
        content-align: center middle;
        hatch: right $background-lighten-1;
        height: auto;
        margin: 0 0 1 0;
    }

    #summary-row {
        layout: horizontal;
        align-horizontal: center;
        align-vertical: middle;
        content-align: center middle;
        width: 100%;
        height: auto;
        margin: 0 0 1 0;
        hatch: right $background-lighten-1;
    }

    #warnings-row {
        layout: horizontal;
        align-horizontal: center;
        align-vertical: middle;
        content-align: center middle;
        width: 100%;
        height: auto;
        hatch: right $background-lighten-1;
    }

    #weather-summary {
        align-horizontal: center;
        align-vertical: middle;
        content-align: center middle;
        height: auto;
        width: 98;
    }


    #lower-row {
        layout: horizontal;
        grid-gutter: 1 2;
        align-horizontal: center;
        content-align: center middle;
        align-vertical: middle;
        height: auto;
        width: auto;
    }

    #weather-warnings {
        layout: vertical;
        align-horizontal: center;
        align-vertical: middle;
        width: auto;
        height: auto;
        content-align: center middle;
        overflow-y: auto;
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

            self.bottom_info_bar = Container(id='lower-row')
            with self.bottom_info_bar:
                self.context_bar = ContextBar()
                yield self.context_bar

        # Footer (credits moved to a dedicated screen)
        yield Footer()

    # Property accessors for child widgets
    @property
    def hourly_forecast(self) -> HourlyForecast:
        return self.query_one(HourlyForecast)

    def on_mount(self) -> None:
        # Hide content until weather data arrives
        self.sub_title = 'Weather data from Open-Meteo'
        self.app.sub_title = 'Weather data from Open-Meteo'
        self.query_one('#main-panel').display = False
        self.warnings_row.display = False
        self.weather_warnings.display = False
        (
            self._locations_sidebar_requested,
            self._alert_details_sidebar_requested,
        ) = self._sidebar_defaults_for_width(self.size.width)
        self.update_saved_locations_sidebar()

    @classmethod
    def _sidebar_defaults_for_width(cls, width: int) -> tuple[bool, bool]:
        """Return initial visibility preferences for the available terminal width."""
        return (
            width >= cls.LOCATIONS_SIDEBAR_MIN_WIDTH,
            width >= cls.ALERT_DETAILS_SIDEBAR_MIN_WIDTH,
        )

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

    def _sync_sidebar_visibility(self) -> None:
        """Apply the user's visibility choices when each sidebar has content."""
        if hasattr(self, 'saved_locations_sidebar'):
            self.saved_locations_sidebar.display = (
                self._locations_sidebar_requested
                and self._locations_sidebar_has_content
                and not self._locations_sidebar_width_collapsed
            )
        if hasattr(self, 'alert_details_sidebar'):
            self.alert_details_sidebar.display = (
                self._alert_details_sidebar_requested
                and self._alert_details_sidebar_has_content
                and not self._alert_details_sidebar_width_collapsed
            )
        if self.is_mounted:
            self.refresh_bindings()

    def on_resize(self, event: Resize) -> None:
        """Collapse sidebars that no longer fit, restoring them if space returns."""
        self._locations_sidebar_width_collapsed = (
            event.size.width < self.LOCATIONS_SIDEBAR_MIN_WIDTH
        )
        self._alert_details_sidebar_width_collapsed = (
            event.size.width < self.ALERT_DETAILS_SIDEBAR_MIN_WIDTH
        )
        self._sync_sidebar_visibility()

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
        self._locations_sidebar_has_content = bool(locations)
        self._sync_sidebar_visibility()

    def toggle_saved_locations_sidebar(self) -> None:
        """Show or hide the saved-location sidebar."""
        self.set_saved_locations_sidebar_visible(
            not self.saved_locations_sidebar_visible
        )

    def set_saved_locations_sidebar_visible(self, visible: bool) -> None:
        """Remember and apply the saved-location sidebar visibility choice."""
        self._locations_sidebar_requested = visible
        if visible:
            self._locations_sidebar_width_collapsed = False
        self._sync_sidebar_visibility()

    def set_alert_details_sidebar_visible(self, visible: bool) -> None:
        """Remember and apply the alert-details sidebar visibility choice."""
        self._alert_details_sidebar_requested = visible
        if visible:
            self._alert_details_sidebar_width_collapsed = False
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
        if not hasattr(self, 'saved_locations_sidebar'):
            return None
        return self.saved_locations_sidebar.selected_location()

    # --- Actions ---
    def action_open_author(self) -> None:
        """Open the Author/Credits screen."""
        self.app.push_screen(AuthorScreen())

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
        """Expose only the visibility action that matches each sidebar's state."""
        if action == 'show_saved_locations':
            return (
                self._locations_sidebar_has_content
                and not self.saved_locations_sidebar_visible
            )
        if action == 'hide_saved_locations':
            return self.saved_locations_sidebar_visible
        if action == 'show_alert_details':
            return (
                self._alert_details_sidebar_has_content
                and not self.alert_details_sidebar_visible
            )
        if action == 'hide_alert_details':
            return self.alert_details_sidebar_visible
        return super().check_action(action, parameters)

    def action_show_saved_locations(self) -> None:
        """Show the saved-location sidebar."""
        self.set_saved_locations_sidebar_visible(True)

    def action_hide_saved_locations(self) -> None:
        """Hide the saved-location sidebar."""
        self.set_saved_locations_sidebar_visible(False)

    def action_show_alert_details(self) -> None:
        """Show the selected warning or tropical-system details."""
        self.set_alert_details_sidebar_visible(True)

    def action_hide_alert_details(self) -> None:
        """Hide the warning and tropical-system details sidebar."""
        self.set_alert_details_sidebar_visible(False)

    # --- Messages ---
    async def on_weather_updated(self, event: WeatherUpdated) -> None:
        """Update all widgets with fresh weather data."""
        self.header.icon = ''
        if self.app.emoji_enabled:
            self.header.icon = event.hourly.get_condition_emoji(0)

        # Explicitly post message to child widgets (messages don't auto-bubble to all descendants)
        self.context_bar.post_message(event)
        self.current_weather.post_message(event)
        self.hourly_forecast.post_message(event)
        self.weather_summary.post_message(event)

        daily = self.query_one(DailyForecast)
        daily.post_message(event)
        await self.render_alert_panel(event.alerts)

        # Reveal main panel and clear errors on success
        main_panel = self.query_one('#main-panel')
        main_panel.display = True
        self.error_banner.update('')
        self.error_banner.display = False

        # Reveal bottom info bar once data is present
        self.bottom_info_bar.display = True

        # Start time refresh timer after data arrives (updates every second)
        if self._time_refresh_timer is None:
            self._time_refresh_timer = self.set_interval(1, self._refresh_time_display)

    async def on_weather_alerts_updated(self, event: WeatherAlertsUpdated) -> None:
        """Render the combined alert and tropical-system tab panel."""
        await self.render_alert_panel(
            event.alerts,
            event.tropical_systems,
            tropical_systems_pending=event.tropical_systems_pending,
        )

    def on_weather_alerts_progress(self, event: WeatherAlertsProgress) -> None:
        """Forward individual warning work to the saved-locations sidebar."""
        self.saved_locations_sidebar.update_warning_progress(event.event, event.payload)

    def on_tropical_systems_progress(self, event: TropicalSystemsProgress) -> None:
        """Forward tropical fetch and local matching work to the sidebar."""
        if event.event == 'tropical_finished':
            self.saved_locations_sidebar.clear_tropical_progress()
            return
        self.saved_locations_sidebar.update_tropical_progress(event.event, event.payload)

    def on_weather_alert_selected(self, event: WeatherAlertSelected) -> None:
        """Show full text for the selected alert in the details sidebar."""
        self.alert_details_sidebar.update_alert(event.alert)
        self._alert_details_sidebar_has_content = True
        self._sync_sidebar_visibility()

    def on_nearby_tropical_system_selected(self, event: NearbyTropicalSystemSelected) -> None:
        """Show supplementary facts for the selected tropical-system tab."""
        self.alert_details_sidebar.update_tropical_system(event.system)
        self._alert_details_sidebar_has_content = True
        self._sync_sidebar_visibility()

    def _refresh_time_display(self) -> None:
        """Periodically refresh time display in context bar."""
        self.context_bar.refresh_time_display()

    async def render_alert_panel(
        self,
        alerts: list[Alert],
        tropical_systems=None,
        *,
        tropical_systems_pending: bool = False,
    ) -> None:
        """Mount nearby systems before ordinary alert tabs, or none when empty."""
        await self.weather_warnings.remove_children()
        self.saved_locations_sidebar.clear_warning_progress()
        if not tropical_systems_pending:
            self.saved_locations_sidebar.clear_tropical_progress()
        tropical_systems = tropical_systems or []
        if not alerts and not tropical_systems:
            self.warnings_row.display = False
            self.weather_warnings.display = False
            self._alert_details_sidebar_has_content = False
            self._sync_sidebar_visibility()
            return

        ordered_alerts = sorted(alerts, key=alert_sort_key)
        if tropical_systems:
            self.alert_details_sidebar.update_tropical_system(tropical_systems[0])
        else:
            self.alert_details_sidebar.update_alert(ordered_alerts[0])
        self._alert_details_sidebar_has_content = True
        self._sync_sidebar_visibility()
        await self.weather_warnings.mount(
            WeatherAlertsPanel(ordered_alerts, tropical_systems=tropical_systems)
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
