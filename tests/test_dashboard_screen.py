"""Mounted checks for the persistent unified dashboard."""

from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime
from io import StringIO
from unittest.mock import AsyncMock, Mock

from rich.console import Console
from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import OptionList, Static, Tab, Tabs
from wevva_warnings import (
    Alert,
    CanonicalTropicalSystem,
    TropicalProduct,
    TropicalSystem,
)
from wevva_warnings.registry import get_source

from tests.weather_fixtures import weather_update
from wevva.app import Wevva
from wevva.conditions import get_condition
from wevva.config import location_key
from wevva.location_metadata import LocationMetadata
from wevva.screens.dashboard_screen import DashboardScreen
from wevva.services.alert_bulletin import BulletinAlert
from wevva.screens.weather_screen import WeatherScreen
from wevva.widgets.dashboard_daily_forecast import DashboardDailyForecast
from wevva.widgets.dashboard_world_map import (
    DashboardAlertMarker,
    DashboardLocationLabel,
    DashboardTropicalLabel,
)
from wevva.widgets.dashboard_hourly_forecast import DashboardHourlyForecast
from wevva.widgets.country_alerts_map import (
    CountryAlertCityLabel,
    CountryAlertSettlementPreviewRequested,
    CountryAlertsMap,
)
from wevva.widgets.saved_locations import SavedLocationWeatherSummary


BERLIN = LocationMetadata(
    name='Berlin',
    admin='Berlin Region',
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


def _rendered(static: Static) -> str:
    console = Console(width=100, file=StringIO(), record=True, color_system=None)
    console.print(static._Static__content)
    return console.export_text()


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
            self.assertTrue(screen.tropical_panel.display)
            self.assertTrue(screen.alert_detail_panel.display)
            self.assertTrue(screen.alerts_panel.display)
            self.assertIn(
                'No active tropical systems',
                screen.query_one(
                    '#dashboard-tropical-detail-state',
                    Static,
                ).render().plain,
            )
            self.assertTrue(
                screen.query_one('#dashboard-alerts-empty', Static).display
            )
            self.assertEqual(len(list(screen.world_map.query(DashboardLocationLabel))), 3)
            self.assertEqual(
                screen.query_one(
                    '#dashboard-forecast-place',
                    Static,
                ).render().plain,
                'Berlin\nGermany',
            )
            self.assertEqual(screen.forecast_panel.current_conditions.temp._value, '13')
            hourly = screen.query_one(
                '#dashboard-hourly-forecast',
                DashboardHourlyForecast,
            )
            self.assertTrue(hourly.display)
            self.assertFalse(hourly.table.show_header)
            self.assertEqual(len(hourly.table.columns), 5)
            self.assertEqual(len(hourly.table.rows), 24)
            self.assertEqual(hourly.table.max_scroll_x, 0)
            hourly_row = hourly.table.get_row_at(0)
            self.assertEqual(hourly_row[0].plain, '05:00')
            self.assertEqual(hourly_row[1].plain, 'OC')
            self.assertEqual(hourly_row[2].plain, '13°C')
            self.assertEqual(hourly_row[3].plain, '0%')
            self.assertEqual(hourly_row[4].plain, '8mp/h E ←')
            self.assertEqual(
                [(span.start, span.end) for span in hourly_row[2].spans],
                [(0, 4)],
            )
            self.assertEqual(
                [(span.start, span.end) for span in hourly_row[4].spans],
                [(0, 5), (6, 9)],
            )
            self.assertTrue(
                all(
                    'bold' in str(span.style)
                    for cell in hourly_row[1:]
                    for span in cell.spans
                )
            )
            daily = screen.query_one(
                '#dashboard-daily-forecast',
                DashboardDailyForecast,
            )
            self.assertTrue(daily.display)
            self.assertEqual(len(daily.table.rows), 3)
            self.assertEqual(len(daily.table.columns), 5)
            self.assertEqual(
                [column_key.value for column_key in daily.table.columns],
                ['date', 'condition', 'temperature', 'rain', 'wind'],
            )
            self.assertEqual(daily.table.max_scroll_x, 0)

            first_feature = app.focused
            self.assertIsInstance(first_feature, DashboardLocationLabel)
            await pilot.press('right')
            await _settle(pilot)
            second_feature = app.focused
            self.assertIsInstance(second_feature, DashboardLocationLabel)
            self.assertIsNot(second_feature, first_feature)
            await pilot.press('left')
            await _settle(pilot)
            self.assertIs(app.focused, first_feature)

            daily_region = daily.region
            hourly.table.focus()
            await pilot.press('down')
            await _settle(pilot)
            self.assertEqual(daily.region, daily_region)
            self.assertEqual(screen.forecast_panel.scroll_y, 0)
            self.assertEqual(screen.forecast_panel.current_conditions.temp._value, '14')
            self.assertEqual(
                screen.forecast_panel.context_bar.air_quality.hour_index,
                1,
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

    async def test_recent_alert_selection_populates_dashboard_reader(self) -> None:
        app = self._app()
        app.open_alerts_centre_screen = Mock()
        app.load_alert_place_weather = AsyncMock(
            return_value={
                'current': {
                    'temperature_2m': 12,
                    'weather_code': 1,
                    'is_day': 1,
                },
                'current_units': {'temperature_2m': '°C'},
            }
        )
        alert = Alert(
            id='flood-1',
            source='fixture',
            event='Extremely Long River Flood Warning Across Multiple Districts',
            headline='Extremely long river flooding warning',
            severity='Severe',
            area_names=['A deliberately long affected-area label for the Lower Rhine'],
            onset=datetime(2026, 10, 21, 8, tzinfo=UTC),
            expires=datetime(2026, 10, 21, 18, tzinfo=UTC),
            description='River levels are expected to remain high.',
            instruction='Avoid flooded roads.',
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
            True,
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
            self.assertFalse(selected_lines[0].startswith('▸ '))
            self.assertTrue(selected_lines[0].startswith('NEW '))
            new_span = next(
                span
                for span in selected_prompt.spans
                if span.start == 0 and span.end == 3
            )
            self.assertNotIn('reverse', str(new_span.style))
            self.assertIn(' on ', str(new_span.style))
            self.assertIn(
                screen.app.theme_variables['background'],
                str(new_span.style),
            )
            self.assertIn(
                screen.app.theme_variables['primary'],
                str(new_span.style),
            )
            self.assertTrue(
                all(
                    ' on ' not in str(span.style)
                    for span in selected_prompt.spans
                    if span.start >= 4
                )
            )
            self.assertTrue(
                all(len(line) <= panel._text_width() for line in selected_lines)
            )
            self.assertEqual(len(panel.query('#dashboard-alert-preview')), 0)
            self.assertEqual(len(panel.query('#dashboard-alert-open')), 0)
            marker = screen.world_map.query_one(
                '#dashboard-alert-marker',
                DashboardAlertMarker,
            )
            self.assertTrue(marker.display)
            self.assertIs(marker.row, row)
            alert_cell = tuple(marker.offset)
            berlin_candidate = next(
                candidate
                for candidate in screen.world_map._callout_candidates(
                    screen.world_map._current_frame
                )
                if candidate.key == location_key(BERLIN)
            )
            self.assertIn(alert_cell, berlin_candidate.preferred_avoidance)
            detail = screen.alert_detail_panel
            alert_map = detail.query_one('#dashboard-alert-map', CountryAlertsMap)
            self.assertTrue(alert_map.display)
            self.assertEqual(len(alert_map.alert_layers), 1)
            self.assertTrue(alert_map.geometry.selected_alert_polygons)
            self.assertEqual(alert_map.alert_layers[0].key, ('fixture', 'flood-1'))
            self.assertEqual(
                [tab.id for tab in detail.query(Tab) if tab.display],
                [
                    'dashboard-alert-map-tab',
                    'dashboard-alert-document-tab',
                ],
            )
            detail.tabs.active = 'dashboard-alert-document-tab'
            await pilot.pause()
            self.assertTrue(
                detail.query_one(
                    '#dashboard-alert-document',
                    VerticalScroll,
                ).display
            )
            document_text = _rendered(
                detail.query_one('#dashboard-alert-document-body', Static)
            )
            self.assertIn('Extremely long river flooding warning', document_text)
            self.assertIn('Active from ', document_text)
            self.assertIn('River levels are expected to remain high.', document_text)
            self.assertIn('Avoid flooded roads.', document_text)
            screen.update_bulletin(1, (row,))
            await pilot.pause()
            self.assertEqual(
                detail.tabs.active,
                'dashboard-alert-document-tab',
            )
            labels = list(alert_map.query(CountryAlertCityLabel))
            self.assertTrue(labels)
            screen.on_country_alert_settlement_preview_requested(
                CountryAlertSettlementPreviewRequested(label=labels[0])
            )
            await pilot.pause(0.2)
            app.load_alert_place_weather.assert_awaited_once()
            self.assertIn('12°C', labels[0].tooltip.plain)
            await pilot.pause(1.05)
            self.assertIsNone(screen.world_map._alert_pulse_task)
            self.assertFalse(marker.has_class('pulse'))
            app.refresh_dashboard_bulletin()
            app.alert_bulletin.schedule_hard_refresh.assert_called_once_with(
                ['DE', None, 'DE']
            )

            marker.action_activate()
            await pilot.pause()
            app.open_alerts_centre_screen.assert_called_once_with(
                country_code='DE',
                alert_identity=('fixture', 'flood-1'),
            )

            panel.on_option_list_option_selected(
                OptionList.OptionSelected(panel.alert_list, option, 0)
            )
            await pilot.pause()
            self.assertIsNone(panel.selected_row)
            self.assertFalse(marker.display)
            self.assertFalse(detail.tabs.display)
            self.assertIn(
                'Select an alert',
                screen.query_one(
                    '#dashboard-alert-detail-state',
                    Static,
                ).render().plain,
            )

            panel.on_option_list_option_selected(
                OptionList.OptionSelected(panel.alert_list, option, 0)
            )
            await pilot.pause()
            self.assertTrue(marker.display)
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
            self.assertTrue(alert_map.display)
            self.assertFalse(alert_map.geometry.selected_alert_polygons)
            self.assertEqual(
                [tab.id for tab in detail.query(Tab) if tab.display],
                [
                    'dashboard-alert-map-tab',
                    'dashboard-alert-document-tab',
                ],
            )
            screen.update_bulletin(3, ())
            await pilot.pause()
            self.assertIsNone(panel.selected_row)

    async def test_place_hover_is_visual_and_repeated_selection_stays_dashboard(self) -> None:
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
                'Berlin',
                dashboard.query_one('#dashboard-forecast-place', Static).render().plain,
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
            self.assertIs(app.screen, dashboard)
            self.assertEqual(app.location, BERLIN)
            self.assertEqual(dashboard.world_map.selected_location_key, location_key(LONDON))
            app.action_refresh.assert_not_awaited()

            await pilot.press('w')
            await _settle(pilot)
            self.assertIs(app.screen, weather)
            self.assertEqual(app.location, BERLIN)

    async def test_resize_reuses_panels_and_compact_tabs(self) -> None:
        app = self._app()
        async with app.run_test(size=(120, 30)) as pilot:
            await _settle(pilot)
            await pilot.press('b')
            await _settle(pilot)
            screen = app.screen
            self.assertIsInstance(screen, DashboardScreen)
            panels = (
                screen.forecast_panel,
                screen.world_map,
                screen.tropical_panel,
                screen.alert_detail_panel,
                screen.alerts_panel,
            )

            await pilot.resize_terminal(80, 24)
            await _settle(pilot)
            tabs = screen.query_one('#dashboard-pane-tabs', Tabs)
            self.assertTrue(tabs.display)
            self.assertEqual(
                [tab.label.plain for tab in tabs.query(Tab)],
                [
                    'Forecast',
                    'Map',
                    'Tropical',
                    'Selected Alert',
                    'Recent Alerts',
                ],
            )
            self.assertFalse(screen.forecast_panel.display)
            self.assertTrue(screen.world_map.display)
            self.assertFalse(screen.tropical_panel.display)
            self.assertFalse(screen.alert_detail_panel.display)
            self.assertFalse(screen.alerts_panel.display)

            tabs.active = 'dashboard-tab-tropical'
            await _settle(pilot)
            self.assertFalse(screen.world_map.display)
            self.assertTrue(screen.tropical_panel.display)
            self.assertFalse(screen.alert_detail_panel.display)

            tabs.active = 'dashboard-tab-alert-detail'
            await _settle(pilot)
            self.assertFalse(screen.world_map.display)
            self.assertFalse(screen.tropical_panel.display)
            self.assertTrue(screen.alert_detail_panel.display)

            tabs.active = 'dashboard-tab-forecast'
            await _settle(pilot)
            self.assertTrue(screen.forecast_panel.display)
            self.assertFalse(screen.world_map.display)
            compact_daily = screen.forecast_panel.daily_forecast
            self.assertTrue(screen.forecast_panel.hourly_forecast.display)
            self.assertTrue(compact_daily.display)
            self.assertEqual(len(compact_daily.table.rows), 2)
            self.assertEqual(compact_daily.table.max_scroll_x, 0)
            self.assertFalse(screen.forecast_panel.context_bar.display)

            await pilot.resize_terminal(100, 30)
            await _settle(pilot)
            self.assertTrue(tabs.display)
            self.assertTrue(screen.forecast_panel.display)
            self.assertEqual(len(compact_daily.table.rows), 4)
            self.assertFalse(screen.forecast_panel.context_bar.display)

            await pilot.resize_terminal(140, 40)
            await _settle(pilot)
            self.assertFalse(tabs.display)
            self.assertTrue(all(panel.display for panel in panels))
            self.assertEqual(screen.forecast_panel.region.width, 37)
            self.assertEqual(screen.alerts_panel.region.width, 32)
            self.assertEqual(screen.world_map.region.height, 17)
            self.assertEqual(screen.tropical_panel.region.height, 18)
            self.assertEqual(len(compact_daily.table.rows), 6)
            self.assertTrue(screen.forecast_panel.context_bar.display)

            await pilot.resize_terminal(120, 30)
            await _settle(pilot)
            self.assertEqual(
                (
                    screen.forecast_panel,
                    screen.world_map,
                    screen.tropical_panel,
                    screen.alert_detail_panel,
                    screen.alerts_panel,
                ),
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
            self.assertGreater(screen.tropical_panel.region.height, 0)
            self.assertEqual(
                screen.tropical_panel.region.height,
                screen.alert_detail_panel.region.height,
            )
            self.assertEqual(len(screen.forecast_panel.hourly_forecast.table.columns), 5)
            self.assertEqual(screen.forecast_panel.hourly_forecast.table.max_scroll_x, 0)
            self.assertEqual(
                screen.forecast_panel.hourly_forecast.table.cell_padding,
                1,
            )
            self.assertEqual(len(screen.forecast_panel.daily_forecast.table.rows), 6)
            self.assertEqual(len(screen.forecast_panel.daily_forecast.table.columns), 8)
            self.assertEqual(
                [
                    key.value
                    for key in screen.forecast_panel.daily_forecast.table.columns
                ],
                [
                    'date',
                    'condition',
                    'temperature',
                    'rain',
                    'precipitation',
                    'wind',
                    'gust',
                    'wind_direction',
                ],
            )
            self.assertEqual(screen.forecast_panel.daily_forecast.table.max_scroll_x, 0)
            daily_row = screen.forecast_panel.daily_forecast.table.get_row_at(0)
            self.assertEqual(daily_row[6].plain, '(19)')
            hourly = screen.forecast_panel.hourly_forecast
            daily = screen.forecast_panel.daily_forecast
            separators = list(screen.forecast_panel.query('.dashboard-forecast-separator'))
            self.assertEqual(separators[2].region.y, hourly.region.bottom)
            self.assertEqual(daily.region.y, separators[2].region.bottom)
            self.assertEqual(screen.forecast_panel.context_bar.region.y, daily.region.bottom)
            self.assertTrue(
                all(
                    widget.border_title == ''
                    for widget in (
                        screen.forecast_panel.context_bar.location,
                        screen.forecast_panel.context_bar.astronomy,
                        screen.forecast_panel.context_bar.air_quality,
                    )
                )
            )

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
        jma.geometries = {
            'forecast_track': {
                'type': 'LineString',
                'coordinates': [[135.0, 28.0], [137.0, 30.0]],
            }
        }
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
        app.load_tropical_products = AsyncMock(
            return_value=[
                TropicalProduct(
                    kind='advisory',
                    label='Public Advisory',
                    content='Official advisory text',
                ),
                TropicalProduct(
                    kind='discussion',
                    label='Forecast Discussion',
                    content='Official forecast discussion',
                ),
            ]
        )
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
            self.assertEqual(
                label.tooltip.plain,
                'Typhoon NANGKA\nMovement NW at 15 kt\nWind 45 kt',
            )
            self.assertEqual(
                list(dashboard.query('#dashboard-tropical-context')),
                [],
            )

            label.action_activate()
            await _settle(pilot, cycles=8)
            self.assertIs(app.screen, dashboard)
            self.assertEqual(
                dashboard.world_map.selected_tropical_key,
                label.tropical_key,
            )
            self.assertIs(app.focused, label)
            app.load_tropical_products.assert_awaited_once_with(jma)
            detail_tabs = dashboard.tropical_panel.tabs
            self.assertEqual(
                [tab.label.plain for tab in detail_tabs.query('Tab')],
                ['Track and Cone', 'Public Advisory', 'Forecast Discussion'],
            )
            self.assertTrue(dashboard.tropical_panel.track.available)
            detail_tabs.active = 'dashboard-tropical-product-0'
            await _settle(pilot)
            product_body = dashboard.query_one(
                '#dashboard-tropical-product-body',
                VerticalScroll,
            )
            self.assertIn(
                'Official advisory text',
                product_body.query_one(Static).render().plain,
            )

            label.action_activate()
            await _settle(pilot)
            app.load_tropical_products.assert_awaited_once_with(jma)

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
            self.assertIs(
                dashboard.forecast_panel.context_bar.location.location,
                LONDON,
            )
            self.assertIs(
                dashboard.forecast_panel.context_bar.air_quality.location,
                LONDON,
            )
            self.assertIn(
                'London',
                dashboard.query_one('#dashboard-forecast-place', Static).render().plain,
            )

    async def test_late_place_forecast_cannot_replace_newer_selection(self) -> None:
        app = self._app()
        app._forecast_cache.pop(app._forecast_cache_key_for(LONDON))
        app._forecast_cache.pop(app._forecast_cache_key_for(TOKYO))
        london_started = asyncio.Event()
        release_london = asyncio.Event()

        async def fetch(**kwargs):
            if kwargs['lat'] == LONDON.latitude:
                london_started.set()
                try:
                    await release_london.wait()
                except asyncio.CancelledError:
                    await release_london.wait()
            return weather_update(with_warnings=False)

        app.controller.fetch = AsyncMock(side_effect=fetch)

        async with app.run_test(size=(120, 30)) as pilot:
            await _settle(pilot)
            await pilot.press('b')
            await _settle(pilot)
            dashboard = app.screen
            labels = {
                label.location.name: label
                for label in dashboard.world_map.query(DashboardLocationLabel)
            }

            labels['London'].action_select_location()
            await london_started.wait()
            labels['Tokyo'].action_select_location()
            await _settle(pilot, cycles=8)
            self.assertIn(
                'Tokyo',
                dashboard.query_one(
                    '#dashboard-forecast-place',
                    Static,
                ).render().plain,
            )

            release_london.set()
            await _settle(pilot, cycles=8)
            self.assertIn(
                'Tokyo',
                dashboard.query_one(
                    '#dashboard-forecast-place',
                    Static,
                ).render().plain,
            )
            self.assertEqual(app.controller.fetch.await_count, 2)

    async def test_late_tropical_products_cannot_replace_newer_selection(self) -> None:
        app = self._app()
        old = _tropical_observation(
            'old-jma',
            'jma_tropical',
            'OLD',
            classification='Typhoon',
            latitude=20.0,
            longitude=130.0,
        )
        new = _tropical_observation(
            'new-cphc',
            'cphc_gis_central_pacific',
            'NEW',
            classification='Tropical Storm',
            latitude=15.0,
            longitude=-150.0,
        )
        app._tropical_system_cache = (
            app._tropical_system_cache_clock(),
            (
                CanonicalTropicalSystem('OLD', [old]),
                CanonicalTropicalSystem('NEW', [new]),
            ),
        )
        old_started = asyncio.Event()
        release_old = asyncio.Event()

        async def load_products(observation: TropicalSystem):
            if observation is old:
                old_started.set()
                try:
                    await release_old.wait()
                except asyncio.CancelledError:
                    await release_old.wait()
                return [
                    TropicalProduct(
                        kind='advisory',
                        label='Old Advisory',
                        content='Old product',
                    )
                ]
            return [
                TropicalProduct(
                    kind='advisory',
                    label='New Advisory',
                    content='New product',
                )
            ]

        app.load_tropical_products = AsyncMock(side_effect=load_products)

        async with app.run_test(size=(180, 45)) as pilot:
            await _settle(pilot)
            await pilot.press('b')
            await _settle(pilot)
            dashboard = app.screen
            labels = {
                label.system.name: label
                for label in dashboard.world_map.query(DashboardTropicalLabel)
            }

            labels['OLD'].action_activate()
            await old_started.wait()
            labels['NEW'].action_activate()
            await _settle(pilot, cycles=8)
            self.assertEqual(
                [tab.label.plain for tab in dashboard.tropical_panel.tabs.query('Tab')],
                ['Track and Cone', 'Forecast', 'New Advisory'],
            )

            release_old.set()
            await _settle(pilot, cycles=8)
            self.assertEqual(
                [tab.label.plain for tab in dashboard.tropical_panel.tabs.query('Tab')],
                ['Track and Cone', 'Forecast', 'New Advisory'],
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
