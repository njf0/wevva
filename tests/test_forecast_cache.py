"""Focused checks for session-only forecast and saved-summary request handling."""

from __future__ import annotations

import asyncio
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
        self.loading_states = []

    def post_message(self, message) -> None:
        self.messages.append(message)

    def saved_location_weather_summary(self, location: LocationMetadata):
        return self.summaries.get((location.latitude, location.longitude))

    def update_saved_location_weather(self, location: LocationMetadata, summary) -> None:
        self.summaries[(location.latitude, location.longitude)] = summary

    def set_forecast_loading(self, loading: bool) -> None:
        self.loading_states.append(loading)


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
        self.assertEqual(self.app.weather_screen.loading_states, [True])
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
        self.assertEqual(self.app.weather_screen.loading_states, [True, False])
        self.assertIsInstance(self.app.weather_screen.messages[0], WeatherFetchFailed)

    async def test_cancelled_forecast_clears_loading_and_propagates(self) -> None:
        self.app.controller.fetch = AsyncMock(side_effect=asyncio.CancelledError)

        with self.assertRaises(asyncio.CancelledError):
            await self._refresh()

        self.assertEqual(self.app.weather_screen.loading_states, [True, False])
        self.assertEqual(self.app.weather_screen.messages, [])

    async def test_dashboard_preview_reuses_cache_without_adopting_location(self) -> None:
        preview_location = LocationMetadata(
            latitude=48.8566,
            longitude=2.3522,
            country_code='FR',
        )

        first = await self.app.load_dashboard_forecast(preview_location)
        second = await self.app.load_dashboard_forecast(preview_location)

        self.app.controller.fetch.assert_awaited_once_with(
            lat=48.8566,
            lon=2.3522,
            country_code='FR',
        )
        self.assertIs(first.current, self.event.current)
        self.assertIs(second.hourly, self.event.hourly)
        self.assertIs(self.app.location, self.location)

    async def test_dashboard_preview_explicit_refresh_bypasses_cache(self) -> None:
        preview_location = LocationMetadata(
            latitude=48.8566,
            longitude=2.3522,
            country_code='FR',
        )

        await self.app.load_dashboard_forecast(preview_location)
        await self.app.load_dashboard_forecast(
            preview_location,
            refresh=True,
        )

        self.assertEqual(self.app.controller.fetch.await_count, 2)

    async def test_cancelled_dashboard_preview_cancels_provider_task(self) -> None:
        preview_location = LocationMetadata(
            latitude=48.8566,
            longitude=2.3522,
            country_code='FR',
        )
        started = asyncio.Event()

        async def delayed_fetch(**kwargs):
            del kwargs
            started.set()
            await asyncio.Event().wait()

        self.app.controller.fetch = AsyncMock(side_effect=delayed_fetch)
        task = asyncio.create_task(
            self.app.load_dashboard_forecast(preview_location)
        )
        await started.wait()
        task.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0)
        self.assertEqual(self.app._dashboard_forecast_tasks, {})
        self.assertEqual(self.app._forecast_cache, {})


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

    async def test_missing_temperature_gets_one_short_retry(self) -> None:
        location = LocationMetadata(
            latitude=19.7297,
            longitude=-155.09,
            country_code='US',
        )
        app = Wevva(
            initial_location=LocationMetadata(
                latitude=52.52,
                longitude=13.405,
                country_code='DE',
            )
        )
        app.weather_screen = _WeatherScreen()
        app._saved_weather_generation = 1
        summary_fetch = AsyncMock(
            side_effect=[
                {'current': {}, 'current_units': {}},
                {
                    'current': {
                        'temperature_2m': 27.0,
                        'weather_code': 1,
                        'is_day': 1,
                    },
                    'current_units': {'temperature_2m': '°C'},
                },
            ]
        )

        with (
            patch('wevva.app.fetch_weather_summary', new=summary_fetch),
            patch('wevva.app.asyncio.sleep', new=AsyncMock()) as retry_sleep,
        ):
            await app._fetch_saved_weather_summary(location, generation=1)

        self.assertEqual(summary_fetch.await_count, 2)
        retry_sleep.assert_awaited_once()
        self.assertEqual(
            app.weather_screen.saved_location_weather_summary(location).temperature,
            27.0,
        )


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

    async def test_application_forwards_alert_place_preview_units(self) -> None:
        app = Wevva()
        weather = {'current': {'temperature_2m': 72}}
        loader = AsyncMock(return_value=weather)

        with patch('wevva.app.fetch_current_weather', new=loader):
            first = await app.load_alert_place_weather(
                34.42,
                -106.83,
                'fahrenheit',
                'mph',
                'inch',
            )
            second = await app.load_alert_place_weather(
                34.42,
                -106.83,
                'fahrenheit',
                'mph',
                'inch',
            )

        self.assertIs(first, weather)
        self.assertIs(second, weather)
        loader.assert_awaited_once_with(
            lat=34.42,
            lon=-106.83,
            temperature_unit='fahrenheit',
            wind_speed_unit='mph',
            precipitation_unit='inch',
        )

    async def test_alert_place_preview_cache_expires_and_separates_units(self) -> None:
        app = Wevva()
        now = [100.0]
        app._alert_place_weather_cache_clock = lambda: now[0]
        loader = AsyncMock(
            side_effect=[
                {'current': {'temperature_2m': 12}},
                {'current': {'temperature_2m': 13}},
                {'current': {'temperature_2m': 55}},
            ]
        )

        with patch('wevva.app.fetch_current_weather', new=loader):
            await app.load_alert_place_weather(52.5, 13.4, 'celsius', 'kmh', 'mm')
            now[0] += app.ALERT_PLACE_WEATHER_CACHE_TTL_SECONDS
            await app.load_alert_place_weather(52.5, 13.4, 'celsius', 'kmh', 'mm')
            await app.load_alert_place_weather(52.5, 13.4, 'fahrenheit', 'mph', 'inch')

        self.assertEqual(loader.await_count, 3)

    async def test_cancelled_preview_caller_does_not_cancel_shared_request(self) -> None:
        app = Wevva()
        started = asyncio.Event()
        release = asyncio.Event()
        weather = {'current': {'temperature_2m': 12}}
        calls = 0

        async def load_weather(**_kwargs):
            nonlocal calls
            calls += 1
            started.set()
            await release.wait()
            return weather

        with patch('wevva.app.fetch_current_weather', new=load_weather):
            first = asyncio.create_task(
                app.load_alert_place_weather(52.5, 13.4, 'celsius', 'kmh', 'mm')
            )
            await started.wait()
            first.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await first
            second = asyncio.create_task(
                app.load_alert_place_weather(52.5, 13.4, 'celsius', 'kmh', 'mm')
            )
            release.set()
            self.assertIs(await second, weather)

        self.assertEqual(len(app._alert_place_weather_tasks), 0)
        self.assertEqual(calls, 1)


class CityTemperatureRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_batches_coordinates_and_asks_only_for_temperature(self) -> None:
        response = Mock()
        response.json.return_value = [
            {'current': {'temperature_2m': 16.4}},
            {'current': {'temperature_2m': 18.8}},
        ]
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.get.return_value = response
        coordinates = ((52.5238, 13.3996), (50.0997, 8.6750))

        with patch('wevva.openmeteo.httpx.AsyncClient', return_value=client):
            result = await OpenMeteoForecast.fetch_current_temperatures(
                coordinates,
                temperature_unit='fahrenheit',
            )

        self.assertEqual(
            result,
            {
                coordinates[0]: 16.4,
                coordinates[1]: 18.8,
            },
        )
        _url, = client.get.await_args.args
        params = client.get.await_args.kwargs['params']
        self.assertEqual(params['latitude'], '52.5238,50.0997')
        self.assertEqual(params['longitude'], '13.3996,8.675')
        self.assertEqual(params['current'], 'temperature_2m')
        self.assertNotIn('hourly', params)
        self.assertNotIn('daily', params)
        self.assertEqual(params['temperature_unit'], 'fahrenheit')
        response.raise_for_status.assert_called_once_with()

    async def test_application_forwards_captured_unit_for_city_temperatures(self) -> None:
        app = Wevva(temperature_unit='fahrenheit')
        loader = AsyncMock(return_value={})
        coordinates = ((52.5238, 13.3996),)

        with patch('wevva.app.fetch_city_temperatures', new=loader):
            result = await app.load_location_map_temperatures(
                coordinates,
                'fahrenheit',
            )

        self.assertEqual(result, {})
        loader.assert_awaited_once_with(
            coordinates,
            temperature_unit='fahrenheit',
        )


if __name__ == '__main__':
    unittest.main()
