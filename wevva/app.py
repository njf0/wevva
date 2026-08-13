"""Textual TUI for displaying weather forecasts."""

import asyncio
import time
from http import HTTPStatus
from typing import ClassVar

import httpx
from textual.app import App
from wevva_warnings import TropicalSystem

from wevva.alerts import Alert
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
    PlaceSelected,
    SavedLocationSelected,
    TropicalSystemsProgress,
    WeatherAlertsProgress,
    WeatherAlertsUpdated,
    WeatherFetchFailed,
    WeatherUpdated,
)
from wevva.screens.help import HelpScreen
from wevva.screens.search_screen import SearchScreen
from wevva.screens.settings_screen import SettingsScreen
from wevva.screens.weather_screen import WeatherScreen
from wevva.services.alerts import (
    _combine_alerts,
    _get_native_alerts_async_with_status,
    _get_reusable_alerts_async_with_status,
    normalize_country_code,
)
from wevva.services.tropical import (
    get_tropical_system_candidates_async,
    nearby_tropical_systems_from_candidates,
)
from wevva.services.weather import fetch_weather_summary
from wevva.widgets.saved_locations import SavedLocationWeatherSummary


AlertCacheKey = tuple[str | None, str]
ForecastCacheKey = tuple[float, float, str, str, str]
ForecastCacheEntry = tuple[float, WeatherUpdated]
TropicalCacheEntry = tuple[float, tuple[TropicalSystem, ...]]


def _weather_fetch_failure_message(error: Exception) -> str:
    """Return a concise notification without a request path or query string."""
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        try:
            reason = HTTPStatus(status).phrase
        except ValueError:
            reason = 'HTTP error'
        return f'{status}: {reason} — {_request_origin(error.request)}'
    if isinstance(error, httpx.RequestError):
        return f'Network error — {_request_origin(error.request)}'
    return f'Refresh failed: {type(error).__name__}: {error}'


def _request_origin(request: httpx.Request) -> str:
    """Return only a request scheme, host, and non-default port for UI errors."""
    url = request.url
    origin = f'{url.scheme}://{url.host}'
    if url.port is not None and url.port not in {80, 443}:
        origin = f'{origin}:{url.port}'
    return origin


class Wevva(App, inherit_bindings=False):
    """Minimal textual weather app showing current, next 24h, daily and warnings."""

    CSS_PATH = 'wevva.tcss'  # single theme stylesheet
    TOOLTIP_DELAY = 0.15
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ('q', 'quit', 'Quit'),  # exit the app
        ('s', 'search', 'Search'),  # open place search screen
        ('r', 'force_refresh', 'Refresh'),  # fetch latest forecast and warnings
        ('l', 'toggle_locations', 'Locations'),  # show/hide saved locations
        ('a', 'save_current_location', 'Save Location'),
        ('d', 'delete_saved_location', 'Delete Location'),
        ('h', 'help', 'Help'),  # show quick help
        ('u', 'settings', 'Settings'),  # open settings
    ]

    ALERT_CACHE_TTL_SECONDS = 30 * 60
    FORECAST_CACHE_TTL_SECONDS = 15 * 60
    TROPICAL_SYSTEM_CACHE_TTL_SECONDS = 30 * 60

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
        self._forecast_cache: dict[ForecastCacheKey, ForecastCacheEntry] = {}
        self._forecast_cache_clock = time.monotonic
        self._alerts_task: asyncio.Task[None] | None = None
        self._alert_cache: dict[AlertCacheKey, tuple[float, tuple[Alert, ...]]] = {}
        self._alert_cache_clock = time.monotonic
        self._tropical_system_cache: TropicalCacheEntry | None = None
        self._tropical_system_cache_clock = time.monotonic
        self._tropical_system_fetch_task: asyncio.Task[tuple[list[TropicalSystem], bool]] | None = None
        self._tropical_context_task: asyncio.Task[None] | None = None
        self._saved_weather_tasks: dict[str, asyncio.Task[None]] = {}
        self._saved_weather_generation = 0
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
            await self.action_refresh()
        else:
            self.push_screen(SearchScreen())

    # ------------------------------------------------------------
    # Actions / key bindings
    # ------------------------------------------------------------
    async def action_refresh(self) -> None:
        """Programmatically refresh weather, reusing valid session results."""
        await self._refresh_weather(force_alert_refresh=False)

    async def action_force_refresh(self) -> None:
        """Refresh weather and explicitly bypass session result caches."""
        await self._refresh_weather(force_alert_refresh=True)

    async def _refresh_weather(self, *, force_alert_refresh: bool) -> None:
        """Fetch or reuse a recent full forecast, then broadcast `WeatherUpdated`."""
        if self._refresh_in_flight:
            return
        if self.location.latitude is None or self.location.longitude is None:
            self.notify('Choose a location before refreshing.', severity='warning')
            return
        self._refresh_in_flight = True
        self._refresh_generation += 1
        refresh_generation = self._refresh_generation
        self._cancel_alerts_task()
        self._cancel_tropical_context_task()
        self._schedule_saved_weather_refresh()
        try:
            forecast_cache_key = self._forecast_cache_key()
            event = None if force_alert_refresh else self._cached_forecast(forecast_cache_key)
            if event is None:
                event = await self.controller.fetch(
                    lat=self.location.latitude,
                    lon=self.location.longitude,
                    country_code=self.location.country_code,
                )
                self._forecast_cache[forecast_cache_key] = self._forecast_cache_clock(), event
            # Forward fresh data to the weather screen
            self.weather_screen.post_message(event)
            forecast_lat = event.metadata.latitude
            forecast_lon = event.metadata.longitude
            self._schedule_alert_refresh(
                refresh_generation,
                force_refresh=force_alert_refresh,
                tropical_lat=forecast_lat,
                tropical_lon=forecast_lon,
            )
        except Exception as e:
            # Forward error to the weather screen to surface it
            self.weather_screen.post_message(WeatherFetchFailed(e))
        finally:
            self._refresh_in_flight = False

    def _forecast_cache_key(self) -> ForecastCacheKey:
        """Key a complete forecast by requested coordinates and display units."""
        assert self.location.latitude is not None
        assert self.location.longitude is not None
        return (
            self.location.latitude,
            self.location.longitude,
            self.temperature_unit,
            self.wind_speed_unit,
            self.precipitation_unit,
        )

    def _cached_forecast(self, cache_key: ForecastCacheKey) -> WeatherUpdated | None:
        """Return a new message around a valid cached complete forecast result."""
        entry = self._forecast_cache.get(cache_key)
        if entry is None:
            return None
        cached_at, cached_event = entry
        if self._forecast_cache_clock() - cached_at >= self.FORECAST_CACHE_TTL_SECONDS:
            del self._forecast_cache[cache_key]
            return None
        return WeatherUpdated(
            metadata=cached_event.metadata,
            current=cached_event.current,
            hourly=cached_event.hourly,
            daily=cached_event.daily,
        )

    def action_search(self):  # textual binding: 's'
        """Open place search screen (fresh instance)."""
        self.push_screen(SearchScreen())

    def action_help(self):  # textual binding: 'h'
        """Open help screen."""
        self.push_screen(HelpScreen())

    def action_toggle_locations(self) -> None:
        """Toggle the saved-location sidebar."""
        self.weather_screen.toggle_saved_locations_sidebar()

    def action_save_current_location(self) -> None:
        """Persist the active location in the saved-location list."""
        if self.location.latitude is None or self.location.longitude is None:
            self.notify('Choose a location before saving it.', severity='warning')
            return

        saved_locations = add_saved_location(self.location)
        self._set_saved_locations_from_config(saved_locations)
        self._schedule_saved_weather_refresh()
        self.notify(f'Saved {self._current_location_label()}.', severity='information')

    def action_delete_saved_location(self) -> None:
        """Remove the highlighted saved location from the sidebar."""
        location = self.weather_screen.selected_saved_location()
        if location is None:
            self.notify('Highlight a saved location before deleting it.', severity='warning')
            return
        saved_keys = {location_key(saved_location) for saved_location in self.saved_locations}
        if location_key(location) not in saved_keys:
            self.notify('That location is not saved yet.', severity='warning')
            return

        saved_locations = remove_saved_location(location)
        self._set_saved_locations_from_config(saved_locations)
        self._schedule_saved_weather_refresh()
        self.notify(f'Removed {location_label(location)}.', severity='information')

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
        temperature_unit_changed = new_temp != self.temperature_unit
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
            self._cancel_tropical_context_task()
            self._schedule_alert_refresh(self._refresh_generation)

        if temperature_unit_changed and (self.location.latitude is None or self.location.longitude is None):
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
        self._saved_weather_generation += 1
        generation = self._saved_weather_generation
        for task in self._saved_weather_tasks.values():
            if not task.done():
                task.cancel()
        self._saved_weather_tasks = {}

        current_key = location_key(self.location)
        for index, location in enumerate(self.saved_locations):
            key = location_key(location)
            if key == current_key:
                continue
            self._saved_weather_tasks[key] = asyncio.create_task(
                self._fetch_saved_weather_summary(
                    location,
                    delay=index * 0.1,
                    generation=generation,
                )
            )

    async def _fetch_saved_weather_summary(
        self,
        location: LocationMetadata,
        *,
        delay: float = 0.0,
        generation: int,
    ) -> None:
        """Fetch compact current condition text for the sidebar."""
        if location.latitude is None or location.longitude is None:
            return

        existing_summary = self.weather_screen.saved_location_weather_summary(location)
        if delay > 0:
            await asyncio.sleep(delay)
        if generation != self._saved_weather_generation:
            return
        try:
            data = await fetch_weather_summary(
                lat=location.latitude,
                lon=location.longitude,
                temperature_unit=self.temperature_unit,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            if existing_summary is None:
                summary = SavedLocationWeatherSummary(error=True)
            else:
                return
        else:
            current = data.get('current', {})
            units = data.get('current_units', {})
            temp = current.get('temperature_2m')
            code = current.get('weather_code')
            condition = get_condition(int(code)) if isinstance(code, (int, float)) else None
            condition_emoji = ''
            if condition is not None:
                condition_emoji = condition.night_emoji if current.get('is_day') == 0 else condition.day_emoji
            summary = SavedLocationWeatherSummary(
                temperature=temp if isinstance(temp, (int, float)) else None,
                temperature_unit=units.get('temperature_2m', '°C'),
                condition=condition,
                condition_emoji=condition_emoji,
            )

        if generation != self._saved_weather_generation:
            return
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

    async def on_weather_updated(self, event: WeatherUpdated) -> None:
        """Cache forecast metadata and merge API data into location."""
        self.forecast_metadata = event.metadata
        # Merge API-provided fields into app location
        if event.metadata.elevation is not None:
            self.location.elevation = event.metadata.elevation
        if event.metadata.timezone_abbreviation:
            self.location.timezone_abbreviation = event.metadata.timezone_abbreviation
        self._has_successful_fetch = True
        current_point = event.current.forecast_timeseries[0] if event.current.forecast_timeseries else {}
        temp = current_point.get('temperature_2m')
        code = current_point.get('weather_code')
        condition = get_condition(int(code)) if isinstance(code, (int, float)) else None
        condition_emoji = ''
        if condition is not None:
            condition_emoji = condition.night_emoji if current_point.get('is_day') == 0 else condition.day_emoji
        self.weather_screen.update_saved_location_weather(
            self.location,
            SavedLocationWeatherSummary(
                temperature=temp if isinstance(temp, (int, float)) else None,
                temperature_unit=event.current.forecast_units.get('temperature_2m', '°C'),
                condition=condition,
                condition_emoji=condition_emoji,
            ),
        )
        self.weather_screen.update_saved_locations_sidebar()

    async def on_weather_fetch_failed(self, event: WeatherFetchFailed) -> None:
        """Show error notification; return to search if CLI location failed on first fetch."""
        self.notify(
            _weather_fetch_failure_message(event.error),
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

    def _cancel_tropical_context_task(self) -> None:
        """Cancel stale location-specific matching, not the shared raw fetch."""
        if self._tropical_context_task is not None and not self._tropical_context_task.done():
            self._tropical_context_task.cancel()
        self._tropical_context_task = None

    def _schedule_alert_refresh(
        self,
        refresh_generation: int,
        *,
        force_refresh: bool = False,
        tropical_lat: float | None = None,
        tropical_lon: float | None = None,
    ) -> None:
        """Fetch ordinary alerts, then refresh nearby tropical context in the background."""
        self._cancel_tropical_context_task()
        lat = self.location.latitude
        lon = self.location.longitude
        if lat is None or lon is None:
            return
        if tropical_lat is None or tropical_lon is None:
            forecast_lat = getattr(self.forecast_metadata, 'latitude', None)
            forecast_lon = getattr(self.forecast_metadata, 'longitude', None)
            if forecast_lat is not None and forecast_lon is not None:
                tropical_lat = forecast_lat
                tropical_lon = forecast_lon
        country_code = normalize_country_code(self.location.country_code)
        warning_language = 'en' if self.warning_language == 'en' else 'auto'
        cache_key = (country_code, warning_language)
        entry = None
        if not force_refresh:
            entry = self._alert_cache.get(cache_key)
            if entry is not None and self._alert_cache_clock() - entry[0] >= self.ALERT_CACHE_TTL_SECONDS:
                del self._alert_cache[cache_key]
                entry = None
        tropical_entry: TropicalCacheEntry | None = None
        tropical_cache_expired = False
        if tropical_lat is not None and tropical_lon is not None and not force_refresh:
            tropical_entry = self._tropical_system_cache
            if (
                tropical_entry is not None
                and self._tropical_system_cache_clock() - tropical_entry[0]
                >= self.TROPICAL_SYSTEM_CACHE_TTL_SECONDS
            ):
                self._tropical_system_cache = None
                tropical_entry = None
                tropical_cache_expired = True
        self._alerts_task = asyncio.create_task(
            self._fetch_alerts_for_location(
                lat=lat,
                lon=lon,
                country_code=country_code,
                warning_language=warning_language,
                cache_key=cache_key,
                refresh_generation=refresh_generation,
                cached_candidates=entry[1] if entry is not None else None,
                tropical_lat=tropical_lat,
                tropical_lon=tropical_lon,
                cached_tropical_systems=tropical_entry[1] if tropical_entry is not None else None,
                allow_late_tropical_cache=not force_refresh and not tropical_cache_expired,
            )
        )

    async def _fetch_alerts_for_location(
        self,
        *,
        lat: float,
        lon: float,
        country_code: str | None,
        warning_language: str,
        cache_key: AlertCacheKey,
        refresh_generation: int,
        cached_candidates: tuple[Alert, ...] | None,
        tropical_lat: float | None,
        tropical_lon: float | None,
        cached_tropical_systems: tuple[TropicalSystem, ...] | None,
        allow_late_tropical_cache: bool,
    ) -> None:
        """Fetch ordinary alerts, then start tropical context in the background."""
        loop = asyncio.get_running_loop()
        provider_names: dict[str, str] = {}
        native_lookup = asyncio.create_task(
            _get_native_alerts_async_with_status(
                lat,
                lon,
                country_code,
                warning_language,
            )
        )
        def report_progress(event: str, payload: dict[str, object]) -> None:
            """Transfer the warning worker's callback safely to the TUI loop."""
            payload = dict(payload)
            source = payload.get('source')
            provider_name = payload.get('provider_name')
            if isinstance(source, str) and isinstance(provider_name, str) and provider_name:
                provider_names[source] = provider_name
            elif isinstance(source, str) and source in provider_names:
                payload['provider_name'] = provider_names[source]
            loop.call_soon_threadsafe(
                self._post_alert_progress_if_current,
                event,
                payload,
                lat,
                lon,
                refresh_generation,
            )

        def report_tropical_progress(event: str, payload: dict[str, object]) -> None:
            """Transfer tropical matching progress safely to the TUI loop."""
            loop.call_soon_threadsafe(
                self._post_tropical_progress_if_current,
                event,
                dict(payload),
                lat,
                lon,
                refresh_generation,
            )

        try:
            if cached_candidates is None:
                try:
                    candidates, completed = await _get_reusable_alerts_async_with_status(
                        country_code,
                        warning_language,
                        progress=report_progress,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    candidates = []
                    completed = False

                if completed:
                    self._alert_cache[cache_key] = self._alert_cache_clock(), tuple(candidates)
            else:
                candidates = list(cached_candidates)

            try:
                native_alerts, _ = await native_lookup
            except asyncio.CancelledError:
                raise
            except Exception:
                native_alerts = []

            if (
                refresh_generation != self._refresh_generation
                or self.location.latitude != lat
                or self.location.longitude != lon
            ):
                return
            alerts = await asyncio.to_thread(
                _combine_alerts,
                candidates,
                native_alerts,
                lat,
                lon,
                progress=report_progress,
            )

            if (
                refresh_generation != self._refresh_generation
                or self.location.latitude != lat
                or self.location.longitude != lon
            ):
                return

            if cached_tropical_systems is None and allow_late_tropical_cache:
                refreshed_tropical_entry = self._tropical_system_cache
                if (
                    refreshed_tropical_entry is not None
                    and self._tropical_system_cache_clock() - refreshed_tropical_entry[0]
                    < self.TROPICAL_SYSTEM_CACHE_TTL_SECONDS
                ):
                    cached_tropical_systems = refreshed_tropical_entry[1]

            tropical_systems = []
            if cached_tropical_systems is not None and tropical_lat is not None and tropical_lon is not None:
                tropical_systems = await asyncio.to_thread(
                    nearby_tropical_systems_from_candidates,
                    cached_tropical_systems,
                    tropical_lat,
                    tropical_lon,
                    selected_country_code=country_code,
                    progress=report_tropical_progress,
                )
            tropical_systems_pending = (
                cached_tropical_systems is None and tropical_lat is not None and tropical_lon is not None
            )
            self.weather_screen.post_message(
                WeatherAlertsUpdated(
                    alerts=alerts,
                    tropical_systems=tropical_systems,
                    tropical_systems_pending=tropical_systems_pending,
                )
            )

            if tropical_systems_pending:
                self._post_tropical_progress_if_current(
                    'tropical_fetch_started',
                    {},
                    lat,
                    lon,
                    refresh_generation,
                )
                tropical_lookup = self._get_tropical_system_fetch_task()
                self._tropical_context_task = asyncio.create_task(
                    self._publish_tropical_context_when_ready(
                        tropical_lookup=tropical_lookup,
                        alerts=alerts,
                        lat=lat,
                        lon=lon,
                        tropical_lat=tropical_lat,
                        tropical_lon=tropical_lon,
                        country_code=country_code,
                        refresh_generation=refresh_generation,
                    )
                )
        finally:
            if not native_lookup.done():
                native_lookup.cancel()

    async def _publish_tropical_context_when_ready(
        self,
        *,
        tropical_lookup: asyncio.Task[tuple[list[TropicalSystem], bool]],
        alerts: list[Alert],
        lat: float,
        lon: float,
        tropical_lat: float,
        tropical_lon: float,
        country_code: str | None,
        refresh_generation: int,
    ) -> None:
        """Publish nearby systems after a background, location-independent raw fetch."""
        loop = asyncio.get_running_loop()

        def report_tropical_progress(event: str, payload: dict[str, object]) -> None:
            """Transfer local matching progress safely from the worker thread."""
            loop.call_soon_threadsafe(
                self._post_tropical_progress_if_current,
                event,
                dict(payload),
                lat,
                lon,
                refresh_generation,
            )

        try:
            raw_tropical_systems, completed = await asyncio.shield(tropical_lookup)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._post_tropical_progress_if_current(
                'tropical_finished',
                {},
                lat,
                lon,
                refresh_generation,
            )
            return
        if completed:
            self._cache_tropical_systems(raw_tropical_systems)
        if not completed:
            self._post_tropical_progress_if_current(
                'tropical_finished',
                {},
                lat,
                lon,
                refresh_generation,
            )
            return
        if (
            refresh_generation != self._refresh_generation
            or self.location.latitude != lat
            or self.location.longitude != lon
        ):
            return
        tropical_systems = await asyncio.to_thread(
            nearby_tropical_systems_from_candidates,
            raw_tropical_systems,
            tropical_lat,
            tropical_lon,
            selected_country_code=country_code,
            progress=report_tropical_progress,
        )
        if (
            refresh_generation != self._refresh_generation
            or self.location.latitude != lat
            or self.location.longitude != lon
        ):
            return
        self.weather_screen.post_message(
            WeatherAlertsUpdated(alerts=alerts, tropical_systems=tropical_systems)
        )

    def _get_tropical_system_fetch_task(self) -> asyncio.Task[tuple[list[TropicalSystem], bool]]:
        """Return the one in-flight global raw-system fetch for this session."""
        task = self._tropical_system_fetch_task
        if task is not None:
            if task.done():
                self._store_tropical_system_cache(task)
                task = self._tropical_system_fetch_task
            if task is not None:
                return task

        task = asyncio.create_task(get_tropical_system_candidates_async())
        task.add_done_callback(self._store_tropical_system_cache)
        self._tropical_system_fetch_task = task
        return task

    def _store_tropical_system_cache(self, task: asyncio.Task[tuple[list[TropicalSystem], bool]]) -> None:
        """Cache a completed raw fetch even if its original location changed."""
        if self._tropical_system_fetch_task is not task:
            return
        self._tropical_system_fetch_task = None
        if task.cancelled():
            return
        try:
            systems, completed = task.result()
        except Exception:
            return
        if completed:
            self._cache_tropical_systems(systems)

    def _cache_tropical_systems(self, systems: list[TropicalSystem]) -> None:
        """Store raw global reports separately from country warning candidates."""
        self._tropical_system_cache = (
            self._tropical_system_cache_clock(),
            tuple(systems),
        )

    def _post_alert_progress_if_current(
        self,
        event: str,
        payload: dict[str, object],
        lat: float,
        lon: float,
        refresh_generation: int,
    ) -> None:
        """Post progress only when it still belongs to the active location."""
        if (
            refresh_generation != self._refresh_generation
            or self.location.latitude != lat
            or self.location.longitude != lon
        ):
            return
        self.weather_screen.post_message(WeatherAlertsProgress(event=event, payload=payload))

    def _post_tropical_progress_if_current(
        self,
        event: str,
        payload: dict[str, object],
        lat: float,
        lon: float,
        refresh_generation: int,
    ) -> None:
        """Post tropical progress only when it still belongs to the active location."""
        if (
            refresh_generation != self._refresh_generation
            or self.location.latitude != lat
            or self.location.longitude != lon
        ):
            return
        self.weather_screen.post_message(TropicalSystemsProgress(event=event, payload=payload))
