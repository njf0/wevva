"""Rendered Dashboard table spacing without mounting provider workspaces."""

import unittest
from pathlib import Path

from textual.app import App, ComposeResult

from tests.weather_fixtures import weather_update
from wevva.widgets.dashboard_daily_forecast import DashboardDailyForecast
from wevva.widgets.dashboard_hourly_forecast import DashboardHourlyForecast


class _ForecastTablesApp(App):
    CSS_PATH = Path(__file__).resolve().parents[1] / 'wevva' / 'wevva.tcss'
    temperature_unit = 'celsius'
    emoji_enabled = False

    def __init__(self, *, delayed=False):
        super().__init__()
        self.delayed = delayed
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
        if not self.delayed:
            self.show_forecast()

    def show_forecast(self):
        self.query_one(DashboardHourlyForecast).update_forecast(self.event)
        daily = self.query_one(DashboardDailyForecast)
        daily.set_row_count(6)
        daily.update_forecast(self.event)


class DashboardForecastTablesTests(unittest.IsolatedAsyncioTestCase):
    async def test_daily_uses_viewport_width_when_forecast_arrives_after_mount(self):
        app = _ForecastTablesApp(delayed=True)
        async with app.run_test(size=(38, 20)) as pilot:
            for _ in range(3):
                await pilot.pause(0)
            daily = app.query_one(DashboardDailyForecast).table
            app.show_forecast()
            for _ in range(3):
                await pilot.pause(0)
            self.assertEqual(daily.size.width, app.query_one(DashboardDailyForecast).content_size.width)
            self.assertEqual(daily.max_scroll_x, 0)
            for index in range(6):
                wind = daily.get_row_at(index)[4].plain
                self.assertIn(wind, daily.render_line(index).text)

            # A later provider response must also keep the complete wind field.
            app.event = weather_update(with_warnings=False)
            for point in app.event.daily.forecast_timeseries:
                point.update(wind_speed_10m_max=122, precipitation_probability_max=100)
            app.show_forecast()
            for _ in range(3):
                await pilot.pause(0)
            for index in range(6):
                rendered = daily.render_line(index).text
                self.assertIn('100%', rendered)
                self.assertIn(daily.get_row_at(index)[4].plain, rendered)
            self.assertEqual(daily.max_scroll_x, 0)

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
            date = daily.get_row_at(0)[0].plain.rstrip()
            self.assertIn(date + ' ', daily.render_line(0).text)
            condition = daily.get_row_at(0)[1].plain.rstrip()
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

    async def test_100_percent_retains_a_separator_at_the_padding_boundary(self):
        app = _ForecastTablesApp()
        for index, point in enumerate(app.event.hourly.forecast_timeseries):
            point.update(temperature_2m=12, precipitation_probability=100 if index % 2 == 0 else 98)
        for index, point in enumerate(app.event.daily.forecast_timeseries):
            point.update(temperature_2m_min=9 if index % 2 else 10, temperature_2m_max=17)
            point['precipitation_probability_max'] = 100 if index % 2 else 89
        async with app.run_test(size=(36, 20)) as pilot:
            for _ in range(3):
                await pilot.pause(0)
            hourly = app.query_one(DashboardHourlyForecast).table
            daily = app.query_one(DashboardDailyForecast).table
            self.assertEqual(hourly.cell_padding, 0)
            self.assertEqual(list(hourly.columns.values())[2].width, 5)
            self.assertIn('12°C 100%', hourly.render_line(0).text)
            self.assertIn('12°C  98%', hourly.render_line(1).text)
            self.assertIn('9°-17°  100%', daily.render_line(0).text)
            self.assertIn('100%  12mp/h', daily.render_line(0).text)
            self.assertIn('10°-17°   89%', daily.render_line(1).text)
            self.assertEqual(hourly.max_scroll_x, 0)
            self.assertEqual(daily.max_scroll_x, 0)

            await pilot.resize_terminal(34, 20)
            for _ in range(3):
                await pilot.pause(0)
            self.assertIn('9°-17° 100% 12mp/h', daily.render_line(0).text)
            self.assertIn(daily.get_row_at(0)[4].plain, daily.render_line(0).text)
            self.assertEqual(daily.max_scroll_x, 0)

            await pilot.resize_terminal(38, 20)
            for _ in range(3):
                await pilot.pause(0)
            self.assertEqual(hourly.cell_padding, 1)
            self.assertEqual([column.width for column in hourly.columns.values()][:4], [5, 2, 4, 4])
            self.assertIn('12°C  100%', hourly.render_line(0).text)
            self.assertEqual(hourly.max_scroll_x, 0)

            await pilot.resize_terminal(54, 20)
            for _ in range(3):
                await pilot.pause(0)
            self.assertEqual(list(hourly.columns.values())[2].width, 4)
            self.assertEqual(list(daily.columns.values())[2].width, 7)
