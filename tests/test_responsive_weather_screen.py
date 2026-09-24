"""Rendered checks for the budget-driven operational weather screen."""

from __future__ import annotations

from io import StringIO
import unittest

from rich.console import Console
from textual.app import App
from textual.coordinate import Coordinate

from tests.weather_fixtures import chicago_location, weather_update
from wevva.layout import (
    CurrentDensity,
    DailyColumn,
    HourlyRow,
    daily_column_widths,
    daily_table_width,
)
from wevva.screens.weather_screen import WeatherScreen
from wevva.widgets.daily_forecast import DailyForecast
from wevva.widgets.weather_alerts import (
    WeatherAlertDetailsPanel,
    WeatherAlertSummary,
    WeatherAlertsModal,
    WeatherAlertsPanel,
)
from wevva.widgets.weather_widget import WeatherWidget


class _ResponsiveWeatherApp(App):
    # Match the real application's general table rule.  HourlyForecast must
    # retain its full-width scrolling viewport despite this higher-level CSS.
    CSS = 'DataTable { width: auto; }'

    def __init__(self) -> None:
        super().__init__()
        self.location = chicago_location()
        self.forecast_metadata = None
        self.saved_locations = []
        self.emoji_enabled = False
        self.temperature_unit = 'celsius'

    def on_mount(self) -> None:
        self.push_screen(WeatherScreen())


async def _load_weather(app: _ResponsiveWeatherApp, pilot, *, warnings: bool) -> WeatherScreen:
    await pilot.pause()
    screen = app.screen
    assert isinstance(screen, WeatherScreen)
    update = weather_update(with_warnings=warnings)
    app.forecast_metadata = update.metadata
    await screen.on_weather_updated(update)
    for _ in range(4):
        await pilot.pause()
    return screen


class ResponsiveWeatherScreenTests(unittest.IsolatedAsyncioTestCase):
    async def test_warning_baseline_exactly_fills_eighty_by_twenty_four(self) -> None:
        app = _ResponsiveWeatherApp()
        async with app.run_test(size=(80, 24)) as pilot:
            screen = await _load_weather(app, pilot, warnings=True)
            budget = screen._layout_budget
            assert budget is not None

            self.assertEqual(budget.current_density, CurrentDensity.SMALLEST)
            self.assertEqual(budget.used_rows, 22)
            self.assertEqual(screen.main_panel.region.height, 22)
            self.assertEqual(screen.main_panel.max_scroll_y, 0)
            self.assertEqual(screen.main_panel.styles.overflow_y, 'hidden')
            self.assertTrue(screen.summary_row.display)
            self.assertEqual(screen.summary_row.region.height, 4)
            self.assertEqual(screen.weather_summary.region.height, 3)
            self.assertEqual(screen.weather_summary.border_title, 'Weather Summary')
            self.assertEqual(screen.warnings_row.region.height, 4)
            self.assertEqual(
                screen.weather_warnings.region.height,
                3,
            )
            self.assertEqual(screen.current_weather.region.height, 3)
            self.assertEqual(screen.current_weather.detail.row_count, 1)
            self.assertEqual(
                screen.current_weather.detail.get_cell_at(Coordinate(0, 0)).plain,
                'Humid.',
            )

            hourly = screen.hourly_forecast
            self.assertEqual(hourly.region.height, 8)
            self.assertEqual(hourly.table.row_count, 3)
            self.assertEqual(len(hourly.table.columns), 24)
            self.assertEqual(
                tuple(row.value for row in hourly.table.rows),
                ('emoji', 'temp_values', 'footer'),
            )
            self.assertGreater(hourly.table.max_scroll_x, 0)
            self.assertEqual(hourly.table.styles.scrollbar_size_horizontal, 0)
            indicator = hourly.scroll_indicator.render().plain
            self.assertTrue(indicator.startswith('◀'))
            self.assertTrue(indicator.endswith('▶'))
            self.assertIn('━', indicator)
            self.assertEqual(hourly.border_subtitle, '←/→ scroll')

            daily = screen.query_one(DailyForecast)
            self.assertFalse(screen.daily_forecast.display)
            self.assertEqual(daily.daily.row_count, 0)
            self.assertEqual(len(daily.daily.columns), 0)
            self.assertEqual(
                screen.next_24_hours.region.bottom,
                screen.main_panel.content_region.bottom,
            )
            self.assertFalse(screen.location_map.display)
            self.assertFalse(screen.bottom_info_bar.display)

    async def test_no_warning_releases_one_row_without_page_scroll(self) -> None:
        app = _ResponsiveWeatherApp()
        async with app.run_test(size=(80, 24)) as pilot:
            screen = await _load_weather(app, pilot, warnings=False)
            budget = screen._layout_budget
            assert budget is not None

            self.assertEqual(budget.used_rows, 22)
            self.assertTrue(screen.summary_row.display)
            self.assertEqual(screen.summary_row.region.height, 4)
            self.assertEqual(screen.weather_summary.region.height, 3)
            self.assertEqual(screen.weather_summary.border_title, 'Weather Summary')
            self.assertFalse(screen.warnings_row.display)
            self.assertEqual(budget.current_density, CurrentDensity.SMALL)
            self.assertEqual(screen.current_weather.region.height, 5)
            self.assertEqual(screen.hourly_forecast.table.row_count, 5)
            self.assertFalse(screen.daily_forecast.display)
            self.assertEqual(screen.query_one(DailyForecast).daily.row_count, 0)
            self.assertEqual(screen.main_panel.max_scroll_y, 0)
            self.assertLessEqual(
                screen.next_24_hours.region.bottom,
                screen.main_panel.content_region.bottom,
            )

    async def test_smallest_current_tiles_are_one_unabbreviated_line(self) -> None:
        app = _ResponsiveWeatherApp()
        async with app.run_test(size=(73, 24)) as pilot:
            screen = await _load_weather(app, pilot, warnings=True)
            budget = screen._layout_budget
            assert budget is not None

            self.assertEqual(budget.current_density, CurrentDensity.SMALLEST)
            self.assertEqual(budget.current_height, 3)

            temperature = screen.query_one('#ww-temp', WeatherWidget)
            wind = screen.query_one('#ww-wind', WeatherWidget)
            temp_value = temperature.query_one('#compact-value').render().plain
            temp_lower = temperature.query_one('#lower').render().plain
            wind_value = wind.query_one('#compact-value').render().plain
            wind_lower = wind.query_one('#lower').render().plain

            self.assertNotIn('(f', temp_value)
            self.assertNotIn('(g', wind_value)
            self.assertTrue(temp_lower.startswith('Feels '))
            self.assertTrue(wind_lower.startswith('Gusts '))
            self.assertFalse(temperature.query_one('#lower').display)
            self.assertFalse(temperature.query_one('#spacer').display)

    async def test_wide_hourly_columns_remain_compact(self) -> None:
        app = _ResponsiveWeatherApp()
        async with app.run_test(size=(140, 24)) as pilot:
            screen = await _load_weather(app, pilot, warnings=True)
            hourly = screen.hourly_forecast

            self.assertEqual(hourly._column_widths, (4,) * 24)
            self.assertEqual(
                sum(hourly._column_widths),
                hourly.table.content_region.width,
            )
            self.assertEqual(hourly.table.max_scroll_x, 0)
            self.assertEqual(hourly.scroll_indicator.render().plain, '')
            self.assertEqual(hourly.border_subtitle, '')

    async def test_very_wide_hourly_columns_stop_at_readable_width(self) -> None:
        app = _ResponsiveWeatherApp()
        async with app.run_test(size=(240, 24)) as pilot:
            screen = await _load_weather(app, pilot, warnings=True)
            hourly = screen.hourly_forecast

            self.assertEqual(max(hourly._column_widths), 4)
            self.assertEqual(sum(hourly._column_widths), 24 * 4)
            self.assertEqual(
                sum(hourly._column_widths),
                hourly.table.content_region.width,
            )
            self.assertEqual(hourly.table.max_scroll_x, 0)
            self.assertEqual(hourly.scroll_indicator.render().plain, '')

    async def test_wide_forecast_frames_are_content_sized_and_centred(self) -> None:
        app = _ResponsiveWeatherApp()
        async with app.run_test(size=(140, 40)) as pilot:
            screen = await _load_weather(app, pilot, warnings=True)
            hourly = screen.hourly_forecast
            daily = screen.query_one(DailyForecast)
            daily_wrap = daily.query_one('#forecast-tabs')
            budget = screen._layout_budget
            assert budget is not None

            self.assertEqual(screen.weather_summary.region.width, 98)
            self.assertEqual(screen.weather_warnings.region.width, 98)
            self.assertEqual(screen.current_weather.region.width, 98)
            self.assertEqual(
                screen.current_weather.detail.get_cell_at(Coordinate(0, 0)).plain,
                'Humidity',
            )
            self.assertEqual(
                tuple(
                    column.width
                    for column in screen.current_weather.detail.columns.values()
                ),
                (11, 6),
            )
            main_center = screen.main_panel.content_region.x + (
                screen.main_panel.content_region.width // 2
            )
            for widget in (
                screen.weather_summary,
                screen.weather_warnings,
                screen.current_weather,
            ):
                self.assertLessEqual(abs(widget.region.center[0] - main_center), 1)

            self.assertEqual(hourly.region.width, 98)
            hourly_left = hourly.region.x - screen.next_24_hours.content_region.x
            hourly_right = (
                screen.next_24_hours.content_region.right - hourly.region.right
            )
            self.assertLessEqual(abs(hourly_left - hourly_right), 1)

            expected_daily_width = daily_table_width(budget.daily_columns) + 2
            self.assertEqual(daily.region.width, expected_daily_width)
            self.assertEqual(daily_wrap.region.width, expected_daily_width)
            self.assertEqual(
                tuple(column.width for column in daily.daily.columns.values()),
                daily_column_widths(budget.daily_columns),
            )
            self.assertIn(DailyColumn.WIND_DIRECTION, budget.daily_columns)
            self.assertNotIn(DailyColumn.GUST, budget.daily_columns)
            self.assertEqual(
                daily_column_widths(budget.daily_columns),
                (13, 31, 8, 5, 7, 13, 5, 7, 7),
            )
            self.assertEqual(
                daily.daily.get_cell_at(Coordinate(0, 0)).plain,
                'Monday 23',
            )
            self.assertEqual(
                daily.daily.get_cell_at(Coordinate(0, 1)).plain,
                'Overcast',
            )
            daily_left = daily.region.x - screen.daily_forecast.content_region.x
            daily_right = screen.daily_forecast.content_region.right - daily.region.right
            self.assertLessEqual(abs(daily_left - daily_right), 1)

    async def test_tall_forecast_stack_is_vertically_centred(self) -> None:
        app = _ResponsiveWeatherApp()
        async with app.run_test(size=(140, 60)) as pilot:
            screen = await _load_weather(app, pilot, warnings=True)

            top_gap = screen.summary_row.region.y - screen.main_panel.content_region.y
            bottom_gap = (
                screen.main_panel.content_region.bottom
                - screen.daily_forecast.region.bottom
            )
            self.assertLessEqual(abs(top_gap - bottom_gap), 1)
            self.assertEqual(screen.main_panel.max_scroll_y, 0)

            daily = screen.query_one(DailyForecast)
            visible = daily.daily._visible_columns
            self.assertLess(
                visible.index(DailyColumn.PRECIPITATION),
                visible.index(DailyColumn.WIND),
            )

    async def test_hour_selection_and_horizontal_position_survive_resize(self) -> None:
        app = _ResponsiveWeatherApp()
        async with app.run_test(size=(80, 24)) as pilot:
            screen = await _load_weather(app, pilot, warnings=True)
            hourly = screen.hourly_forecast
            initial_indicator = hourly.scroll_indicator.render().plain
            hourly.table.focus()
            hourly.table.move_cursor(column=23, animate=False, scroll=True)
            await pilot.pause()

            selected_index = hourly._col_indices[hourly.table.cursor_column]
            self.assertEqual(selected_index, 23)
            self.assertGreater(hourly.table.scroll_x, 0)
            self.assertNotEqual(
                hourly.scroll_indicator.render().plain,
                initial_indicator,
            )

            await pilot.resize_terminal(100, 30)
            for _ in range(3):
                await pilot.pause()

            self.assertEqual(
                hourly._col_indices[hourly.table.cursor_column],
                selected_index,
            )
            self.assertEqual(screen.current_weather.hour_index, selected_index)
            self.assertIn(HourlyRow.TIME, screen._layout_budget.hourly_rows)
            self.assertEqual(screen.main_panel.max_scroll_y, 0)

    async def test_warning_summary_opens_tabbed_scrolling_modal(self) -> None:
        app = _ResponsiveWeatherApp()
        async with app.run_test(size=(80, 24)) as pilot:
            screen = await _load_weather(app, pilot, warnings=True)
            summary = screen.query_one(WeatherAlertSummary)

            self.assertEqual(summary.region.height, 3)
            self.assertEqual(summary.render().plain, 'Severe Heat Warning · +1 more')
            summary.focus()
            await pilot.press('enter')
            await pilot.pause()

            self.assertIsInstance(app.screen, WeatherAlertsModal)
            panel = app.screen.query_one(WeatherAlertsPanel)
            details = app.screen.query_one(WeatherAlertDetailsPanel)
            panel.tabs.active = 'alert-item-1'
            await pilot.pause()

            console = Console(width=80, file=StringIO(), record=True)
            console.print(getattr(details.content, '_Static__content'))
            self.assertIn(
                'High waves and dangerous currents',
                console.export_text(),
            )
            self.assertEqual(details.styles.overflow_y, 'auto')

            await pilot.press('escape')
            await pilot.pause()
            self.assertIs(app.screen, screen)


if __name__ == '__main__':
    unittest.main()
