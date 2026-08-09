"""Focused checks for the TUI's session-only warning-result cache."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import unittest
from unittest.mock import AsyncMock, patch

from wevva.alerts import Alert
from wevva.app import Wevva
from wevva.location_metadata import LocationMetadata
from wevva.services.alerts import _combine_alerts, _get_alerts_with_status, _get_native_alerts_with_status
from wevva.widgets.saved_locations import SavedLocationsSidebar


class _WeatherScreen:
    def __init__(self) -> None:
        self.messages = []

    def post_message(self, message) -> None:
        self.messages.append(message)


def _alert_in_box(identifier: str, *, min_lat: float, max_lat: float, min_lon: float, max_lon: float) -> Alert:
    return Alert(
        id=identifier,
        source='test',
        event='Rain',
        headline=f'{identifier} rain warning',
        geometry={
            'type': 'Polygon',
            'coordinates': [[
                [min_lon, min_lat],
                [max_lon, min_lat],
                [max_lon, max_lat],
                [min_lon, max_lat],
                [min_lon, min_lat],
            ]],
        },
    )


class WarningCacheTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.location = LocationMetadata(latitude=52.52, longitude=13.405, country_code='DE')
        self.app = Wevva(initial_location=self.location)
        self.app.weather_screen = _WeatherScreen()
        self.app._refresh_generation = 1
        self.clock = 1_000.0
        self.app._alert_cache_clock = lambda: self.clock

    async def _schedule_and_wait(self, *, force_refresh: bool = False) -> None:
        self.app._schedule_alert_refresh(1, force_refresh=force_refresh)
        if self.app._alerts_task is not None:
            await self.app._alerts_task

    async def test_cache_hit_and_forced_refresh(self) -> None:
        reusable_lookup = AsyncMock(return_value=([
            _alert_in_box('berlin', min_lat=52.3, max_lat=52.8, min_lon=13.0, max_lon=13.8),
            _alert_in_box('munich', min_lat=47.9, max_lat=48.4, min_lon=11.2, max_lon=11.9),
        ], True))
        native_lookup = AsyncMock(return_value=([], True))
        with (
            patch('wevva.app._get_reusable_alerts_async_with_status', new=reusable_lookup),
            patch('wevva.app._get_native_alerts_async_with_status', new=native_lookup),
        ):
            await self._schedule_and_wait()
            await self._schedule_and_wait()

            self.app.location = LocationMetadata(latitude=48.137, longitude=11.575, country_code='DE')
            await self._schedule_and_wait()
            await self._schedule_and_wait(force_refresh=True)

        self.assertEqual(reusable_lookup.await_count, 2)
        self.assertEqual(native_lookup.await_count, 4)
        self.assertEqual(len(self.app._alert_cache), 1)
        self.assertEqual([alert.id for alert in self.app.weather_screen.messages[0].alerts], ['berlin'])
        self.assertEqual([alert.id for alert in self.app.weather_screen.messages[2].alerts], ['munich'])
        self.assertEqual(len(self.app.weather_screen.messages), 4)

    async def test_ttl_expiry_discards_entry_and_queries_again(self) -> None:
        reusable_lookup = AsyncMock(return_value=([], True))
        native_lookup = AsyncMock(return_value=([], True))
        with (
            patch('wevva.app._get_reusable_alerts_async_with_status', new=reusable_lookup),
            patch('wevva.app._get_native_alerts_async_with_status', new=native_lookup),
        ):
            await self._schedule_and_wait()
            self.clock += self.app.ALERT_CACHE_TTL_SECONDS
            await self._schedule_and_wait()

        self.assertEqual(reusable_lookup.await_count, 2)
        self.assertEqual(native_lookup.await_count, 2)
        self.assertEqual(len(self.app._alert_cache), 1)

    async def test_empty_success_is_cached_but_failure_is_not(self) -> None:
        reusable_lookup = AsyncMock(side_effect=[([], True), ([], False), ([], False)])
        native_lookup = AsyncMock(return_value=([], True))
        with (
            patch('wevva.app._get_reusable_alerts_async_with_status', new=reusable_lookup),
            patch('wevva.app._get_native_alerts_async_with_status', new=native_lookup),
        ):
            await self._schedule_and_wait()
            await self._schedule_and_wait()
        self.assertEqual(reusable_lookup.await_count, 1)
        self.assertEqual(len(self.app._alert_cache), 1)

        self.app._alert_cache.clear()
        with (
            patch('wevva.app._get_reusable_alerts_async_with_status', new=reusable_lookup),
            patch('wevva.app._get_native_alerts_async_with_status', new=native_lookup),
        ):
            await self._schedule_and_wait()
            await self._schedule_and_wait()
        self.assertEqual(reusable_lookup.await_count, 3)
        self.assertEqual(native_lookup.await_count, 4)
        self.assertEqual(self.app._alert_cache, {})

    async def test_cancelled_lookup_is_not_cached(self) -> None:
        started = asyncio.Event()
        unblock = asyncio.Event()

        async def lookup(*_args, **_kwargs):
            started.set()
            await unblock.wait()
            return [], True

        with patch('wevva.app._get_reusable_alerts_async_with_status', new=lookup):
            self.app._schedule_alert_refresh(1)
            assert self.app._alerts_task is not None
            await started.wait()
            self.app._alerts_task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await self.app._alerts_task

        self.assertEqual(self.app._alert_cache, {})

    async def test_key_changes_and_expired_alert_filtering(self) -> None:
        reusable_lookup = AsyncMock(return_value=([], True))
        native_lookup = AsyncMock(return_value=([], True))
        with (
            patch('wevva.app._get_reusable_alerts_async_with_status', new=reusable_lookup),
            patch('wevva.app._get_native_alerts_async_with_status', new=native_lookup),
        ):
            await self._schedule_and_wait()
            self.app.location.country_code = 'DEU'
            await self._schedule_and_wait()
            self.app.location.longitude = -0.2
            await self._schedule_and_wait()
            self.app.location.country_code = 'FRA'
            await self._schedule_and_wait()
            self.app.warning_language = 'en'
            await self._schedule_and_wait()

        self.assertEqual(reusable_lookup.await_count, 3)
        self.assertEqual(native_lookup.await_count, 5)

        expired_alert = Alert(
            id='expired',
            source='test',
            event='Rain',
            headline='Expired rain warning',
            expires=datetime.now(UTC) - timedelta(seconds=1),
        )
        self.app.location = LocationMetadata(latitude=52.52, longitude=13.405, country_code='DE')
        self.app.warning_language = 'auto'
        key = ('DE', 'auto')
        self.app._alert_cache[key] = self.clock, (expired_alert,)
        with patch('wevva.app._get_native_alerts_async_with_status', new=AsyncMock(return_value=([], True))):
            await self._schedule_and_wait()
        self.assertEqual(self.app.weather_screen.messages[-1].alerts, [])

    async def test_stale_location_cannot_receive_old_result(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def lookup(*_args, **_kwargs):
            started.set()
            await release.wait()
            return [], True

        with patch('wevva.app._get_reusable_alerts_async_with_status', new=lookup):
            self.app._schedule_alert_refresh(1)
            assert self.app._alerts_task is not None
            await started.wait()
            self.app.location = LocationMetadata(latitude=48.9, longitude=2.3, country_code='FRA')
            release.set()
            await self.app._alerts_task

        self.assertEqual(self.app.weather_screen.messages, [])

    async def test_native_point_results_are_not_cached_between_us_locations(self) -> None:
        self.app.location = LocationMetadata(latitude=40.7128, longitude=-74.0060, country_code='US')
        reusable_lookup = AsyncMock(return_value=([], True))
        native_lookup = AsyncMock(side_effect=[
            ([Alert(id='new-york', source='nws', event='Flood', headline='New York flood')], True),
            ([Alert(id='denver', source='nws', event='Fire', headline='Denver fire')], True),
        ])

        with (
            patch('wevva.app._get_reusable_alerts_async_with_status', new=reusable_lookup),
            patch('wevva.app._get_native_alerts_async_with_status', new=native_lookup),
        ):
            await self._schedule_and_wait()
            self.app.location = LocationMetadata(latitude=39.7392, longitude=-104.9903, country_code='US')
            await self._schedule_and_wait()

        self.assertEqual(reusable_lookup.await_count, 1)
        self.assertEqual(native_lookup.await_count, 2)
        self.assertEqual([alert.id for alert in self.app.weather_screen.messages[0].alerts], ['new-york'])
        self.assertEqual([alert.id for alert in self.app.weather_screen.messages[1].alerts], ['denver'])


class AlertServiceStatusTests(unittest.TestCase):
    def test_provider_failure_is_not_a_successful_empty_result(self) -> None:
        with patch('wevva.services.alerts.get_alerts_for_point', side_effect=RuntimeError('offline')):
            alerts, completed = _get_alerts_with_status(51.5, -0.1, 'GB')
        self.assertEqual(alerts, [])
        self.assertFalse(completed)

    def test_native_point_result_is_preserved_without_geometry(self) -> None:
        native_alert = Alert(id='nws-point', source='nws', event='Flood', headline='Point-query flood')
        with patch('wevva.services.alerts.get_native_alerts_for_point', return_value=[native_alert]) as lookup:
            alerts, completed = _get_native_alerts_with_status(40.7128, -74.0060, 'US')

        self.assertTrue(completed)
        self.assertEqual(alerts, [native_alert])
        lookup.assert_called_once_with(
            lat=40.7128,
            lon=-74.0060,
            country_code='US',
            lang=None,
            active_only=False,
        )

    def test_combining_keeps_native_point_results_and_matches_cached_candidates(self) -> None:
        reusable_alert = _alert_in_box('geometry', min_lat=40.0, max_lat=41.0, min_lon=-75.0, max_lon=-73.0)
        native_alert = Alert(id='nws-point', source='nws', event='Flood', headline='Point-query flood')

        alerts = _combine_alerts([reusable_alert], [native_alert], 40.7128, -74.0060)

        self.assertEqual([alert.id for alert in alerts], ['geometry', 'nws-point'])


class WarningProgressTests(unittest.TestCase):
    def test_provider_start_uses_an_indeterminate_progress_bar(self) -> None:
        self.assertEqual(
            SavedLocationsSidebar._warning_progress_details('source_started', {'source': 'dwd'}),
            (0, None),
        )
        self.assertEqual(SavedLocationsSidebar._warning_progress_title(None), 'Fetching warnings')

    def test_alert_total_switches_to_measured_progress(self) -> None:
        self.assertEqual(
            SavedLocationsSidebar._warning_progress_details(
                'alerts_total',
                {'source': 'dwd', 'total': 3, 'phase': 'matching'},
            ),
            (0, 3),
        )
        self.assertEqual(SavedLocationsSidebar._warning_progress_title(3), 'Checking warnings')


if __name__ == '__main__':
    unittest.main()
