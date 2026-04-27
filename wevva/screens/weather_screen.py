"""Main weather screen.

Shows the primary weather grid (top bar, current conditions,
hourly forecast, daily views) with a header/footer. This keeps
the main UI self-contained as a `Screen` so the `App` can focus
on orchestration (search/help, data refresh, and screen routing).
"""

from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from wevva.alerts import Alert
from wevva.messages import (
    DaySelected,
    HourHighlighted,
    WeatherAlertsUpdated,
    WeatherFetchFailed,
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
from wevva.widgets.weather_alerts import WeatherAlertCard
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
        ('c', 'open_author', 'Credits'),  # Only screen-specific binding
        ('?', 'help', 'Help'),  # Context-aware help (AQ or general)
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._time_refresh_timer = None  # Track the 1-second update timer

    DEFAULT_CSS = """
    # Tooltip {
    #     # padding: 2 4;
    #     border: $primary;
    #     # color: auto 90%;
    # }

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
        # width: auto;
        # overflow-x: auto;
        margin: 0 0 1 0;
    }

    #daily-forecast {
        padding: 0 1;
        align-horizontal: center;
        align-vertical: middle;
        content-align: center middle;
        hatch: right $background-lighten-1;
        height: auto;
        # width: auto;
        # overflow-x: auto;
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
        # padding: 0 1;
        align-horizontal: center;
        align-vertical: middle;
        content-align: center middle;
        height: auto;
        width: 98;
        # border: round $primary;
        # border-title-color: $primary;
        # border-title-align: left;
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
        # margin: 0 0 1 0;
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
        yield self.saved_locations_sidebar

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

            # Weather alerts section (legacy container ID kept for CSS stability)
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

            # Daily forecast (7-day view) - temporarily disabled
            self.daily_forecast = Container(id='daily-forecast')
            with self.daily_forecast:
                yield DailyForecast()

            # Bottom info bar (misnamed Top) moved to the bottom
            self.bottom_info_bar = Container(id='lower-row')
            with self.bottom_info_bar:
                self.context_bar = ContextBar()
                yield self.context_bar
                # Air quality widget is mounted inside ContextBar

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
        self.update_saved_locations_sidebar()
        if not getattr(self.app, 'saved_locations', []):
            self.saved_locations_sidebar.display = False

    def update_saved_locations_sidebar(self) -> None:
        """Sync saved-location sidebar from app state."""
        if not hasattr(self, 'saved_locations_sidebar'):
            return
        locations = getattr(self.app, 'saved_locations', [])
        self.saved_locations_sidebar.set_locations(locations)
        if locations:
            self.saved_locations_sidebar.display = True

    def toggle_saved_locations_sidebar(self) -> None:
        """Show or hide the saved-location sidebar."""
        if not hasattr(self, 'saved_locations_sidebar'):
            return
        if not self.saved_locations_sidebar.is_mounted:
            return
        self.saved_locations_sidebar.display = not self.saved_locations_sidebar.display

    def update_saved_location_weather(self, location, summary: str) -> None:
        """Update compact weather text for one saved location."""
        if not hasattr(self, 'saved_locations_sidebar'):
            return
        self.saved_locations_sidebar.update_weather_summary(location, summary)

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

    # --- Messages ---
    async def on_weather_updated(self, event: WeatherUpdated) -> None:
        """Update all widgets with fresh weather data."""
        # Update header icon
        if self.app.emoji_enabled:
            self.header.icon = event.hourly.get_weather_code(0, return_emoji=True)
        else:
            self.header.icon = event.hourly.get_condition_abbreviation(0)

        # Explicitly post message to child widgets (messages don't auto-bubble to all descendants)
        self.context_bar.post_message(event)
        self.current_weather.post_message(event)
        self.hourly_forecast.post_message(event)
        self.weather_summary.post_message(event)

        daily = self.query_one(DailyForecast)
        daily.post_message(event)
        await self._render_alert_cards(event.alerts)

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
        """Render alerts that arrive after the main forecast content."""
        await self._render_alert_cards(event.alerts)

    def _refresh_time_display(self) -> None:
        """Periodically refresh time display in context bar."""
        self.context_bar.refresh_time_display()

    async def on_weather_fetch_failed(self, event: WeatherFetchFailed) -> None:
        self.app.notify(f'Weather fetch failed: {event.error}', severity='error')

    async def _render_alert_cards(self, alerts: list[Alert]) -> None:
        """Mount one alert card per alert, or none when there are no alerts."""
        await self.weather_warnings.remove_children()
        if not alerts:
            self.warnings_row.display = False
            self.weather_warnings.display = False
            return

        ordered_alerts = sorted(alerts, key=alert_sort_key)
        cards = [WeatherAlertCard(alert) for alert in ordered_alerts]
        await self.weather_warnings.mount(*cards)
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
