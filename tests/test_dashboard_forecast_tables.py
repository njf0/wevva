"""Rendered Dashboard table spacing without mounting provider workspaces."""

import unittest

from textual.app import App, ComposeResult

from tests.weather_fixtures import weather_update
from wevva.widgets.dashboard_daily_forecast import DashboardDailyForecast
from wevva.widgets.dashboard_hourly_forecast import DashboardHourlyForecast


class _ForecastTablesApp(App):
    temperature_unit = 'celsius'
    emoji_enabled = False

    def __init__(self):
        super().__init__()
        self.event = weather_update(with_warnings=False)
        for index, point in enumerate(self.event.hourly.forecast_timeseries):
            point.update(
                temperature_2m=(-1, 0, 2, 4)[index % 4],
                precipitation_probability=(0, 7, 13, 14)[index % 4],
                wind_speed_10m=(5, 6, 1, 14)[index % 4],
                wind_direction_10m=(0, 45, 90, 315)[index % 4],
            )
        for index, point in enumerate(self.event.daily.forecast_timeseries):
            point['wind_direction_10m_dominant'] = (0, 45, 90, 315)[index % 4]

    def compose(self) -> ComposeResult:
        yield DashboardHourlyForecast(id='hourly')
        yield DashboardDailyForecast(id='daily')

    def on_mount(self):
        self.query_one(DashboardHourlyForecast).update_forecast(self.event)
        daily = self.query_one(DashboardDailyForecast)
        daily.set_row_count(6)
        daily.update_forecast(self.event)


class DashboardForecastTablesTests(unittest.IsolatedAsyncioTestCase):
    async def test_narrow_hourly_padding_and_numeric_and_wind_alignment(self):
        app = _ForecastTablesApp()
        async with app.run_test(size=(36, 20)) as pilot:
            for _ in range(3):
                await pilot.pause(0)
            hourly = app.query_one(DashboardHourlyForecast).table
            daily = app.query_one(DashboardDailyForecast).table
            self.assertEqual(hourly.cell_padding, 1)
            self.assertEqual(hourly.max_scroll_x, 0)
            self.assertEqual(daily.max_scroll_x, 0)

            rows = [hourly.get_row_at(index) for index in range(4)]
            self.assertEqual(rows[0][0].plain, '05:00')
            self.assertEqual(rows[0][2].plain, '-1°C')
            self.assertEqual(rows[0][3].plain, '0%')
            for row in rows:
                for cell in row[2:]:
                    self.assertEqual(cell.justify, 'right')
            # Fixed direction slots anchor speeds independently of N/NE/NW.
            for table in (hourly, daily):
                rendered = [table.render_line(index).text for index in range(4)]
                self.assertEqual(len({line.index('mp/h') for line in rendered}), 1)
                self.assertEqual(len({len(line.rstrip()) for line in rendered}), 1)
            date = daily.get_row_at(0)[0].plain
            self.assertIn(date + ' ', daily.render_line(0).text)
            condition = daily.get_row_at(0)[1].plain
            self.assertIn(condition + ' ', daily.render_line(0).text)

            # Reflow preserves selection and gives the smallest rail a compact
            # fallback instead of forcing a hidden horizontal scroll range.
            hourly.move_cursor(row=3)
            await pilot.resize_terminal(30, 20)
            for _ in range(3):
                await pilot.pause(0)
            self.assertEqual(hourly.cell_padding, 0)
            self.assertEqual(hourly.max_scroll_x, 0)
            self.assertEqual(hourly.cursor_row, 3)
            await pilot.resize_terminal(54, 20)
            for _ in range(3):
                await pilot.pause(0)
            self.assertEqual(hourly.cell_padding, 1)
            self.assertEqual(daily.cell_padding, 1)
            self.assertEqual(hourly.max_scroll_x, 0)
            self.assertEqual(daily.max_scroll_x, 0)

    async def test_padding_retains_longer_units_and_complete_readings(self):
        app = _ForecastTablesApp()
        app.temperature_unit = 'fahrenheit'
        app.event.hourly.forecast_units['temperature_2m'] = '°F'
        app.event.hourly.forecast_units['wind_speed_10m'] = 'km/h'
        for point in app.event.hourly.forecast_timeseries:
            point.update(
                temperature_2m=-24, precipitation_probability=100,
                wind_speed_10m=123, wind_direction_10m=45,
            )
        async with app.run_test(size=(40, 20)) as pilot:
            for _ in range(3):
                await pilot.pause(0)
            hourly = app.query_one(DashboardHourlyForecast).table
            self.assertEqual(hourly.cell_padding, 1)
            self.assertEqual(hourly.max_scroll_x, 0)
            rendered = hourly.render_line(0).text
            for value in ('05:00', '-24°F', '100%', '123km/h NE ↙'):
                self.assertIn(value, rendered)
