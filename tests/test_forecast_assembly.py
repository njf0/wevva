"""Checks for shared weather and air-quality assembly."""

from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import AsyncMock, patch

from wevva.api import _build_forecast_bundle
from wevva.controller import WeatherController
from wevva.services.air_quality import merge_air_quality_fields


class AirQualityMergeTests(unittest.TestCase):
    def test_series_are_padded_or_truncated_without_mutating_inputs(self) -> None:
        hourly = {
            'time': ['2099-01-01T00:00', '2099-01-01T01:00', '2099-01-01T02:00'],
            'temperature_2m': [10, 11, 12],
        }
        air_quality = {
            'hourly': {
                'us_aqi': [20],
                'european_aqi': [10, 11, 12, 13],
                'pm2_5': [1, 2, 3],
            }
        }
        original_hourly = deepcopy(hourly)
        original_air_quality = deepcopy(air_quality)

        merged = merge_air_quality_fields(hourly, air_quality)

        self.assertEqual(merged['us_aqi'], [20, None, None])
        self.assertEqual(merged['european_aqi'], [10, 11, 12])
        self.assertEqual(merged['pm2_5'], [1, 2, 3])
        self.assertEqual(hourly, original_hourly)
        self.assertEqual(air_quality, original_air_quality)

    def test_missing_or_malformed_air_quality_leaves_hourly_weather_usable(self) -> None:
        hourly = {'time': ['2099-01-01T00:00'], 'temperature_2m': [10]}
        malformed_values = (
            None,
            [],
            {},
            {'hourly': []},
            {'hourly': {'us_aqi': 'not-a-series'}},
        )

        for air_quality in malformed_values:
            with self.subTest(air_quality=air_quality):
                merged = merge_air_quality_fields(hourly, air_quality)
                self.assertEqual(merged, hourly)
                self.assertIsNot(merged, hourly)


class ForecastAssemblyIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_controller_and_public_api_apply_the_same_air_quality_alignment(self) -> None:
        weather = {
            'latitude': 52.52,
            'longitude': 13.405,
            'elevation': 34,
            'timezone': 'UTC',
            'current': {},
            'hourly': {
                'time': ['2099-01-01T00:00', '2099-01-01T01:00'],
                'temperature_2m': [10, 11],
            },
            'daily': {},
        }
        air_quality = {'hourly': {'us_aqi': [42]}}
        original_weather = deepcopy(weather)

        with (
            patch('wevva.controller.fetch_weather', new=AsyncMock(return_value=weather)),
            patch('wevva.controller.fetch_air_quality', new=AsyncMock(return_value=air_quality)),
        ):
            event = await WeatherController().fetch(lat=52.52, lon=13.405, country_code='DE')

        with patch('wevva.api.fetch_air_quality', new=AsyncMock(return_value=air_quality)):
            bundle = await _build_forecast_bundle(weather, country_code='DE')

        self.assertEqual(
            [point['us_aqi'] for point in event.hourly.forecast_timeseries],
            [42, None],
        )
        self.assertEqual(
            [point['us_aqi'] for point in bundle.hourly.forecast_timeseries],
            [42, None],
        )
        self.assertEqual(weather, original_weather)
        self.assertIsNot(bundle.raw, weather)
        self.assertEqual(bundle.raw['hourly']['us_aqi'], [42, None])


if __name__ == '__main__':
    unittest.main()
