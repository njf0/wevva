"""Deterministic checks for nearby tropical-system context."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call, patch

from rich.console import Console
from wevva_warnings import CanonicalTropicalSystem, TropicalSystem

from wevva.app import Wevva
from wevva.location_metadata import LocationMetadata
from wevva.messages import WeatherAlertsUpdated
from wevva.services.tropical import (
    NearbyTropicalSystem,
    center_distance_km,
    forecast_track_distance_km,
    get_nearby_tropical_systems,
    get_tropical_system_candidates,
    haversine_distance_km,
    nearby_tropical_systems_from_candidates,
)
from wevva.widgets.tropical_systems import (
    build_tropical_coordinates_text,
    build_tropical_system_details,
    build_tropical_system_text,
    build_tropical_tab_label,
)


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

    def test_forecast_track_distance_uses_the_nearest_segment_not_only_fixes(self) -> None:
        system = _system(
            center_lat=10.0,
            center_lon=-10.0,
            geometries={
                'forecast_track': {
                    'type': 'LineString',
                    'coordinates': [[-2.0, 1.0], [2.0, 1.0]],
                },
            },
        )

        distance = forecast_track_distance_km(system, 0.0, 0.0)

        assert distance is not None
        self.assertAlmostEqual(distance, 111.195080, places=4)

    def test_system_matches_when_its_forecast_track_approaches_the_location(self) -> None:
        system = _system(
            center_lat=10.0,
            center_lon=-10.0,
            geometries={
                'forecast_track': {
                    'type': 'LineString',
                    'coordinates': [[-2.0, 1.0], [2.0, 1.0]],
                },
            },
        )

        with patch('wevva.services.tropical.match_tropical_systems_to_point', return_value=[]):
            systems = nearby_tropical_systems_from_candidates(
                [system],
                0.0,
                0.0,
                selected_country_code='US',
            )

        self.assertEqual([nearby.system.id for nearby in systems], ['test-system'])

    def test_empty_raw_result_is_cacheable(self) -> None:
        with patch('wevva.services.tropical.get_canonical_tropical_systems', return_value=[]) as lookup:
            systems, completed = get_tropical_system_candidates()

        self.assertEqual(systems, [])
        self.assertTrue(completed)
        lookup.assert_called_once_with()

    def test_provider_failure_is_quiet(self) -> None:
        with patch('wevva.services.tropical.get_canonical_tropical_systems', side_effect=RuntimeError('offline')):
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
            'DOLPHIN\n74 mi away · Moving Northwest · Northwest Pacific',
        )
        self.assertEqual(text.plain.count('\n'), 1)
        self.assertNotIn('Centre', text.plain)
        self.assertNotIn('40 km/h', text.plain)
        self.assertNotIn('980 hPa', text.plain)
        distance_start = text.plain.index('74 mi away')
        separator_start = text.plain.index(' · ')
        basin_start = text.plain.index('Northwest Pacific')
        self.assertFalse(any(span.start <= distance_start < span.end and span.style == 'dim' for span in text.spans))
        self.assertTrue(
            any(
                span.start == separator_start and span.end == separator_start + 3 and span.style == 'dim' for span in text.spans
            )
        )
        self.assertFalse(any(span.start <= basin_start < span.end and span.style == 'dim' for span in text.spans))

    def test_markdown_details_include_available_facts_and_linked_coordinates(self) -> None:
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

        details = build_tropical_system_details(
            NearbyTropicalSystem(system=system, distance_km=119.091),
            {'text-accent': '#abcdef'},
        )
        console = Console(width=80, file=StringIO(), record=True)
        console.print(details)
        rendered = console.export_text()

        self.assertLess(rendered.index('Low Pressure Area: DOLPHIN'), rendered.index('Name: DOLPHIN'))
        self.assertIn('• Name: DOLPHIN', rendered)
        self.assertIn('• Classification: Tropical Storm', rendered)
        self.assertIn('• Centre distance: 119.1 km (74 mi)', rendered)
        self.assertIn('Centre: 31.20° S, 113.80° E', rendered)
        self.assertIn('• Movement: Northwest', rendered)
        self.assertIn('• Minimum pressure: 980 hPa', rendered)
        self.assertIn('• Advisory: 6', rendered)
        self.assertIn('• Issued: 11 Aug 2026, 20:26 UTC+08:00', rendered)
        self.assertTrue(rendered.rstrip().endswith('View official source'))
        self.assertNotIn('Provider details', rendered)

        coordinate_segments = [
            segment
            for line in Console(width=80).render_lines(details)
            for segment in line
            if '31.20° S' in segment.text or '113.80° E' in segment.text
        ]
        self.assertTrue(coordinate_segments)
        self.assertTrue(all(not segment.style.bold and not segment.style.dim for segment in coordinate_segments))

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
            'DOLPHIN\n74 mi away · Northwest Pacific',
        )

    def test_tab_label_shows_coloured_classification_before_name(self) -> None:
        nearby = NearbyTropicalSystem(system=_system(classification='Typhoon', name='DOLPHIN'), distance_km=15.0)

        label = build_tropical_tab_label(nearby, accent='#abcdef')

        self.assertEqual(label.plain, 'Typhoon DOLPHIN')

class TropicalAppTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.app = Wevva(initial_location=LocationMetadata(latitude=22.3, longitude=114.2, country_code='HK'))
        self.app.weather_screen = _WeatherScreen()
        self.app._refresh_generation = 1

    def test_raw_tropical_cache_lasts_thirty_minutes(self) -> None:
        self.assertEqual(self.app.TROPICAL_SYSTEM_CACHE_TTL_SECONDS, 30 * 60)

    async def test_weather_alert_refresh_does_not_fetch_tropical_systems(self) -> None:
        tropical_lookup = AsyncMock(return_value=([], True))
        with (
            patch('wevva.app.get_alert_candidates_async', new=AsyncMock(return_value=([], True))),
            patch('wevva.app.get_native_point_alerts_async', new=AsyncMock(return_value=([], True))),
            patch('wevva.app.get_tropical_system_candidates_async', new=tropical_lookup),
        ):
            self.app._schedule_alert_refresh(1)
            assert self.app._alerts_task is not None
            await self.app._alerts_task

        tropical_lookup.assert_not_awaited()
        self.assertIsNone(self.app._tropical_system_fetch_task)
        self.assertIsNone(self.app._tropical_system_cache)
        updates = [message for message in self.app.weather_screen.messages if isinstance(message, WeatherAlertsUpdated)]
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0].alerts, [])

    async def test_expired_workspace_cache_is_refetched_on_demand(self) -> None:
        stale = CanonicalTropicalSystem('STALE', [_system(name='STALE')])
        fresh = CanonicalTropicalSystem('FRESH', [_system(name='FRESH')])
        self.app._tropical_system_cache_clock = lambda: 1_000.0
        self.app._cache_tropical_systems([stale])
        self.app._tropical_system_cache_clock = lambda: 1_000.0 + self.app.TROPICAL_SYSTEM_CACHE_TTL_SECONDS
        lookup = AsyncMock(return_value=([fresh], True))

        with patch('wevva.app.get_tropical_system_candidates_async', new=lookup):
            systems = await self.app.load_tropical_systems()

        self.assertEqual(systems, [fresh])
        lookup.assert_awaited_once_with()


if __name__ == '__main__':
    unittest.main()
