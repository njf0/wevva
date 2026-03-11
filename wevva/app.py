"""Textual TUI for displaying weather forecasts."""

from typing import ClassVar

from textual.app import App

from wevva.config import load_preferences, save_preferences
from wevva.constants import DEFAULT_EMOJI_ENABLED
from wevva.controller import WeatherController  # central async orchestrator
from wevva.location_metadata import LocationMetadata
from wevva.messages import PlaceSelected, WeatherFetchFailed, WeatherUpdated
from wevva.screens.help import HelpScreen
from wevva.screens.search_screen import SearchScreen
from wevva.screens.settings_screen import SettingsScreen
from wevva.screens.weather_screen import WeatherScreen


class Wevva(App, inherit_bindings=False):
    """Minimal textual weather app showing current, next 24h, daily and warnings."""

    CSS_PATH = 'wevva.tcss'  # single theme stylesheet
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ('q', 'quit', 'Quit'),  # exit the app
        ('s', 'search', 'Search'),  # open place search screen
        ('r', 'refresh', 'Refresh'),  # fetch latest forecast
        ('h', 'help', 'Help'),  # show quick help
        ('u', 'settings', 'Settings'),  # open settings
    ]

    def __init__(
        self,
        initial_location: LocationMetadata | None = None,
        emoji_enabled: bool = DEFAULT_EMOJI_ENABLED,
        theme_name: str | None = None,
        temperature_unit: str = 'celsius',
        wind_speed_unit: str = 'kmh',
        precipitation_unit: str = 'mm',
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
        self.sub_title = 'Weather data from Open-Meteo'  # static subtitle for all screens
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
        """Fetch via controller and broadcast `WeatherUpdated`."""
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
        preferences = load_preferences()
        self.push_screen(
            SettingsScreen(
                theme_name=self.theme,
                emoji_enabled=self.emoji_enabled,
                temperature_unit=self.temperature_unit,
                wind_speed_unit=self.wind_speed_unit,
                precipitation_unit=self.precipitation_unit,
                saved_default_location=preferences.get('default_location'),
                current_location_label=self._current_location_label(),
            ),
            callback=self._on_settings_result,
        )

    async def _on_settings_result(self, result: dict | None) -> None:
        """Handle settings updates from the modal screen."""
        if not result:
            return

        new_temp = result['temperature_unit']
        new_wind = result['wind_speed_unit']
        new_precip = result['precipitation_unit']
        new_theme = result['theme']
        new_emoji_enabled = result['emoji_enabled']
        default_location_action = result['default_location_action']
        save_defaults = bool(result.get('save_defaults'))

        units_changed = (
            new_temp != self.temperature_unit or new_wind != self.wind_speed_unit or new_precip != self.precipitation_unit
        )

        self.temperature_unit = new_temp
        self.wind_speed_unit = new_wind
        self.precipitation_unit = new_precip
        self.theme = new_theme
        self.emoji_enabled = new_emoji_enabled

        if units_changed:
            self.controller = WeatherController(
                temperature_unit=self.temperature_unit,
                wind_speed_unit=self.wind_speed_unit,
                precipitation_unit=self.precipitation_unit,
            )
            if self.location.latitude is not None and self.location.longitude is not None:
                await self.action_refresh()

        if save_defaults:
            save_kwargs: dict = {
                'temperature_unit': self.temperature_unit,
                'wind_speed_unit': self.wind_speed_unit,
                'precipitation_unit': self.precipitation_unit,
                'theme': self.theme,
                'emoji_enabled': self.emoji_enabled,
            }
            if default_location_action == 'use_current':
                save_kwargs['default_location'] = self._current_location_label()
                save_kwargs['default_location_metadata'] = self._location_config_from_current_location()
            elif default_location_action == 'clear':
                save_kwargs['default_location'] = None
                save_kwargs['default_location_metadata'] = None

            save_preferences(**save_kwargs)
            self.notify('Default settings saved.', severity='information')

    def _current_location_label(self) -> str | None:
        """Build a readable label for the current in-app location."""
        if self.location.latitude is None or self.location.longitude is None:
            return None

        parts = [
            part.strip() for part in (self.location.name, self.location.admin, self.location.country) if part and part.strip()
        ]
        if parts:
            return ', '.join(parts)
        return f'{self.location.latitude:.3f}, {self.location.longitude:.3f}'

    def _location_config_from_current_location(self) -> dict:
        """Serialize current location to config format."""
        return {
            'latitude': self.location.latitude,
            'longitude': self.location.longitude,
            'elevation': self.location.elevation,
            'name': self.location.name,
            'admin': self.location.admin,
            'country': self.location.country,
            'country_code': self.location.country_code,
            'timezone': self.location.timezone,
            'timezone_abbreviation': self.location.timezone_abbreviation,
        }

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
            f'Refresh failed: {type(event.error).__name__}: {event.error}',
            title='Weather Fetch Failed',
            severity='error',
            timeout=5.0,
        )

        # If CLI location failed on first fetch, return to search for recovery
        if self.started_with_cli_location and not self._has_successful_fetch:
            self.push_screen(SearchScreen())
