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
from unittest.mock import AsyncMock

from textual.widgets import Tabs
from wevva_warnings import CanonicalTropicalSystem

from tests.test_alerts_centre_map import EAST_GERMANY, WEST_GERMANY, _alert
from tests.test_tropical_systems_screen import _observation
from tests.test_world_locations_map import LONDON, NEW_YORK, TOKYO
from tests.weather_fixtures import weather_update
from wevva import geography
from wevva.app import Wevva
from wevva.location_metadata import LocationMetadata
from wevva.screens.alerts_centre_screen import AlertsCentreScreen
from wevva.screens.search_screen import SearchScreen
from wevva.screens.tropical_systems_screen import TropicalSystemsScreen
from wevva.screens.weather_screen import WeatherScreen
from wevva.screens.world_locations_screen import WorldLocationsScreen
from wevva.widgets import country_alerts_map, tropical_track, world_locations_map


BERLIN = LocationMetadata(
    name='Berlin',
    country='Germany',
    country_code='DE',
    latitude=52.52,
    longitude=13.405,
)


class _CountryService:
    """Immediate deterministic substitute for country-warning retrieval."""

    last_country_code: str | None = None

    def __init__(self) -> None:
        self.calls = 0
        geometries = (WEST_GERMANY, EAST_GERMANY, WEST_GERMANY)
        self.alerts = [
            _alert(
                f'fixture-{index}',
                severity=('Severe', 'Moderate', 'Minor')[index % 3],
                geometry=geometries[index % len(geometries)],
            )
            for index in range(6)
        ]

    async def get_alerts(self, country_code: str, **_kwargs: Any) -> list:
        assert country_code == 'DE'
        self.calls += 1
        return list(self.alerts)

    def new_alert_identities(self, *_args: Any, **_kwargs: Any) -> frozenset:
        return frozenset()


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
        tropical_track._visible_world_polygons,
        world_locations_map._projected_world_land,
    ):
        cached.cache_clear()


async def _search_scenarios(recorder: _Recorder) -> None:
    async def construct() -> Wevva:
        return Wevva()

    app = await recorder.measure('startup.construct_no_location', construct)
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
    finally:
        await runner.__aexit__(None, None, None)


async def _workspace_scenarios(recorder: _Recorder) -> None:
    service = _CountryService()
    systems = _tropical_systems()

    async def construct() -> Wevva:
        return Wevva(
            initial_location=BERLIN,
            saved_locations=[LONDON, NEW_YORK, TOKYO],
            emoji_enabled=False,
        )

    app = await recorder.measure('startup.construct_with_location', construct)
    app.action_refresh = AsyncMock()
    app.country_alerts_service = service  # type: ignore[assignment]
    app.weather_screen._city_temperature_loader = AsyncMock(return_value={})
    app._tropical_system_cache = (time.monotonic(), tuple(systems))
    app.load_tropical_products = AsyncMock(return_value=[])
    app.load_tropical_centre_weather = AsyncMock(return_value={})
    runner = app.run_test(size=(140, 45))

    async def enter():
        pilot = await runner.__aenter__()
        await _settle(pilot, 3)
        return pilot

    pilot = await recorder.measure('weather.cold_entry', enter)
    try:
        weather = app.screen
        assert isinstance(weather, WeatherScreen)

        async def weather_update_local() -> None:
            await weather.on_weather_updated(weather_update())
            await _settle(pilot, 4)

        await recorder.measure('weather.forecast_update_72h', weather_update_local)
        await recorder.measure('weather.resize_burst', lambda: _resize_burst(pilot))

        async def open_alerts() -> None:
            app.open_alerts_centre_screen()
            await _settle(pilot, 4)

        await recorder.measure('alerts.cold_entry_6', open_alerts)
        alerts = app.screen
        assert isinstance(alerts, AlertsCentreScreen)

        async def alert_selection() -> None:
            alerts._select_alert(alerts.alerts[-1])
            await _settle(pilot, 2)

        await recorder.measure('alerts.selection', alert_selection)
        await recorder.measure('alerts.resize_burst', lambda: _resize_burst(pilot))

        async def exit_alerts() -> None:
            await app.pop_screen()
            await _settle(pilot)

        await recorder.measure('alerts.exit_to_weather', exit_alerts)
        await recorder.measure('alerts.warm_reentry_persistent', open_alerts)
        await app.pop_screen()
        await _settle(pilot)

        async def open_tropical() -> None:
            await app.open_tropical_systems_screen()
            await _settle(pilot, 4)

        await recorder.measure('tropical.cold_entry_2_systems_3_sources', open_tropical)
        tropical = app.screen
        assert isinstance(tropical, TropicalSystemsScreen)

        async def source_selection() -> None:
            tropical.query_one('#tropical-source-tabs', Tabs).active = (
                'tropical-screen-source-1'
            )
            await _settle(pilot, 3)

        await recorder.measure('tropical.source_selection', source_selection)
        await recorder.measure('tropical.resize_burst', lambda: _resize_burst(pilot))

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
                    'provider_wait': 'excluded; all loaders are immediate fixtures',
                    'warmup': args.warmup,
                    'repeat': args.repeat,
                    'tracemalloc': args.tracemalloc,
                },
                'fixtures': {
                    'search_places': [10, 100, 10],
                    'weather': {'hourly_points': 72, 'daily_points': 7, 'alerts': 2},
                    'alerts_centre': {'alerts': 6, 'unique_polygons': 2},
                    'tropical': {'systems': 2, 'source_observations': 3},
                    'world_locations': 3,
                    'resize_events_per_burst': 4,
                },
                'scenarios': scenarios,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == '__main__':
    main()
