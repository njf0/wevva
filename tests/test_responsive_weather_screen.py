"""Rendered checks for the budget-driven operational weather screen."""

from __future__ import annotations

from io import StringIO
import unittest

from rich.console import Console
from textual.app import App
from textual.containers import Container
from textual.coordinate import Coordinate

from tests.weather_fixtures import chicago_location, weather_update
from wevva.alerts import Alert
from wevva.layout import (
    ContextPresentation,
    CurrentDensity,
    DailyColumn,
    HourlyRow,
    WarningDensity,
    daily_column_widths,
    daily_table_width,
)
from wevva.screens.weather_screen import WeatherScreen
from wevva.widgets.daily_forecast import DailyForecast
from wevva.widgets.location_map import LocationMapLabel
from wevva.widgets.weather_alerts import (
    WeatherAlertSummary,
    WeatherAlertsModal,
    WeatherAlertsReader,
)
from wevva.widgets.weather_widget import WeatherWidget


class _ResponsiveWeatherApp(App):
    # Match the real application's general table rule.  HourlyForecast must
    # retain its full-width scrolling viewport despite this higher-level CSS.
    CSS = 'DataTable { width: auto; }'

    def __init__(
        self,
        *,
        emoji_enabled: bool = False,
        temperature_unit: str = 'celsius',
        theme_name: str | None = None,
    ) -> None:
        super().__init__()
        self.location = chicago_location()
        self.forecast_metadata = None
        self.saved_locations = []
        self.emoji_enabled = emoji_enabled
        self.temperature_unit = temperature_unit
        if theme_name is not None:
            self.theme = theme_name

    def on_mount(self) -> None:
        self.push_screen(WeatherScreen())


async def _load_weather(app: _ResponsiveWeatherApp, pilot, *, warnings: bool) -> WeatherScreen:
    return await _load_update(app, pilot, weather_update(with_warnings=warnings))


async def _load_update(
    app: _ResponsiveWeatherApp,
    pilot,
    update,
) -> WeatherScreen:
    await pilot.pause()
    screen = app.screen
    assert isinstance(screen, WeatherScreen)
    app.forecast_metadata = update.metadata
    await screen.on_weather_updated(update)
    for _ in range(4):
        await pilot.pause()
    return screen


def _imperial_update(*, long_warning: bool, multiple_warnings: bool):
    """Return a fresh update with the longest supported display-unit labels."""

    update = weather_update(with_warnings=multiple_warnings)
    hourly_units = update.hourly.forecast_units
    hourly_units.update(
        {
            'temperature_2m': '°F',
            'apparent_temperature': '°F',
            'precipitation': 'inch',
            'wind_speed_10m': 'km/h',
            'wind_gusts_10m': 'km/h',
        }
    )
    update.daily.forecast_units.update(
        {
            'temperature_2m_min': '°F',
            'temperature_2m_max': '°F',
            'precipitation_sum': 'inch',
            'wind_speed_10m_max': 'km/h',
            'wind_gusts_10m_max': 'km/h',
        }
    )
    if long_warning:
        long_alert = Alert(
            id='fixture-long-warning',
            source='nws',
            event='Excessive Heat and Dangerous Humidity Warning',
            severity='Extreme',
            headline=(
                'Excessive heat and dangerous humidity expected across the entire '
                'metropolitan region through late evening'
            ),
            description='Dangerously hot conditions are expected.',
            instruction='Limit prolonged outdoor activity.',
        )
        update.alerts = (
            [long_alert, *update.alerts]
            if multiple_warnings
            else [long_alert]
        )
    return update


class ResponsiveWeatherScreenTests(unittest.IsolatedAsyncioTestCase):
    async def test_long_units_emoji_and_alternate_themes_remain_bounded(self) -> None:
        cases = (
            ((80, 24), 'textual-light', False),
            ((120, 40), 'gruvbox', True),
        )
        for size, theme_name, multiple_warnings in cases:
            with self.subTest(
                size=size,
                theme=theme_name,
                multiple_warnings=multiple_warnings,
            ):
                app = _ResponsiveWeatherApp(
                    emoji_enabled=True,
                    temperature_unit='fahrenheit',
                    theme_name=theme_name,
                )
                async with app.run_test(size=size) as pilot:
                    screen = await _load_update(
                        app,
                        pilot,
                        _imperial_update(
                            long_warning=True,
                            multiple_warnings=multiple_warnings,
                        ),
                    )
                    budget = screen._layout_budget
                    assert budget is not None

                    self.assertLessEqual(
                        budget.used_rows,
                        screen.main_panel.region.height,
                    )
                    self.assertEqual(screen.main_panel.max_scroll_y, 0)
                    self.assertTrue(screen.header.icon)
                    warning = screen.query_one(WeatherAlertSummary)
                    if budget.warning_density is WarningDensity.SUMMARY:
                        self.assertEqual(screen.warnings_row.region.height, 4)
                        self.assertTrue(warning.display)
                        self.assertFalse(screen.weather_alert_panel.display)
                        self.assertEqual(warning.region.height, 3)
                        self.assertEqual(warning.content_size.height, 1)
                        self.assertEqual(warning.styles.text_overflow, 'ellipsis')
                    else:
                        self.assertEqual(
                            budget.warning_density,
                            WarningDensity.TABBED,
                        )
                        self.assertEqual(screen.warnings_row.region.height, 7)
                        self.assertFalse(warning.display)
                        self.assertTrue(screen.weather_alert_panel.display)
                        self.assertEqual(screen.weather_alert_panel.region.height, 6)

                    temperature = screen.query_one('#ww-temp', WeatherWidget)
                    wind = screen.query_one('#ww-wind', WeatherWidget)
                    self.assertIn(
                        '°F',
                        temperature.query_one('#compact-value').render().plain,
                    )
                    self.assertIn(
                        'km/h',
                        wind.query_one('#compact-value').render().plain,
                    )
                    self.assertEqual(len(screen.hourly_forecast.table.columns), 24)

                    daily = screen.query_one(DailyForecast).daily
                    if daily.row_count:
                        visible = daily._visible_columns
                        precip_index = visible.index(DailyColumn.PRECIPITATION)
                        wind_index = visible.index(DailyColumn.WIND)
                        self.assertLess(precip_index, wind_index)
                        for row_index in range(daily.row_count):
                            for column_index, column in enumerate(daily.columns.values()):
                                cell = daily.get_cell_at(
                                    Coordinate(row_index, column_index)
                                )
                                self.assertLessEqual(cell.cell_len, column.width)

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
                - screen.context_row.region.bottom
            )
            self.assertLessEqual(abs(top_gap - bottom_gap), 1)
            self.assertEqual(screen.main_panel.max_scroll_y, 0)
            self.assertTrue(screen._layout_budget.show_context_matrix)
            self.assertEqual(
                screen._layout_budget.context_presentation,
                ContextPresentation.BOTTOM,
            )
            self.assertTrue(screen.context_row.display)
            self.assertTrue(screen.bottom_info_bar.display)
            self.assertTrue(screen.location_map.display)
            self.assertEqual(screen.context_row.region.height, 14)
            self.assertEqual(screen.bottom_info_bar.region.height, 14)
            self.assertEqual(screen.context_bar.region.height, 14)
            self.assertEqual(screen.location_map.region.height, 14)
            self.assertEqual(screen.location_map.styles.padding, (0, 0, 0, 0))
            self.assertLessEqual(
                abs(screen.context_bar.region.width - screen.location_map.region.width),
                1,
            )
            self.assertEqual(screen.context_bar.location.row_count, 2)
            self.assertEqual(screen.context_bar.astronomy.row_count, 2)
            self.assertEqual(screen.context_bar.air_quality.row_count, 2)
            self.assertEqual(
                tuple(row.value for row in screen.context_bar.location.rows),
                ('coords', 'elev'),
            )
            self.assertEqual(
                tuple(row.value for row in screen.context_bar.astronomy.rows),
                ('sunrise', 'sunset'),
            )
            self.assertEqual(
                tuple(row.value for row in screen.context_bar.air_quality.rows),
                ('aqi', 'pollen'),
            )
            self.assertTrue(screen.context_bar.air_quality.display)
            self.assertTrue(
                any(
                    label.label_text.startswith('• Chicago')
                    for label in screen.location_map.query(LocationMapLabel)
                )
            )

            daily = screen.query_one(DailyForecast)
            visible = daily.daily._visible_columns
            self.assertLess(
                visible.index(DailyColumn.PRECIPITATION),
                visible.index(DailyColumn.WIND),
            )

    async def test_wide_context_uses_sidecar_before_auxiliary_rails(self) -> None:
        app = _ResponsiveWeatherApp()
        async with app.run_test(size=(160, 45)) as pilot:
            screen = await _load_weather(app, pilot, warnings=True)
            budget = screen._layout_budget
            assert budget is not None

            self.assertEqual(
                budget.context_presentation,
                ContextPresentation.SIDECAR,
            )
            self.assertEqual(screen.weather_workspace.region.width, 140)
            self.assertEqual(screen.forecast_column.region.width, 98)
            self.assertEqual(screen.context_row.region.width, 40)
            self.assertEqual(
                screen.context_row.region.x - screen.forecast_column.region.right,
                2,
            )
            self.assertEqual(screen.context_bar.region.height, 15)
            self.assertEqual(screen.location_map.region.height, 25)
            self.assertEqual(
                screen.location_map.region.y - screen.context_bar.region.bottom,
                1,
            )
            self.assertEqual(screen.context_row.region.height, 41)
            self.assertTrue(screen.context_bar.location.display)
            self.assertTrue(screen.context_bar.astronomy.display)
            self.assertFalse(screen.context_bar.air_quality.display)
            self.assertLessEqual(
                sum(
                    not label.current and label.display
                    for label in screen.location_map.query(LocationMapLabel)
                ),
                4,
            )
            self.assertEqual(screen.query_one(DailyForecast).daily.row_count, 6)
            self.assertFalse(screen.saved_locations_sidebar_visible)
            self.assertFalse(screen.alert_details_sidebar_visible)
            self.assertEqual(screen.main_panel.max_scroll_y, 0)

    async def test_context_widgets_survive_bottom_to_sidecar_resize(self) -> None:
        app = _ResponsiveWeatherApp()
        async with app.run_test(size=(140, 60)) as pilot:
            screen = await _load_weather(app, pilot, warnings=True)
            context_bar = screen.context_bar
            location_map = screen.location_map
            self.assertEqual(
                screen._layout_budget.context_presentation,
                ContextPresentation.BOTTOM,
            )
            self.assertTrue(screen.context_bar.air_quality.display)

            await pilot.resize_terminal(160, 60)
            for _ in range(3):
                await pilot.pause()

            self.assertIs(screen.context_bar, context_bar)
            self.assertIs(screen.location_map, location_map)
            self.assertEqual(
                screen._layout_budget.context_presentation,
                ContextPresentation.SIDECAR,
            )
            self.assertFalse(screen.context_bar.air_quality.display)
            self.assertEqual(screen.weather_workspace.styles.layout.name, 'horizontal')
            self.assertEqual(screen.main_panel.max_scroll_y, 0)

            await pilot.resize_terminal(140, 60)
            for _ in range(3):
                await pilot.pause()

            self.assertIs(screen.context_bar, context_bar)
            self.assertIs(screen.location_map, location_map)
            self.assertEqual(
                screen._layout_budget.context_presentation,
                ContextPresentation.BOTTOM,
            )
            self.assertTrue(screen.context_bar.air_quality.display)
            self.assertEqual(screen.weather_workspace.styles.layout.name, 'vertical')
            self.assertEqual(screen.main_panel.max_scroll_y, 0)

    async def test_context_matrix_fits_the_supported_narrow_width(self) -> None:
        app = _ResponsiveWeatherApp()
        async with app.run_test(size=(80, 60)) as pilot:
            screen = await _load_weather(app, pilot, warnings=False)
            budget = screen._layout_budget
            assert budget is not None

            self.assertTrue(budget.show_context_matrix)
            self.assertEqual(budget.context_detail_rows, 4)
            self.assertEqual(screen.bottom_info_bar.region.width, 76)
            self.assertEqual(screen.context_bar.region.width, 37)
            self.assertEqual(screen.location_map.region.width, 37)
            self.assertEqual(
                screen.location_map.region.x - screen.context_bar.region.right,
                2,
            )
            self.assertEqual(screen.context_bar.location.content_region.width, 35)
            self.assertRegex(
                screen.context_bar.location.get_cell('date', 'value').plain,
                r'^\w{3} \d{2} \w{3} \d{4}$',
            )
            self.assertTrue(
                any(
                    label.label_text.startswith('• Chicago')
                    for label in screen.location_map.query(LocationMapLabel)
                )
            )
            self.assertEqual(screen.main_panel.max_scroll_y, 0)

    async def test_wide_short_and_narrow_tall_spend_independent_budgets(self) -> None:
        wide_app = _ResponsiveWeatherApp()
        async with wide_app.run_test(size=(160, 24)) as pilot:
            wide = await _load_weather(wide_app, pilot, warnings=True)
            wide_budget = wide._layout_budget
            assert wide_budget is not None

            self.assertEqual(wide_budget.current_density, CurrentDensity.SMALLEST)
            self.assertEqual(len(wide_budget.hourly_rows), 3)
            self.assertEqual(wide_budget.daily_row_count, 0)
            self.assertTrue(wide_budget.full_detail_labels)
            self.assertEqual(wide.main_panel.max_scroll_y, 0)

        tall_app = _ResponsiveWeatherApp()
        async with tall_app.run_test(size=(80, 40)) as pilot:
            tall = await _load_weather(tall_app, pilot, warnings=True)
            tall_budget = tall._layout_budget
            assert tall_budget is not None

            self.assertEqual(tall_budget.current_density, CurrentDensity.STANDARD)
            self.assertEqual(
                tall_budget.hourly_rows,
                (
                    HourlyRow.CONDITION,
                    HourlyRow.TEMPERATURE,
                    HourlyRow.RAIN,
                    HourlyRow.WIND,
                    HourlyRow.TIME,
                ),
            )
            self.assertEqual(tall_budget.daily_row_count, 4)
            self.assertEqual(tall_budget.warning_density, WarningDensity.TABBED)
            self.assertFalse(tall_budget.full_detail_labels)
            self.assertEqual(tall.main_panel.max_scroll_y, 0)

    async def test_context_matrix_grows_and_hides_at_complete_tiers(self) -> None:
        app = _ResponsiveWeatherApp()
        async with app.run_test(size=(140, 63)) as pilot:
            screen = await _load_weather(app, pilot, warnings=True)
            self.assertTrue(screen.context_row.display)
            self.assertEqual(screen._layout_budget.context_detail_rows, 3)

            await pilot.resize_terminal(140, 60)
            for _ in range(3):
                await pilot.pause()

            self.assertTrue(screen._layout_budget.show_context_matrix)
            self.assertEqual(screen._layout_budget.context_detail_rows, 2)
            self.assertEqual(screen.context_row.region.height, 14)
            self.assertEqual(screen.location_map.region.height, 14)
            self.assertEqual(screen.context_bar.location.row_count, 2)

            await pilot.resize_terminal(140, 59)
            for _ in range(3):
                await pilot.pause()

            self.assertFalse(screen._layout_budget.show_context_matrix)
            self.assertFalse(screen.context_row.display)
            self.assertFalse(screen.bottom_info_bar.display)
            self.assertFalse(screen.location_map.display)
            self.assertEqual(screen._layout_budget.daily_row_count, 6)
            self.assertEqual(screen.main_panel.max_scroll_y, 0)

            await pilot.resize_terminal(140, 69)
            for _ in range(3):
                await pilot.pause()

            self.assertTrue(screen._layout_budget.show_context_matrix)
            self.assertEqual(screen._layout_budget.context_detail_rows, 5)
            self.assertTrue(screen.context_row.display)
            self.assertTrue(screen.bottom_info_bar.display)
            self.assertTrue(screen.location_map.display)
            self.assertEqual(screen.context_row.region.height, 23)
            self.assertEqual(screen.location_map.region.height, 23)
            self.assertEqual(screen.context_bar.location.row_count, 5)
            self.assertEqual(screen.context_bar.astronomy.row_count, 5)
            self.assertEqual(screen.context_bar.air_quality.row_count, 5)
            self.assertEqual(screen.main_panel.max_scroll_y, 0)

    async def test_day_focus_and_hour_survive_width_variant_boundaries(self) -> None:
        app = _ResponsiveWeatherApp()
        async with app.run_test(size=(101, 40)) as pilot:
            screen = await _load_weather(app, pilot, warnings=True)
            hourly = screen.hourly_forecast
            daily = screen.query_one(DailyForecast).daily

            daily.focus()
            daily.move_cursor(row=1, animate=False, scroll=False)
            await pilot.pause()
            self.assertEqual(hourly.tabs.active, 'day-2030-09-24')

            hourly.table.focus()
            hourly.table.move_cursor(column=23, animate=False, scroll=True)
            await pilot.pause()
            selected_index = hourly._col_indices[hourly.table.cursor_column]
            self.assertEqual(selected_index, 66)

            await pilot.resize_terminal(102, 40)
            for _ in range(3):
                await pilot.pause()

            self.assertEqual(hourly.tabs.active, 'day-2030-09-24')
            self.assertEqual(
                hourly._col_indices[hourly.table.cursor_column],
                selected_index,
            )
            self.assertEqual(daily.cursor_row, 1)
            self.assertIs(app.focused, hourly.table)
            self.assertIn(
                DailyColumn.WIND_DIRECTION,
                screen._layout_budget.daily_columns,
            )

            await pilot.resize_terminal(80, 40)
            for _ in range(3):
                await pilot.pause()

            self.assertEqual(hourly.tabs.active, 'day-2030-09-24')
            self.assertEqual(
                hourly._col_indices[hourly.table.cursor_column],
                selected_index,
            )
            self.assertEqual(daily.cursor_row, 1)
            self.assertIs(app.focused, hourly.table)
            self.assertGreater(hourly.table.scroll_x, 0)
            self.assertNotIn(
                DailyColumn.WIND_DIRECTION,
                screen._layout_budget.daily_columns,
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
            reader = app.screen.query_one(WeatherAlertsReader)
            details = reader.details
            dialog = app.screen.query_one('#weather-alert-modal', Container)
            self.assertEqual(dialog.styles.border_top[0], 'round')
            self.assertIsNone(details.border_title)
            self.assertEqual(details.styles.border_top[0], '')
            reader.tabs.active = 'alert-item-1'
            reader.tabs.focus()
            await pilot.pause()

            console = Console(width=80, file=StringIO(), record=True)
            console.print(getattr(details.content, '_Static__content'))
            self.assertIn(
                'High waves and dangerous currents',
                console.export_text(),
            )
            self.assertEqual(details.styles.overflow_y, 'auto')

            await pilot.resize_terminal(140, 40)
            for _ in range(3):
                await pilot.pause()

            self.assertEqual(reader.tabs.active, 'alert-item-1')
            self.assertEqual(reader.selected_index, 1)
            self.assertIs(app.focused, reader.tabs)
            console = Console(width=140, file=StringIO(), record=True)
            console.print(getattr(details.content, '_Static__content'))
            self.assertIn(
                'High waves and dangerous currents',
                console.export_text(),
            )

            await pilot.press('escape')
            await pilot.pause()
            self.assertIs(app.screen, screen)

    async def test_roomy_warning_uses_tabs_and_body_opens_selected_document(self) -> None:
        app = _ResponsiveWeatherApp()
        async with app.run_test(size=(80, 40)) as pilot:
            screen = await _load_weather(app, pilot, warnings=True)
            budget = screen._layout_budget
            assert budget is not None

            self.assertEqual(budget.warning_density, WarningDensity.TABBED)
            self.assertEqual(screen.warnings_row.region.height, 7)
            self.assertFalse(screen.weather_alert_summary.display)
            self.assertTrue(screen.weather_alert_panel.display)
            self.assertEqual(screen.weather_alert_panel.region.height, 6)

            screen.weather_alert_panel.tabs.active = 'alert-item-1'
            await pilot.pause()
            await pilot.click('#weather-alert-body')
            await pilot.pause()

            self.assertIsInstance(app.screen, WeatherAlertsModal)
            reader = app.screen.query_one(WeatherAlertsReader)
            self.assertEqual(reader.selected_index, 1)
            self.assertEqual(reader.tabs.active, 'alert-item-1')
            console = Console(width=80, file=StringIO(), record=True)
            console.print(getattr(reader.details.content, '_Static__content'))
            rendered = console.export_text()
            self.assertIn('High waves and dangerous currents', rendered)
            self.assertIn('Waves of five to eight feet', rendered)


if __name__ == '__main__':
    unittest.main()
