"""Textual TUI for displaying weather forecasts."""

import asyncio
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from http import HTTPStatus
from typing import ClassVar

import httpx
from textual.app import App
from wevva_warnings import CanonicalTropicalSystem, TropicalProduct, TropicalSystem

from wevva.alerts import Alert
from wevva.config import (
    ConfigWriteError,
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
    WeatherAlertsProgress,
    WeatherAlertsUpdated,
    WeatherFetchFailed,
    WeatherUpdated,
)
from wevva.screens.alerts_centre_screen import AlertsCentreScreen
from wevva.screens.dashboard_screen import DashboardScreen
from wevva.screens.help import HelpScreen
from wevva.screens.search_screen import SearchScreen
from wevva.screens.settings_screen import SettingsScreen
from wevva.screens.tropical_systems_screen import TropicalSystemsScreen
from wevva.screens.weather_screen import WeatherScreen
from wevva.screens.world_locations_screen import WorldLocationsScreen
from wevva.services.alerts import (
    get_alert_candidates_async,
    get_native_point_alerts_async,
    match_alert_candidates_async,
    normalize_country_code,
)
from wevva.services.alert_bulletin import AlertBulletinCoordinator
from wevva.services.country_alerts import (
    CountryAlertsService,
    list_supported_alert_countries,
)
from wevva.services.warning_cache import WarningCache, WarningCacheProduct
from wevva.services.tropical import (
    get_tropical_products_async,
    get_tropical_system_candidates_async,
)
from wevva.geography import short_location_name
from wevva.services.weather import (
    fetch_city_temperatures,
    fetch_current_weather,
    fetch_weather_summary,
)
from wevva.widgets.saved_locations import SavedLocationWeatherSummary
from wevva.widgets.tropical_systems import canonical_storm_key


ForecastCacheKey = tuple[float, float, str, str, str]
ForecastCacheEntry = tuple[float, WeatherUpdated]
TropicalCacheEntry = tuple[float, tuple[CanonicalTropicalSystem, ...]]
TropicalProductCacheKey = tuple[str, str, str]
_SAVED_WEATHER_RETRY_DELAY_SECONDS = 0.75


def _saved_weather_summary(
    current: Mapping[str, object],
    units: Mapping[str, object],
) -> SavedLocationWeatherSummary:
    """Build the compact shared-location reading from current conditions."""

    temperature = current.get('temperature_2m')
    code = current.get('weather_code')
    condition = get_condition(int(code)) if isinstance(code, (int, float)) else None
    condition_emoji = ''
    if condition is not None:
        condition_emoji = (
            condition.night_emoji
            if current.get('is_day') == 0
            else condition.day_emoji
        )
    unit = units.get('temperature_2m', '°C')
    return SavedLocationWeatherSummary(
        temperature=(
            temperature
            if isinstance(temperature, (int, float))
            and not isinstance(temperature, bool)
            else None
        ),
        temperature_unit=unit if isinstance(unit, str) else '°C',
        condition=condition,
        condition_emoji=condition_emoji,
    )


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
        ('a', 'save_current_location', 'Save Location'),
        ('d', 'delete_saved_location', 'Delete Location'),
        ('h', 'help', 'Help'),  # show quick help
        ('u', 'settings', 'Settings'),  # open settings
    ]

    ALERT_CACHE_TTL_SECONDS = 30 * 60
    ALERT_CACHE_STALE_GRACE_SECONDS = 6 * 60 * 60
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
        self.sub_title = 'Powered by Open-Meteo'
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
        self._dashboard_forecast_tasks: dict[
            ForecastCacheKey,
            asyncio.Task[WeatherUpdated],
        ] = {}
        self._forecast_cache_clock = time.monotonic
        self._alerts_task: asyncio.Task[None] | None = None
        self._alert_indicator_generation: int | None = None
        self._warning_cache_clock = lambda: datetime.now(UTC)
        self.warning_cache = WarningCache(
            clock=lambda: self._warning_cache_clock(),
        )
        self.country_alerts_service = CountryAlertsService(cache=self.warning_cache)
        self.alert_bulletin = AlertBulletinCoordinator(
            self.country_alerts_service,
            [country.code for country in list_supported_alert_countries()],
            warning_language=warning_language,
            on_update=self._on_bulletin_updated,
        )
        self._alerts_centre_screen: AlertsCentreScreen | None = None
        self._tropical_system_cache: TropicalCacheEntry | None = None
        self._tropical_system_cache_clock = time.monotonic
        self._tropical_system_fetch_task: asyncio.Task[tuple[list[CanonicalTropicalSystem], bool]] | None = None
        self._tropical_product_cache: dict[TropicalProductCacheKey, tuple[TropicalProduct, ...]] = {}
        self._tropical_product_tasks: dict[
            TropicalProductCacheKey,
            asyncio.Task[list[TropicalProduct]],
        ] = {}
        self._saved_weather_tasks: dict[str, asyncio.Task[None]] = {}
        self._saved_weather_generation = 0
        self._saved_location_weather_summaries: dict[
            str,
            SavedLocationWeatherSummary,
        ] = {}
        self._dashboard_screen: DashboardScreen | None = None
        # Emoji rendering toggle (widgets can read via self.app.emoji_enabled)
        self.emoji_enabled = bool(emoji_enabled)
        self.warning_language = warning_language
        # Store unit preferences for widgets
        self.temperature_unit = temperature_unit
        self.wind_speed_unit = wind_speed_unit
        self.precipitation_unit = precipitation_unit
        self.saved_locations = sorted(saved_locations or [], key=lambda item: location_label(item).casefold())
        # Initialize main weather screen once
        self.weather_screen = WeatherScreen(
            city_temperature_loader=self.load_location_map_temperatures,
        )
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

    def on_unmount(self) -> None:
        """Stop session-only bulletin work with the Textual application."""

        self.alert_bulletin.stop()

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
        self._schedule_saved_weather_refresh()
        try:
            forecast_cache_key = self._forecast_cache_key()
            event = None if force_alert_refresh else self._cached_forecast(forecast_cache_key)
            if event is None:
                self._set_forecast_loading(True)
                event = await self.controller.fetch(
                    lat=self.location.latitude,
                    lon=self.location.longitude,
                    country_code=self.location.country_code,
                )
                self._forecast_cache[forecast_cache_key] = self._forecast_cache_clock(), event
            # Forward fresh data to the weather screen
            self.weather_screen.post_message(event)
            self._schedule_alert_refresh(
                refresh_generation,
                force_refresh=force_alert_refresh,
            )
        except asyncio.CancelledError:
            self._set_forecast_loading(False)
            raise
        except Exception as e:
            # Forward error to the weather screen to surface it
            self._set_forecast_loading(False)
            self.weather_screen.post_message(WeatherFetchFailed(e))
        finally:
            self._refresh_in_flight = False

    def _forecast_cache_key(self) -> ForecastCacheKey:
        """Key a complete forecast by requested coordinates and display units."""

        return self._forecast_cache_key_for(self.location)

    def _forecast_cache_key_for(
        self,
        location: LocationMetadata,
    ) -> ForecastCacheKey:
        """Key a complete forecast for a location without adopting it."""

        assert location.latitude is not None
        assert location.longitude is not None
        return (
            location.latitude,
            location.longitude,
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

    def dashboard_forecast_snapshot(
        self,
        location: LocationMetadata,
    ) -> WeatherUpdated | None:
        """Return a valid app-owned preview without starting provider work."""

        if location.latitude is None or location.longitude is None:
            return None
        return self._cached_forecast(self._forecast_cache_key_for(location))

    async def load_dashboard_forecast(
        self,
        location: LocationMetadata,
    ) -> WeatherUpdated:
        """Load one preview without changing the active Weather location."""

        if location.latitude is None or location.longitude is None:
            raise ValueError('Dashboard forecast requires coordinates')
        cache_key = self._forecast_cache_key_for(location)
        cached = self._cached_forecast(cache_key)
        if cached is not None:
            self._update_summary_from_forecast(location, cached)
            return cached

        task = self._dashboard_forecast_tasks.get(cache_key)
        if task is None:
            task = asyncio.create_task(
                self._fetch_dashboard_forecast(location, cache_key)
            )
            self._dashboard_forecast_tasks[cache_key] = task
            task.add_done_callback(
                lambda completed, key=cache_key: self._discard_dashboard_forecast_task(
                    key,
                    completed,
                )
            )
        try:
            event = await task
            self._update_summary_from_forecast(location, event)
            return event
        finally:
            if task.done() and self._dashboard_forecast_tasks.get(cache_key) is task:
                self._dashboard_forecast_tasks.pop(cache_key, None)

    def _discard_dashboard_forecast_task(
        self,
        cache_key: ForecastCacheKey,
        task: asyncio.Task[WeatherUpdated],
    ) -> None:
        """Forget a completed preview request, including cancelled waiters."""

        if self._dashboard_forecast_tasks.get(cache_key) is task:
            self._dashboard_forecast_tasks.pop(cache_key, None)

    def _update_summary_from_forecast(
        self,
        location: LocationMetadata,
        event: WeatherUpdated,
    ) -> None:
        """Promote useful Dashboard current data to shared location surfaces."""

        timeseries = getattr(event.current, 'forecast_timeseries', ())
        if not timeseries or not isinstance(timeseries[0], Mapping):
            return
        units = getattr(event.current, 'forecast_units', {})
        if not isinstance(units, Mapping):
            units = {}
        summary = _saved_weather_summary(timeseries[0], units)
        if summary.temperature is not None:
            self._update_saved_location_weather(location, summary)

    async def _fetch_dashboard_forecast(
        self,
        location: LocationMetadata,
        cache_key: ForecastCacheKey,
    ) -> WeatherUpdated:
        """Fetch and retain one Dashboard preview through the shared controller."""

        assert location.latitude is not None
        assert location.longitude is not None
        event = await self.controller.fetch(
            lat=location.latitude,
            lon=location.longitude,
            country_code=location.country_code,
        )
        self._forecast_cache[cache_key] = self._forecast_cache_clock(), event
        return WeatherUpdated(
            metadata=event.metadata,
            current=event.current,
            hourly=event.hourly,
            daily=event.daily,
        )

    def action_search(self):  # textual binding: 's'
        """Open place search screen (fresh instance)."""
        self.push_screen(SearchScreen())

    def action_help(self):  # textual binding: 'h'
        """Open help screen."""
        self.push_screen(HelpScreen())

    def open_alerts_centre_screen(
        self,
        *,
        country_code: str | None = None,
        alert_identity: tuple[str, str] | None = None,
    ) -> None:
        """Open the installed country-alert workspace and its isolated cache."""

        requested_country = normalize_country_code(country_code)
        if self._alerts_centre_screen is None:
            self._alerts_centre_screen = AlertsCentreScreen(
                service=self.country_alerts_service,
                initial_country_code=requested_country or self.location.country_code,
                warning_language=self.warning_language,
                place_weather_loader=self.load_alert_place_weather,
            )
            self.install_screen(self._alerts_centre_screen, 'alerts-centre')
        else:
            self._alerts_centre_screen.initial_country_code = normalize_country_code(
                requested_country or self.location.country_code
            )
            self._alerts_centre_screen.apply_preferences(
                warning_language=self.warning_language,
                units_changed=False,
                appearance_changed=False,
            )
        if requested_country is not None and alert_identity is not None:
            self._alerts_centre_screen.prepare_alert_deep_link(
                requested_country,
                alert_identity,
            )
        self.push_screen('alerts-centre')

    def open_dashboard_screen(self) -> None:
        """Open the one installed dashboard without starting provider work."""

        if self._dashboard_screen is None:
            self._dashboard_screen = DashboardScreen()
            self.install_screen(self._dashboard_screen, 'dashboard')
        if self.screen is not self._dashboard_screen:
            self.push_screen('dashboard')

    def note_bulletin_country_used(self, country_code: str | None) -> None:
        """Promote one recently inspected country without restarting the queue."""

        self.alert_bulletin.note_country_used(country_code)

    def _sync_bulletin_priorities(self) -> None:
        countries = [self.location.country_code]
        if self._dashboard_screen is not None:
            countries.append(self._dashboard_screen.selected_country_code())
        countries.extend(location.country_code for location in self.saved_locations)
        self.alert_bulletin.set_priority_countries(countries)

    def _dashboard_bulletin_countries(self) -> list[str | None]:
        countries: list[str | None] = [self.location.country_code]
        if self._dashboard_screen is not None:
            countries.append(self._dashboard_screen.selected_country_code())
            countries.append(
                self._dashboard_screen.selected_alert_country_code()
            )
        return countries

    def refresh_dashboard_bulletin(self) -> None:
        """Hard-refresh only the Dashboard's bounded local country set."""

        self._sync_bulletin_priorities()
        self.alert_bulletin.schedule_hard_refresh(
            self._dashboard_bulletin_countries()
        )

    def _on_bulletin_updated(self, generation: int) -> None:
        """Publish coordinator state without giving Dashboard fetch ownership."""

        if self._dashboard_screen is None:
            return
        self._dashboard_screen.update_bulletin(
            generation,
            self.alert_bulletin.recent_alerts_snapshot(),
        )

    async def open_tropical_systems_screen(
        self,
        *,
        system: CanonicalTropicalSystem | None = None,
        observation: TropicalSystem | None = None,
    ) -> None:
        """Open the dedicated global storm workspace from its own cache."""
        cached = self._cached_tropical_systems()
        systems = list(cached[1]) if cached is not None else []
        forecast = self.forecast_metadata
        latitude = getattr(forecast, 'latitude', None)
        longitude = getattr(forecast, 'longitude', None)
        if latitude is None:
            latitude = self.location.latitude
        if longitude is None:
            longitude = self.location.longitude
        await self.push_screen(
            TropicalSystemsScreen(
                systems,
                location_latitude=latitude,
                location_longitude=longitude,
                location_name=short_location_name(self.location),
                product_loader=self.load_tropical_products,
                centre_weather_loader=self.load_tropical_centre_weather,
                systems_loader=self.load_tropical_systems if cached is None else None,
                refresh_loader=self.refresh_tropical_systems,
                initial_storm_key=(
                    canonical_storm_key(system) if system is not None else None
                ),
                initial_observation_source=(
                    observation.source if observation is not None else None
                ),
                initial_observation_id=(
                    observation.id if observation is not None else None
                ),
            )
        )

    async def load_tropical_centre_weather(self, latitude: float, longitude: float) -> dict:
        """Fetch current conditions at one source observation's storm centre."""
        return await fetch_current_weather(
            lat=latitude,
            lon=longitude,
            temperature_unit=self.temperature_unit,
            wind_speed_unit=self.wind_speed_unit,
            precipitation_unit=self.precipitation_unit,
        )

    async def load_location_map_temperatures(
        self,
        coordinates: Sequence[tuple[float, float]],
        temperature_unit: str,
    ) -> dict[tuple[float, float], float]:
        """Fetch lightweight current readings for ranked location-map cities."""
        return await fetch_city_temperatures(
            coordinates,
            temperature_unit=temperature_unit,
        )

    async def load_alert_place_weather(
        self,
        latitude: float,
        longitude: float,
        temperature_unit: str,
        wind_speed_unit: str,
        precipitation_unit: str,
    ) -> dict:
        """Fetch compact current weather for one Alerts Centre settlement."""

        return await fetch_current_weather(
            lat=latitude,
            lon=longitude,
            temperature_unit=temperature_unit,
            wind_speed_unit=wind_speed_unit,
            precipitation_unit=precipitation_unit,
        )

    def open_world_locations_screen(self) -> None:
        """Open a world overview using application-owned location summaries."""

        locations = self._locations_for_saved_surfaces()
        summaries = self.saved_location_weather_summaries(locations)
        self.push_screen(
            WorldLocationsScreen(
                locations,
                summaries=summaries,
                current_location=self.location,
                temperature_unit=self.temperature_unit,
            )
        )

    def _locations_for_saved_surfaces(self) -> list[LocationMetadata]:
        """Return saved locations plus a distinct active forecast location."""

        locations = list(self.saved_locations)
        if self.location.latitude is None or self.location.longitude is None:
            return locations
        saved_keys = {location_key(location) for location in locations}
        if location_key(self.location) not in saved_keys:
            locations.append(self.location)
        return locations

    def locations_for_dashboard(self) -> list[LocationMetadata]:
        """Return only saved places for the persistent dashboard map."""

        return list(self.saved_locations)

    def saved_location_weather_summary(
        self,
        location: LocationMetadata,
    ) -> SavedLocationWeatherSummary | None:
        """Return the application-owned compact summary for one location."""

        return self._saved_location_weather_summaries.get(location_key(location))

    def saved_location_weather_summaries(
        self,
        locations: Sequence[LocationMetadata],
    ) -> dict[str, SavedLocationWeatherSummary]:
        """Return known summaries for a bounded set of location surfaces."""

        summaries: dict[str, SavedLocationWeatherSummary] = {}
        for location in locations:
            key = location_key(location)
            summary = self._saved_location_weather_summaries.get(key)
            if summary is not None:
                summaries[key] = summary
        return summaries

    def _update_saved_location_weather(
        self,
        location: LocationMetadata,
        summary: SavedLocationWeatherSummary,
    ) -> None:
        """Keep list and world-map saved-location surfaces synchronized."""

        self._saved_location_weather_summaries[location_key(location)] = summary
        self.weather_screen.update_saved_location_weather(location, summary)
        if self._dashboard_screen is not None:
            self._dashboard_screen.update_weather_summary(
                location,
                summary,
                temperature_unit=self.temperature_unit,
            )
        if self.is_running and isinstance(self.screen, WorldLocationsScreen):
            self.screen.update_weather_summary(
                location,
                summary,
                temperature_unit=self.temperature_unit,
            )

    async def load_tropical_systems(self) -> list[CanonicalTropicalSystem]:
        """Return the shared canonical set for a screen opened before discovery."""
        cached = self._cached_tropical_systems()
        if cached is not None:
            return list(cached[1])
        systems, completed = await asyncio.shield(self._get_tropical_system_fetch_task())
        if not completed:
            raise RuntimeError('Canonical tropical-system retrieval did not complete')
        self._cache_tropical_systems(systems)
        return systems

    def tropical_systems_snapshot(
        self,
    ) -> tuple[CanonicalTropicalSystem, ...] | None:
        """Return a fresh canonical cache snapshot without starting provider work."""

        cached = self._cached_tropical_systems()
        return None if cached is None else cached[1]

    async def refresh_tropical_systems(self) -> list[CanonicalTropicalSystem]:
        """Force a new shared canonical fetch for the active tropical screen."""
        self._tropical_system_cache = None
        self._tropical_product_cache.clear()
        systems, completed = await asyncio.shield(self._get_tropical_system_fetch_task())
        if not completed:
            raise RuntimeError('Canonical tropical-system retrieval did not complete')
        self._cache_tropical_systems(systems)
        return systems

    async def load_tropical_products(self, system: TropicalSystem) -> list[TropicalProduct]:
        """Fetch one source observation lazily and reuse it across screen visits."""
        key = self._tropical_product_cache_key(system)
        cached = self._tropical_product_cache.get(key)
        if cached is not None:
            return list(cached)
        task = self._tropical_product_tasks.get(key)
        if task is None:
            task = asyncio.create_task(get_tropical_products_async(system))
            self._tropical_product_tasks[key] = task
            task.add_done_callback(
                lambda completed_task, cache_key=key: self._store_tropical_products(
                    cache_key,
                    completed_task,
                )
            )
        products = await asyncio.shield(task)
        self._tropical_product_cache[key] = tuple(products)
        return list(products)

    def _store_tropical_products(
        self,
        key: TropicalProductCacheKey,
        task: asyncio.Task[list[TropicalProduct]],
    ) -> None:
        """Retain a completed lazy request even if its screen was closed."""
        if self._tropical_product_tasks.get(key) is task:
            del self._tropical_product_tasks[key]
        if task.cancelled():
            return
        try:
            products = task.result()
        except Exception:
            return
        self._tropical_product_cache[key] = tuple(products)

    @staticmethod
    def _tropical_product_cache_key(system: TropicalSystem) -> TropicalProductCacheKey:
        issued = system.issued_at.isoformat() if system.issued_at is not None else ''
        return system.source, system.id, issued

    def action_save_current_location(self) -> None:
        """Persist the active location in the saved-location list."""
        if self.location.latitude is None or self.location.longitude is None:
            self.notify('Choose a location before saving it.', severity='warning')
            return

        try:
            saved_locations = add_saved_location(self.location)
        except ConfigWriteError as error:
            self.notify(str(error), severity='error')
            return
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

        try:
            saved_locations = remove_saved_location(location)
        except ConfigWriteError as error:
            self.notify(str(error), severity='error')
            return
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
        appearance_changed = (
            new_theme != self.theme
            or new_emoji_enabled != self.emoji_enabled
        )

        self.temperature_unit = new_temp
        self.wind_speed_unit = new_wind
        self.precipitation_unit = new_precip
        self.theme = new_theme
        self.emoji_enabled = new_emoji_enabled
        self.warning_language = new_warning_language
        if warning_language_changed:
            self.alert_bulletin.set_warning_language(self.warning_language)

        if self._alerts_centre_screen is not None:
            self._alerts_centre_screen.apply_preferences(
                warning_language=self.warning_language,
                units_changed=units_changed,
                appearance_changed=appearance_changed,
            )
        if appearance_changed and self._dashboard_screen is not None:
            self._dashboard_screen.refresh_appearance()

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

            try:
                save_preferences(**save_kwargs)
            except ConfigWriteError as error:
                self.notify(str(error), severity='error')
                return
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
        self._sync_bulletin_priorities()
        if self._dashboard_screen is not None:
            self._dashboard_screen.sync_from_app()

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

        existing_summary = self.saved_location_weather_summary(location)
        if delay > 0:
            await asyncio.sleep(delay)
        if generation != self._saved_weather_generation:
            return
        summary: SavedLocationWeatherSummary | None = None
        for attempt in range(2):
            try:
                data = await fetch_weather_summary(
                    lat=location.latitude,
                    lon=location.longitude,
                    temperature_unit=self.temperature_unit,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                if attempt == 1:
                    if existing_summary is None:
                        summary = SavedLocationWeatherSummary(error=True)
                    break
            else:
                if not isinstance(data, Mapping):
                    data = {}
                current = data.get('current', {})
                units = data.get('current_units', {})
                if not isinstance(current, Mapping):
                    current = {}
                if not isinstance(units, Mapping):
                    units = {}
                summary = _saved_weather_summary(current, units)
                if summary.temperature is not None or attempt == 1:
                    break

            await asyncio.sleep(_SAVED_WEATHER_RETRY_DELAY_SECONDS)
            if generation != self._saved_weather_generation:
                return

        if generation != self._saved_weather_generation or summary is None:
            return
        self._update_saved_location_weather(location, summary)

    # ---------------- Messages ----------------
    async def on_place_selected(self, message: PlaceSelected) -> None:
        """Handle place selection → fetch → show main content.

        Adopts selected location first so widgets see correct context on WeatherUpdated.
        """
        self.location = message.location
        if self._alerts_centre_screen is not None:
            self._alerts_centre_screen.preserve_country_on_next_resume(
                message.preserve_alerts_context
            )
        if self.screen is not self.weather_screen:
            self.push_screen(self.weather_screen)
        await self.action_refresh()

    async def on_saved_location_selected(self, message: SavedLocationSelected) -> None:
        """Switch to a saved location."""
        self.location = message.location
        if self._alerts_centre_screen is not None:
            self._alerts_centre_screen.preserve_country_on_next_resume(False)
        if isinstance(self.screen, WorldLocationsScreen):
            await self.pop_screen()
        else:
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
        self._update_saved_location_weather(
            self.location,
            _saved_weather_summary(current_point, event.current.forecast_units),
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
        if self._alert_indicator_generation is not None:
            self._set_warning_checking(False)
            self._alert_indicator_generation = None
        if self._alerts_task is not None and not self._alerts_task.done():
            self._alerts_task.cancel()
        self._alerts_task = None

    def _set_warning_checking(self, checking: bool) -> None:
        """Update the weather header when that screen supports the indicator."""

        setter = getattr(self.weather_screen, 'set_warning_checking', None)
        if callable(setter):
            setter(checking)

    def _set_forecast_loading(self, loading: bool) -> None:
        """Update the weather workspace when a full forecast request is pending."""

        setter = getattr(self.weather_screen, 'set_forecast_loading', None)
        if callable(setter):
            setter(loading)

    def _schedule_alert_refresh(
        self,
        refresh_generation: int,
        *,
        force_refresh: bool = False,
    ) -> None:
        """Fetch ordinary alerts independently of the tropical workspace."""
        lat = self.location.latitude
        lon = self.location.longitude
        if lat is None or lon is None:
            return
        self._alert_indicator_generation = refresh_generation
        self._set_warning_checking(True)
        country_code = normalize_country_code(self.location.country_code)
        warning_language = 'en' if self.warning_language == 'en' else 'auto'
        self._alerts_task = asyncio.create_task(
            self._fetch_alerts_for_location(
                lat=lat,
                lon=lon,
                country_code=country_code,
                warning_language=warning_language,
                refresh_generation=refresh_generation,
                force_refresh=force_refresh,
            )
        )

    async def _fetch_alerts_for_location(
        self,
        *,
        lat: float,
        lon: float,
        country_code: str | None,
        warning_language: str,
        refresh_generation: int,
        force_refresh: bool,
    ) -> None:
        """Fetch and publish ordinary weather alerts."""
        loop = asyncio.get_running_loop()
        provider_names: dict[str, str] = {}
        candidate_lookup: asyncio.Task | None = None
        native_lookup = asyncio.create_task(
            get_native_point_alerts_async(
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

        try:
            cached_candidates: tuple[Alert, ...] | None = None
            cached_is_stale = False
            if not force_refresh and country_code is not None:
                entry = await self.warning_cache.load(
                    WarningCacheProduct.REUSABLE_CANDIDATES,
                    country_code,
                    warning_language,
                )
                if entry is not None:
                    age = max(
                        0.0,
                        (
                            self._warning_cache_clock() - entry.fetched_at
                        ).total_seconds(),
                    )
                    if age < (
                        self.ALERT_CACHE_TTL_SECONDS
                        + self.ALERT_CACHE_STALE_GRACE_SECONDS
                    ):
                        cached_candidates = entry.alerts
                        cached_is_stale = age >= self.ALERT_CACHE_TTL_SECONDS

            if cached_candidates is not None and not cached_is_stale:
                native_alerts, _ = await native_lookup
                await self._publish_alert_candidates(
                    candidates=cached_candidates,
                    native_alerts=native_alerts,
                    lat=lat,
                    lon=lon,
                    refresh_generation=refresh_generation,
                    progress=report_progress,
                )
                return

            candidate_lookup = asyncio.create_task(
                get_alert_candidates_async(
                    country_code,
                    warning_language,
                    progress=report_progress,
                )
            )
            native_alerts, _ = await native_lookup

            if cached_candidates is not None:
                await self._publish_alert_candidates(
                    candidates=cached_candidates,
                    native_alerts=native_alerts,
                    lat=lat,
                    lon=lon,
                    refresh_generation=refresh_generation,
                    progress=report_progress,
                )

            candidates, completed = await candidate_lookup
            if completed and country_code is not None:
                await self.warning_cache.store(
                    WarningCacheProduct.REUSABLE_CANDIDATES,
                    country_code,
                    warning_language,
                    candidates,
                    fetched_at=self._warning_cache_clock(),
                )

            if cached_candidates is not None and not completed:
                return
            await self._publish_alert_candidates(
                candidates=candidates,
                native_alerts=native_alerts,
                lat=lat,
                lon=lon,
                refresh_generation=refresh_generation,
                progress=report_progress,
            )
        finally:
            if candidate_lookup is not None and not candidate_lookup.done():
                candidate_lookup.cancel()
            if not native_lookup.done():
                native_lookup.cancel()
            if self._alert_indicator_generation == refresh_generation:
                self._alert_indicator_generation = None
                self._set_warning_checking(False)
            if self.is_running:
                self._sync_bulletin_priorities()
                self.alert_bulletin.start()

    async def _publish_alert_candidates(
        self,
        *,
        candidates: Sequence[Alert],
        native_alerts: list[Alert],
        lat: float,
        lon: float,
        refresh_generation: int,
        progress,
    ) -> None:
        """Match and publish candidates only for their requesting location."""
        if not self._alert_request_is_current(lat, lon, refresh_generation):
            return
        alerts = await match_alert_candidates_async(
            list(candidates),
            native_alerts,
            lat,
            lon,
            progress=progress,
        )
        if self._alert_request_is_current(lat, lon, refresh_generation):
            self.weather_screen.post_message(WeatherAlertsUpdated(alerts=alerts))

    def _alert_request_is_current(
        self,
        lat: float,
        lon: float,
        refresh_generation: int,
    ) -> bool:
        return (
            refresh_generation == self._refresh_generation
            and self.location.latitude == lat
            and self.location.longitude == lon
        )

    def _get_tropical_system_fetch_task(self) -> asyncio.Task[tuple[list[CanonicalTropicalSystem], bool]]:
        """Return the one in-flight global canonical fetch for this session."""
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

    def _store_tropical_system_cache(self, task: asyncio.Task[tuple[list[CanonicalTropicalSystem], bool]]) -> None:
        """Cache a completed tropical-workspace fetch."""
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

    def _cache_tropical_systems(self, systems: list[CanonicalTropicalSystem]) -> None:
        """Store global canonical groups separately from country warnings."""
        self._tropical_system_cache = (
            self._tropical_system_cache_clock(),
            tuple(systems),
        )

    def _cached_tropical_systems(self) -> TropicalCacheEntry | None:
        """Return an unexpired workspace cache entry."""
        cached = self._tropical_system_cache
        if cached is None:
            return None
        if self._tropical_system_cache_clock() - cached[0] < self.TROPICAL_SYSTEM_CACHE_TTL_SECONDS:
            return cached
        self._tropical_system_cache = None
        self._tropical_product_cache.clear()
        return None

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
