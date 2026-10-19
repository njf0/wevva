"""Run the Task 0025 local screen baseline without live provider requests.

This is checkout-only audit tooling, not a benchmark test.  Timings are
indicative and deliberately have no pass/fail thresholds.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import gc
import json
import platform
from statistics import median
import time
import tracemalloc
from typing import Any
from unittest.mock import AsyncMock, patch
import weakref

from textual.widgets import Tabs
from wevva_warnings import CanonicalTropicalSystem, TropicalProduct, TropicalSystem

from tests.test_alerts_centre_map import EAST_GERMANY, WEST_GERMANY, _alert
from tests.test_tropical_systems_screen import _observation
from tests.test_world_locations_map import LONDON, NEW_YORK, TOKYO
from tests.weather_fixtures import hourly_forecast, weather_update
from wevva import geography
from wevva.app import Wevva
from wevva.location_metadata import LocationMetadata
from wevva.messages import (
    DaySelected,
    HourHighlighted,
    PlaceSelected,
    SearchQueryReady,
    WeatherAlertsProgress,
    WeatherAlertsUpdated,
)
from wevva.screens.alerts_centre_screen import AlertsCentreScreen
from wevva.screens.search_screen import SearchScreen
from wevva.screens.tropical_systems_screen import TropicalSystemsScreen
from wevva.screens.weather_screen import WeatherScreen
from wevva.screens.world_locations_screen import WorldLocationsScreen
from wevva.widgets import country_alerts_map, tropical_track, world_locations_map
from wevva.widgets.saved_locations import SavedLocationWeatherSummary
from wevva.widgets.world_locations_map import WorldLocationLabel


BERLIN = LocationMetadata(
    name='Berlin',
    country='Germany',
    country_code='DE',
    latitude=52.52,
    longitude=13.405,
)

LIFECYCLE_CYCLES = 5


class _CountryService:
    """Immediate deterministic substitute for country-warning retrieval."""

    last_country_code: str | None = None

    def __init__(self) -> None:
        self.calls = 0
        self.results = {
            'DE': _country_alerts('ordinary', 6, (WEST_GERMANY, EAST_GERMANY)),
            'FR': _country_alerts('france', 6, (_box_geometry(1.0, 45.5, 2.5, 2.0),)),
            'US': _country_alerts('us-unique', 100, _unique_us_geometries(100)),
        }
        self._gate: asyncio.Event | None = None
        self.started = asyncio.Event()

    def gate_next_request(self) -> asyncio.Event:
        self._gate = asyncio.Event()
        self.started = asyncio.Event()
        return self._gate

    async def get_alerts(self, country_code: str, **_kwargs: Any) -> list:
        self.calls += 1
        gate = self._gate
        if gate is not None:
            self._gate = None
            self.started.set()
            await gate.wait()
        return list(self.results[country_code])

    def new_alert_identities(self, *_args: Any, **_kwargs: Any) -> frozenset:
        return frozenset()


def _box_geometry(
    longitude: float,
    latitude: float,
    width: float,
    height: float,
) -> dict[str, object]:
    return {
        'type': 'Polygon',
        'coordinates': [[
            [longitude, latitude],
            [longitude + width, latitude],
            [longitude + width, latitude + height],
            [longitude, latitude + height],
            [longitude, latitude],
        ]],
    }


def _unique_us_geometries(count: int) -> tuple[dict[str, object], ...]:
    return tuple(
        _box_geometry(
            -124.0 + (index % 10) * 5.8,
            25.0 + (index // 10) * 2.5,
            2.2,
            1.3,
        )
        for index in range(count)
    )


def _country_alerts(
    prefix: str,
    count: int,
    geometries: tuple[dict[str, object], ...],
) -> list:
    severities = ('Severe', 'Moderate', 'Minor')
    return [
        _alert(
            f'{prefix}-{index}',
            severity=severities[min(2, index * 3 // max(1, count))],
            geometry=geometries[index % len(geometries)],
        )
        for index in range(count)
    ]


@dataclass(frozen=True)
class _Observation:
    elapsed_ms: float
    peak_kib: float | None


class _Recorder:
    def __init__(self, *, trace_memory: bool) -> None:
        self.trace_memory = trace_memory
        self.results: dict[str, _Observation] = {}

    async def measure(
        self,
        name: str,
        action: Callable[[], Awaitable[Any]],
    ) -> Any:
        gc.collect()
        if self.trace_memory:
            before, _peak = tracemalloc.get_traced_memory()
            tracemalloc.reset_peak()
        started = time.perf_counter()
        result = await action()
        elapsed_ms = (time.perf_counter() - started) * 1_000
        peak_kib = None
        if self.trace_memory:
            _current, peak = tracemalloc.get_traced_memory()
            peak_kib = max(0, peak - before) / 1024
        self.results[name] = _Observation(elapsed_ms, peak_kib)
        return result


async def _settle(pilot, cycles: int = 2) -> None:
    for _ in range(cycles):
        await pilot.pause(0)


async def _resize_burst(pilot) -> None:
    for width, height in ((80, 24), (140, 45), (100, 30), (180, 55)):
        await pilot.resize_terminal(width, height)
    await _settle(pilot, 3)


def _places(count: int) -> list[dict[str, object]]:
    return [
        {
            'name': f'Fixture Place {index}',
            'country': 'Germany' if index % 2 else 'France',
            'country_code': 'DE' if index % 2 else 'FR',
            'admin': f'Region {index % 4}',
            'latitude': 48.0 + index / 100,
            'longitude': 8.0 + index / 100,
            'elevation': 100 + index,
            'tz_identifier': 'Europe/Berlin',
        }
        for index in range(count)
    ]


def _world_locations(count: int) -> list[LocationMetadata]:
    return [
        LocationMetadata(
            name=f'Location {index:02d}',
            country='Fixture',
            country_code='XX',
            latitude=-55.0 + (index % 8) * 15.0,
            longitude=-170.0 + (index // 8) * 70.0,
        )
        for index in range(count)
    ]


def _tropical_systems() -> list[CanonicalTropicalSystem]:
    nangka = [
        _observation(
            'nangka-jma',
            'jma_tropical',
            'NANGKA',
            classification='Typhoon',
            latitude=28.0,
            longitude=135.0,
            track=[[135.0, 28.0], [136.0, 29.0], [137.0, 30.0]],
        ),
        _observation(
            'nangka-cma',
            'cma_tropical',
            'NANGKA',
            classification='Tropical Storm',
            latitude=20.0,
            longitude=120.0,
            track=[[120.0, 20.0], [119.0, 21.0], [118.0, 22.0]],
        ),
    ]
    lala = _observation(
        'lala-cphc',
        'cphc_gis_central_pacific',
        'LALA',
        classification='Tropical Storm',
        latitude=15.2,
        longitude=-145.5,
        track=[[-145.5, 15.2], [-150.0, 17.0], [-155.0, 19.0]],
    )
    return [
        CanonicalTropicalSystem('NANGKA', nangka),
        CanonicalTropicalSystem('LALA', [lala]),
    ]


def _tropical_products(system: TropicalSystem) -> list[TropicalProduct]:
    """Representative coordinate metadata plus two visible documents."""
    latitude = float(system.center_lat or 0.0)
    longitude = float(system.center_lon or 0.0)
    return [
        TropicalProduct(
            kind='forecast',
            label='Forecast fixes',
            data={
                'points': [
                    {
                        'latitude': latitude + 1.0,
                        'longitude': longitude + 1.0,
                        'lead_hours': 24,
                    }
                ]
            },
        ),
        TropicalProduct(
            kind='advisory',
            label='Public Advisory',
            content='Representative official advisory text. ' * 12,
        ),
        TropicalProduct(
            kind='discussion',
            label='Forecast Discussion',
            content='## Discussion\n\nRepresentative forecast reasoning. ' * 8,
            content_format='markdown',
        ),
    ]


def _tropical_centre_weather(latitude: float, longitude: float) -> dict[str, Any]:
    return {
        'latitude': latitude,
        'longitude': longitude,
        'current': {
            'temperature_2m': 29.4,
            'apparent_temperature': 33.1,
            'precipitation_probability': 60,
            'precipitation': 1.8,
            'weather_code': 95,
            'surface_pressure': 986.4,
            'is_day': 1,
            'wind_speed_10m': 55.4,
            'wind_gusts_10m': 78.4,
            'wind_direction_10m': 315,
        },
        'current_units': {
            'temperature_2m': '°C',
            'precipitation': 'mm',
            'surface_pressure': 'hPa',
            'wind_speed_10m': 'km/h',
        },
    }


def _clear_geography_caches() -> None:
    for cached in (
        geography._map_units,
        geography.map_unit,
        geography.world_map_unit_polygons,
        geography.world_populated_places,
        geography.detailed_world_populated_places,
        geography._populated_places_resource,
        geography.subunit,
        country_alerts_map._country_alerts_map_source,
        country_alerts_map.build_country_alerts_map_geometry,
        tropical_track._native_scope_frame,
        tropical_track._visible_world_polygons,
        world_locations_map._projected_world_land,
        world_locations_map._world_frame,
    ):
        cached.cache_clear()


async def _search_scenarios(recorder: _Recorder) -> None:
    async def construct() -> Wevva:
        return Wevva()

    app = await recorder.measure('startup.construct_no_location', construct)
    app.action_refresh = AsyncMock()
    runner = app.run_test(size=(100, 30))

    async def enter():
        pilot = await runner.__aenter__()
        await _settle(pilot, 3)
        return pilot

    pilot = await recorder.measure('search.cold_entry', enter)
    try:
        screen = app.screen
        assert isinstance(screen, SearchScreen)

        async def update_results() -> None:
            screen.dialog.show_results(_places(10))
            await _settle(pilot)

        await recorder.measure('search.results_update_10', update_results)

        async def query_round_trip() -> None:
            async def search_fixture(*_args: Any, **_kwargs: Any) -> list[dict[str, object]]:
                return _places(10)

            with patch('wevva.screens.search_screen.search_places', new=search_fixture):
                screen.post_message(SearchQueryReady('fixture'))
                await _settle(pilot)
                workers = [worker for worker in screen.workers if not worker.is_cancelled]
                if workers:
                    await screen.workers.wait_for_complete(workers)
                await _settle(pilot)

        await recorder.measure('search.query_round_trip_10', query_round_trip)

        async def replace_results() -> None:
            screen.dialog.show_results(_places(100))
            screen.dialog.show_results(_places(10))
            await _settle(pilot)

        await recorder.measure('search.results_replace_100_to_10', replace_results)
        await recorder.measure('search.resize_burst', lambda: _resize_burst(pilot))

        async def dismiss() -> None:
            screen.dismiss()
            await _settle(pilot)

        await recorder.measure('search.exit', dismiss)

        async def reopen() -> None:
            app.action_search()
            await _settle(pilot, 3)

        await recorder.measure('search.warm_reentry_fresh_modal', reopen)

        async def select_place() -> None:
            current = app.screen
            assert isinstance(current, SearchScreen)
            current.dialog.post_message(PlaceSelected(location=BERLIN))
            await _settle(pilot, 4)

        await recorder.measure('search.select_to_weather_no_provider', select_place)
        assert app.screen is app.weather_screen
        app.action_refresh.assert_awaited_once()
    finally:
        await runner.__aexit__(None, None, None)


async def _workspace_scenarios(recorder: _Recorder) -> None:
    service = _CountryService()
    systems = _tropical_systems()
    hourly_started = asyncio.Event()
    hourly_release = asyncio.Event()

    async def load_place_hourly(*_args: Any):
        hourly_started.set()
        await hourly_release.wait()
        return hourly_forecast()

    async def construct() -> Wevva:
        return Wevva(
            initial_location=BERLIN,
            saved_locations=[LONDON, NEW_YORK, TOKYO],
            emoji_enabled=False,
        )

    app = await recorder.measure('startup.construct_with_location', construct)
    app.action_refresh = AsyncMock()
    app.country_alerts_service = service  # type: ignore[assignment]
    app.load_alert_place_hourly_forecast = load_place_hourly  # type: ignore[method-assign]
    app.weather_screen._city_temperature_loader = AsyncMock(return_value={})
    app._tropical_system_cache = (time.monotonic(), tuple(systems))
    app.load_tropical_products = AsyncMock(side_effect=_tropical_products)
    app.load_tropical_centre_weather = AsyncMock(side_effect=_tropical_centre_weather)
    app.refresh_tropical_systems = AsyncMock(return_value=systems)
    runner = app.run_test(size=(140, 45))

    async def enter():
        pilot = await runner.__aenter__()
        await _settle(pilot, 3)
        return pilot

    pilot = await recorder.measure('weather.cold_entry', enter)
    try:
        weather = app.screen
        assert isinstance(weather, WeatherScreen)

        update = weather_update()

        async def weather_update_local() -> None:
            await weather.on_weather_updated(update)
            await _settle(pilot, 4)

        await recorder.measure('weather.forecast_update_72h', weather_update_local)

        async def cached_weather_update() -> None:
            await weather.on_weather_updated(update)
            await _settle(pilot, 3)

        await recorder.measure('weather.cached_forecast_reapply_72h', cached_weather_update)

        async def warning_progress() -> None:
            weather.on_weather_alerts_progress(
                WeatherAlertsProgress(
                    event='source_started',
                    payload={'source': 'fixture'},
                )
            )
            weather.on_weather_alerts_progress(
                WeatherAlertsProgress(
                    event='alerts_total',
                    payload={'total': 6, 'phase': 'documents'},
                )
            )
            weather.on_weather_alerts_progress(
                WeatherAlertsProgress(
                    event='alerts_checked',
                    payload={'completed': 6, 'total': 6, 'phase': 'documents'},
                )
            )
            await _settle(pilot)

        await recorder.measure('weather.warning_progress_3', warning_progress)

        async def alert_completion() -> None:
            await weather.on_weather_alerts_updated(
                WeatherAlertsUpdated(list(update.alerts))
            )
            await _settle(pilot)

        await recorder.measure('weather.alert_completion_same_2', alert_completion)

        async def hour_selection() -> None:
            await weather.on_hour_highlighted(HourHighlighted(4))
            await _settle(pilot)

        await recorder.measure('weather.hour_selection', hour_selection)

        async def day_selection() -> None:
            weather.on_day_selected(DaySelected(1))
            await _settle(pilot, 3)

        await recorder.measure('weather.day_selection', day_selection)

        async def time_updates() -> None:
            for _ in range(40):
                weather._refresh_time_display()
            await _settle(pilot)

        await recorder.measure('weather.time_updates_40', time_updates)

        async def map_temperature_enrichment() -> None:
            temperatures = {
                coordinates: 12.0 + index
                for index, coordinates in enumerate(weather.location_map.city_coordinates)
            }
            weather.location_map.update_temperatures(
                temperatures,
                temperature_unit='celsius',
            )
            await _settle(pilot, 3)

        await recorder.measure('weather.map_temperature_enrichment', map_temperature_enrichment)
        await recorder.measure('weather.resize_burst', lambda: _resize_burst(pilot))

        async def open_alerts() -> None:
            app.open_alerts_centre_screen()
            await _settle(pilot, 4)

        await recorder.measure('alerts.cold_entry_6', open_alerts)
        alerts = app.screen
        assert isinstance(alerts, AlertsCentreScreen)

        async def progress_updates() -> None:
            generation = alerts._load_generation
            country_code = alerts.selected_country_code
            assert country_code is not None
            alerts._apply_progress(
                generation,
                country_code,
                'source_started',
                {'provider_name': 'Fixture Weather Service'},
            )
            alerts._apply_progress(
                generation,
                country_code,
                'alerts_total',
                {'total': 6},
            )
            alerts._apply_progress(
                generation,
                country_code,
                'alerts_checked',
                {'completed': 6, 'total': 6},
            )
            await _settle(pilot)

        await recorder.measure('alerts.progress_updates_3', progress_updates)

        async def filter_and_sort() -> None:
            alerts.new_alert_keys = {('fixture', 'ordinary-4')}
            alerts.alert_severity_filter = 'moderate'
            alerts.alert_sort_value = 'new'
            alerts._apply_alert_filter('ordinary')
            await _settle(pilot, 2)

        await recorder.measure('alerts.filter_sort_6', filter_and_sort)
        alerts.alert_severity_filter = ''
        alerts.alert_sort_value = 'severity'
        alerts._apply_alert_filter('')
        await _settle(pilot, 2)

        async def alert_selection() -> None:
            alerts._select_alert(alerts.alerts[-1])
            await _settle(pilot, 2)

        await recorder.measure('alerts.selection', alert_selection)

        geometry = alerts.country_map.geometry
        assert geometry is not None and geometry.places
        place = geometry.places[0][0]

        async def settlement_selection() -> None:
            alerts._select_settlement(place)
            await hourly_started.wait()
            await _settle(pilot, 2)

        await recorder.measure(
            'alerts.settlement_selection_loading',
            settlement_selection,
        )

        async def hourly_completion() -> None:
            hourly_release.set()
            await _settle(pilot, 4)

        await recorder.measure('alerts.hourly_completion_72h', hourly_completion)

        async def hourly_cache_hit() -> None:
            alerts._select_settlement(place)
            await _settle(pilot, 2)

        await recorder.measure('alerts.hourly_cache_hit_72h', hourly_cache_hit)
        await recorder.measure('alerts.resize_burst', lambda: _resize_burst(pilot))

        async def exit_alerts() -> None:
            await app.pop_screen()
            await _settle(pilot)

        await recorder.measure('alerts.exit_to_weather', exit_alerts)
        await recorder.measure('alerts.warm_reentry_persistent', open_alerts)

        async def switch_country_france() -> None:
            alerts._choose_country('FR')
            await _settle(pilot, 4)

        await recorder.measure('alerts.country_switch_6', switch_country_france)

        service.results['DE'] = _country_alerts(
            'shared',
            100,
            (WEST_GERMANY, EAST_GERMANY),
        )

        async def switch_shared_stress() -> None:
            alerts._choose_country('DE')
            await _settle(pilot, 4)

        await recorder.measure('alerts.country_switch_shared_100', switch_shared_stress)

        async def switch_unique_stress() -> None:
            alerts._choose_country('US')
            await _settle(pilot, 4)

        await recorder.measure('alerts.country_switch_us_unique_100', switch_unique_stress)

        async def stress_filter_sort() -> None:
            alerts.alert_severity_filter = 'moderate'
            alerts.alert_sort_value = 'new'
            alerts._apply_alert_filter('us-unique')
            await _settle(pilot, 3)

        await recorder.measure('alerts.filter_sort_unique_100', stress_filter_sort)

        pending_release = service.gate_next_request()
        alerts.action_refresh_alerts()
        await service.started.wait()
        await recorder.measure('alerts.exit_with_country_pending', exit_alerts)

        async def complete_country_while_hidden() -> None:
            pending_release.set()
            await _settle(pilot, 4)

        await recorder.measure(
            'alerts.country_completion_while_hidden',
            complete_country_while_hidden,
        )
        await recorder.measure('alerts.reentry_after_pending_completion', open_alerts)
        await app.pop_screen()
        await _settle(pilot)

        async def open_tropical() -> None:
            await app.open_tropical_systems_screen()
            await _settle(pilot, 4)

        await recorder.measure('tropical.cold_entry_2_systems_3_sources', open_tropical)
        tropical = app.screen
        assert isinstance(tropical, TropicalSystemsScreen)

        async def storm_selection() -> None:
            tropical.query_one('#tropical-storm-tabs', Tabs).active = (
                'tropical-storm-1'
            )
            await _settle(pilot, 3)

        await recorder.measure('tropical.storm_selection', storm_selection)

        tropical.query_one('#tropical-storm-tabs', Tabs).active = 'tropical-storm-0'
        await _settle(pilot, 3)

        async def source_selection() -> None:
            tropical.query_one('#tropical-source-tabs', Tabs).active = (
                'tropical-screen-source-1'
            )
            await _settle(pilot, 3)

        await recorder.measure('tropical.source_selection', source_selection)

        async def product_selection() -> None:
            tropical.query_one('#tropical-product-tabs', Tabs).active = (
                'tropical-product-2'
            )
            await _settle(pilot, 3)

        await recorder.measure('tropical.product_selection', product_selection)

        observation = tropical.selected_observation
        assert observation is not None
        observation_key = app._tropical_product_cache_key(observation)
        screen_key = '\0'.join(observation_key)
        tropical._products.pop(screen_key, None)
        product_release = asyncio.Event()

        async def delayed_products(system: TropicalSystem) -> list[TropicalProduct]:
            await product_release.wait()
            return _tropical_products(system)

        tropical._product_loader = delayed_products
        await tropical._show_observation()

        async def lazy_product_completion() -> None:
            product_release.set()
            await _settle(pilot, 4)

        await recorder.measure(
            'tropical.lazy_product_completion',
            lazy_product_completion,
        )

        centre_key = (
            round(float(observation.center_lat), 4),
            round(float(observation.center_lon), 4),
        )
        tropical._centre_weather.pop(centre_key, None)
        weather_release = asyncio.Event()

        async def delayed_centre_weather(
            latitude: float,
            longitude: float,
        ) -> dict[str, Any]:
            await weather_release.wait()
            return _tropical_centre_weather(latitude, longitude)

        tropical._centre_weather_loader = delayed_centre_weather
        tropical._show_centre_weather(observation)

        async def centre_weather_completion() -> None:
            weather_release.set()
            await _settle(pilot, 4)

        await recorder.measure(
            'tropical.centre_weather_completion',
            centre_weather_completion,
        )

        await recorder.measure('tropical.resize_burst', lambda: _resize_burst(pilot))

        async def refresh_tropical() -> None:
            tropical.action_refresh_systems()
            await _settle(pilot, 5)

        await recorder.measure('tropical.refresh', refresh_tropical)

        async def exit_tropical() -> None:
            await app.pop_screen()
            await _settle(pilot)

        await recorder.measure('tropical.exit_to_weather', exit_tropical)
        await recorder.measure('tropical.warm_reentry_cached_systems', open_tropical)
        await app.pop_screen()
        await _settle(pilot)

        async def open_world() -> None:
            app.open_world_locations_screen()
            await _settle(pilot, 4)

        await recorder.measure('world.cold_entry_3_locations', open_world)
        world = app.screen
        assert isinstance(world, WorldLocationsScreen)

        async def summary_updates() -> None:
            for index, location in enumerate((LONDON, NEW_YORK, TOKYO)):
                world.update_weather_summary(
                    location,
                    SavedLocationWeatherSummary(
                        temperature=12.0 + index,
                        temperature_unit='°C',
                    ),
                    temperature_unit='celsius',
                )
            await _settle(pilot, 3)

        await recorder.measure('world.summary_updates_3', summary_updates)

        async def move_focus() -> None:
            for _ in range(8):
                world.action_next_location()
            await _settle(pilot)

        await recorder.measure('world.selection_burst_8', move_focus)
        await recorder.measure('world.resize_burst', lambda: _resize_burst(pilot))

        async def exit_world() -> None:
            await app.pop_screen()
            await _settle(pilot)

        await recorder.measure('world.exit_to_weather', exit_world)
        await recorder.measure('world.warm_reentry_fresh_screen', open_world)

        async def activate_location() -> None:
            current = app.screen
            assert isinstance(current, WorldLocationsScreen)
            labels = list(current.world_map.query(WorldLocationLabel))
            labels[-1].action_select_location()
            await _settle(pilot, 4)

        await recorder.measure(
            'world.activate_to_weather_no_provider',
            activate_location,
        )
        assert app.screen is app.weather_screen

        stress_locations = _world_locations(40)

        async def open_stress_world() -> None:
            app.push_screen(
                WorldLocationsScreen(
                    stress_locations,
                    current_location=stress_locations[0],
                    temperature_unit='celsius',
                )
            )
            await _settle(pilot, 4)

        await recorder.measure('world.stress_entry_40_locations', open_stress_world)
        stress_world = app.screen
        assert isinstance(stress_world, WorldLocationsScreen)

        async def stress_summary_updates() -> None:
            for index, location in enumerate(stress_locations):
                stress_world.update_weather_summary(
                    location,
                    SavedLocationWeatherSummary(
                        temperature=-5.0 + index,
                        temperature_unit='°C',
                    ),
                    temperature_unit='celsius',
                )
            await _settle(pilot, 3)

        await recorder.measure('world.stress_summary_updates_40', stress_summary_updates)

        async def stress_focus() -> None:
            for _ in range(80):
                stress_world.action_next_location()
            await _settle(pilot)

        await recorder.measure('world.stress_selection_burst_80', stress_focus)
        await recorder.measure(
            'world.stress_resize_burst_40',
            lambda: _resize_burst(pilot),
        )
        await app.pop_screen()
        await _settle(pilot)

        transient_refs: list[weakref.ReferenceType[object]] = []
        weather_timer = weather._time_refresh_timer
        weather_stack_depth = len(app.screen_stack)

        async def search_cycles() -> None:
            for _ in range(LIFECYCLE_CYCLES):
                app.action_search()
                await _settle(pilot, 2)
                transient = app.screen
                assert isinstance(transient, SearchScreen)
                transient_refs.append(weakref.ref(transient))
                transient.dismiss()
                del transient
                await _settle(pilot, 2)

        await recorder.measure('lifecycle.weather_search_5_cycles', search_cycles)

        alerts_screen = app._alerts_centre_screen
        assert alerts_screen is not None
        if alerts_screen.selected_country_code != 'DE':
            alerts_screen._choose_country('DE')
            await _settle(pilot, 4)
        alerts_calls = service.calls

        async def alerts_cycles() -> None:
            for _ in range(LIFECYCLE_CYCLES):
                app.open_alerts_centre_screen()
                await _settle(pilot, 2)
                assert app.screen is alerts_screen
                await app.pop_screen()
                await _settle(pilot, 2)

        await recorder.measure('lifecycle.weather_alerts_5_cycles', alerts_cycles)

        async def tropical_cycles() -> None:
            for _ in range(LIFECYCLE_CYCLES):
                await app.open_tropical_systems_screen()
                await _settle(pilot, 3)
                transient = app.screen
                assert isinstance(transient, TropicalSystemsScreen)
                transient_refs.append(weakref.ref(transient))
                await app.pop_screen()
                del transient
                await _settle(pilot, 2)

        await recorder.measure('lifecycle.weather_tropical_5_cycles', tropical_cycles)

        async def world_cycles() -> None:
            for _ in range(LIFECYCLE_CYCLES):
                app.open_world_locations_screen()
                await _settle(pilot, 3)
                transient = app.screen
                assert isinstance(transient, WorldLocationsScreen)
                transient_refs.append(weakref.ref(transient))
                await app.pop_screen()
                del transient
                await _settle(pilot, 2)

        await recorder.measure('lifecycle.weather_world_5_cycles', world_cycles)

        search_started = asyncio.Event()
        search_release = asyncio.Event()

        async def delayed_search(*_args: Any, **_kwargs: Any) -> list[dict[str, object]]:
            search_started.set()
            await search_release.wait()
            return _places(10)

        with patch('wevva.screens.search_screen.search_places', new=delayed_search):
            app.action_search()
            await _settle(pilot, 2)
            pending_search = app.screen
            assert isinstance(pending_search, SearchScreen)
            pending_search.post_message(SearchQueryReady('pending'))
            await search_started.wait()
            pending_search_ref = weakref.ref(pending_search)

            async def exit_pending_search() -> None:
                pending_search.dismiss()
                search_release.set()
                await _settle(pilot, 3)

            await recorder.measure('lifecycle.search_pending_exit', exit_pending_search)
            transient_refs.append(pending_search_ref)
            del pending_search

        tropical_started = asyncio.Event()
        tropical_release = asyncio.Event()
        tropical_calls = 0

        async def delayed_systems() -> tuple[list[CanonicalTropicalSystem], bool]:
            nonlocal tropical_calls
            tropical_calls += 1
            tropical_started.set()
            await tropical_release.wait()
            return systems, True

        cache_now = time.monotonic()
        app._tropical_system_cache = (
            cache_now - app.TROPICAL_SYSTEM_CACHE_TTL_SECONDS,
            tuple(systems),
        )
        app._tropical_system_cache_clock = lambda: cache_now
        with patch('wevva.app.get_tropical_system_candidates_async', new=delayed_systems):
            await app.open_tropical_systems_screen()
            await tropical_started.wait()
            pending_tropical = app.screen
            assert isinstance(pending_tropical, TropicalSystemsScreen)
            pending_tropical_ref = weakref.ref(pending_tropical)

            async def exit_pending_tropical() -> None:
                await app.pop_screen()
                await _settle(pilot, 2)

            await recorder.measure(
                'lifecycle.tropical_expired_cache_pending_exit',
                exit_pending_tropical,
            )

            async def complete_tropical_while_hidden() -> None:
                tropical_release.set()
                await _settle(pilot, 4)

            await recorder.measure(
                'lifecycle.tropical_completion_while_hidden',
                complete_tropical_while_hidden,
            )
            transient_refs.append(pending_tropical_ref)
            del pending_tropical

            await recorder.measure(
                'lifecycle.tropical_reentry_after_hidden_completion',
                open_tropical,
            )
            await app.pop_screen()
            await _settle(pilot, 3)

        app._tropical_system_cache_clock = time.monotonic
        gc.collect()
        await _settle(pilot, 3)
        gc.collect()

        assert app.screen is weather
        assert len(app.screen_stack) == weather_stack_depth, [
            type(screen).__name__ for screen in app.screen_stack
        ]
        assert app._alerts_centre_screen is alerts_screen
        assert service.calls == alerts_calls
        assert alerts_screen._load_task is None
        assert alerts_screen._place_hourly_task is None
        assert app._tropical_system_fetch_task is None
        assert not app._tropical_product_tasks
        assert tropical_calls == 1
        assert weather._time_refresh_timer is weather_timer
        assert all(reference() is None for reference in transient_refs)
    finally:
        await runner.__aexit__(None, None, None)


async def _run_once(*, trace_memory: bool) -> dict[str, _Observation]:
    _clear_geography_caches()
    recorder = _Recorder(trace_memory=trace_memory)
    await _search_scenarios(recorder)
    await _workspace_scenarios(recorder)
    return recorder.results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeat', type=int, default=3)
    parser.add_argument(
        '--warmup',
        type=int,
        default=1,
        help='Discard this many complete harness runs before sampling.',
    )
    parser.add_argument(
        '--tracemalloc',
        action='store_true',
        help='Observe per-scenario Python allocation peaks (slower).',
    )
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error('--repeat must be at least 1')
    if args.warmup < 0:
        parser.error('--warmup cannot be negative')
    if args.tracemalloc:
        tracemalloc.start()

    for _ in range(args.warmup):
        asyncio.run(_run_once(trace_memory=False))
    runs = [
        asyncio.run(_run_once(trace_memory=args.tracemalloc))
        for _ in range(args.repeat)
    ]
    scenarios = {}
    for name in runs[0]:
        elapsed = [run[name].elapsed_ms for run in runs]
        peaks = [run[name].peak_kib for run in runs if run[name].peak_kib is not None]
        scenarios[name] = {
            'median_ms': round(median(elapsed), 3),
            'range_ms': [round(min(elapsed), 3), round(max(elapsed), 3)],
            'peak_kib': round(median(peaks), 1) if peaks else None,
        }

    print(
        json.dumps(
            {
                'environment': {
                    'python': platform.python_version(),
                    'implementation': platform.python_implementation(),
                    'textual': __import__('textual').__version__,
                    'platform': platform.platform(),
                    'machine': platform.machine(),
                    'terminal_sizes': ['80x24', '100x30', '140x45', '180x55'],
                    'provider_wait': (
                        'excluded; immediate fixtures or controlled gates '
                        'released at measurement start'
                    ),
                    'warmup': args.warmup,
                    'repeat': args.repeat,
                    'tracemalloc': args.tracemalloc,
                },
                'fixtures': {
                    'search_places': [10, 100, 10],
                    'weather': {'hourly_points': 72, 'daily_points': 7, 'alerts': 2},
                    'alerts_centre': {
                        'ordinary_alerts': 6,
                        'ordinary_unique_polygons': 2,
                        'stress_alerts': 100,
                        'stress_shapes': ['shared_2', 'mostly_unique_us'],
                        'hourly_points': 72,
                    },
                    'tropical': {'systems': 2, 'source_observations': 3},
                    'world_locations': {'ordinary': 3, 'stress': 40},
                    'resize_events_per_burst': 4,
                    'lifecycle_cycles': LIFECYCLE_CYCLES,
                },
                'scenarios': scenarios,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == '__main__':
    main()
