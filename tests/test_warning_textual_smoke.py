"""Mounted Textual smoke checks for warning progress and stale results."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from wevva.alerts import Alert
from wevva.app import Wevva
from wevva.location_metadata import LocationMetadata
from wevva.messages import WeatherAlertsProgress, WeatherAlertsUpdated
from wevva.services.warning_cache import WarningCache, WarningCacheProduct


def _location(
    latitude: float = 52.52,
    longitude: float = 13.405,
    *,
    name: str = 'Berlin',
    country: str = 'Germany',
    country_code: str = 'DE',
) -> LocationMetadata:
    return LocationMetadata(
        latitude=latitude,
        longitude=longitude,
        name=name,
        country=country,
        country_code=country_code,
    )


class WarningTextualSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_individual_warning_work_shows_measured_progress(self) -> None:
        location = _location()
        app = Wevva(
            initial_location=location,
            saved_locations=[location],
            start_on_dashboard=False,
        )

        with patch.object(Wevva, 'action_refresh', new=AsyncMock()):
            async with app.run_test(size=(160, 40)) as pilot:
                await pilot.pause()
                progress = app.weather_screen.saved_locations_sidebar.warning_progress

                app.weather_screen.post_message(
                    WeatherAlertsProgress(
                        event='alerts_total',
                        payload={'total': 3, 'phase': 'sources'},
                    )
                )
                await pilot.pause()
                self.assertFalse(progress.display)

                app.weather_screen.post_message(
                    WeatherAlertsProgress(
                        event='alerts_total',
                        payload={'total': 3, 'phase': 'documents'},
                    )
                )
                await pilot.pause()
                self.assertTrue(progress.display)
                self.assertEqual(progress.border_title, 'Checking alerts')

    async def test_empty_candidate_cache_hit_does_not_show_progress(self) -> None:
        location = _location()
        app = Wevva(
            initial_location=location,
            saved_locations=[location],
            start_on_dashboard=False,
        )
        app.warning_cache = WarningCache(None)
        app.country_alerts_service.cache = app.warning_cache
        await app.warning_cache.store(
            WarningCacheProduct.REUSABLE_CANDIDATES,
            'DE',
            'auto',
            [],
        )
        reusable_lookup = AsyncMock(return_value=([], True))

        with (
            patch.object(Wevva, 'action_refresh', new=AsyncMock()),
            patch('wevva.app.get_alert_candidates_async', new=reusable_lookup),
            patch(
                'wevva.app.get_native_point_alerts_async',
                new=AsyncMock(return_value=([], True)),
            ),
        ):
            async with app.run_test(size=(160, 40)) as pilot:
                await pilot.pause()
                app._refresh_generation = 1
                app._schedule_alert_refresh(1)
                assert app._alerts_task is not None
                await app._alerts_task
                await pilot.pause()

                reusable_lookup.assert_not_awaited()
                self.assertFalse(
                    app.weather_screen.saved_locations_sidebar.warning_progress.display
                )
                self.assertEqual(app.weather_screen._alerts, [])

    async def test_location_switch_cannot_render_stale_warning_results(self) -> None:
        old_location = _location()
        current_alert = Alert(
            id='current-location',
            source='test',
            event='Wind',
            headline='Current-location wind warning',
        )
        stale_alert = Alert(
            id='old-location',
            source='test',
            event='Rain',
            headline='Old-location rain warning',
        )
        started = asyncio.Event()
        release = asyncio.Event()

        async def delayed_lookup(*_args, **_kwargs):
            started.set()
            await release.wait()
            return [stale_alert], True

        app = Wevva(
            initial_location=old_location,
            saved_locations=[old_location],
            start_on_dashboard=False,
        )
        app.warning_cache = WarningCache(None)
        app.country_alerts_service.cache = app.warning_cache
        with (
            patch.object(Wevva, 'action_refresh', new=AsyncMock()),
            patch('wevva.app.get_alert_candidates_async', new=delayed_lookup),
            patch(
                'wevva.app.get_native_point_alerts_async',
                new=AsyncMock(return_value=([], True)),
            ),
        ):
            async with app.run_test(size=(160, 40)) as pilot:
                await pilot.pause()
                app._refresh_generation = 1
                app._schedule_alert_refresh(1)
                assert app._alerts_task is not None
                await started.wait()

                app.location = _location(
                    48.8566,
                    2.3522,
                    name='Paris',
                    country='France',
                    country_code='FR',
                )
                app._refresh_generation = 2
                app.weather_screen.post_message(
                    WeatherAlertsUpdated(alerts=[current_alert])
                )
                await pilot.pause()

                release.set()
                await app._alerts_task
                await pilot.pause()

                self.assertEqual(
                    [alert.id for alert in app.weather_screen._alerts],
                    ['current-location'],
                )


if __name__ == '__main__':
    unittest.main()
