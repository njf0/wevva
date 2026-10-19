"""Application integration checks for Task 0020 Slice D."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from textual.widgets import Input, Select

from wevva.app import Wevva
from wevva.location_metadata import LocationMetadata
from wevva.screens.alerts_centre_screen import AlertFilterDialog, AlertsCentreScreen
from wevva.screens.weather_screen import WeatherScreen
from wevva.widgets.country_alerts_map import CountryAlertCityLabel


BERLIN = LocationMetadata(
    name='Berlin',
    country='Germany',
    country_code='DE',
    latitude=52.52,
    longitude=13.405,
)


class AlertsCentreApplicationIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def _app(self) -> Wevva:
        app = Wevva(initial_location=BERLIN)
        app.action_refresh = AsyncMock()
        app.country_alerts_service.get_alerts = AsyncMock(return_value=[])
        app.load_location_map_temperatures = AsyncMock(return_value={})
        app.load_alert_place_weather = AsyncMock(
            return_value={
                'current': {'temperature_2m': 18},
                'current_units': {'temperature_2m': '°C'},
            }
        )
        return app

    async def test_g_resumes_installed_workspace_and_w_returns_to_weather(self) -> None:
        app = self._app()

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            weather_screen = app.screen
            self.assertIsInstance(weather_screen, WeatherScreen)

            await pilot.press('g')
            for _ in range(3):
                await pilot.pause()

            alerts_screen = app.screen
            self.assertIsInstance(alerts_screen, AlertsCentreScreen)
            self.assertTrue(app.is_screen_installed(alerts_screen))
            self.assertIs(alerts_screen.service, app.country_alerts_service)
            first_call = app.country_alerts_service.get_alerts.await_args
            self.assertEqual(first_call.args, ('DE',))
            self.assertEqual(first_call.kwargs['warning_language'], 'auto')
            self.assertFalse(first_call.kwargs['refresh'])

            await pilot.press('w')
            await pilot.pause()
            self.assertIs(app.screen, weather_screen)
            self.assertTrue(alerts_screen.is_mounted)
            filter_button = alerts_screen.alert_filter_button

            await pilot.press('g')
            for _ in range(2):
                await pilot.pause()
            self.assertIs(app.screen, alerts_screen)
            self.assertIs(alerts_screen.alert_filter_button, filter_button)
            filter_button.focus()
            await pilot.press('enter')
            await pilot.pause()
            self.assertIsInstance(app.screen, AlertFilterDialog)
            field = app.screen.query_one(
                '#alerts-centre-filter-dialog-input',
                Input,
            )
            self.assertEqual(field.value, '')
            self.assertEqual(field.placeholder, 'Condition, location, or source')
            severity_select = app.screen.query_one(
                '#alerts-centre-filter-dialog-severity',
                Select,
            )
            self.assertEqual(severity_select.value, '')
            sort_select = app.screen.query_one(
                '#alerts-centre-filter-dialog-sort',
                Select,
            )
            self.assertEqual(sort_select.value, 'severity')
            self.assertEqual(
                len(alerts_screen.query('#alerts-centre-sort-select')),
                0,
            )
            await pilot.press('x', 'enter')
            await pilot.pause()
            self.assertIs(app.screen, alerts_screen)
            self.assertEqual(alerts_screen.alert_filter_value, 'x')

            filter_button.focus()
            await pilot.press('enter')
            await pilot.pause()
            self.assertEqual(
                app.screen.query_one(
                    '#alerts-centre-filter-dialog-input',
                    Input,
                ).value,
                'x',
            )
            await pilot.press('escape')
            await pilot.pause()
            self.assertEqual(alerts_screen.alert_filter_value, 'x')

            filter_button.focus()
            await pilot.press('enter')
            await pilot.pause()
            app.screen.query_one(
                '#alerts-centre-filter-dialog-sort',
                Select,
            ).value = 'new'
            await pilot.click('#alerts-centre-filter-clear')
            await pilot.pause()
            self.assertIs(app.screen, alerts_screen)
            self.assertEqual(alerts_screen.alert_filter_value, '')
            self.assertEqual(alerts_screen.alert_sort_value, 'new')

    async def test_settlement_activation_opens_weather_and_preserves_alert_context(self) -> None:
        app = self._app()

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press('g')
            for _ in range(3):
                await pilot.pause()
            alerts_screen = app.screen
            self.assertIsInstance(alerts_screen, AlertsCentreScreen)
            selected_country = alerts_screen.selected_country_code
            label = next(iter(alerts_screen.country_map.query(CountryAlertCityLabel)))
            refresh_count = app.action_refresh.await_count

            label.action_select_settlement()
            for _ in range(3):
                await pilot.pause()

            self.assertIs(app.screen, app.weather_screen)
            self.assertEqual(app.location.name, label.place.name)
            self.assertEqual(app.location.latitude, label.place.latitude)
            self.assertEqual(app.location.longitude, label.place.longitude)
            self.assertEqual(app.action_refresh.await_count, refresh_count + 1)

            await pilot.press('g')
            for _ in range(2):
                await pilot.pause()
            self.assertIs(app.screen, alerts_screen)
            self.assertEqual(alerts_screen.selected_country_code, selected_country)

    async def test_late_provider_progress_does_not_block_reopening_workspace(self) -> None:
        class LingeringProgressService:
            last_country_code: str | None = None

            def __init__(self) -> None:
                self.calls = 0
                self.started = asyncio.Event()
                self.progress = None

            async def get_alerts(
                service_self,
                _country_code,
                *,
                warning_language,
                progress,
                refresh,
            ):
                del warning_language, refresh
                service_self.calls += 1
                if service_self.calls > 1:
                    return []
                service_self.progress = progress
                service_self.started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    # Model the underlying provider thread outliving its
                    # cancelled asyncio wrapper.
                    return []

        app = self._app()
        service = LingeringProgressService()
        app.country_alerts_service = service  # type: ignore[assignment]

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press('g')
            await service.started.wait()
            alerts_screen = app.screen
            self.assertIsInstance(alerts_screen, AlertsCentreScreen)

            await pilot.press('w')
            await pilot.pause()
            self.assertIsInstance(app.screen, WeatherScreen)
            self.assertIsNotNone(service.progress)

            with patch.object(
                app,
                'call_from_thread',
                wraps=app.call_from_thread,
            ) as bridge:
                await asyncio.to_thread(
                    service.progress,
                    'alerts_checked',
                    {'completed': 1, 'total': 20},
                )
                self.assertEqual(bridge.call_count, 0)

            await pilot.press('g')
            for _ in range(2):
                await pilot.pause()
            self.assertIs(app.screen, alerts_screen)
            self.assertEqual(service.calls, 1)

    async def test_alert_refresh_does_not_fetch_place_weather_without_hover(self) -> None:
        app = self._app()

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press('g')
            for _ in range(3):
                await pilot.pause()
            country_calls = app.country_alerts_service.get_alerts.await_count

            await pilot.press('r')
            for _ in range(3):
                await pilot.pause()

            self.assertEqual(
                app.country_alerts_service.get_alerts.await_count,
                country_calls + 1,
            )
            self.assertTrue(
                app.country_alerts_service.get_alerts.await_args.kwargs['refresh']
            )
            self.assertEqual(app.load_location_map_temperatures.await_count, 0)
            self.assertEqual(app.load_alert_place_weather.await_count, 0)
            self.assertEqual(app.action_refresh.await_count, 1)

    async def test_open_workspace_tracks_unit_and_language_setting_changes(self) -> None:
        app = self._app()

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press('g')
            for _ in range(3):
                await pilot.pause()
            screen = app.screen
            self.assertIsInstance(screen, AlertsCentreScreen)
            screen._place_weather_hover_delay_seconds = 0
            label = next(iter(screen.country_map.query(CountryAlertCityLabel)))
            screen._start_place_weather_preview(label)
            await pilot.pause()

            await app._on_settings_result(
                {
                    'temperature_unit': 'fahrenheit',
                    'wind_speed_unit': 'mph',
                    'precipitation_unit': 'inch',
                    'theme': app.theme,
                    'emoji_enabled': app.emoji_enabled,
                    'warning_language': 'en',
                    'default_location_action': 'keep',
                    'save_defaults': False,
                }
            )
            for _ in range(3):
                await pilot.pause()

            self.assertEqual(screen.warning_language, 'en')
            self.assertEqual(
                app.country_alerts_service.get_alerts.await_args.kwargs['warning_language'],
                'en',
            )
            screen._start_place_weather_preview(label)
            await pilot.pause()
            self.assertEqual(
                app.load_alert_place_weather.await_args.args[2:],
                ('fahrenheit', 'mph', 'inch'),
            )

    async def test_closed_workspace_applies_settings_when_reopened(self) -> None:
        app = self._app()

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press('g')
            for _ in range(3):
                await pilot.pause()
            alerts_screen = app.screen
            assert isinstance(alerts_screen, AlertsCentreScreen)
            alerts_screen._place_weather_hover_delay_seconds = 0
            label = next(
                iter(alerts_screen.country_map.query(CountryAlertCityLabel))
            )
            alerts_screen._start_place_weather_preview(label)
            await pilot.pause()
            await pilot.press('w')
            await pilot.pause()

            await app._on_settings_result(
                {
                    'temperature_unit': 'fahrenheit',
                    'wind_speed_unit': 'mph',
                    'precipitation_unit': 'inch',
                    'theme': app.theme,
                    'emoji_enabled': app.emoji_enabled,
                    'warning_language': 'en',
                    'default_location_action': 'keep',
                    'save_defaults': False,
                }
            )
            await pilot.press('g')
            for _ in range(3):
                await pilot.pause()

            self.assertIs(app.screen, alerts_screen)
            label = next(
                iter(alerts_screen.country_map.query(CountryAlertCityLabel))
            )
            alerts_screen._start_place_weather_preview(label)
            await pilot.pause()
            self.assertEqual(
                app.load_alert_place_weather.await_args.args[2:],
                ('fahrenheit', 'mph', 'inch'),
            )
            self.assertEqual(
                app.country_alerts_service.get_alerts.await_args.kwargs['warning_language'],
                'en',
            )

class AlertsCentreBindingTests(unittest.TestCase):
    def test_launcher_does_not_displace_local_warning_details(self) -> None:
        bindings = {key: (action, label) for key, action, label in WeatherScreen.BINDINGS}

        self.assertEqual(bindings['g'], ('alerts_centre', 'Alerts Centre'))
        self.assertEqual(bindings['i'], ('alert_details', 'Warning details'))


if __name__ == '__main__':
    unittest.main()
