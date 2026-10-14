"""Fixed Alerts Centre hourly-strip rendering checks."""

from __future__ import annotations

import unittest

from textual.app import App, ComposeResult

from tests.weather_fixtures import hourly_forecast
from wevva.layout import HourlyRow
from wevva.widgets.alert_place_hourly_forecast import AlertPlaceHourlyForecast


ALL_ROWS = (
    HourlyRow.TEMPERATURE_BAR,
    HourlyRow.TEMPERATURE,
    HourlyRow.RAIN_BAR,
    HourlyRow.RAIN,
    HourlyRow.WIND_BAR,
    HourlyRow.WIND,
    HourlyRow.TIME,
)


class _StripApp(App[None]):
    temperature_unit = 'celsius'

    def compose(self) -> ComposeResult:
        yield AlertPlaceHourlyForecast(id='strip')


class AlertPlaceHourlyForecastTests(unittest.IsolatedAsyncioTestCase):
    async def test_loading_uses_a_centred_indicator_without_status_text(self) -> None:
        app = _StripApp()
        async with app.run_test(size=(80, 20)) as pilot:
            strip = app.query_one('#strip', AlertPlaceHourlyForecast)
            strip.set_state(place_name='Chicago', state='loading', forecast=None)
            strip.set_layout(9, ())
            await pilot.pause()

            self.assertTrue(strip.loading_indicator.display)
            self.assertFalse(strip.content.display)
            self.assertEqual(strip.content.render().plain, '')
            self.assertEqual(strip.region.height, 9)

    async def test_fills_width_with_at_most_24_consecutive_hours(self) -> None:
        app = _StripApp()
        async with app.run_test(size=(100, 20)) as pilot:
            strip = app.query_one('#strip', AlertPlaceHourlyForecast)
            strip.set_state(
                place_name='Chicago',
                state='ready',
                forecast=hourly_forecast(),
            )
            strip.set_layout(9, ALL_ROWS)
            await pilot.pause()

            self.assertEqual(strip.hour_count, 24)
            self.assertEqual(sum(strip.column_widths), strip.size.width)
            self.assertTrue(all(width >= 4 for width in strip.column_widths))
            self.assertEqual(strip.border_title, 'Hourly forecast — Chicago')
            self.assertFalse(strip.can_focus)
            self.assertEqual(len(strip.content.render().plain.splitlines()), 7)

    async def test_resize_refits_columns_without_a_scrollable_child(self) -> None:
        app = _StripApp()
        async with app.run_test(size=(54, 16)) as pilot:
            strip = app.query_one('#strip', AlertPlaceHourlyForecast)
            forecast = hourly_forecast()
            strip.set_state(place_name='Chicago', state='ready', forecast=forecast)
            strip.set_layout(
                4,
                (HourlyRow.TEMPERATURE, HourlyRow.TIME),
            )
            await pilot.pause()
            first_count = strip.hour_count

            await pilot.resize_terminal(38, 16)
            await pilot.pause()

            self.assertGreater(first_count, strip.hour_count)
            self.assertEqual(sum(strip.column_widths), strip.size.width)
            self.assertEqual(len(strip.content.render().plain.splitlines()), 2)
            self.assertEqual(len(strip.query('DataTable')), 0)


if __name__ == '__main__':
    unittest.main()
