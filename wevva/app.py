"""Textual TUI for displaying weather forecasts and warnings (mini version).

Public-facing code should be easy to scan; this file adds concise
comments to highlight major blocks, actions, and message handlers.
Behavior remains unchanged.
"""

from typing import ClassVar

from textual.app import App

from wevva.controller import WeatherController  # central async orchestrator
from wevva.location_metadata import LocationMetadata
from wevva.messages import PlaceSelected, WeatherFetchFailed, WeatherUpdated
from wevva.screens.help import HelpScreen
from wevva.screens.search_screen import SearchScreen
from wevva.screens.settings_screen import SettingsScreen
from wevva.screens.weather_screen import WeatherScreen


class Wevva(App, inherit_bindings=False):
    """Minimal textual weather app showing current, next 24h, daily and warnings.

    - Message-first architecture: widgets react to `WeatherUpdated`.
    - Compose once, then update in place for new data.
    - Keep IDs stable to maintain `wevva.tcss` compatibility.
    """

    CSS_PATH = "wevva.tcss"  # single theme stylesheet
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("q", "quit", "Quit"),  # exit the app
        ("s", "search", "Search"),  # open place search screen
        ("r", "refresh", "Refresh"),  # fetch latest forecast
        ("h", "help", "Help"),  # show quick help
        ("u", "settings", "Units"),  # open settings
    ]

    def __init__(
        self,
        initial_location: LocationMetadata | None = None,
        emoji_enabled: bool = True,
        theme_name: str | None = None,
        temperature_unit: str = "celsius",
        wind_speed_unit: str = "kmh",
        precipitation_unit: str = "mm",
        **kwargs,
    ):
        """Initialize application (no postcode required; starts with place search).

        Sets up controller, location state, and a refresh guard.
        """
        super().__init__(**kwargs)
        self.controller = WeatherController(
            temperature_unit=temperature_unit,
            wind_speed_unit=wind_speed_unit,
            precipitation_unit=precipitation_unit,
        )
        self.sub_title = (
            "Weather data from Open-Meteo"  # static subtitle for all screens
        )
        self.forecast_metadata = None  # LocationMetadata after first fetch
        # unified location context (holds geocoded place + last forecast metadata)
        self.location = initial_location or LocationMetadata()  # set from CLI or search
        # Track whether the app started with a CLI-provided location and any successful fetch yet
        self.started_with_cli_location = initial_location is not None
        self._has_successful_fetch = False
        # guard to prevent overlapping refreshes
        self._refresh_in_flight = False  # debounce concurrent refreshes
        # Emoji rendering toggle (widgets can read via self.app.emoji_enabled)
        self.emoji_enabled = bool(emoji_enabled)
        # Store unit preferences for widgets
        self.temperature_unit = temperature_unit
        self.wind_speed_unit = wind_speed_unit
        self.precipitation_unit = precipitation_unit
        # Initialize main weather screen once
        self.weather_screen = WeatherScreen()
        # Theme selection from CLI (validated by Textual during assignment)
        if theme_name is not None:
            self.theme = theme_name

    async def on_mount(self):
        """Start with search screen, or if location provided via CLI, fetch weather directly."""
        if self.location.latitude is not None and self.location.longitude is not None:
            self.push_screen(self.weather_screen)
            await self.action_refresh()
        else:
            self.push_screen(SearchScreen())

    # ------------------------------------------------------------
    # Actions / key bindings
    # ------------------------------------------------------------
    async def action_refresh(self) -> None:
        """Fetch via controller and broadcast `WeatherUpdated`.

        Uses an in-flight guard to prevent overlapping requests.
        """
        if self._refresh_in_flight:
            return
        self._refresh_in_flight = True
        try:
            event = await self.controller.fetch(
                lat=self.location.latitude,
                lon=self.location.longitude,
                country_code=self.location.country_code,
            )
            # Forward fresh data to the weather screen
            self.weather_screen.post_message(event)
        except Exception as e:
            # Forward error to the weather screen to surface it
            self.weather_screen.post_message(WeatherFetchFailed(e))
        finally:
            self._refresh_in_flight = False

    def action_search(self):  # textual binding: 's'
        """Open place search screen (fresh instance)."""
        self.push_screen(SearchScreen())

    def action_help(self):  # textual binding: 'h'
        """Open help screen."""
        self.push_screen(HelpScreen())

    def action_settings(self) -> None:
        """Open settings screen and handle result via callback."""
        self.push_screen(
            SettingsScreen(
                temperature_unit=self.temperature_unit,
                wind_speed_unit=self.wind_speed_unit,
                precipitation_unit=self.precipitation_unit,
            ),
            callback=self._on_settings_result,
        )

    async def _on_settings_result(self, result: dict | None) -> None:
        """Handle settings screen dismiss with optional result."""
        # If user clicked Apply (result is dict), update units and refresh
        if result:
            self.temperature_unit = result["temperature_unit"]
            self.wind_speed_unit = result["wind_speed_unit"]
            self.precipitation_unit = result["precipitation_unit"]

            # Update controller with new units
            self.controller = WeatherController(
                temperature_unit=self.temperature_unit,
                wind_speed_unit=self.wind_speed_unit,
                precipitation_unit=self.precipitation_unit,
            )

            # Refresh weather with new units
            if (
                self.location.latitude is not None
                and self.location.longitude is not None
            ):
                await self.action_refresh()

    # ---------------- Messages ----------------
    async def on_place_selected(self, message: PlaceSelected) -> None:
        """Handle place selection → fetch → show main content.

        Adopts selected location first so widgets see correct context on WeatherUpdated.
        """
        self.location = message.location
        self.push_screen(self.weather_screen)
        await self.action_refresh()

    async def on_weather_updated(self, event: WeatherUpdated) -> None:
        """Cache forecast metadata and merge API data into location."""
        self.forecast_metadata = event.metadata
        # Merge API-provided fields into app location
        if event.metadata.elevation is not None:
            self.location.elevation = event.metadata.elevation
        if event.metadata.timezone_abbreviation:
            self.location.timezone_abbreviation = event.metadata.timezone_abbreviation
        self._has_successful_fetch = True

    async def on_weather_fetch_failed(self, event: WeatherFetchFailed) -> None:
        """Show error notification; return to search if CLI location failed on first fetch."""
        self.notify(
            f"Refresh failed: {type(event.error).__name__}: {event.error}",
            title="Weather Fetch Failed",
            severity="error",
            timeout=5.0,
        )

        # If CLI location failed on first fetch, return to search for recovery
        if self.started_with_cli_location and not self._has_successful_fetch:
            self.push_screen(SearchScreen())
