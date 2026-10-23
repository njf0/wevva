"""Mounted checks for the persistent unified dashboard."""

from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime
from io import StringIO
from unittest.mock import AsyncMock, Mock, patch

from rich.console import Console
from rich.text import Text
from textual.containers import Container, VerticalScroll
from textual.widgets import OptionList, Static, Tab, Tabs
from wevva_warnings import (
    Alert,
    CanonicalTropicalSystem,
    TropicalProduct,
    TropicalSystem,
)
from wevva_warnings.registry import get_source

from tests.weather_fixtures import warning_alerts, weather_update
from wevva.app import Wevva
from wevva.conditions import get_condition
from wevva.config import location_key
from wevva.location_metadata import LocationMetadata
from wevva.messages import PlaceSelected
from wevva.screens.dashboard_screen import (
    DashboardScreen,
    DashboardWeatherAlertsPanel,
)
from wevva.services.alert_bulletin import BulletinAlert
from wevva.screens.weather_screen import WeatherScreen
from wevva.widgets.dashboard_daily_forecast import DashboardDailyForecast
from wevva.widgets.dashboard_world_map import (
    DashboardAlertMarker,
    DashboardIncomingAlertMarker,
    DashboardLocationLabel,
    DashboardTropicalLabel,
)
from wevva.widgets.dashboard_hourly_forecast import DashboardHourlyForecast
from wevva.widgets.country_alerts_map import (
    CountryAlertCityLabel,
    CountryAlertSettlementPreviewRequested,
    CountryAlertSettlementSelected,
    CountryAlertsMap,
)
from wevva.widgets.saved_locations import SavedLocationWeatherSummary
from wevva.widgets.tropical_track import TropicalFixLabel


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
            start_on_dashboard=False,
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
        app.load_dashboard_alerts = AsyncMock(return_value=[])
        app._tropical_system_cache = (
            app._tropical_system_cache_clock(),
            (),
        )
        return app

    async def test_location_warnings_reuse_tabs_with_only_a_top_rule(self) -> None:
        app = self._app()
        release_london_alerts = asyncio.Event()

        async def load_dashboard_alerts(location):
            if location.name == 'Berlin':
                return warning_alerts()
            await release_london_alerts.wait()
            return []

        app.load_dashboard_alerts = AsyncMock(side_effect=load_dashboard_alerts)
        app.open_alerts_centre_screen = Mock()
        async with app.run_test(size=(120, 30)) as pilot:
            await _settle(pilot, 8)
            await pilot.press('b')
            await _settle(pilot, 8)

            screen = app.screen
            self.assertIsInstance(screen, DashboardScreen)
            warning_panel = screen.query_one(DashboardWeatherAlertsPanel)
            self.assertTrue(warning_panel.display)
            self.assertEqual(len(warning_panel.tabs.query(Tab)), 2)
            self.assertEqual(warning_panel.border_title, '')
            self.assertEqual(warning_panel.styles.border_top[0], 'solid')
            self.assertEqual(warning_panel.styles.border_left[0], '')
            self.assertEqual(warning_panel.styles.border_right[0], '')
            self.assertEqual(warning_panel.styles.border_bottom[0], '')
            self.assertEqual(warning_panel.region.height, 5)
            self.assertLess(
                warning_panel.region.y,
                screen.forecast_panel.current_conditions.region.y,
            )
            self.assertLessEqual(
                warning_panel.region.bottom,
                screen.forecast_panel.content_region.bottom,
            )
            self.assertFalse(screen.forecast_panel.context_bar.display)

            await pilot.resize_terminal(160, 42)
            await _settle(pilot)
            self.assertTrue(warning_panel.display)
            self.assertTrue(screen.forecast_panel.context_bar.display)
            self.assertLessEqual(
                screen.forecast_panel.context_bar.region.bottom,
                screen.forecast_panel.content_region.bottom,
            )

            heading = screen.query_one(
                '#dashboard-forecast-place',
                Static,
            ).render()
            self.assertEqual(heading.plain, 'Berlin\nGermany')
            country_span = heading.spans[-1]
            self.assertEqual(
                heading.plain[country_span.start : country_span.end],
                'Germany',
            )
            self.assertIn('dim', str(country_span.style))
            self.assertIn('not bold', str(country_span.style))

            warning_panel.refresh_appearance()
            warning_panel.body.focus()
            await pilot.press('enter')
            await _settle(pilot)
            self.assertIs(app.screen, screen)
            app.open_alerts_centre_screen.assert_called_once_with(
                country_code='DE',
                alert_identity=('nws', 'fixture-heat'),
            )

            london = next(
                label
                for label in screen.world_map.query(DashboardLocationLabel)
                if label.location.name == 'London'
            )
            london.action_select_location()
            await _settle(pilot)
            self.assertFalse(screen.forecast_panel.location_alerts.display)
            self.assertEqual(
                len(screen.forecast_panel.location_alerts.children),
                0,
            )

    async def test_dashboard_alert_loader_combines_catalogue_and_native_results(self) -> None:
        app = self._app()
        del app.load_dashboard_alerts
        catalogue_alert = warning_alerts()[0]
        native_alert = Alert(
            id='native-point',
            source='fixture',
            event='Wind Warning',
            headline='Wind Warning',
            severity='Moderate',
        )
        app.country_alerts_service.get_alerts = AsyncMock(
            return_value=[catalogue_alert]
        )
        matched = [catalogue_alert, native_alert]

        with (
            patch(
                'wevva.app.get_native_point_alerts_async',
                new=AsyncMock(return_value=([native_alert], True)),
            ) as native_loader,
            patch(
                'wevva.app.match_alert_candidates_async',
                new=AsyncMock(return_value=matched),
            ) as matcher,
        ):
            alerts = await app.load_dashboard_alerts(BERLIN)

        self.assertEqual(alerts, matched)
        app.country_alerts_service.get_alerts.assert_awaited_once_with(
            'DE',
            warning_language='auto',
        )
        native_loader.assert_awaited_once_with(
            BERLIN.latitude,
            BERLIN.longitude,
            'DE',
            'auto',
        )
        matcher.assert_awaited_once_with(
            [catalogue_alert],
            [native_alert],
            BERLIN.latitude,
            BERLIN.longitude,
        )

    async def test_bulletin_update_ignores_an_incomplete_dashboard_tree(self) -> None:
        app = self._app()
        async with app.run_test(size=(120, 30)) as pilot:
            await _settle(pilot)
            await pilot.press('b')
            await _settle(pilot)

            screen = app.screen
            self.assertIsInstance(screen, DashboardScreen)
            generation = screen._bulletin_generation
            await screen.alerts_panel.remove()
            await _settle(pilot)

            app._on_bulletin_updated(generation + 1)
            self.assertEqual(screen._bulletin_generation, generation)

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
            self.assertIsNotNone(screen._time_refresh_timer)
            self.assertIn(
                'No active tropical systems',
                screen.query_one(
                    '#dashboard-tropical-detail-state',
                    Static,
                ).render().plain,
            )
            screen.tropical_panel.show_overview(None)
            tropical_content = screen.query_one(
                '#dashboard-tropical-content',
                Container,
            )
            self.assertFalse(screen.tropical_panel.loading)
            self.assertTrue(tropical_content.loading)
            self.assertEqual(
                screen.tropical_panel.border_title,
                'Tropical System',
            )
            screen.tropical_panel.show_overview(())
            self.assertFalse(tropical_content.loading)
            self.assertTrue(
                screen.query_one('#dashboard-alerts-empty', Static).display
            )
            self.assertEqual(
                screen.alerts_panel.border_title,
                'Severe Weather Alert Bulletin',
            )
            self.assertEqual(
                screen.query_one(
                    '#dashboard-alerts-empty',
                    Static,
                ).render().plain,
                'New weather alerts will display here.',
            )
            map_locations = list(screen.world_map.query(DashboardLocationLabel))
            self.assertEqual(
                {label.location.name for label in map_locations},
                {'London', 'Tokyo'},
            )
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
            self.assertIsNotNone(
                hourly.table.get_component_rich_style(
                    'datatable--even-row'
                ).bgcolor
            )
            self.assertIsNotNone(
                daily.table.get_component_rich_style(
                    'datatable--even-row'
                ).bgcolor
            )

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
            incoming = list(
                screen.world_map.query(DashboardIncomingAlertMarker)
            )
            self.assertEqual(len(incoming), 1)
            self.assertTrue(incoming[0].display)
            self.assertTrue(marker.display)
            self.assertEqual(marker.render().plain, '!')
            self.assertIs(marker.row, row)
            alert_cell = tuple(marker.offset)
            saved_candidate = next(
                candidate
                for candidate in screen.world_map._callout_candidates(
                    screen.world_map._current_frame
                )
                if candidate.key == location_key(LONDON)
            )
            self.assertIn(alert_cell, saved_candidate.preferred_avoidance)
            detail = screen.alert_detail_panel
            self.assertEqual(
                detail.border_title,
                'Extremely Long River Flood Warning Across Multiple Districts',
            )
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
            selected_place = labels[0].place
            app.controller.fetch = AsyncMock(
                return_value=weather_update(with_warnings=False)
            )
            screen.on_country_alert_settlement_selected(
                CountryAlertSettlementSelected(place=selected_place)
            )
            await _settle(pilot, cycles=8)
            self.assertIs(app.screen, screen)
            self.assertEqual(app.location, BERLIN)
            self.assertIn(
                selected_place.name,
                screen.query_one(
                    '#dashboard-forecast-place',
                    Static,
                ).render().plain,
            )
            screen.on_country_alert_settlement_preview_requested(
                CountryAlertSettlementPreviewRequested(label=labels[0])
            )
            await pilot.pause(0.2)
            app.load_alert_place_weather.assert_awaited_once()
            self.assertIn('12°C', labels[0].tooltip.plain)
            await pilot.pause(1.05)
            self.assertIsNotNone(
                screen.world_map._incoming_alert_pulse_task
            )
            app.refresh_dashboard_bulletin()
            app.alert_bulletin.schedule_hard_refresh.assert_called_once_with(
                ['DE', 'DE', 'DE']
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
            self.assertIsNotNone(
                screen.world_map._incoming_alert_pulse_task
            )
            self.assertFalse(marker.has_class('pulse'))
            self.assertFalse(detail.tabs.display)
            self.assertEqual(detail.border_title, 'Selected Alert')
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
            self.assertIsNone(screen.world_map._incoming_alert_pulse_task)
            await pilot.press('b')
            await _settle(pilot)
            self.assertIs(app.screen, screen)
            self.assertIs(panel.selected_row, row)
            self.assertTrue(marker.display)
            self.assertIsNone(screen.world_map._incoming_alert_pulse_task)
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

    async def test_new_alert_batch_flashes_all_cells_at_highest_severity(self) -> None:
        app = self._app()
        same_area = {
            'type': 'Polygon',
            'coordinates': [
                [[-1, 50], [1, 50], [1, 52], [-1, 52], [-1, 50]]
            ],
        }
        other_area = {
            'type': 'Polygon',
            'coordinates': [
                [[138, 34], [141, 34], [141, 37], [138, 37], [138, 34]]
            ],
        }
        rows = (
            BulletinAlert(
                'GB',
                Alert(
                    id='rain',
                    source='fixture',
                    event='Rain Warning',
                    headline='Rain warning',
                    severity='Moderate',
                    geometry=same_area,
                ),
                datetime.now(UTC),
                True,
            ),
            BulletinAlert(
                'GB',
                Alert(
                    id='wind',
                    source='fixture',
                    event='Wind Warning',
                    headline='Wind warning',
                    severity='Extreme',
                    geometry=same_area,
                ),
                datetime.now(UTC),
                True,
            ),
            BulletinAlert(
                'JP',
                Alert(
                    id='snow',
                    source='fixture',
                    event='Snow Warning',
                    headline='Snow warning',
                    severity='Minor',
                    geometry=other_area,
                ),
                datetime.now(UTC),
                True,
            ),
        )

        async with app.run_test(size=(120, 30)) as pilot:
            await _settle(pilot)
            await pilot.press('b')
            await _settle(pilot)
            screen = app.screen
            self.assertIsInstance(screen, DashboardScreen)

            screen.update_bulletin(1, rows)
            await _settle(pilot)

            markers = [
                marker
                for marker in screen.world_map.query(
                    DashboardIncomingAlertMarker
                )
                if marker.display
            ]
            self.assertEqual(len(markers), 2)
            self.assertEqual({marker.count for marker in markers}, {1, 2})
            grouped = next(marker for marker in markers if marker.count == 2)
            self.assertEqual(grouped.row.alert.id, 'wind')
            self.assertIsNotNone(
                screen.world_map._incoming_alert_pulse_task
            )
            pulse_task = screen.world_map._incoming_alert_pulse_task

            screen.update_bulletin(2, rows)
            await _settle(pilot)
            self.assertIs(screen.world_map._incoming_alert_pulse_task, pulse_task)

            screen.world_map.set_selected_alert(rows[0])
            await pilot.pause()
            self.assertFalse(screen.world_map.alert_marker.has_class('pulse'))
            self.assertIsNotNone(
                screen.world_map._incoming_alert_pulse_task
            )

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

    async def test_place_selection_preserves_callout_direction_and_layout(self) -> None:
        app = self._app()
        async with app.run_test(size=(120, 30)) as pilot:
            await _settle(pilot)
            await pilot.press('b')
            await _settle(pilot)

            dashboard = app.screen
            self.assertIsInstance(dashboard, DashboardScreen)
            tokyo = next(
                label
                for label in dashboard.world_map.query(DashboardLocationLabel)
                if label.location.name == 'Tokyo'
            )
            self.assertTrue(tokyo.label_text.endswith(' •'))
            placements_before = dashboard.world_map.placements

            tokyo.action_select_location()
            await _settle(pilot)

            self.assertTrue(tokyo.has_class('selected-place'))
            self.assertTrue(tokyo.label_text.endswith(' •'))
            self.assertEqual(dashboard.world_map.placements, placements_before)
            self.assertTrue(
                all(
                    label.display
                    for label in dashboard.world_map.query(DashboardLocationLabel)
                )
            )

    async def test_saved_weather_location_is_selected_when_dashboard_opens(self) -> None:
        app = self._app()
        app.location = LONDON
        async with app.run_test(size=(120, 30)) as pilot:
            await _settle(pilot)

            await pilot.press('b')
            await _settle(pilot)

            dashboard = app.screen
            self.assertIsInstance(dashboard, DashboardScreen)
            london = next(
                label
                for label in dashboard.world_map.query(DashboardLocationLabel)
                if label.location.name == 'London'
            )
            self.assertIsNone(dashboard._selected_location)
            self.assertEqual(
                dashboard.world_map.selected_location_key,
                location_key(LONDON),
            )
            self.assertTrue(london.has_class('selected-place'))

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

            with patch.object(
                screen.forecast_panel.daily_forecast.table,
                '_update_display',
                wraps=screen.forecast_panel.daily_forecast.table._update_display,
            ) as update_daily:
                await pilot.resize_terminal(80, 24)
                await _settle(pilot)
                self.assertEqual(update_daily.call_count, 1)
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
                TropicalProduct(
                    kind='forecast',
                    label='Forecast',
                    data={
                        'points': [
                            {
                                'latitude': 30.0,
                                'longitude': 137.0,
                                'lead_hours': 24,
                            }
                        ]
                    },
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
            self.assertIn('★', label.label_text)
            self.assertNotIn('•', label.label_text)
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
            self.assertEqual(
                dashboard.tropical_panel.border_title,
                'Typhoon NANGKA',
            )
            self.assertIs(app.focused, label)
            app.load_tropical_products.assert_awaited_once_with(jma)
            detail_tabs = dashboard.tropical_panel.tabs
            self.assertEqual(
                [tab.label.plain for tab in detail_tabs.query('Tab')],
                ['Track and Cone', 'Public Advisory', 'Forecast Discussion'],
            )
            self.assertTrue(dashboard.tropical_panel.track.available)
            self.assertEqual(
                [
                    fix._body_text
                    for fix in dashboard.tropical_panel.track.query(TropicalFixLabel)
                ],
                ['Now', '24h'],
            )
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

            storm_place = LocationMetadata(
                name='Storm City',
                country_code='JP',
                latitude=27.5,
                longitude=134.5,
            )
            app.controller.fetch = AsyncMock(
                return_value=weather_update(with_warnings=False)
            )
            dashboard.post_message(PlaceSelected(location=storm_place))
            await _settle(pilot, cycles=8)
            self.assertIs(app.screen, dashboard)
            self.assertEqual(app.location, BERLIN)
            self.assertEqual(
                dashboard.query_one(
                    '#dashboard-forecast-place',
                    Static,
                ).render().plain,
                'Storm City\nJapan',
            )
            self.assertNotIn(
                'Storm City',
                {
                    place.location.name
                    for place in dashboard.world_map.query(DashboardLocationLabel)
                },
            )

    async def test_selected_place_loads_preview_without_becoming_active(self) -> None:
        app = self._app()
        app._forecast_cache.pop(app._forecast_cache_key_for(LONDON))
        app._saved_location_weather_summaries[location_key(LONDON)] = (
            SavedLocationWeatherSummary(error=True)
        )
        event = weather_update(with_warnings=False)
        forecast_started = asyncio.Event()
        release_forecast = asyncio.Event()

        async def fetch_forecast(**_kwargs):
            forecast_started.set()
            await release_forecast.wait()
            return event

        app.controller.fetch = AsyncMock(side_effect=fetch_forecast)

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
            self.assertIn('--', london.label_text)
            show_forecast = Mock(
                wraps=dashboard.forecast_panel.show_forecast,
            )
            dashboard.forecast_panel.show_forecast = show_forecast
            rebuild_hourly = Mock(
                wraps=dashboard.forecast_panel.hourly_forecast._rebuild,
            )
            dashboard.forecast_panel.hourly_forecast._rebuild = rebuild_hourly

            london.action_select_location()
            await forecast_started.wait()
            forecast_status = dashboard.query_one(
                '#dashboard-forecast-status',
                Static,
            )
            self.assertFalse(dashboard.forecast_panel.loading)
            self.assertTrue(forecast_status.loading)
            self.assertEqual(
                dashboard.forecast_panel.border_title,
                'Location Forecast',
            )

            release_forecast.set()
            await _settle(pilot, cycles=8)

            self.assertEqual(app.location, BERLIN)
            self.assertFalse(dashboard.forecast_panel.loading)
            self.assertFalse(forecast_status.loading)
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
            self.assertNotIn('--', london.label_text)
            self.assertEqual(
                app.saved_location_weather_summary(LONDON).temperature,
                13,
            )
            self.assertEqual(show_forecast.call_count, 1)
            self.assertEqual(rebuild_hourly.call_count, 1)

            app._update_saved_location_weather(LONDON, _summary(18))
            await _settle(pilot)
            self.assertEqual(show_forecast.call_count, 1)
            self.assertIn('18', london.label_text)

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

    async def test_stale_storm_click_keeps_detail_until_refresh_is_complete(self) -> None:
        app = self._app()
        old = _tropical_observation(
            'nangka-jma',
            'jma_tropical',
            'NANGKA',
            classification='Typhoon',
            latitude=20.0,
            longitude=130.0,
        )
        fresh = _tropical_observation(
            'nangka-jma',
            'jma_tropical',
            'NANGKA',
            classification='Super Typhoon',
            latitude=24.0,
            longitude=134.0,
        )
        old_system = CanonicalTropicalSystem('NANGKA', [old])
        fresh_system = CanonicalTropicalSystem('NANGKA', [fresh])
        now = [1_000.0]
        app._tropical_system_cache_clock = lambda: now[0]
        app._tropical_system_cache = (now[0], (old_system,))
        fresh_products_started = asyncio.Event()
        release_fresh_products = asyncio.Event()

        async def load_products(observation: TropicalSystem):
            if observation is old:
                return [
                    TropicalProduct(
                        kind='advisory',
                        label='Old Advisory',
                        content='Old product',
                    )
                ]
            fresh_products_started.set()
            await release_fresh_products.wait()
            return [
                TropicalProduct(
                    kind='advisory',
                    label='Fresh Advisory',
                    content='Fresh product',
                )
            ]

        app.load_tropical_products = AsyncMock(side_effect=load_products)
        tropical_lookup = AsyncMock(return_value=([fresh_system], True))

        with patch(
            'wevva.app.get_tropical_system_candidates_async',
            new=tropical_lookup,
        ):
            async with app.run_test(size=(180, 45)) as pilot:
                await _settle(pilot)
                await pilot.press('b')
                await _settle(pilot)
                dashboard = app.screen
                label = dashboard.world_map.query_one(DashboardTropicalLabel)

                label.action_activate()
                await _settle(pilot, cycles=8)
                self.assertIs(dashboard.tropical_panel._observation, old)
                self.assertEqual(
                    [
                        tab.label.plain
                        for tab in dashboard.tropical_panel.tabs.query('Tab')
                    ],
                    ['Track and Cone', 'Old Advisory'],
                )

                now[0] += app.TROPICAL_SYSTEM_CACHE_TTL_SECONDS
                label.action_activate()
                await fresh_products_started.wait()
                tropical_content = dashboard.query_one(
                    '#dashboard-tropical-content',
                    Container,
                )
                self.assertFalse(dashboard.tropical_panel.loading)
                self.assertTrue(tropical_content.loading)
                self.assertEqual(
                    dashboard.tropical_panel.border_title,
                    'Typhoon NANGKA',
                )
                refresh_task = dashboard._tropical_selection_refresh_task
                label.action_activate()
                await pilot.pause()
                self.assertIs(
                    dashboard._tropical_selection_refresh_task,
                    refresh_task,
                )
                self.assertIs(dashboard.tropical_panel._observation, old)
                self.assertEqual(
                    [
                        tab.label.plain
                        for tab in dashboard.tropical_panel.tabs.query('Tab')
                    ],
                    ['Track and Cone', 'Old Advisory'],
                )

                release_fresh_products.set()
                await _settle(pilot, cycles=8)
                self.assertIs(app.screen, dashboard)
                self.assertFalse(dashboard.tropical_panel.loading)
                self.assertFalse(tropical_content.loading)
                self.assertIs(dashboard.tropical_panel._observation, fresh)
                self.assertEqual(
                    [
                        tab.label.plain
                        for tab in dashboard.tropical_panel.tabs.query('Tab')
                    ],
                    ['Track and Cone', 'Fresh Advisory'],
                )
                refreshed_label = dashboard.world_map.query_one(
                    DashboardTropicalLabel
                )
                self.assertIs(refreshed_label.observation, fresh)
                tropical_lookup.assert_awaited_once_with()

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

            with patch.object(
                dashboard.forecast_panel.hourly_forecast,
                'update_forecast',
                wraps=dashboard.forecast_panel.hourly_forecast.update_forecast,
            ) as update_hourly:
                await pilot.press('w')
                await _settle(pilot)
                self.assertIs(app.screen, weather)
                self.assertEqual(app.location, BERLIN)
                app.action_refresh.assert_not_awaited()

                await pilot.press('b')
                await _settle(pilot)
                self.assertEqual(update_hourly.call_count, 0)
            self.assertIs(app.screen, dashboard)
            self.assertEqual(dashboard.world_map.selected_location_key, location_key(TOKYO))


if __name__ == '__main__':
    unittest.main()
