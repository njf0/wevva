"""Regression checks for the synchronous public API wrappers."""

from __future__ import annotations

import gc
import unittest
import warnings
from unittest.mock import AsyncMock, patch, sentinel

from wevva.api import (
    WevvaAPIError,
    forecast_by_coordinates_sync,
    forecast_by_place_sync,
    geocode_sync,
)


class SyncAPIEventLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_wrappers_reject_active_loop_without_creating_coroutines(self) -> None:
        cases = (
            ('wevva.api.geocode', lambda: geocode_sync('Berlin')),
            (
                'wevva.api.forecast_by_coordinates',
                lambda: forecast_by_coordinates_sync(lat=52.52, lon=13.405),
            ),
            ('wevva.api.forecast_by_place', lambda: forecast_by_place_sync('Berlin')),
        )

        for target, invoke in cases:
            with self.subTest(target=target), patch(target, new_callable=AsyncMock) as async_api:
                with warnings.catch_warnings(record=True) as captured:
                    warnings.simplefilter('always')
                    with self.assertRaisesRegex(
                        WevvaAPIError,
                        'Sync API cannot run inside an active event loop',
                    ):
                        invoke()
                    gc.collect()

                async_api.assert_not_called()
                leaked = [
                    warning
                    for warning in captured
                    if issubclass(warning.category, RuntimeWarning)
                    and 'was never awaited' in str(warning.message)
                ]
                self.assertEqual(leaked, [])


class SyncAPINormalUseTests(unittest.TestCase):
    def test_geocode_sync_runs_async_api_with_existing_arguments(self) -> None:
        async_api = AsyncMock(return_value=[sentinel.location])
        with patch('wevva.api.geocode', new=async_api):
            result = geocode_sync('Berlin', count=3, language='de')

        self.assertEqual(result, [sentinel.location])
        async_api.assert_awaited_once_with('Berlin', count=3, language='de')

    def test_forecast_by_coordinates_sync_runs_async_api_with_existing_arguments(self) -> None:
        async_api = AsyncMock(return_value=sentinel.forecast)
        with patch('wevva.api.forecast_by_coordinates', new=async_api):
            result = forecast_by_coordinates_sync(
                lat=52.52,
                lon=13.405,
                temperature_unit='fahrenheit',
                wind_speed_unit='mph',
                precipitation_unit='inch',
                country_code='DE',
            )

        self.assertIs(result, sentinel.forecast)
        async_api.assert_awaited_once_with(
            lat=52.52,
            lon=13.405,
            temperature_unit='fahrenheit',
            wind_speed_unit='mph',
            precipitation_unit='inch',
            country_code='DE',
        )

    def test_forecast_by_place_sync_runs_async_api_with_existing_arguments(self) -> None:
        async_api = AsyncMock(return_value=sentinel.forecast)
        with patch('wevva.api.forecast_by_place', new=async_api):
            result = forecast_by_place_sync(
                'Berlin',
                language='de',
                temperature_unit='fahrenheit',
                wind_speed_unit='mph',
                precipitation_unit='inch',
            )

        self.assertIs(result, sentinel.forecast)
        async_api.assert_awaited_once_with(
            'Berlin',
            language='de',
            temperature_unit='fahrenheit',
            wind_speed_unit='mph',
            precipitation_unit='inch',
        )


if __name__ == '__main__':
    unittest.main()
