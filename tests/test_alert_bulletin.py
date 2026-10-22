"""Focused checks for the session alert-bulletin coordinator."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import unittest
from unittest.mock import AsyncMock, patch

from wevva_warnings import WarningSource

from wevva.alerts import Alert
from wevva.services.alert_bulletin import (
    AlertBulletinCoordinator,
    BulletinCatalogue,
)
from wevva.services.country_alerts import (
    AlertObservation,
    CountryAlertsCacheHit,
    CountryAlertsService,
)
from wevva.services.warning_cache import WarningCache, WarningCacheProduct


class _Clock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class _Cache:
    def __init__(self, keys=()) -> None:
        self.keys = tuple(keys)

    async def retained_keys(self, _product):
        return self.keys


class _Service:
    def __init__(self, *, retained=None) -> None:
        self.cache = _Cache(
            (
                (WarningCacheProduct.COUNTRY_CATALOGUE, 'FR', 'auto'),
            )
            if retained is not None
            else ()
        )
        self.retained = retained
        self.calls: list[tuple[str, str]] = []
        self.active = 0
        self.max_active = 0
        self.observations = ()

    async def get_cached_alerts(self, country_code, *, warning_language):
        del country_code, warning_language
        return self.retained

    async def refresh_alerts(self, country_code, *, warning_language, progress=None):
        del progress
        self.calls.append((country_code, warning_language))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0)
        self.active -= 1
        return [Alert(id=country_code, source='test', event='Rain', headline='Rain')]

    def cancel_refreshes(self) -> None:
        pass

    def observation_journal(self):
        return self.observations


class AlertBulletinCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_catalogue_is_baseline_and_second_lap_marks_only_added_alerts(
        self,
    ) -> None:
        initial = tuple(
            Alert(
                id=f'existing-{index}',
                source='test',
                event='Rain',
                headline='Rain',
            )
            for index in range(50)
        )
        added = Alert(
            id='added',
            source='test',
            event='Wind',
            headline='Wind',
        )
        service = _Service()
        service.refresh_alerts = AsyncMock(
            side_effect=[
                list(initial),
                [added, *initial],
                RuntimeError('offline'),
                [added, *initial],
            ]
        )
        coordinator = AlertBulletinCoordinator(
            service,  # type: ignore[arg-type]
            ['GB'],
        )

        await coordinator._refresh('GB', generation=0)

        self.assertEqual(
            coordinator.catalogues_snapshot()[0].new_alert_identities,
            frozenset(),
        )
        self.assertEqual(coordinator.recent_alerts_snapshot(), ())

        await coordinator._refresh('GB', generation=0)

        self.assertEqual(
            coordinator.catalogues_snapshot()[0].new_alert_identities,
            frozenset({('test', 'added')}),
        )
        self.assertEqual(
            [row.alert.id for row in coordinator.recent_alerts_snapshot() if row.is_new],
            ['added'],
        )
        self.assertEqual(
            [row.alert.id for row in coordinator.recent_alerts_snapshot()],
            ['added'],
        )

        await coordinator._refresh('GB', generation=0)
        self.assertEqual(
            coordinator.catalogues_snapshot()[0].new_alert_identities,
            frozenset({('test', 'added')}),
        )

        await coordinator._refresh('GB', generation=0)
        self.assertEqual(
            coordinator.catalogues_snapshot()[0].new_alert_identities,
            frozenset(),
        )
        self.assertFalse(any(row.is_new for row in coordinator.recent_alerts_snapshot()))
        self.assertEqual(
            [row.alert.id for row in coordinator.recent_alerts_snapshot()],
            ['added'],
        )

    async def test_successfully_empty_first_catalogue_is_still_a_baseline(self) -> None:
        added = Alert(
            id='added',
            source='test',
            event='Snow',
            headline='Snow',
        )
        service = _Service()
        service.refresh_alerts = AsyncMock(side_effect=[[], [added]])
        coordinator = AlertBulletinCoordinator(
            service,  # type: ignore[arg-type]
            ['GB'],
        )

        await coordinator._refresh('GB', generation=0)
        await coordinator._refresh('GB', generation=0)

        self.assertTrue(coordinator.recent_alerts_snapshot()[0].is_new)

    async def test_latest_discovery_replaces_previous_country_new_badges(
        self,
    ) -> None:
        gb_existing = Alert(
            id='gb-existing',
            source='test',
            event='Rain',
            headline='Rain',
        )
        gb_new = Alert(
            id='gb-new',
            source='test',
            event='Wind',
            headline='Wind',
        )
        fr_existing = Alert(
            id='fr-existing',
            source='test',
            event='Snow',
            headline='Snow',
        )
        fr_new = Alert(
            id='fr-new',
            source='test',
            event='Flood',
            headline='Flood',
        )
        service = _Service()
        service.refresh_alerts = AsyncMock(
            side_effect=[
                [gb_existing],
                [gb_existing, gb_new],
                [fr_existing],
                [fr_existing, fr_new],
            ]
        )
        coordinator = AlertBulletinCoordinator(
            service,  # type: ignore[arg-type]
            ['GB', 'FR'],
        )

        await coordinator._refresh('GB', generation=0)
        await coordinator._refresh('GB', generation=0)
        self.assertEqual(
            {
                row.alert.id
                for row in coordinator.recent_alerts_snapshot()
                if row.is_new
            },
            {'gb-new'},
        )

        await coordinator._refresh('FR', generation=0)
        self.assertEqual(
            {
                row.alert.id
                for row in coordinator.recent_alerts_snapshot()
                if row.is_new
            },
            {'gb-new'},
        )

        await coordinator._refresh('FR', generation=0)
        rows = coordinator.recent_alerts_snapshot()
        self.assertEqual(
            {row.alert.id for row in rows if row.is_new},
            {'fr-new'},
        )
        self.assertEqual(
            {row.alert.id for row in rows},
            {'gb-new', 'fr-new'},
        )

    async def test_recent_rows_deduplicate_and_use_earliest_country_observation(self) -> None:
        now = datetime(2030, 1, 1, 12, tzinfo=UTC)
        shared_gb = Alert(
            id='shared',
            source='test',
            event='Wind',
            headline='Wind',
            expires=now + timedelta(hours=1),
        )
        shared_fr = Alert(
            id='shared',
            source='test',
            event='Wind',
            headline='Vent',
            expires=now + timedelta(hours=1),
        )
        newest = Alert(
            id='newest',
            source='test',
            event='Rain',
            headline='Rain',
        )
        expired = Alert(
            id='expired',
            source='test',
            event='Snow',
            headline='Snow',
            expires=now - timedelta(seconds=1),
        )
        service = _Service()
        service.observations = (
            AlertObservation('GB', 'auto', 'test', 'shared', now - timedelta(hours=1), now),
            AlertObservation('FR', 'auto', 'test', 'shared', now - timedelta(hours=2), now),
            AlertObservation('GB', 'auto', 'test', 'newest', now - timedelta(minutes=2), now),
        )
        coordinator = AlertBulletinCoordinator(
            service,  # type: ignore[arg-type]
            ['GB', 'FR'],
            wall_clock=lambda: now,
        )
        coordinator._catalogues = {
            ('GB', 'auto'): BulletinCatalogue(
                'GB',
                'auto',
                (shared_gb, newest),
                now,
                visible_alert_identities=frozenset(
                    {('test', 'shared'), ('test', 'newest')}
                ),
            ),
            ('FR', 'auto'): BulletinCatalogue(
                'FR',
                'auto',
                (shared_fr, expired),
                now,
                visible_alert_identities=frozenset(
                    {('test', 'shared'), ('test', 'expired')}
                ),
            ),
        }

        rows = coordinator.recent_alerts_snapshot()

        self.assertEqual(
            [(row.alert.id, row.country_code) for row in rows],
            [('newest', 'GB'), ('shared', 'FR')],
        )

    async def test_shared_feed_prefers_named_territory_then_primary_country(self) -> None:
        now = datetime(2030, 1, 1, 12, tzinfo=UTC)
        source = WarningSource(
            id='shared',
            name='Shared warnings',
            backend='fixture',
            country_code='US',
            additional_country_codes=('AS', 'GU'),
            url='https://example.test/alerts',
        )
        ordinary = Alert(
            id='ordinary',
            source='shared',
            event='Flood Warning',
            headline='Flooding expected in coastal counties',
            source_info=source,
        )
        territory = Alert(
            id='territory',
            source='shared',
            event='High Surf Warning',
            headline='High surf warning for American Samoa',
            source_info=source,
        )
        service = _Service()
        coordinator = AlertBulletinCoordinator(
            service,  # type: ignore[arg-type]
            ['US', 'AS'],
            wall_clock=lambda: now,
        )
        identities = frozenset(
            {('shared', 'ordinary'), ('shared', 'territory')}
        )
        coordinator._catalogues = {
            ('AS', 'auto'): BulletinCatalogue(
                'AS',
                'auto',
                (ordinary, territory),
                now - timedelta(minutes=10),
                identities,
                identities,
            ),
            ('US', 'auto'): BulletinCatalogue(
                'US',
                'auto',
                (ordinary, territory),
                now,
                identities,
                identities,
            ),
        }

        rows = coordinator.recent_alerts_snapshot()

        self.assertEqual(
            {row.alert.id: row.country_code for row in rows},
            {'ordinary': 'US', 'territory': 'AS'},
        )
        self.assertTrue(all(row.is_new for row in rows))

    async def test_priority_then_rolling_lane_are_staggered_and_fair(self) -> None:
        clock = _Clock()
        service = _Service()
        coordinator = AlertBulletinCoordinator(
            service,  # type: ignore[arg-type]
            ['GB', 'FR', 'DE'],
            clock=clock,
            jitter=lambda value: value,
        )
        coordinator.set_priority_countries(['GB'])

        self.assertTrue(await coordinator.refresh_due_once())
        self.assertEqual(service.calls, [('GB', 'auto')])
        self.assertFalse(await coordinator.refresh_due_once())

        clock.advance(5)
        self.assertTrue(await coordinator.refresh_due_once())
        self.assertEqual(service.calls, [('GB', 'auto'), ('DE', 'auto')])

    async def test_hard_refresh_is_deduplicated_capped_and_low_concurrency(self) -> None:
        service = _Service()
        coordinator = AlertBulletinCoordinator(
            service,  # type: ignore[arg-type]
            ['GB', 'FR', 'DE', 'US'],
        )

        task = coordinator.schedule_hard_refresh(['GB', 'GB', 'FR', 'DE', 'US'])
        assert task is not None
        await task

        self.assertEqual([code for code, _ in service.calls], ['GB', 'FR', 'DE'])
        self.assertLessEqual(service.max_active, 2)

    async def test_failed_key_waits_for_bounded_backoff(self) -> None:
        clock = _Clock()
        service = _Service()
        service.refresh_alerts = AsyncMock(
            side_effect=[RuntimeError('offline'), []]
        )
        coordinator = AlertBulletinCoordinator(
            service,  # type: ignore[arg-type]
            ['GB'],
            clock=clock,
            retry_base_seconds=60,
            jitter=lambda value: value,
        )
        coordinator.set_priority_countries(['GB'])

        self.assertTrue(await coordinator.refresh_due_once())
        clock.advance(2)
        self.assertFalse(await coordinator.refresh_due_once())
        clock.advance(58)
        self.assertTrue(await coordinator.refresh_due_once())
        self.assertEqual(service.refresh_alerts.await_count, 2)

    async def test_fresh_catalogue_is_hidden_baseline_before_refresh(self) -> None:
        fetched_at = datetime(2030, 1, 1, 12, tzinfo=UTC)
        alert = Alert(id='warm', source='test', event='Wind', headline='Wind')
        added = Alert(id='added', source='test', event='Rain', headline='Rain')
        retained = CountryAlertsCacheHit(
            (alert,),
            frozenset({('test', 'warm')}),
            provisional=False,
            fetched_at=fetched_at,
        )
        service = _Service(retained=retained)
        coordinator = AlertBulletinCoordinator(
            service,  # type: ignore[arg-type]
            ['FR'],
            wall_clock=lambda: fetched_at + timedelta(minutes=5),
        )

        await coordinator.hydrate()

        snapshot = coordinator.catalogues_snapshot()
        self.assertEqual([(item.country_code, item.alerts) for item in snapshot], [('FR', (alert,))])
        self.assertEqual(snapshot[0].new_alert_identities, frozenset())
        self.assertEqual(snapshot[0].visible_alert_identities, frozenset())
        self.assertEqual(coordinator.recent_alerts_snapshot(), ())
        self.assertEqual(service.calls, [])

        service.refresh_alerts = AsyncMock(return_value=[alert, added])
        await coordinator._refresh('FR', generation=0)

        rows = coordinator.recent_alerts_snapshot()
        self.assertEqual([row.alert.id for row in rows], ['added'])
        self.assertTrue(rows[0].is_new)

    async def test_stale_retained_catalogue_stays_hidden_and_live_fetch_is_baseline(
        self,
    ) -> None:
        fetched_at = datetime(2030, 1, 1, 12, tzinfo=UTC)
        retained_alert = Alert(
            id='retained',
            source='test',
            event='Old wind',
            headline='Old wind',
        )
        live_alert = Alert(
            id='live',
            source='test',
            event='Current wind',
            headline='Current wind',
        )
        retained = CountryAlertsCacheHit(
            (retained_alert,),
            frozenset({('test', 'retained')}),
            provisional=True,
            fetched_at=fetched_at,
        )
        service = _Service(retained=retained)
        added_alert = Alert(
            id='added',
            source='test',
            event='New rain',
            headline='New rain',
        )
        service.refresh_alerts = AsyncMock(
            side_effect=[[live_alert], [live_alert, added_alert]]
        )
        coordinator = AlertBulletinCoordinator(
            service,  # type: ignore[arg-type]
            ['FR'],
            wall_clock=lambda: fetched_at + timedelta(minutes=20),
        )

        await coordinator.hydrate()
        self.assertEqual(coordinator.catalogues_snapshot(), ())
        self.assertEqual(coordinator.recent_alerts_snapshot(), ())

        await coordinator._refresh('FR', generation=0)
        self.assertEqual(coordinator.recent_alerts_snapshot(), ())

        await coordinator._refresh('FR', generation=0)
        rows = coordinator.recent_alerts_snapshot()
        self.assertEqual([row.alert.id for row in rows], ['added'])
        self.assertTrue(rows[0].is_new)

    async def test_stop_cancels_the_session_scheduler(self) -> None:
        service = _Service()
        coordinator = AlertBulletinCoordinator(
            service,  # type: ignore[arg-type]
            ['GB'],
            jitter=lambda value: value,
        )

        coordinator.start()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.assertTrue(coordinator.is_running)

        coordinator.stop()
        await asyncio.sleep(0)
        self.assertFalse(coordinator.is_running)

    async def test_country_service_coalesces_same_key_refreshes(self) -> None:
        service = CountryAlertsService(
            cache=WarningCache(None),
            observation_path=None,
        )
        started = asyncio.Event()
        release = asyncio.Event()
        alert = Alert(id='one', source='test', event='Rain', headline='Rain')
        worker_functions = []

        async def fake_to_thread(function, *args, **kwargs):
            worker_functions.append(function)
            if function.__name__ == '_fetch_country_alerts':
                started.set()
                await release.wait()
                return [alert]
            return function(*args, **kwargs)

        with patch(
            'wevva.services.country_alerts.asyncio.to_thread',
            new=AsyncMock(side_effect=fake_to_thread),
        ):
            first = asyncio.create_task(service.refresh_alerts('GB'))
            await started.wait()
            second = asyncio.create_task(service.refresh_alerts('GB'))
            await asyncio.sleep(0)
            release.set()
            self.assertEqual(await first, [alert])
            self.assertEqual(await second, [alert])

        self.assertEqual(
            [function.__name__ for function in worker_functions].count(
                '_fetch_country_alerts'
            ),
            1,
        )


if __name__ == '__main__':
    unittest.main()
