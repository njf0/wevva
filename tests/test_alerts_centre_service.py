"""Country-alert service contract and cache regressions."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from wevva_warnings import Alert, WarningSource

from wevva.services.country_alerts import (
    CountryAlertsService,
    country_alert_default_filter,
    list_supported_alert_countries,
    sort_country_alerts,
)


def _alert(
    alert_id: str,
    severity: str,
    *,
    expires_in_hours: int,
) -> Alert:
    return Alert(
        id=alert_id,
        source='fixture',
        event='Flood Warning',
        headline=f'Flood warning {alert_id}',
        severity=severity,
        expires=datetime(2030, 1, 2, tzinfo=UTC)
        + timedelta(hours=expires_in_hours),
        area_names=[f'{alert_id} district'],
    )


class SupportedCountryTests(unittest.TestCase):
    def test_country_choices_follow_primary_and_additional_source_coverage(self) -> None:
        source = WarningSource(
            id='fixture',
            name='Fixture warnings',
            backend='fixture',
            country_code='DE',
            additional_country_codes=('AT', 'DE'),
            url='https://example.test/alerts',
        )
        tropical = WarningSource(
            id='fixture-tropical',
            name='Fixture tropical',
            backend='fixture',
            country_code='FR',
            kind='tropical_system',
            url='https://example.test/tropical',
        )
        global_source = WarningSource(
            id='fixture-global',
            name='Fixture global',
            backend='fixture',
            country_code=None,
            url='https://example.test/global',
        )

        with patch(
            'wevva.services.country_alerts.list_sources',
            return_value=[source, tropical, global_source],
        ) as registry:
            countries = list_supported_alert_countries()

        registry.assert_called_once_with(kind='alert')
        self.assertEqual(
            [(country.code, country.name) for country in countries],
            [('AT', 'Austria'), ('DE', 'Germany')],
        )

    def test_shared_feed_territory_gets_a_country_name_filter(self) -> None:
        shared = WarningSource(
            id='shared',
            name='Shared warnings',
            backend='fixture',
            country_code='US',
            additional_country_codes=('GU', 'PR'),
            url='https://example.test/alerts',
        )
        direct = WarningSource(
            id='guam-direct',
            name='Guam warnings',
            backend='fixture',
            country_code='GU',
            url='https://example.test/guam',
        )

        with patch(
            'wevva.services.country_alerts.list_sources',
            return_value=[shared],
        ):
            self.assertEqual(country_alert_default_filter('GU', 'Guam'), 'Guam')
            self.assertEqual(country_alert_default_filter('US', 'United States'), '')

        with patch(
            'wevva.services.country_alerts.list_sources',
            return_value=[shared, direct],
        ):
            self.assertEqual(country_alert_default_filter('GU', 'Guam'), '')


class CountryAlertOrderingTests(unittest.TestCase):
    def test_alerts_are_deduplicated_and_ordered_by_severity_then_expiry(self) -> None:
        later_severe = _alert('later', 'Severe', expires_in_hours=4)
        sooner_severe = _alert('sooner', 'Severe', expires_in_hours=1)
        extreme = _alert('extreme', 'Extreme', expires_in_hours=8)
        moderate = _alert('moderate', 'Moderate', expires_in_hours=0)

        ordered = sort_country_alerts(
            [moderate, later_severe, extreme, sooner_severe, sooner_severe]
        )

        self.assertEqual(
            [alert.id for alert in ordered],
            ['extreme', 'sooner', 'later', 'moderate'],
        )


class CountryAlertsServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_cache_hit_and_expiry_are_isolated_by_country_and_language(self) -> None:
        now = [100.0]
        service = CountryAlertsService(
            ttl_seconds=30,
            clock=lambda: now[0],
            observation_path=None,
        )
        fetched = [_alert('first', 'Moderate', expires_in_hours=1)]

        with patch(
            'wevva.services.country_alerts._fetch_country_alerts',
            return_value=fetched,
        ) as fetch:
            first = await service.get_alerts('DE')
            fetched.clear()
            cached = await service.get_alerts('DE')
            await service.get_alerts('DE', warning_language='en')
            now[0] = 131.0
            await service.get_alerts('DE')

        self.assertEqual([alert.id for alert in first], ['first'])
        self.assertEqual([alert.id for alert in cached], ['first'])
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(service.last_country_code, 'DE')

    async def test_refresh_bypasses_a_fresh_cache_entry(self) -> None:
        service = CountryAlertsService(
            ttl_seconds=300,
            clock=lambda: 10.0,
            observation_path=None,
        )
        results = [
            [_alert('cached', 'Moderate', expires_in_hours=1)],
            [_alert('refreshed', 'Severe', expires_in_hours=2)],
        ]

        with patch(
            'wevva.services.country_alerts._fetch_country_alerts',
            side_effect=results,
        ) as fetch:
            await service.get_alerts('DE')
            refreshed = await service.get_alerts('DE', refresh=True)

        self.assertEqual([alert.id for alert in refreshed], ['refreshed'])
        self.assertEqual(fetch.call_count, 2)

    async def test_failed_fetch_is_not_cached(self) -> None:
        service = CountryAlertsService(observation_path=None)

        with patch(
            'wevva.services.country_alerts._fetch_country_alerts',
            side_effect=[RuntimeError('offline'), []],
        ) as fetch:
            with self.assertRaisesRegex(RuntimeError, 'offline'):
                await service.get_alerts('DE')
            self.assertEqual(await service.get_alerts('DE'), [])

        self.assertEqual(fetch.call_count, 2)

    async def test_new_alerts_compare_successive_fresh_snapshots(self) -> None:
        first = _alert('first', 'Moderate', expires_in_hours=1)
        second = _alert('second', 'Severe', expires_in_hours=2)

        with TemporaryDirectory() as temporary_directory:
            observation_path = Path(temporary_directory) / 'observations.json'
            service = CountryAlertsService(
                ttl_seconds=300,
                observation_path=observation_path,
            )
            with patch(
                'wevva.services.country_alerts._fetch_country_alerts',
                side_effect=[[first], [second, first], [second, first]],
            ) as fetch:
                await service.get_alerts('DE')
                self.assertEqual(service.new_alert_identities('DE'), frozenset())

                await service.get_alerts('DE', refresh=True)
                self.assertEqual(
                    service.new_alert_identities('DE'),
                    frozenset({('fixture', 'second')}),
                )

                await service.get_alerts('DE')
                self.assertEqual(
                    service.new_alert_identities('DE'),
                    frozenset({('fixture', 'second')}),
                )

                await service.get_alerts('DE', refresh=True)
                self.assertEqual(service.new_alert_identities('DE'), frozenset())

            self.assertEqual(fetch.call_count, 3)

    async def test_observation_snapshot_survives_a_new_service(self) -> None:
        first = _alert('first', 'Moderate', expires_in_hours=1)
        second = _alert('second', 'Severe', expires_in_hours=2)

        with TemporaryDirectory() as temporary_directory:
            observation_path = Path(temporary_directory) / 'observations.json'
            initial_service = CountryAlertsService(
                observation_path=observation_path,
            )
            with patch(
                'wevva.services.country_alerts._fetch_country_alerts',
                return_value=[first],
            ):
                await initial_service.get_alerts('DE')

            next_service = CountryAlertsService(
                observation_path=observation_path,
            )
            with patch(
                'wevva.services.country_alerts._fetch_country_alerts',
                return_value=[second, first],
            ):
                await next_service.get_alerts('DE')

            self.assertEqual(
                next_service.new_alert_identities('DE'),
                frozenset({('fixture', 'second')}),
            )


if __name__ == '__main__':
    unittest.main()
