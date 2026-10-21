"""Mounted Slice A checks for the persistent unified dashboard."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

from rich.text import Text
from textual.widgets import OptionList, Static, Tabs
from wevva_warnings import Alert, CanonicalTropicalSystem, TropicalSystem
from wevva_warnings.registry import get_source

from tests.weather_fixtures import weather_update
from wevva.app import Wevva
from wevva.conditions import get_condition
from wevva.config import location_key
from wevva.location_metadata import LocationMetadata
from wevva.screens.dashboard_screen import DashboardScreen
from wevva.services.alert_bulletin import BulletinAlert
from wevva.screens.tropical_systems_screen import TropicalSystemsScreen
from wevva.screens.weather_screen import WeatherScreen
from wevva.widgets.dashboard_daily_forecast import DashboardDailyForecast
from wevva.widgets.dashboard_world_map import (
    DashboardAlertMarker,
    DashboardLocationLabel,
    DashboardTropicalLabel,
)
from wevva.widgets.dashboard_hourly_forecast import DashboardHourlyForecast
from wevva.widgets.saved_locations import SavedLocationWeatherSummary


BERLIN = LocationMetadata(
    name='Berlin',
    country='Germany',
    country_code='DE',
    latitude=52.52,
    longitude=13.405,
)
LONDON = LocationMetadata(
    name='London',
    country='United Kingdom',
    country_code='GB',
    latitude=51.5072,
    longitude=-0.1276,
)
TOKYO = LocationMetadata(
    name='Tokyo',
    country='Japan',
    country_code='JP',
    latitude=35.6762,
    longitude=139.6503,
)


async def _settle(pilot, cycles: int = 4) -> None:
    for _ in range(cycles):
        await pilot.pause(0)


def _summary(temperature: float) -> SavedLocationWeatherSummary:
    condition = get_condition(1)
    return SavedLocationWeatherSummary(
        temperature=temperature,
        temperature_unit='°C',
        condition=condition,
        condition_emoji=condition.day_emoji,
    )


def _tropical_observation(
    system_id: str,
    source: str,
    name: str,
    *,
    classification: str,
    latitude: float,
    longitude: float,
) -> TropicalSystem:
    return TropicalSystem(
        id=system_id,
        source=source,
        name=name,
        headline=f'{classification} {name}',
        classification=classification,
        center_lat=latitude,
        center_lon=longitude,
        movement='NW at 15 kt',
        max_wind='45 kt',
        issued_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
        source_info=get_source(source),
        geometries={},
    )


class DashboardScreenTests(unittest.IsolatedAsyncioTestCase):
    def _app(self) -> Wevva:
        app = Wevva(
            initial_location=BERLIN,
            saved_locations=[LONDON, TOKYO],
            emoji_enabled=False,
        )
        app.action_refresh = AsyncMock()
        app.alert_bulletin.schedule_hard_refresh = Mock()
        app._saved_location_weather_summaries = {
            location_key(BERLIN): _summary(14),
            location_key(LONDON): _summary(11),
            location_key(TOKYO): _summary(23),
        }
        event = weather_update(with_warnings=False)
        cached_at = app._forecast_cache_clock()
        app._forecast_cache = {
            app._forecast_cache_key_for(location): (cached_at, event)
            for location in (BERLIN, LONDON, TOKYO)
        }
        app.controller.fetch = AsyncMock()
        app._tropical_system_cache = (
            app._tropical_system_cache_clock(),
            (),
        )
        return app

    async def test_wide_dashboard_uses_existing_state_without_fetching(self) -> None:
        app = self._app()
        async with app.run_test(size=(120, 30)) as pilot:
            await _settle(pilot)
            app.action_refresh.reset_mock()

            await pilot.press('b')
            await _settle(pilot)

            screen = app.screen
            self.assertIsInstance(screen, DashboardScreen)
            self.assertIs(screen, app._dashboard_screen)
            self.assertFalse(screen.query_one('#dashboard-pane-tabs', Tabs).display)
            self.assertTrue(screen.forecast_panel.display)
            self.assertTrue(screen.world_map.display)
            self.assertTrue(screen.alerts_panel.display)
            self.assertEqual(len(list(screen.world_map.query(DashboardLocationLabel))), 3)
            self.assertIn(
                'Berlin',
                screen.query_one('#dashboard-forecast-place', Static).render().plain,
            )
            self.assertIn(
                '13°C',
                screen.query_one('#dashboard-current-summary', Static).render().plain,
            )
            hourly = screen.query_one(
                '#dashboard-hourly-forecast',
                DashboardHourlyForecast,
            )
            self.assertTrue(hourly.display)
            self.assertGreater(len(hourly.table.columns), 0)
            self.assertEqual(len(hourly.table.rows), 24)
            self.assertEqual(hourly.table.max_scroll_x, 0)
            daily = screen.query_one(
                '#dashboard-daily-forecast',
                DashboardDailyForecast,
            )
            self.assertTrue(daily.display)
            self.assertEqual(len(daily.table.rows), 3)
            self.assertEqual(len(daily.table.columns), 8)
            self.assertEqual(daily.table.max_scroll_x, 0)

            daily_region = daily.region
            hourly.table.focus()
            await pilot.press('down')
            await _settle(pilot)
            self.assertEqual(daily.region, daily_region)
            self.assertEqual(screen.forecast_panel.scroll_y, 0)
            self.assertIn(
                '14°C',
                screen.query_one(
                    '#dashboard-current-summary',
                    Static,
                ).render().plain,
            )
            await pilot.press('r')
            await _settle(pilot)
            app.action_refresh.assert_not_awaited()
            app.alert_bulletin.schedule_hard_refresh.assert_called_once_with(
                ['DE', None, None]
            )
            app.controller.fetch.assert_not_awaited()

            screen.refresh_appearance = Mock(wraps=screen.refresh_appearance)
            await app._on_settings_result(
                {
                    'temperature_unit': app.temperature_unit,
                    'wind_speed_unit': app.wind_speed_unit,
                    'precipitation_unit': app.precipitation_unit,
                    'theme': 'textual-light',
                    'emoji_enabled': True,
                    'warning_language': app.warning_language,
                    'default_location_action': 'keep',
                    'save_defaults': False,
                }
            )
            await _settle(pilot)
            screen.refresh_appearance.assert_called_once_with()
            app.action_refresh.assert_not_awaited()
            app.controller.fetch.assert_not_awaited()

    async def test_recent_alert_selection_and_open_use_stable_deep_link(self) -> None:
        app = self._app()
        app.open_alerts_centre_screen = Mock()
        alert = Alert(
            id='flood-1',
            source='fixture',
            event='Extremely Long River Flood Warning Across Multiple Districts',
            headline='Extremely long river flooding warning',
            severity='Severe',
            area_names=['A deliberately long affected-area label for the Lower Rhine'],
            geometry={
                'type': 'Polygon',
                'coordinates': [
                    [[6, 49], [10, 49], [10, 52], [6, 52], [6, 49]]
                ],
            },
        )
        row = BulletinAlert(
            'DE',
            alert,
            datetime.now(UTC),
        )

        async with app.run_test(size=(120, 30)) as pilot:
            await _settle(pilot)
            await pilot.press('b')
            await _settle(pilot)
            screen = app.screen
            self.assertIsInstance(screen, DashboardScreen)
            screen.update_bulletin(1, (row,))
            panel = screen.alerts_panel
            option = panel.alert_list.options[0]

            panel.on_option_list_option_selected(
                OptionList.OptionSelected(panel.alert_list, option, 0)
            )
            await pilot.pause()
            self.assertIs(panel.selected_row, row)
            selected_prompt = panel.alert_list.options[0].prompt
            self.assertIsInstance(selected_prompt, Text)
            selected_lines = selected_prompt.plain.splitlines()
            self.assertEqual(len(selected_lines), 2)
            self.assertTrue(selected_lines[0].startswith('▸ '))
            self.assertTrue(
                all(len(line) <= panel._text_width() for line in selected_lines)
            )
            marker = screen.world_map.query_one(
                '#dashboard-alert-marker',
                DashboardAlertMarker,
            )
            self.assertTrue(marker.display)
            self.assertIs(marker.row, row)
            await pilot.pause(0.55)
            self.assertIsNone(screen.world_map._alert_pulse_task)
            self.assertFalse(marker.has_class('pulse'))
            self.assertIn(
                'First found by Wevva',
                panel.query_one('#dashboard-alert-preview', Static).render().plain,
            )
            app.refresh_dashboard_bulletin()
            app.alert_bulletin.schedule_hard_refresh.assert_called_once_with(
                ['DE', None, 'DE']
            )

            panel.post_message(panel.OpenRequested(row))
            await pilot.pause()
            app.open_alerts_centre_screen.assert_called_once_with(
                country_code='DE',
                alert_identity=('fixture', 'flood-1'),
            )

            marker.action_activate()
            await pilot.pause()
            self.assertEqual(app.open_alerts_centre_screen.call_count, 2)

            panel.on_option_list_option_selected(
                OptionList.OptionSelected(panel.alert_list, option, 0)
            )
            await pilot.pause()
            self.assertIsNone(panel.selected_row)
            self.assertFalse(marker.display)

            panel.on_option_list_option_selected(
                OptionList.OptionSelected(panel.alert_list, option, 0)
            )
            await pilot.pause()
            self.assertIsNotNone(screen.world_map._alert_pulse_task)
            screen.action_back()
            await _settle(pilot)
            self.assertIsNot(app.screen, screen)
            self.assertIsNone(screen.world_map._alert_pulse_task)
            await pilot.press('b')
            await _settle(pilot)
            self.assertIs(app.screen, screen)
            self.assertIs(panel.selected_row, row)
            self.assertTrue(marker.display)
            self.assertIsNone(screen.world_map._alert_pulse_task)
            await pilot.press('escape')
            await pilot.pause()
            self.assertIsNone(panel.selected_row)
            self.assertFalse(marker.display)

            panel.post_message(panel.Previewed(row))
            await pilot.pause()
            self.assertTrue(marker.display)
            self.assertTrue(marker.preview)
            panel.post_message(panel.Previewed(None))
            await pilot.pause()
            self.assertFalse(marker.display)

            geometryless = BulletinAlert(
                'DE',
                Alert(
                    id='heat-1',
                    source='fixture',
                    event='Heat Warning',
                    headline='Heat warning',
                    severity='Moderate',
                ),
                datetime.now(UTC),
            )
            screen.update_bulletin(2, (geometryless,))
            geometryless_option = panel.alert_list.options[0]
            panel.on_option_list_option_selected(
                OptionList.OptionSelected(
                    panel.alert_list,
                    geometryless_option,
                    0,
                )
            )
            await pilot.pause()
            self.assertIs(panel.selected_row, geometryless)
            self.assertFalse(marker.display)
            screen.update_bulletin(3, ())
            await pilot.pause()
            self.assertIsNone(panel.selected_row)

    async def test_place_select_then_activate_returns_to_existing_weather(self) -> None:
        app = self._app()
        async with app.run_test(size=(120, 30)) as pilot:
            await _settle(pilot)
            weather = app.screen
            self.assertIsInstance(weather, WeatherScreen)
            app.action_refresh.reset_mock()

            await pilot.press('b')
            await _settle(pilot)
            dashboard = app.screen
            self.assertIsInstance(dashboard, DashboardScreen)
            london = next(
                label
                for label in dashboard.world_map.query(DashboardLocationLabel)
                if label.location.name == 'London'
            )

            london.focus()
            await _settle(pilot)
            self.assertEqual(app.location, BERLIN)
            self.assertIn(
                'London',
                dashboard.query_one('#dashboard-forecast-place', Static).render().plain,
            )
            self.assertEqual(
                dashboard.query_one('#dashboard-forecast-role', Static).render().plain,
                'Preview',
            )

            await pilot.press('enter')
            await _settle(pilot)
            self.assertIs(app.screen, dashboard)
            self.assertEqual(app.location, BERLIN)
            self.assertEqual(dashboard.world_map.selected_location_key, location_key(LONDON))
            self.assertIn(
                'London',
                dashboard.query_one('#dashboard-forecast-place', Static).render().plain,
            )
            app.action_refresh.assert_not_awaited()

            await pilot.press('enter')
            await _settle(pilot)
            self.assertIs(app.screen, weather)
            self.assertEqual(app.location, LONDON)
            app.action_refresh.assert_awaited_once()

            await pilot.press('b')
            await _settle(pilot)
            self.assertIs(app.screen, dashboard)
            self.assertEqual(dashboard.world_map.selected_location_key, location_key(LONDON))

    async def test_resize_reuses_panels_and_compact_tabs(self) -> None:
        app = self._app()
        async with app.run_test(size=(120, 30)) as pilot:
            await _settle(pilot)
            await pilot.press('b')
            await _settle(pilot)
            screen = app.screen
            self.assertIsInstance(screen, DashboardScreen)
            panels = (screen.forecast_panel, screen.world_map, screen.alerts_panel)

            await pilot.resize_terminal(80, 24)
            await _settle(pilot)
            tabs = screen.query_one('#dashboard-pane-tabs', Tabs)
            self.assertTrue(tabs.display)
            self.assertFalse(screen.forecast_panel.display)
            self.assertTrue(screen.world_map.display)
            self.assertFalse(screen.alerts_panel.display)

            tabs.active = 'dashboard-tab-forecast'
            await _settle(pilot)
            self.assertTrue(screen.forecast_panel.display)
            self.assertFalse(screen.world_map.display)
            compact_daily = screen.forecast_panel.daily_forecast
            self.assertTrue(screen.forecast_panel.hourly_forecast.display)
            self.assertTrue(compact_daily.display)
            self.assertEqual(len(compact_daily.table.rows), 2)
            self.assertEqual(compact_daily.table.max_scroll_x, 0)
            self.assertFalse(
                screen.query_one('#dashboard-open-weather-hint', Static).display
            )

            await pilot.resize_terminal(120, 30)
            await _settle(pilot)
            self.assertEqual(
                (screen.forecast_panel, screen.world_map, screen.alerts_panel),
                panels,
            )
            self.assertTrue(all(panel.display for panel in panels))

    async def test_very_large_layout_widens_rails_and_shortens_map(self) -> None:
        app = self._app()
        async with app.run_test(size=(250, 70)) as pilot:
            await _settle(pilot)
            await pilot.press('b')
            await _settle(pilot)
            screen = app.screen

            self.assertEqual(screen.forecast_panel.region.width, 54)
            self.assertEqual(screen.alerts_panel.region.width, 46)
            self.assertLess(screen.world_map.region.height, screen.forecast_panel.region.height)
            self.assertEqual(len(screen.forecast_panel.hourly_forecast.table.columns), 8)
            self.assertEqual(screen.forecast_panel.hourly_forecast.table.max_scroll_x, 0)
            self.assertEqual(len(screen.forecast_panel.daily_forecast.table.rows), 6)
            self.assertEqual(len(screen.forecast_panel.daily_forecast.table.columns), 9)
            self.assertEqual(screen.forecast_panel.daily_forecast.table.max_scroll_x, 0)

    async def test_tropical_overlay_uses_source_anchor_and_deep_links(self) -> None:
        app = self._app()
        cma = _tropical_observation(
            'nangka-cma',
            'cma_tropical',
            'NANGKA',
            classification='Tropical Storm',
            latitude=20.0,
            longitude=120.0,
        )
        jma = _tropical_observation(
            'nangka-jma',
            'jma_tropical',
            'NANGKA',
            classification='Typhoon',
            latitude=28.0,
            longitude=135.0,
        )
        nangka = CanonicalTropicalSystem('NANGKA', [cma, jma])
        lala_observation = _tropical_observation(
            'lala-cphc',
            'cphc_gis_central_pacific',
            'LALA',
            classification='Tropical Storm',
            latitude=15.2,
            longitude=-145.5,
        )
        lala = CanonicalTropicalSystem('LALA', [lala_observation])
        app._tropical_system_cache = (
            app._tropical_system_cache_clock(),
            (lala, nangka),
        )
        app.load_tropical_products = AsyncMock(return_value=[])
        app.load_tropical_centre_weather = AsyncMock(return_value={})

        async with app.run_test(size=(180, 45)) as pilot:
            await _settle(pilot)
            await pilot.press('b')
            await _settle(pilot, cycles=8)
            dashboard = app.screen
            self.assertIsInstance(dashboard, DashboardScreen)
            labels = list(dashboard.world_map.query(DashboardTropicalLabel))
            self.assertEqual(len(labels), 2)
            label = next(item for item in labels if item.system.name == 'NANGKA')
            self.assertIn('Typhoon NANGKA', label.label_text)
            self.assertIs(label.observation, jma)
            self.assertTrue(label.display)
            placement_keys = [
                placement.key for placement in dashboard.world_map.placements
            ]
            self.assertTrue(placement_keys[0].startswith('tropical:'))
            self.assertTrue(placement_keys[1].startswith('tropical:'))

            label.focus()
            await _settle(pilot)
            context = dashboard.query_one(
                '#dashboard-tropical-context',
                Static,
            ).render().plain
            self.assertIn('Moving NW at 15 kt', context)
            self.assertIn('Wind 45 kt', context)
            self.assertIn('JMA', context)

            label.action_activate()
            await _settle(pilot, cycles=10)
            tropical = app.screen
            self.assertIsInstance(tropical, TropicalSystemsScreen)
            self.assertEqual(tropical.systems[tropical.selected_storm_index].name, 'NANGKA')
            self.assertIs(tropical.selected_observation, jma)

            await pilot.press('w')
            await _settle(pilot, cycles=6)
            self.assertIs(app.screen, dashboard)
            self.assertEqual(
                dashboard.world_map.selected_tropical_key,
                label.tropical_key,
            )
            self.assertIs(app.focused, label)

    async def test_selected_place_loads_preview_without_becoming_active(self) -> None:
        app = self._app()
        app._forecast_cache.pop(app._forecast_cache_key_for(LONDON))
        event = weather_update(with_warnings=False)
        app.controller.fetch = AsyncMock(return_value=event)

        async with app.run_test(size=(120, 30)) as pilot:
            await _settle(pilot)
            await pilot.press('b')
            await _settle(pilot)
            dashboard = app.screen
            london = next(
                label
                for label in dashboard.world_map.query(DashboardLocationLabel)
                if label.location.name == 'London'
            )

            london.action_select_location()
            await _settle(pilot, cycles=8)

            self.assertEqual(app.location, BERLIN)
            app.controller.fetch.assert_awaited_once_with(
                lat=LONDON.latitude,
                lon=LONDON.longitude,
                country_code=LONDON.country_code,
            )
            self.assertTrue(dashboard.forecast_panel.hourly_forecast.display)
            self.assertIn(
                'London',
                dashboard.query_one('#dashboard-forecast-place', Static).render().plain,
            )

    async def test_weather_key_returns_without_refresh_and_preserves_selection(self) -> None:
        app = self._app()
        async with app.run_test(size=(100, 30)) as pilot:
            await _settle(pilot)
            weather = app.screen
            app.action_refresh.reset_mock()
            await pilot.press('b')
            await _settle(pilot)
            dashboard = app.screen
            tokyo = next(
                label
                for label in dashboard.world_map.query(DashboardLocationLabel)
                if label.location.name == 'Tokyo'
            )
            tokyo.action_select_location()
            await _settle(pilot)

            await pilot.press('w')
            await _settle(pilot)
            self.assertIs(app.screen, weather)
            self.assertEqual(app.location, BERLIN)
            app.action_refresh.assert_not_awaited()

            await pilot.press('b')
            await _settle(pilot)
            self.assertIs(app.screen, dashboard)
            self.assertEqual(dashboard.world_map.selected_location_key, location_key(TOKYO))


if __name__ == '__main__':
    unittest.main()
