"""Cross-screen lifecycle regressions for Task 0025 Slice G."""

from __future__ import annotations

import asyncio
import gc
import time
import unittest
from unittest.mock import AsyncMock, patch
import weakref

from wevva_warnings import CanonicalTropicalSystem

from tests.test_tropical_systems_screen import _observation
from tests.test_world_locations_map import LONDON, NEW_YORK
from tests.weather_fixtures import weather_update
from wevva.app import Wevva
from wevva.location_metadata import LocationMetadata
from wevva.messages import SearchQueryReady
from wevva.screens.alerts_centre_screen import AlertsCentreScreen
from wevva.screens.search_screen import SearchScreen
from wevva.screens.tropical_systems_screen import TropicalSystemsScreen
from wevva.screens.weather_screen import WeatherScreen
from wevva.screens.world_locations_screen import WorldLocationsScreen


BERLIN = LocationMetadata(
    name='Berlin',
    country='Germany',
    country_code='DE',
    latitude=52.52,
    longitude=13.405,
)


def _systems() -> list[CanonicalTropicalSystem]:
    observation = _observation(
        'fixture-jma',
        'jma_tropical',
        'FIXTURE',
        classification='Typhoon',
        latitude=28.0,
        longitude=135.0,
        track=[[135.0, 28.0], [136.0, 29.0]],
    )
    return [CanonicalTropicalSystem('FIXTURE', [observation])]


class _CountryService:
    last_country_code: str | None = None

    def __init__(self, *, gated: bool = False) -> None:
        self.calls = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        if not gated:
            self.release.set()

    async def get_alerts(self, country_code: str, **_kwargs):
        self.calls += 1
        self.last_country_code = country_code
        self.started.set()
        await self.release.wait()
        return []

    def new_alert_identities(self, *_args, **_kwargs) -> frozenset:
        return frozenset()


async def _settle(pilot, cycles: int = 3) -> None:
    for _ in range(cycles):
        await pilot.pause(0)


class ScreenLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def _app(self, service: _CountryService) -> Wevva:
        systems = _systems()
        app = Wevva(
            initial_location=BERLIN,
            saved_locations=[LONDON, NEW_YORK],
            emoji_enabled=False,
        )
        app.action_refresh = AsyncMock()
        app.country_alerts_service = service  # type: ignore[assignment]
        app._tropical_system_cache = (time.monotonic(), tuple(systems))
        app.load_tropical_products = AsyncMock(return_value=[])
        app.load_tropical_centre_weather = AsyncMock(return_value={})
        app.weather_screen._city_temperature_loader = AsyncMock(return_value={})
        return app

    async def test_repeated_transitions_restore_one_stack_and_collect_fresh_screens(self) -> None:
        app = self._app(_CountryService())
        async with app.run_test(size=(100, 30)) as pilot:
            await _settle(pilot)
            weather = app.screen
            self.assertIsInstance(weather, WeatherScreen)
            await weather.on_weather_updated(weather_update())
            await _settle(pilot)
            timer = weather._time_refresh_timer
            stack_depth = len(app.screen_stack)
            transient_refs: list[weakref.ReferenceType[object]] = []

            for _ in range(3):
                app.action_search()
                await _settle(pilot)
                transient = app.screen
                self.assertIsInstance(transient, SearchScreen)
                transient_refs.append(weakref.ref(transient))
                transient.dismiss()
                del transient
                await _settle(pilot)

            app.open_alerts_centre_screen()
            await _settle(pilot, 4)
            alerts = app.screen
            self.assertIsInstance(alerts, AlertsCentreScreen)
            await app.pop_screen()
            await _settle(pilot)
            for _ in range(2):
                app.open_alerts_centre_screen()
                await _settle(pilot)
                self.assertIs(app.screen, alerts)
                await app.pop_screen()
                await _settle(pilot)

            for _ in range(3):
                await app.open_tropical_systems_screen()
                await _settle(pilot)
                transient = app.screen
                self.assertIsInstance(transient, TropicalSystemsScreen)
                transient_refs.append(weakref.ref(transient))
                await app.pop_screen()
                del transient
                await _settle(pilot)

                app.open_world_locations_screen()
                await _settle(pilot)
                transient = app.screen
                self.assertIsInstance(transient, WorldLocationsScreen)
                transient_refs.append(weakref.ref(transient))
                await app.pop_screen()
                del transient
                await _settle(pilot)

            gc.collect()
            await _settle(pilot)
            gc.collect()
            self.assertIs(app.screen, weather)
            self.assertEqual(len(app.screen_stack), stack_depth)
            self.assertIs(app._alerts_centre_screen, alerts)
            self.assertIs(weather._time_refresh_timer, timer)
            self.assertIsNone(alerts._load_task)
            self.assertIsNone(alerts._place_weather_task)
            self.assertTrue(all(reference() is None for reference in transient_refs))

    async def test_pending_transient_work_and_hidden_alerts_keep_their_owners(self) -> None:
        country_service = _CountryService(gated=True)
        app = self._app(country_service)
        systems = _systems()
        async with app.run_test(size=(100, 30)) as pilot:
            await _settle(pilot)
            weather = app.screen
            stack_depth = len(app.screen_stack)

            search_started = asyncio.Event()
            search_release = asyncio.Event()

            async def delayed_search(*_args, **_kwargs):
                search_started.set()
                await search_release.wait()
                return []

            with patch('wevva.screens.search_screen.search_places', new=delayed_search):
                app.action_search()
                await _settle(pilot)
                search = app.screen
                self.assertIsInstance(search, SearchScreen)
                search.post_message(SearchQueryReady('pending'))
                await search_started.wait()
                search_ref = weakref.ref(search)
                search.dismiss()
                search_release.set()
                del search
                await _settle(pilot, 4)

            app.open_alerts_centre_screen()
            await country_service.started.wait()
            alerts = app.screen
            self.assertIsInstance(alerts, AlertsCentreScreen)
            await app.pop_screen()
            self.assertIsNotNone(alerts._load_task)
            country_service.release.set()
            await _settle(pilot, 4)
            self.assertIsNone(alerts._load_task)
            app.open_alerts_centre_screen()
            await _settle(pilot)
            self.assertIs(app.screen, alerts)
            self.assertEqual(country_service.calls, 1)
            await app.pop_screen()

            tropical_started = asyncio.Event()
            tropical_release = asyncio.Event()
            tropical_calls = 0

            async def delayed_systems():
                nonlocal tropical_calls
                tropical_calls += 1
                tropical_started.set()
                await tropical_release.wait()
                return systems, True

            now = time.monotonic()
            app._tropical_system_cache = (
                now - app.TROPICAL_SYSTEM_CACHE_TTL_SECONDS,
                tuple(systems),
            )
            app._tropical_system_cache_clock = lambda: now
            with patch('wevva.app.get_tropical_system_candidates_async', new=delayed_systems):
                await app.open_tropical_systems_screen()
                await tropical_started.wait()
                tropical = app.screen
                self.assertIsInstance(tropical, TropicalSystemsScreen)
                tropical_ref = weakref.ref(tropical)
                await app.pop_screen()
                del tropical
                self.assertIsNotNone(app._tropical_system_fetch_task)
                tropical_release.set()
                await _settle(pilot, 5)
                self.assertIsNone(app._tropical_system_fetch_task)
                self.assertEqual(app._tropical_system_cache[1], tuple(systems))
                await app.open_tropical_systems_screen()
                await _settle(pilot)
                self.assertEqual(tropical_calls, 1)
                await app.pop_screen()

            app._tropical_system_cache_clock = time.monotonic
            gc.collect()
            await _settle(pilot)
            gc.collect()
            self.assertIs(app.screen, weather)
            self.assertEqual(len(app.screen_stack), stack_depth)
            self.assertIsNone(search_ref())
            self.assertIsNone(tropical_ref())
            self.assertFalse(app._tropical_product_tasks)


if __name__ == '__main__':
    unittest.main()
