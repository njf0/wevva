"""Deterministic checks for nearby tropical-system context."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import ANY, AsyncMock, Mock, call, patch

from wevva.alerts import Alert
from wevva.app import Wevva
from wevva.location_metadata import LocationMetadata
from wevva.messages import TropicalSystemsProgress, WeatherAlertsUpdated, WeatherUpdated
from wevva.services.tropical import (
    NearbyTropicalSystem,
    center_distance_km,
    get_tropical_system_candidates,
    get_nearby_tropical_systems,
    haversine_distance_km,
    nearby_tropical_systems_from_candidates,
)
from wevva.widgets.tropical_systems import (
    build_tropical_coordinates_text,
    build_tropical_system_text,
    build_tropical_tab_label,
    tropical_system_detail_rows,
)
from wevva.widgets.weather_alerts import WeatherAlertsPanel
from wevva_warnings import TropicalSystem


class _WeatherScreen:
    def __init__(self) -> None:
        self.messages = []

    def post_message(self, message) -> None:
        self.messages.append(message)


def _system(**overrides) -> TropicalSystem:
    values = {
        'id': 'test-system',
        'source': 'test-source',
        'classification': 'Tropical Storm',
        'name': 'DOLPHIN',
        'headline': 'Tropical Storm DOLPHIN',
    }
    values.update(overrides)
    return TropicalSystem(**values)


class TropicalServiceTests(unittest.TestCase):
    def test_center_distance_uses_local_haversine_calculation(self) -> None:
        system = _system(center_lat=0.0, center_lon=1.0)

        self.assertAlmostEqual(haversine_distance_km(0.0, 0.0, 0.0, 1.0), 111.195080, places=5)
        self.assertAlmostEqual(center_distance_km(system, 0.0, 0.0), 111.195080, places=5)

    def test_empty_raw_result_is_cacheable(self) -> None:
        with patch('wevva.services.tropical.get_tropical_systems', return_value=[]) as lookup:
            systems, completed = get_tropical_system_candidates()

        self.assertEqual(systems, [])
        self.assertTrue(completed)
        lookup.assert_called_once_with()

    def test_provider_failure_is_quiet(self) -> None:
        with patch('wevva.services.tropical.get_tropical_systems', side_effect=RuntimeError('offline')):
            systems, completed = get_tropical_system_candidates()

        self.assertEqual(systems, [])
        self.assertFalse(completed)

    def test_same_country_issuer_report_hides_same_named_foreign_equivalents(self) -> None:
        japanese_report = _system(
            id='jma-dolphin',
            source='jma_tropical',
            center_lat=22.4,
            center_lon=114.3,
            source_info=SimpleNamespace(name='Japan Meteorological Agency', issuer_country_code='JP'),
        )
        hong_kong_report = _system(
            id='hko-dolphin',
            source='hko_tropical',
            center_lat=23.0,
            center_lon=115.0,
            source_info=SimpleNamespace(name='Hong Kong Observatory', issuer_country_code='HK'),
        )
        a_different_foreign_storm = _system(
            id='jma-mango',
            source='jma_tropical',
            name='MANGO',
            center_lat=22.5,
            center_lon=114.4,
            source_info=SimpleNamespace(name='Japan Meteorological Agency', issuer_country_code='JP'),
        )

        with patch(
            'wevva.services.tropical.match_tropical_systems_to_point',
            side_effect=[[japanese_report], [hong_kong_report], [a_different_foreign_storm]],
        ) as match:
            systems = nearby_tropical_systems_from_candidates(
                [japanese_report, hong_kong_report, a_different_foreign_storm],
                22.3,
                114.2,
                selected_country_code='HK',
            )

        self.assertEqual([nearby.system.id for nearby in systems], ['hko-dolphin', 'jma-mango'])
        self.assertEqual(
            match.call_args_list,
            [
                call([japanese_report], lat=22.3, lon=114.2, radius_km=250.0),
                call([hong_kong_report], lat=22.3, lon=114.2, radius_km=250.0),
                call([a_different_foreign_storm], lat=22.3, lon=114.2, radius_km=250.0),
            ],
        )

    def test_newest_same_named_foreign_report_wins_without_a_local_issuer(self) -> None:
        japanese_report = _system(
            id='jma-dolphin',
            source='jma_tropical',
            center_lat=22.4,
            center_lon=114.3,
            issued_at=datetime(2026, 8, 12, 5, tzinfo=timezone.utc),
            source_info=SimpleNamespace(name='Japan Meteorological Agency', issuer_country_code='JP'),
        )
        hong_kong_report = _system(
            id='hko-dolphin',
            source='hko_tropical',
            center_lat=23.0,
            center_lon=115.0,
            issued_at=datetime(2026, 8, 12, 6, tzinfo=timezone.utc),
            source_info=SimpleNamespace(name='Hong Kong Observatory', issuer_country_code='HK'),
        )

        with patch(
            'wevva.services.tropical.match_tropical_systems_to_point',
            side_effect=[[japanese_report], [hong_kong_report]],
        ):
            systems = nearby_tropical_systems_from_candidates(
                [japanese_report, hong_kong_report],
                22.3,
                114.2,
                selected_country_code='KR',
            )

        self.assertEqual([nearby.system.id for nearby in systems], ['hko-dolphin'])

    def test_newest_local_report_wins_when_multiple_local_reports_share_a_name(self) -> None:
        older = _system(
            id='jma-dolphin-older',
            source='jma_tropical',
            issued_at=datetime(2026, 8, 12, 5, tzinfo=timezone.utc),
            source_info=SimpleNamespace(name='Japan Meteorological Agency', issuer_country_code='JP'),
        )
        newer = _system(
            id='jma-dolphin-newer',
            source='jma_tropical_secondary',
            issued_at=datetime(2026, 8, 12, 6, tzinfo=timezone.utc),
            source_info=SimpleNamespace(name='Japan Meteorological Agency', issuer_country_code='JP'),
        )
        foreign = _system(
            id='hko-dolphin',
            source='hko_tropical',
            issued_at=datetime(2026, 8, 12, 7, tzinfo=timezone.utc),
            source_info=SimpleNamespace(name='Hong Kong Observatory', issuer_country_code='HK'),
        )

        with patch(
            'wevva.services.tropical.match_tropical_systems_to_point',
            side_effect=[[older], [newer], [foreign]],
        ):
            systems = nearby_tropical_systems_from_candidates(
                [older, newer, foreign],
                22.3,
                114.2,
                selected_country_code='JP',
            )

        self.assertEqual([nearby.system.id for nearby in systems], ['jma-dolphin-newer'])

    def test_cached_reports_emit_progress_while_they_are_matched(self) -> None:
        first = _system(id='one')
        second = _system(id='two')
        progress = Mock()

        with patch(
            'wevva.services.tropical.match_tropical_systems_to_point',
            side_effect=[[first], []],
        ):
            nearby_tropical_systems_from_candidates(
                [first, second],
                22.3,
                114.2,
                selected_country_code='HK',
                progress=progress,
            )

        self.assertEqual(
            progress.call_args_list,
            [
                call('tropical_check_total', {'total': 2}),
                call('tropical_checked', {'completed': 1, 'total': 2}),
                call('tropical_checked', {'completed': 2, 'total': 2}),
            ],
        )

    def test_simple_one_call_path_remains_available(self) -> None:
        system = _system(center_lat=22.4, center_lon=114.3)
        with patch('wevva.services.tropical.get_tropical_systems_near', return_value=[system]) as lookup:
            systems = get_nearby_tropical_systems(22.3, 114.2, selected_country_code='HK')

        self.assertEqual([nearby.system.id for nearby in systems], ['test-system'])
        lookup.assert_called_once_with(22.3, 114.2, radius_km=250.0)


class TropicalDisplayTests(unittest.TestCase):
    def test_tab_rendering_keeps_core_context_to_two_lines(self) -> None:
        system = _system(
            name='',
            headline='DOLPHIN',
            classification='Severe Tropical Storm',
            basin='Northwest Pacific',
            url='https://www.hko.gov.hk/tropical/dolphin',
            issued_at=datetime(2026, 8, 11, 20, 26, tzinfo=timezone(timedelta(hours=8))),
            advisory_number='6',
            movement='Northwest',
            min_pressure='980 hPa',
            max_wind='40 km/h',
            parameters={
                'HKO Peak Intensity': ['Typhoon'],
                'HKO Peak Maximum Wind': ['120 km/h'],
                'HKO Peak Time': ['2026-08-11T00:00:00+00:00'],
            },
            source_info=SimpleNamespace(name='Hong Kong Observatory', issuer_country_code='HK'),
        )

        text = build_tropical_system_text(NearbyTropicalSystem(system=system, distance_km=119.091))

        self.assertEqual(
            text.plain,
            'DOLPHIN\n'
            'Centre 74 mi away · 40 km/h winds · 980 hPa · Moving Northwest',
        )
        self.assertEqual(text.plain.count('\n'), 1)
        self.assertNotIn('Northwest Pacific', text.plain)

    def test_details_table_starts_with_name_and_uses_linked_coordinates(self) -> None:
        system = _system(
            headline='Low Pressure Area: DOLPHIN',
            center_lat=-31.2,
            center_lon=113.8,
            basin='Northwest Pacific',
            url='https://www.hko.gov.hk/tropical/dolphin',
            issued_at=datetime(2026, 8, 11, 20, 26, tzinfo=timezone(timedelta(hours=8))),
            advisory_number='6',
            movement='Northwest',
            min_pressure='980 hPa',
            max_wind='40 km/h',
            parameters={
                'HKO Peak Intensity': ['Typhoon'],
                'HKO Peak Maximum Wind': ['120 km/h'],
                'HKO Peak Time': ['2026-08-11T00:00:00+00:00'],
            },
            source_info=SimpleNamespace(name='Hong Kong Observatory', issuer_country_code='HK'),
        )

        rows = tropical_system_detail_rows(
            NearbyTropicalSystem(system=system, distance_km=119.091),
            {'text-accent': '#abcdef'},
        )
        details = {label: value.plain for label, value in rows}

        self.assertEqual(rows[0][0], 'Name')
        self.assertEqual(details['Name'], 'DOLPHIN')
        self.assertEqual(details['Centre'], '31.20° S, 113.80° E')
        self.assertEqual(details['Movement'], 'Northwest')
        self.assertEqual(details['Minimum pressure'], '980 hPa')
        self.assertEqual(details['Advisory'], '6')
        self.assertEqual(details['Issued'], '11 Aug 2026, 20:26 UTC+08:00')
        self.assertEqual(details['Official source'], 'View official source')
        self.assertNotIn('Provider details', details)

        coordinates = build_tropical_coordinates_text(-31.2, 113.8, accent='#abcdef')
        self.assertEqual(coordinates.plain, '31.20° S, 113.80° E')
        self.assertTrue(any('openstreetmap.org/#map=12/-31.20000/113.80000' in span.style for span in coordinates.spans))
        self.assertFalse(any('underline' in span.style for span in coordinates.spans))

    def test_compact_rendering_omits_absent_optional_fields(self) -> None:
        system = _system(name='', headline='Provider headline', classification='')

        text = build_tropical_system_text(NearbyTropicalSystem(system=system, distance_km=None))

        self.assertEqual(text.plain, 'Provider headline')
        self.assertNotIn('Issued', text.plain)
        self.assertNotIn('winds', text.plain)
        self.assertNotIn('Centre', text.plain)

    def test_tab_uses_basin_when_movement_is_not_available(self) -> None:
        system = _system(headline='DOLPHIN', basin='Northwest Pacific', max_wind='40 km/h', min_pressure='980 hPa')

        text = build_tropical_system_text(NearbyTropicalSystem(system=system, distance_km=119.091))

        self.assertEqual(
            text.plain,
            'DOLPHIN\nCentre 74 mi away · 40 km/h winds · 980 hPa · Northwest Pacific',
        )

    def test_tab_label_shows_coloured_classification_before_name(self) -> None:
        nearby = NearbyTropicalSystem(system=_system(classification='Typhoon', name='DOLPHIN'), distance_km=15.0)

        label = build_tropical_tab_label(nearby, accent='#abcdef')

        self.assertEqual(label.plain, 'Typhoon DOLPHIN')

    def test_combined_panel_places_tropical_tabs_before_weather_alerts(self) -> None:
        nearby = NearbyTropicalSystem(system=_system(), distance_km=15.0)
        alert = Alert(id='rain', source='test', event='Rain', headline='Rain warning')

        panel = WeatherAlertsPanel([alert], tropical_systems=[nearby])

        self.assertEqual(panel.items, [nearby, alert])
        self.assertEqual(panel.panel_title(), '1 Nearby tropical system · 1 Severe Weather Alert')


class TropicalAppTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.app = Wevva(initial_location=LocationMetadata(latitude=22.3, longitude=114.2, country_code='HK'))
        self.app.weather_screen = _WeatherScreen()
        self.app._refresh_generation = 1

    def test_raw_tropical_cache_lasts_thirty_minutes(self) -> None:
        self.assertEqual(self.app.TROPICAL_SYSTEM_CACHE_TTL_SECONDS, 30 * 60)

    async def test_raw_tropical_reports_use_a_separate_global_cache_and_match_each_location(self) -> None:
        nearby = NearbyTropicalSystem(
            system=_system(source_info=SimpleNamespace(name='Hong Kong Observatory', issuer_country_code='HK')),
            distance_km=15.0,
        )
        lookup = AsyncMock(return_value=([nearby.system], True))
        match = Mock(return_value=[nearby])

        with (
            patch('wevva.app._get_reusable_alerts_async_with_status', new=AsyncMock(return_value=([], True))),
            patch('wevva.app._get_native_alerts_async_with_status', new=AsyncMock(return_value=([], True))),
            patch('wevva.app.get_tropical_system_candidates_async', new=lookup),
            patch('wevva.app.nearby_tropical_systems_from_candidates', new=match),
        ):
            self.app._schedule_alert_refresh(1, tropical_lat=22.31, tropical_lon=114.21)
            assert self.app._alerts_task is not None
            await self.app._alerts_task
            first_tropical_context = self.app._tropical_context_task
            assert first_tropical_context is not None
            await first_tropical_context
            self.assertIsNotNone(self.app._tropical_system_cache)
            self.app.location = LocationMetadata(latitude=23.0, longitude=115.0, country_code='HK')
            self.app._schedule_alert_refresh(1, tropical_lat=23.01, tropical_lon=115.01)
            assert self.app._alerts_task is not None
            await self.app._alerts_task

        self.assertEqual(lookup.await_count, 1)
        cached_candidates = self.app._alert_cache[('HK', 'auto')][1]
        self.assertEqual(cached_candidates, ())
        self.assertIsNotNone(self.app._tropical_system_cache)
        assert self.app._tropical_system_cache is not None
        self.assertEqual(self.app._tropical_system_cache[1], (nearby.system,))
        alert_updates = [
            message for message in self.app.weather_screen.messages if isinstance(message, WeatherAlertsUpdated)
        ]
        self.assertEqual(alert_updates[-1].tropical_systems, [nearby])
        self.assertTrue(any(isinstance(message, TropicalSystemsProgress) for message in self.app.weather_screen.messages))
        self.assertEqual(
            match.call_args_list,
            [
                call(
                    [nearby.system],
                    22.31,
                    114.21,
                    selected_country_code='HK',
                    progress=ANY,
                ),
                call(
                    (nearby.system,),
                    23.01,
                    115.01,
                    selected_country_code='HK',
                    progress=ANY,
                ),
            ],
        )

    async def test_tropical_raw_cache_expires_and_force_refresh_bypasses_it(self) -> None:
        self.app._tropical_system_cache_clock = lambda: 1_000.0
        lookup = AsyncMock(return_value=([], True))
        match = Mock(return_value=[])

        with (
            patch('wevva.app._get_reusable_alerts_async_with_status', new=AsyncMock(return_value=([], True))),
            patch('wevva.app._get_native_alerts_async_with_status', new=AsyncMock(return_value=([], True))),
            patch('wevva.app.get_tropical_system_candidates_async', new=lookup),
            patch('wevva.app.nearby_tropical_systems_from_candidates', new=match),
        ):
            self.app._schedule_alert_refresh(1, tropical_lat=22.31, tropical_lon=114.21)
            assert self.app._alerts_task is not None
            await self.app._alerts_task
            assert self.app._tropical_context_task is not None
            await self.app._tropical_context_task

            self.app._tropical_system_cache_clock = lambda: 1_000.0 + self.app.TROPICAL_SYSTEM_CACHE_TTL_SECONDS
            self.app._schedule_alert_refresh(1, tropical_lat=22.31, tropical_lon=114.21)
            assert self.app._alerts_task is not None
            await self.app._alerts_task
            assert self.app._tropical_context_task is not None
            await self.app._tropical_context_task

            self.app._schedule_alert_refresh(1, force_refresh=True, tropical_lat=22.31, tropical_lon=114.21)
            assert self.app._alerts_task is not None
            await self.app._alerts_task
            assert self.app._tropical_context_task is not None
            await self.app._tropical_context_task

        self.assertEqual(lookup.await_count, 3)

    async def test_location_change_reuses_an_inflight_raw_tropical_fetch(self) -> None:
        tropical_lookup_started = asyncio.Event()
        release_tropical_lookup = asyncio.Event()
        raw_system = _system(center_lat=22.4, center_lon=114.3)

        async def delayed_tropical_lookup():
            tropical_lookup_started.set()
            await release_tropical_lookup.wait()
            return [raw_system], True

        lookup = AsyncMock(side_effect=delayed_tropical_lookup)
        match = Mock(return_value=[])
        with (
            patch('wevva.app._get_reusable_alerts_async_with_status', new=AsyncMock(return_value=([], True))),
            patch('wevva.app._get_native_alerts_async_with_status', new=AsyncMock(return_value=([], True))),
            patch('wevva.app.get_tropical_system_candidates_async', new=lookup),
            patch('wevva.app.nearby_tropical_systems_from_candidates', new=match),
        ):
            self.app._schedule_alert_refresh(1, tropical_lat=22.31, tropical_lon=114.21)
            first_refresh = self.app._alerts_task
            assert first_refresh is not None
            await first_refresh
            await tropical_lookup_started.wait()

            self.app.location = LocationMetadata(latitude=23.0, longitude=115.0, country_code='HK')
            self.app._refresh_generation = 2
            self.app._schedule_alert_refresh(2, tropical_lat=23.01, tropical_lon=115.01)
            second_refresh = self.app._alerts_task
            assert second_refresh is not None
            release_tropical_lookup.set()
            await second_refresh
            second_tropical_context = self.app._tropical_context_task
            if second_tropical_context is not None:
                await second_tropical_context

        self.assertEqual(lookup.await_count, 1)
        self.assertIsNotNone(self.app._tropical_system_cache)
        match.assert_called_once_with(
            (raw_system,),
            23.01,
            115.01,
            selected_country_code='HK',
            progress=ANY,
        )

    async def test_raw_tropical_lookup_starts_after_country_alerts(self) -> None:
        country_lookup_started = asyncio.Event()
        release_country_lookup = asyncio.Event()
        tropical_lookup_started = asyncio.Event()
        release_tropical_lookup = asyncio.Event()

        async def delayed_country_lookup(*args, **kwargs):
            country_lookup_started.set()
            await release_country_lookup.wait()
            return [], True

        native_lookup = AsyncMock(return_value=([], True))
        async def delayed_tropical_lookup():
            tropical_lookup_started.set()
            await release_tropical_lookup.wait()
            return [], True

        with (
            patch('wevva.app._get_reusable_alerts_async_with_status', new=delayed_country_lookup),
            patch('wevva.app._get_native_alerts_async_with_status', new=native_lookup),
            patch('wevva.app.get_tropical_system_candidates_async', new=delayed_tropical_lookup),
            patch('wevva.app.nearby_tropical_systems_from_candidates', new=Mock(return_value=[])),
        ):
            self.app._schedule_alert_refresh(1, tropical_lat=22.31, tropical_lon=114.21)
            assert self.app._alerts_task is not None
            await country_lookup_started.wait()
            await asyncio.sleep(0)
            self.assertEqual(native_lookup.await_count, 1)
            self.assertFalse(tropical_lookup_started.is_set())
            release_country_lookup.set()
            await self.app._alerts_task
            await tropical_lookup_started.wait()
            release_tropical_lookup.set()
            assert self.app._tropical_context_task is not None
            await self.app._tropical_context_task

    async def test_raw_tropical_lookup_updates_after_normal_alerts_with_progress(self) -> None:
        tropical_lookup_started = asyncio.Event()
        release_tropical_lookup = asyncio.Event()

        async def delayed_tropical_lookup(*args, **kwargs):
            tropical_lookup_started.set()
            await release_tropical_lookup.wait()
            return [], True

        with (
            patch('wevva.app._get_reusable_alerts_async_with_status', new=AsyncMock(return_value=([], True))),
            patch('wevva.app._get_native_alerts_async_with_status', new=AsyncMock(return_value=([], True))),
            patch('wevva.app.get_tropical_system_candidates_async', new=delayed_tropical_lookup),
            patch('wevva.app.nearby_tropical_systems_from_candidates', new=Mock(return_value=[])),
        ):
            self.app._schedule_alert_refresh(1, tropical_lat=22.31, tropical_lon=114.21)
            assert self.app._alerts_task is not None
            await self.app._alerts_task
            await tropical_lookup_started.wait()
            alert_updates = [
                message for message in self.app.weather_screen.messages if isinstance(message, WeatherAlertsUpdated)
            ]
            self.assertEqual(len(alert_updates), 1)
            self.assertEqual(alert_updates[0].tropical_systems, [])
            self.assertTrue(any(isinstance(message, TropicalSystemsProgress) for message in self.app.weather_screen.messages))
            release_tropical_lookup.set()
            assert self.app._tropical_context_task is not None
            await self.app._tropical_context_task

        alert_updates = [
            message for message in self.app.weather_screen.messages if isinstance(message, WeatherAlertsUpdated)
        ]
        self.assertEqual(len(alert_updates), 2)

    async def test_failed_raw_tropical_lookup_finishes_its_progress_panel(self) -> None:
        with (
            patch('wevva.app._get_reusable_alerts_async_with_status', new=AsyncMock(return_value=([], True))),
            patch('wevva.app._get_native_alerts_async_with_status', new=AsyncMock(return_value=([], True))),
            patch('wevva.app.get_tropical_system_candidates_async', new=AsyncMock(return_value=([], False))),
        ):
            self.app._schedule_alert_refresh(1, tropical_lat=22.31, tropical_lon=114.21)
            assert self.app._alerts_task is not None
            await self.app._alerts_task
            assert self.app._tropical_context_task is not None
            await self.app._tropical_context_task

        tropical_events = [
            message.event for message in self.app.weather_screen.messages if isinstance(message, TropicalSystemsProgress)
        ]
        self.assertEqual(tropical_events, ['tropical_fetch_started', 'tropical_finished'])

    async def test_refresh_uses_final_forecast_coordinates_for_tropical_query(self) -> None:
        forecast_metadata = LocationMetadata(latitude=22.3125, longitude=114.21875)
        event = WeatherUpdated(metadata=forecast_metadata, current=None, hourly=None, daily=None)
        self.app.controller.fetch = AsyncMock(return_value=event)
        lookup = AsyncMock(return_value=([], True))
        match = Mock(return_value=[])

        with (
            patch('wevva.app._get_reusable_alerts_async_with_status', new=AsyncMock(return_value=([], True))),
            patch('wevva.app._get_native_alerts_async_with_status', new=AsyncMock(return_value=([], True))),
            patch('wevva.app.get_tropical_system_candidates_async', new=lookup),
            patch('wevva.app.nearby_tropical_systems_from_candidates', new=match),
        ):
            await self.app._refresh_weather(force_alert_refresh=False)
            assert self.app._alerts_task is not None
            await self.app._alerts_task
            assert self.app._tropical_context_task is not None
            await self.app._tropical_context_task

        lookup.assert_awaited_once_with()
        match.assert_called_once_with(
            [],
            22.3125,
            114.21875,
            selected_country_code='HK',
            progress=ANY,
        )

    async def test_alert_only_refresh_reuses_displayed_forecast_coordinates_for_tropical_matching(self) -> None:
        self.app.location = LocationMetadata(latitude=22.3, longitude=114.2, country_code='HK')
        self.app.forecast_metadata = LocationMetadata(latitude=22.3125, longitude=114.21875)
        lookup = AsyncMock(return_value=([], True))
        match = Mock(return_value=[])

        with (
            patch('wevva.app._get_reusable_alerts_async_with_status', new=AsyncMock(return_value=([], True))),
            patch('wevva.app._get_native_alerts_async_with_status', new=AsyncMock(return_value=([], True))),
            patch('wevva.app.get_tropical_system_candidates_async', new=lookup),
            patch('wevva.app.nearby_tropical_systems_from_candidates', new=match),
        ):
            self.app._schedule_alert_refresh(1)
            assert self.app._alerts_task is not None
            await self.app._alerts_task
            assert self.app._tropical_context_task is not None
            await self.app._tropical_context_task

        match.assert_called_once_with(
            [],
            22.3125,
            114.21875,
            selected_country_code='HK',
            progress=ANY,
        )


if __name__ == '__main__':
    unittest.main()
