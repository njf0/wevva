"""Focused checks for the TUI's session-only warning-result cache."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, Mock, call, patch

from wevva.alerts import Alert
from wevva.app import Wevva
from wevva.location_metadata import LocationMetadata
from wevva.messages import WeatherAlertsProgress, WeatherAlertsUpdated
from wevva.services.alerts import (
    AlertCandidateResult,
    _get_alerts_with_status,
    _get_native_alerts_with_status,
    get_alert_candidates_async,
    match_alert_candidates,
    match_alert_candidates_async,
)
from wevva.services.warning_cache import (
    WarningCache,
    WarningCacheProduct,
)
from wevva.widgets.saved_locations import SavedLocationsSidebar
from wevva_warnings import UnsupportedCountryError, WarningSource


class _WeatherScreen:
    def __init__(self) -> None:
        self.messages = []
        self.warning_checking = []

    def post_message(self, message) -> None:
        self.messages.append(message)

    def set_warning_checking(self, checking: bool) -> None:
        self.warning_checking.append(checking)


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
        self.app.notify = Mock()
        self.app._refresh_generation = 1
        self.clock = 1_000.0
        self.app._alert_cache_clock = lambda: self.clock

    async def _schedule_and_wait(self, *, force_refresh: bool = False) -> None:
        self.app._schedule_alert_refresh(1, force_refresh=force_refresh)
        if self.app._alerts_task is not None:
            await self.app._alerts_task

    def test_country_candidate_cache_lasts_thirty_minutes(self) -> None:
        self.assertEqual(self.app.ALERT_CACHE_TTL_SECONDS, 30 * 60)

    def test_alerts_centre_uses_the_application_warning_cache(self) -> None:
        self.assertIs(
            self.app.country_alerts_service.cache,
            self.app.warning_cache,
        )

    def _alert_updates(self) -> list[WeatherAlertsUpdated]:
        return [
            message
            for message in self.app.weather_screen.messages
            if isinstance(message, WeatherAlertsUpdated)
        ]

    async def test_cache_hit_and_forced_refresh(self) -> None:
        reusable_lookup = AsyncMock(return_value=([
            _alert_in_box('berlin', min_lat=52.3, max_lat=52.8, min_lon=13.0, max_lon=13.8),
            _alert_in_box('munich', min_lat=47.9, max_lat=48.4, min_lon=11.2, max_lon=11.9),
        ], True))
        native_lookup = AsyncMock(return_value=([], True))
        with (
            patch('wevva.app.get_alert_candidates_async', new=reusable_lookup),
            patch('wevva.app.get_native_point_alerts_async', new=native_lookup),
        ):
            await self._schedule_and_wait()
            await self._schedule_and_wait()

            self.app.location = LocationMetadata(latitude=48.137, longitude=11.575, country_code='DE')
            await self._schedule_and_wait()
            await self._schedule_and_wait(force_refresh=True)

        self.assertEqual(reusable_lookup.await_count, 2)
        self.assertEqual(native_lookup.await_count, 4)
        self.assertEqual(len(self.app._alert_cache), 1)
        updates = self._alert_updates()
        self.assertEqual([alert.id for alert in updates[0].alerts], ['berlin'])
        self.assertEqual([alert.id for alert in updates[2].alerts], ['munich'])
        self.assertEqual(len(updates), 4)

    async def test_ttl_expiry_discards_entry_and_queries_again(self) -> None:
        reusable_lookup = AsyncMock(return_value=([], True))
        native_lookup = AsyncMock(return_value=([], True))
        with (
            patch('wevva.app.get_alert_candidates_async', new=reusable_lookup),
            patch('wevva.app.get_native_point_alerts_async', new=native_lookup),
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
            patch('wevva.app.get_alert_candidates_async', new=reusable_lookup),
            patch('wevva.app.get_native_point_alerts_async', new=native_lookup),
        ):
            await self._schedule_and_wait()
            await self._schedule_and_wait()
        self.assertEqual(reusable_lookup.await_count, 1)
        self.assertEqual(len(self.app._alert_cache), 1)

        self.app._alert_cache.clear()
        with (
            patch('wevva.app.get_alert_candidates_async', new=reusable_lookup),
            patch('wevva.app.get_native_point_alerts_async', new=native_lookup),
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

        with patch('wevva.app.get_alert_candidates_async', new=lookup):
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
            patch('wevva.app.get_alert_candidates_async', new=reusable_lookup),
            patch('wevva.app.get_native_point_alerts_async', new=native_lookup),
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
        with patch('wevva.app.get_native_point_alerts_async', new=AsyncMock(return_value=([], True))):
            await self._schedule_and_wait()
        self.assertEqual(self._alert_updates()[-1].alerts, [])

    async def test_stale_location_cannot_receive_old_result(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def lookup(*_args, **_kwargs):
            started.set()
            await release.wait()
            return [], True

        with patch('wevva.app.get_alert_candidates_async', new=lookup):
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
            patch('wevva.app.get_alert_candidates_async', new=reusable_lookup),
            patch('wevva.app.get_native_point_alerts_async', new=native_lookup),
        ):
            await self._schedule_and_wait()
            self.app.location = LocationMetadata(latitude=39.7392, longitude=-104.9903, country_code='US')
            await self._schedule_and_wait()

        self.assertEqual(reusable_lookup.await_count, 1)
        self.assertEqual(native_lookup.await_count, 2)
        updates = self._alert_updates()
        self.assertEqual([alert.id for alert in updates[0].alerts], ['new-york'])
        self.assertEqual([alert.id for alert in updates[1].alerts], ['denver'])

    async def test_cached_candidates_report_measured_matching_progress(self) -> None:
        self.app._alert_cache[('DE', 'auto')] = self.clock, (
            _alert_in_box('berlin', min_lat=52.3, max_lat=52.8, min_lon=13.0, max_lon=13.8),
            _alert_in_box('munich', min_lat=47.9, max_lat=48.4, min_lon=11.2, max_lon=11.9),
        )

        with patch(
            'wevva.app.get_native_point_alerts_async',
            new=AsyncMock(return_value=([], True)),
        ):
            await self._schedule_and_wait()

        progress = [
            message
            for message in self.app.weather_screen.messages
            if isinstance(message, WeatherAlertsProgress)
        ]
        self.assertEqual(
            [(message.event, message.payload) for message in progress],
            [
                ('alerts_total', {'total': 2, 'phase': 'matching'}),
                ('alerts_checked', {'completed': 1, 'total': 2, 'phase': 'matching'}),
                ('alerts_checked', {'completed': 2, 'total': 2, 'phase': 'matching'}),
            ],
        )

    async def test_warning_indicator_wraps_empty_success_without_toasts(self) -> None:
        with (
            patch(
                'wevva.app.get_alert_candidates_async',
                new=AsyncMock(return_value=([], True)),
            ),
            patch(
                'wevva.app.get_native_point_alerts_async',
                new=AsyncMock(return_value=([], True)),
            ),
        ):
            await self._schedule_and_wait()

        self.assertEqual(self.app.weather_screen.warning_checking, [True, False])
        self.app.notify.assert_not_called()

    async def test_warning_progress_does_not_create_toasts(self) -> None:
        def report_progress(_country_code, _warning_language, *, progress):
            progress('source_started', {'source': 'dwd'})
            progress('alerts_total', {'total': 2, 'phase': 'documents'})
            progress(
                'alerts_checked',
                {'completed': 1, 'total': 2, 'phase': 'documents'},
            )
            return [], True

        with (
            patch(
                'wevva.app.get_alert_candidates_async',
                new=AsyncMock(side_effect=report_progress),
            ),
            patch(
                'wevva.app.get_native_point_alerts_async',
                new=AsyncMock(return_value=([], True)),
            ),
        ):
            await self._schedule_and_wait()

        self.assertEqual(self.app.weather_screen.warning_checking, [True, False])
        self.app.notify.assert_not_called()

    async def test_warning_failure_stops_indicator_without_toast(self) -> None:
        with (
            patch(
                'wevva.app.get_alert_candidates_async',
                new=AsyncMock(return_value=([], False)),
            ),
            patch(
                'wevva.app.get_native_point_alerts_async',
                new=AsyncMock(return_value=([], True)),
            ),
        ):
            await self._schedule_and_wait()

        self.assertEqual(self.app.weather_screen.warning_checking, [True, False])
        self.app.notify.assert_not_called()

    async def test_active_warning_uses_widget_instead_of_terminal_toast(self) -> None:
        alert = _alert_in_box(
            'berlin',
            min_lat=52.3,
            max_lat=52.8,
            min_lon=13.0,
            max_lon=13.8,
        )
        with (
            patch(
                'wevva.app.get_alert_candidates_async',
                new=AsyncMock(return_value=([alert], True)),
            ),
            patch(
                'wevva.app.get_native_point_alerts_async',
                new=AsyncMock(return_value=([], True)),
            ),
        ):
            await self._schedule_and_wait()

        self.assertEqual(self.app.weather_screen.warning_checking, [True, False])
        self.app.notify.assert_not_called()
        self.assertEqual(self._alert_updates()[-1].alerts, [alert])

    async def test_visible_progress_sidebar_uses_same_header_indicator(self) -> None:
        self.app.weather_screen.saved_locations_sidebar_visible = True
        with (
            patch(
                'wevva.app.get_alert_candidates_async',
                new=AsyncMock(return_value=([], True)),
            ),
            patch(
                'wevva.app.get_native_point_alerts_async',
                new=AsyncMock(return_value=([], True)),
            ),
        ):
            await self._schedule_and_wait()

        self.assertEqual(self.app.weather_screen.warning_checking, [True, False])
        self.app.notify.assert_not_called()


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

        alerts = match_alert_candidates([reusable_alert], [native_alert], 40.7128, -74.0060)

        self.assertEqual([alert.id for alert in alerts], ['geometry', 'nws-point'])

    def test_combining_reports_measured_matching_progress(self) -> None:
        progress = Mock()
        reusable_alert = _alert_in_box('geometry', min_lat=40.0, max_lat=41.0, min_lon=-75.0, max_lon=-73.0)
        unmatched_alert = _alert_in_box('elsewhere', min_lat=50.0, max_lat=51.0, min_lon=-2.0, max_lon=-1.0)

        alerts = match_alert_candidates(
            [reusable_alert, unmatched_alert],
            [],
            40.7128,
            -74.0060,
            progress=progress,
        )

        self.assertEqual([alert.id for alert in alerts], ['geometry'])
        self.assertEqual(
            progress.call_args_list,
            [
                call('alerts_total', {'total': 2, 'phase': 'matching'}),
                call('alerts_checked', {'completed': 1, 'total': 2, 'phase': 'matching'}),
                call('alerts_checked', {'completed': 2, 'total': 2, 'phase': 'matching'}),
            ],
        )


class AlertCandidateServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_empty_candidate_result_is_cacheable(self) -> None:
        with patch('wevva.services.alerts.get_reusable_alerts_for_country', return_value=[]):
            result = await get_alert_candidates_async('GB')

        self.assertEqual(result, AlertCandidateResult(candidates=[], completed=True))

    async def test_unsupported_country_is_a_completed_empty_result(self) -> None:
        with patch(
            'wevva.services.alerts.get_reusable_alerts_for_country',
            side_effect=UnsupportedCountryError('ZZ'),
        ):
            result = await get_alert_candidates_async('ZZ')

        self.assertEqual(result, AlertCandidateResult(candidates=[], completed=True))

    async def test_provider_failure_is_an_uncacheable_empty_result(self) -> None:
        with patch(
            'wevva.services.alerts.get_reusable_alerts_for_country',
            side_effect=RuntimeError('offline'),
        ):
            result = await get_alert_candidates_async('GB')

        self.assertEqual(result, AlertCandidateResult(candidates=[], completed=False))

    async def test_candidate_cancellation_propagates_without_a_result(self) -> None:
        with patch(
            'wevva.services.alerts.asyncio.to_thread',
            new=AsyncMock(side_effect=asyncio.CancelledError),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await get_alert_candidates_async('GB')

    async def test_matching_failure_is_normalized_by_the_service(self) -> None:
        with patch(
            'wevva.services.alerts.match_alert_candidates',
            side_effect=RuntimeError('invalid geometry'),
        ):
            alerts = await match_alert_candidates_async([], [], 51.5, -0.1)

        self.assertEqual(alerts, [])


class PersistentWarningCacheTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.now = datetime(2030, 1, 2, 12, tzinfo=UTC)
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.cache_path = Path(self.temporary_directory.name)

    def _cache(self) -> WarningCache:
        return WarningCache(
            self.cache_path,
            clock=lambda: self.now,
        )

    def _complete_alert(self, *, source: str = 'fixture') -> Alert:
        return Alert(
            id='alert-1',
            source=source,
            event='Flood Warning',
            headline='Flooding expected',
            url='https://example.test/alert-1',
            severity='Severe',
            urgency='Immediate',
            certainty='Likely',
            description='Complete provider description.',
            instruction='Move to higher ground.',
            onset=self.now - timedelta(minutes=10),
            expires=self.now + timedelta(hours=2),
            area_names=['North district', 'River valley'],
            geocodes={'SAME': ['012345'], 'UGC': ['ABC001']},
            parameters={'response': ['Evacuate'], 'flag': ['α', 'β']},
            geometry={
                'type': 'GeometryCollection',
                'geometries': [
                    {
                        'type': 'Polygon',
                        'coordinates': [[[-1.0, 50.0], [0.0, 51.0], [-1.0, 50.0]]],
                    },
                    {'type': 'Point', 'coordinates': [-0.5, 50.5]},
                ],
            },
        )

    async def test_round_trip_preserves_every_alert_field_and_metadata(self) -> None:
        source = WarningSource(
            id='fixture',
            name='Fixture warnings',
            backend='fixture',
            country_code='GB',
            url='https://example.test',
        )
        cache = self._cache()
        alert = self._complete_alert()

        stored = await cache.store(
            WarningCacheProduct.COUNTRY_CATALOGUE,
            'gbr',
            'en',
            [alert],
            fetched_at=self.now,
            new_alert_identities={('fixture', 'alert-1')},
        )
        restarted = self._cache()
        with patch(
            'wevva.services.warning_cache.list_sources',
            return_value=[source],
        ):
            entry = await restarted.load('country_catalogue', 'GB', 'en')

        self.assertTrue(stored)
        self.assertIsNotNone(entry)
        assert entry is not None
        restored = entry.alerts[0]
        for field_name in (
            'id',
            'source',
            'event',
            'headline',
            'url',
            'severity',
            'urgency',
            'certainty',
            'description',
            'instruction',
            'onset',
            'expires',
            'area_names',
            'geocodes',
            'parameters',
            'geometry',
        ):
            self.assertEqual(getattr(restored, field_name), getattr(alert, field_name))
        self.assertIs(restored.source_info, source)
        self.assertEqual(entry.fetched_at, self.now)
        self.assertEqual(
            entry.new_alert_identities,
            frozenset({('fixture', 'alert-1')}),
        )

    async def test_product_and_language_namespaces_do_not_collide(self) -> None:
        cache = self._cache()
        catalogue = self._complete_alert(source='unknown-catalogue')
        candidates = self._complete_alert(source='unknown-candidates')

        await cache.store('country_catalogue', 'GB', 'auto', [catalogue])
        await cache.store('reusable_candidates', 'GB', 'auto', [candidates])
        await cache.store('country_catalogue', 'GB', 'en', [])
        restarted = self._cache()

        auto_catalogue = await restarted.load('country_catalogue', 'GB')
        auto_candidates = await restarted.load('reusable_candidates', 'GB')
        english_catalogue = await restarted.load('country_catalogue', 'GB', 'en')

        assert auto_catalogue is not None
        assert auto_candidates is not None
        assert english_catalogue is not None
        self.assertEqual(auto_catalogue.alerts[0].source, 'unknown-catalogue')
        self.assertIsNone(auto_catalogue.alerts[0].source_info)
        self.assertEqual(auto_candidates.alerts[0].source, 'unknown-candidates')
        self.assertEqual(english_catalogue.alerts, ())
        self.assertEqual(len(list(self.cache_path.glob('*.json.gz'))), 3)

    async def test_incomplete_or_malformed_entries_do_not_replace_success(self) -> None:
        cache = self._cache()
        original = self._complete_alert()
        self.assertTrue(
            await cache.store('country_catalogue', 'GB', 'auto', [original])
        )
        malformed = self._complete_alert()
        malformed.geometry = {'type': 'Point', 'coordinates': [float('nan'), 2.0]}

        self.assertFalse(
            await cache.store(
                'country_catalogue',
                'GB',
                'auto',
                [],
                completed=False,
            )
        )
        self.assertFalse(
            await cache.store('country_catalogue', 'GB', 'auto', [malformed])
        )
        entry = await cache.load('country_catalogue', 'GB')

        assert entry is not None
        self.assertEqual([alert.id for alert in entry.alerts], ['alert-1'])

    async def test_corrupt_incompatible_and_future_files_are_cache_misses(self) -> None:
        cache = self._cache()
        path = self.cache_path / 'country_catalogue-GB-auto.json.gz'
        path.parent.mkdir(parents=True, exist_ok=True)

        path.write_bytes(b'not gzip data')
        self.assertIsNone(await self._cache().load('country_catalogue', 'GB'))

        path.write_bytes(gzip.compress(json.dumps({'schema_version': 999}).encode()))
        self.assertIsNone(await self._cache().load('country_catalogue', 'GB'))

        future_writer = WarningCache(
            self.cache_path,
            clock=lambda: self.now + timedelta(minutes=6),
        )
        self.assertTrue(
            await future_writer.store('country_catalogue', 'GB', 'auto', [])
        )
        self.assertIsNone(
            await self._cache().load('country_catalogue', 'GB')
        )

    async def test_unwritable_path_keeps_validated_entry_in_memory(self) -> None:
        blocked_path = self.cache_path / 'not-a-directory'
        blocked_path.write_text('occupied')
        cache = WarningCache(blocked_path, clock=lambda: self.now)

        self.assertFalse(
            await cache.store('reusable_candidates', 'GB', 'auto', [])
        )
        entry = await cache.load('reusable_candidates', 'GB')

        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.alerts, ())

    async def test_atomic_replacement_leaves_no_temporary_file(self) -> None:
        cache = self._cache()
        await cache.store('country_catalogue', 'GB', 'auto', [])
        await cache.store(
            'country_catalogue',
            'GB',
            'auto',
            [self._complete_alert()],
            fetched_at=self.now + timedelta(minutes=1),
        )

        self.assertEqual(list(self.cache_path.glob('*.tmp')), [])
        entry = await self._cache().load('country_catalogue', 'GB')
        assert entry is not None
        self.assertEqual([alert.id for alert in entry.alerts], ['alert-1'])


class WarningProgressTests(unittest.TestCase):
    def test_provider_start_uses_an_indeterminate_progress_bar(self) -> None:
        self.assertEqual(
            SavedLocationsSidebar._warning_progress_details('source_started', {'source': 'dwd'}),
            (0, None),
        )
        self.assertEqual(SavedLocationsSidebar._warning_progress_title(None), 'Fetching alerts')

    def test_alert_total_switches_to_measured_progress(self) -> None:
        self.assertEqual(
            SavedLocationsSidebar._warning_progress_details(
                'alerts_total',
                {'source': 'dwd', 'total': 3, 'phase': 'matching'},
            ),
            (0, 3),
        )
        self.assertEqual(SavedLocationsSidebar._warning_progress_title(3), 'Checking alerts')

    def test_later_sources_do_not_restart_indeterminate_progress(self) -> None:
        self.assertIsNone(
            SavedLocationsSidebar._warning_progress_details(
                'source_started',
                {'source': 'nearby_tropical_systems'},
                has_measured_progress=True,
            )
        )

if __name__ == '__main__':
    unittest.main()
