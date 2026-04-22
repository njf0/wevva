"""Textual TUI for displaying weather forecasts."""

import asyncio
from typing import ClassVar

from textual.app import App

from wevva.alerts import get_alerts_async
from wevva.config import (
    add_saved_location,
    load_preferences,
    location_config_from_metadata,
    location_key,
    location_label,
    location_metadata_from_config,
    remove_saved_location,
    save_preferences,
)
from wevva.conditions import get_condition
from wevva.constants import DEFAULT_EMOJI_ENABLED
from wevva.controller import WeatherController  # central async orchestrator
from wevva.location_metadata import LocationMetadata
from wevva.messages import (
    DeleteSavedLocationRequested,
    PlaceSelected,
    SaveCurrentLocationRequested,
    SavedLocationSelected,
    WeatherAlertsUpdated,
    WeatherFetchFailed,
    WeatherUpdated,
)
from wevva.screens.help import HelpScreen
from wevva.screens.search_screen import SearchScreen
from wevva.screens.settings_screen import SettingsScreen
from wevva.screens.weather_screen import WeatherScreen
from wevva.services.weather import fetch_weather
from wevva.widgets.saved_locations import SavedLocationWeatherSummary


class Wevva(App, inherit_bindings=False):
    """Minimal textual weather app showing current, next 24h, daily and warnings."""

    CSS_PATH = 'wevva.tcss'  # single theme stylesheet
    TOOLTIP_DELAY = 0.15
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ('q', 'quit', 'Quit'),  # exit the app
        ('s', 'search', 'Search'),  # open place search screen
        ('r', 'refresh', 'Refresh'),  # fetch latest forecast
        ('l', 'toggle_locations', 'Locations'),  # show/hide saved locations
        ('h', 'help', 'Help'),  # show quick help
        ('u', 'settings', 'Settings'),  # open settings
    ]

    def __init__(
        self,
        initial_location: LocationMetadata | None = None,
        emoji_enabled: bool = DEFAULT_EMOJI_ENABLED,
        theme_name: str | None = None,
        warning_language: str = 'auto',
        temperature_unit: str = 'celsius',
        wind_speed_unit: str = 'kmh',
        precipitation_unit: str = 'mm',
        saved_locations: list[LocationMetadata] | None = None,
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
        self._refresh_generation = 0
        self._alerts_task: asyncio.Task[None] | None = None
        self._saved_weather_tasks: dict[str, asyncio.Task[None]] = {}
        # Emoji rendering toggle (widgets can read via self.app.emoji_enabled)
        self.emoji_enabled = bool(emoji_enabled)
        self.warning_language = warning_language
        # Store unit preferences for widgets
        self.temperature_unit = temperature_unit
        self.wind_speed_unit = wind_speed_unit
        self.precipitation_unit = precipitation_unit
        self.saved_locations = sorted(saved_locations or [], key=lambda item: location_label(item).casefold())
        # Initialize main weather screen once
        self.weather_screen = WeatherScreen()
        # Theme selection from CLI (validated by Textual during assignment)
        if theme_name is not None:
            self.theme = theme_name

    async def on_mount(self):
        """Start with search screen, or if location provided via CLI, fetch weather directly."""
        if self.location.latitude is not None and self.location.longitude is not None:
            self.push_screen(self.weather_screen)
            self._schedule_saved_weather_refresh()
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
        if self.location.latitude is None or self.location.longitude is None:
            self.notify('Choose a location before refreshing.', severity='warning')
            return
        self._refresh_in_flight = True
        self._refresh_generation += 1
        refresh_generation = self._refresh_generation
        self._cancel_alerts_task()
        try:
            event = await self.controller.fetch(
                lat=self.location.latitude,
                lon=self.location.longitude,
                country_code=self.location.country_code,
            )
            # Forward fresh data to the weather screen
            self.weather_screen.post_message(event)
            self._schedule_alert_refresh(refresh_generation)
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

    def action_toggle_locations(self) -> None:
        """Toggle the saved-location sidebar."""
        self.weather_screen.toggle_saved_locations_sidebar()

    def action_settings(self) -> None:
        """Open settings screen and handle result via callback."""
        preferences = load_preferences()
        self.push_screen(
            SettingsScreen(
                theme_name=self.theme,
                emoji_enabled=self.emoji_enabled,
                warning_language=self.warning_language,
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
        new_warning_language = result['warning_language']
        default_location_action = result['default_location_action']
        save_defaults = bool(result.get('save_defaults'))

        units_changed = (
            new_temp != self.temperature_unit or new_wind != self.wind_speed_unit or new_precip != self.precipitation_unit
        )
        warning_language_changed = new_warning_language != self.warning_language

        self.temperature_unit = new_temp
        self.wind_speed_unit = new_wind
        self.precipitation_unit = new_precip
        self.theme = new_theme
        self.emoji_enabled = new_emoji_enabled
        self.warning_language = new_warning_language

        if units_changed:
            self.controller = WeatherController(
                temperature_unit=self.temperature_unit,
                wind_speed_unit=self.wind_speed_unit,
                precipitation_unit=self.precipitation_unit,
            )
            if self.location.latitude is not None and self.location.longitude is not None:
                await self.action_refresh()
        elif warning_language_changed and self.location.latitude is not None and self.location.longitude is not None:
            self._refresh_generation += 1
            self._cancel_alerts_task()
            self._schedule_alert_refresh(self._refresh_generation)

        if units_changed:
            self._schedule_saved_weather_refresh()

        if save_defaults:
            save_kwargs: dict = {
                'temperature_unit': self.temperature_unit,
                'wind_speed_unit': self.wind_speed_unit,
                'precipitation_unit': self.precipitation_unit,
                'theme': self.theme,
                'emoji_enabled': self.emoji_enabled,
                'warning_language': self.warning_language,
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
        return location_config_from_metadata(self.location)

    def _set_saved_locations_from_config(self, saved_locations: list[dict]) -> None:
        """Adopt normalized saved-location config data."""
        locations = [location_metadata_from_config(item) for item in saved_locations]
        self.saved_locations = sorted(
            [location for location in locations if location is not None],
            key=lambda item: location_label(item).casefold(),
        )
        self.weather_screen.update_saved_locations_sidebar()

    def _schedule_saved_weather_refresh(self) -> None:
        """Fetch compact weather summaries for all saved locations."""
        for task in self._saved_weather_tasks.values():
            if not task.done():
                task.cancel()
        self._saved_weather_tasks = {}

        for location in self.saved_locations:
            key = location_key(location)
            self._saved_weather_tasks[key] = asyncio.create_task(self._fetch_saved_weather_summary(location))

    async def _fetch_saved_weather_summary(self, location: LocationMetadata) -> None:
        """Fetch compact current condition text for the sidebar."""
        if location.latitude is None or location.longitude is None:
            return

        try:
            data = await fetch_weather(
                lat=location.latitude,
                lon=location.longitude,
                temperature_unit=self.temperature_unit,
                wind_speed_unit=self.wind_speed_unit,
                precipitation_unit=self.precipitation_unit,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            summary = SavedLocationWeatherSummary(error=True)
        else:
            current = data.get('current', {})
            units = data.get('current_units', {})
            temp = current.get('temperature_2m')
            code = current.get('weather_code')
            condition = get_condition(int(code)) if isinstance(code, (int, float)) else None
            summary = SavedLocationWeatherSummary(
                temperature=temp if isinstance(temp, (int, float)) else None,
                temperature_unit=units.get('temperature_2m', '°C'),
                condition=condition,
            )

        self.weather_screen.update_saved_location_weather(location, summary)

    # ---------------- Messages ----------------
    async def on_place_selected(self, message: PlaceSelected) -> None:
        """Handle place selection → fetch → show main content.

        Adopts selected location first so widgets see correct context on WeatherUpdated.
        """
        self.location = message.location
        self.push_screen(self.weather_screen)
        await self.action_refresh()

    async def on_saved_location_selected(self, message: SavedLocationSelected) -> None:
        """Switch to a saved location."""
        self.location = message.location
        self.push_screen(self.weather_screen)
        await self.action_refresh()

    def on_save_current_location_requested(self, message: SaveCurrentLocationRequested) -> None:
        """Persist the active location in the saved-location list."""
        if self.location.latitude is None or self.location.longitude is None:
            self.notify('Choose a location before saving it.', severity='warning')
            return

        saved_locations = add_saved_location(self.location)
        self._set_saved_locations_from_config(saved_locations)
        self._schedule_saved_weather_refresh()
        self.notify(f'Saved {self._current_location_label()}.', severity='information')

    def on_delete_saved_location_requested(self, message: DeleteSavedLocationRequested) -> None:
        """Remove one location from the saved-location list."""
        saved_locations = remove_saved_location(message.location)
        self._set_saved_locations_from_config(saved_locations)
        self._schedule_saved_weather_refresh()
        self.notify(f'Removed {location_label(message.location)}.', severity='information')

    async def on_weather_updated(self, event: WeatherUpdated) -> None:
        """Cache forecast metadata and merge API data into location."""
        self.forecast_metadata = event.metadata
        # Merge API-provided fields into app location
        if event.metadata.elevation is not None:
            self.location.elevation = event.metadata.elevation
        if event.metadata.timezone_abbreviation:
            self.location.timezone_abbreviation = event.metadata.timezone_abbreviation
        self._has_successful_fetch = True
        point = event.hourly.get_point(0) or {}
        temp = point.get('temperature_2m')
        code = point.get('weather_code')
        condition = get_condition(int(code)) if isinstance(code, (int, float)) else None
        self.weather_screen.update_saved_location_weather(
            self.location,
            SavedLocationWeatherSummary(
                temperature=temp if isinstance(temp, (int, float)) else None,
                temperature_unit=event.hourly.forecast_units.get('temperature_2m', '°C'),
                condition=condition,
            ),
        )
        self.weather_screen.update_saved_locations_sidebar()

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

    def _cancel_alerts_task(self) -> None:
        """Cancel any in-flight background alert fetch."""
        if self._alerts_task is not None and not self._alerts_task.done():
            self._alerts_task.cancel()
        self._alerts_task = None

    def _schedule_alert_refresh(self, refresh_generation: int) -> None:
        """Start a background alert fetch for the current location."""
        lat = self.location.latitude
        lon = self.location.longitude
        if lat is None or lon is None:
            return
        self._alerts_task = asyncio.create_task(
            self._fetch_alerts_for_location(
                lat=lat,
                lon=lon,
                country_code=self.location.country_code,
                refresh_generation=refresh_generation,
            )
        )

    async def _fetch_alerts_for_location(
        self,
        *,
        lat: float,
        lon: float,
        country_code: str,
        refresh_generation: int,
    ) -> None:
        """Fetch alerts in the background and post them if still current."""
        try:
            alerts = await get_alerts_async(
                lat,
                lon,
                country_code or None,
                self.warning_language,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            alerts = []

        if refresh_generation != self._refresh_generation:
            return
        if self.location.latitude != lat or self.location.longitude != lon:
            return
        self.weather_screen.post_message(WeatherAlertsUpdated(alerts=alerts))
