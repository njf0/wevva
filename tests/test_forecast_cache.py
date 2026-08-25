"""Focused checks for session-only forecast and saved-summary request handling."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock, patch

from wevva.app import Wevva
from wevva.location_metadata import LocationMetadata
from wevva.messages import WeatherFetchFailed, WeatherUpdated
from wevva.openmeteo import OpenMeteoForecast


class _WeatherScreen:
    def __init__(self) -> None:
        self.messages = []
        self.summaries = {}

    def post_message(self, message) -> None:
        self.messages.append(message)

    def saved_location_weather_summary(self, location: LocationMetadata):
        return self.summaries.get((location.latitude, location.longitude))

    def update_saved_location_weather(self, location: LocationMetadata, summary) -> None:
        self.summaries[(location.latitude, location.longitude)] = summary


class ForecastCacheTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.location = LocationMetadata(latitude=52.52, longitude=13.405, country_code='DE')
        self.app = Wevva(initial_location=self.location)
        self.app.weather_screen = _WeatherScreen()
        self.clock = 1_000.0
        self.app._forecast_cache_clock = lambda: self.clock
        self.event = WeatherUpdated(
            metadata=LocationMetadata(latitude=52.5201, longitude=13.4049),
            current=object(),
            hourly=object(),
            daily=object(),
        )
        self.app.controller.fetch = AsyncMock(return_value=self.event)

    async def _refresh(self, *, force: bool = False) -> Mock:
        with (
            patch.object(self.app, '_schedule_saved_weather_refresh'),
            patch.object(self.app, '_schedule_alert_refresh') as schedule_alerts,
        ):
            await self.app._refresh_weather(force_alert_refresh=force)
        return schedule_alerts

    async def test_complete_forecast_is_reused_within_fifteen_minutes(self) -> None:
        await self._refresh()
        await self._refresh()

        self.app.controller.fetch.assert_awaited_once_with(lat=52.52, lon=13.405, country_code='DE')
        first, cached = self.app.weather_screen.messages
        self.assertIs(first, self.event)
        self.assertIsNot(cached, self.event)
        self.assertIs(cached.current, self.event.current)
        self.assertIs(cached.hourly, self.event.hourly)
        self.assertIs(cached.daily, self.event.daily)

    async def test_expiry_and_explicit_refresh_bypass_the_forecast_cache(self) -> None:
        await self._refresh()
        self.clock += self.app.FORECAST_CACHE_TTL_SECONDS
        await self._refresh()
        await self._refresh(force=True)

        self.assertEqual(self.app.controller.fetch.await_count, 3)

    async def test_forecast_cache_key_includes_display_units(self) -> None:
        await self._refresh()
        self.app.temperature_unit = 'fahrenheit'
        await self._refresh()

        self.assertEqual(self.app.controller.fetch.await_count, 2)

    async def test_failed_forecast_is_not_cached(self) -> None:
        self.app.controller.fetch = AsyncMock(side_effect=RuntimeError('offline'))

        await self._refresh()

        self.assertEqual(self.app._forecast_cache, {})
        self.assertIsInstance(self.app.weather_screen.messages[0], WeatherFetchFailed)


class SavedWeatherSummaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_saved_summary_uses_the_current_only_weather_request(self) -> None:
        location = LocationMetadata(latitude=48.8566, longitude=2.3522, country_code='FR')
        app = Wevva(initial_location=LocationMetadata(latitude=52.52, longitude=13.405, country_code='DE'))
        app.weather_screen = _WeatherScreen()
        app._saved_weather_generation = 1
        summary_fetch = AsyncMock(return_value={
            'current': {'temperature_2m': 22.5, 'weather_code': 1, 'is_day': 1},
            'current_units': {'temperature_2m': '°C'},
        })

        with patch('wevva.app.fetch_weather_summary', new=summary_fetch):
            await app._fetch_saved_weather_summary(location, generation=1)

        summary_fetch.assert_awaited_once_with(
            lat=48.8566,
            lon=2.3522,
            temperature_unit='celsius',
        )
        summary = app.weather_screen.saved_location_weather_summary(location)
        self.assertEqual(summary.temperature, 22.5)
        self.assertEqual(summary.temperature_unit, '°C')
        self.assertFalse(summary.error)


class TropicalCentreWeatherRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_current_conditions_request_omits_hourly_and_daily_payloads(self) -> None:
        response = Mock()
        response.json.return_value = {'current': {'temperature_2m': 84}}
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.get.return_value = response

        with patch('wevva.openmeteo.httpx.AsyncClient', return_value=client):
            result = await OpenMeteoForecast.fetch_current_conditions(
                17.8,
                -153.5,
                temperature_unit='fahrenheit',
                wind_speed_unit='mph',
                precipitation_unit='inch',
            )

        self.assertEqual(result, {'current': {'temperature_2m': 84}})
        _url, = client.get.await_args.args
        params = client.get.await_args.kwargs['params']
        self.assertIn('current', params)
        self.assertNotIn('hourly', params)
        self.assertNotIn('daily', params)
        self.assertEqual(params['temperature_unit'], 'fahrenheit')
        self.assertEqual(params['wind_speed_unit'], 'mph')
        self.assertEqual(params['precipitation_unit'], 'inch')
        response.raise_for_status.assert_called_once_with()

    async def test_application_uses_configured_units_for_storm_centre(self) -> None:
        app = Wevva(
            temperature_unit='fahrenheit',
            wind_speed_unit='mph',
            precipitation_unit='inch',
        )
        loader = AsyncMock(return_value={'current': {}})

        with patch('wevva.app.fetch_current_weather', new=loader):
            result = await app.load_tropical_centre_weather(17.8, -153.5)

        self.assertEqual(result, {'current': {}})
        loader.assert_awaited_once_with(
            lat=17.8,
            lon=-153.5,
            temperature_unit='fahrenheit',
            wind_speed_unit='mph',
            precipitation_unit='inch',
        )


if __name__ == '__main__':
    unittest.main()
