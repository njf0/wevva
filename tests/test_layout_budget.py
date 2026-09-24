"""Responsive weather-screen budget and viewport geometry checks."""

from __future__ import annotations

import unittest

from textual.app import App

from tests.weather_fixtures import location_map_geometry, weather_update
from wevva.layout import (
    AuxiliaryPresentation,
    CurrentDensity,
    DailyColumn,
    DetailRow,
    HourlyRow,
    daily_column_widths,
    daily_table_width,
    weather_layout_for,
)
from wevva.screens.weather_screen import WeatherScreen


TERMINAL_MATRIX = (
    (80, 24),
    (80, 40),
    (100, 30),
    (120, 40),
    (160, 24),
    (160, 45),
    (160, 60),
    (186, 53),
    (220, 24),
    (220, 45),
    (220, 60),
    (267, 75),
)


class LayoutBudgetTests(unittest.TestCase):
    def test_supported_baseline_fits_warning_case_exactly(self) -> None:
        # Header and footer each consume one row of an 80x24 terminal.
        budget = weather_layout_for(80, 22, has_warnings=True)

        self.assertEqual(budget.current_density, CurrentDensity.SMALLEST)
        self.assertEqual(budget.current_height, 3)
        self.assertEqual(
            budget.detail_rows,
            (DetailRow.HUMIDITY,),
        )
        self.assertEqual(
            budget.hourly_rows,
            (
                HourlyRow.CONDITION,
                HourlyRow.TEMPERATURE,
                HourlyRow.TIME,
            ),
        )
        self.assertEqual(budget.daily_row_count, 0)
        self.assertEqual(
            budget.daily_columns,
            (
                DailyColumn.DATE,
                DailyColumn.CONDITION,
                DailyColumn.TEMPERATURE,
                DailyColumn.RAIN,
                DailyColumn.PRECIPITATION,
                DailyColumn.WIND,
                DailyColumn.GUST,
                DailyColumn.SUNRISE,
                DailyColumn.SUNSET,
            ),
        )
        self.assertTrue(budget.show_summary)
        self.assertFalse(budget.show_context_matrix)
        self.assertEqual(budget.used_rows, 22)
        self.assertEqual(budget.remaining_rows, 0)

    def test_no_warning_restores_summary_and_hourly_rain(self) -> None:
        budget = weather_layout_for(80, 22, has_warnings=False)

        self.assertIn(HourlyRow.RAIN, budget.hourly_rows)
        self.assertIn(HourlyRow.WIND, budget.hourly_rows)
        self.assertTrue(budget.show_summary)
        self.assertEqual(budget.current_density, CurrentDensity.SMALL)
        self.assertEqual(budget.daily_row_count, 0)
        self.assertEqual(budget.used_rows, 22)
        self.assertEqual(budget.remaining_rows, 0)

    def test_height_upgrades_follow_the_documented_priority(self) -> None:
        expected = {
            22: (CurrentDensity.SMALLEST, 3, 3, 0, False),
            23: (CurrentDensity.SMALLEST, 3, 4, 0, False),
            24: (CurrentDensity.SMALLEST, 3, 5, 0, False),
            26: (CurrentDensity.SMALL, 5, 5, 0, False),
            28: (CurrentDensity.STANDARD, 7, 5, 0, False),
            33: (CurrentDensity.STANDARD, 7, 5, 2, False),
            35: (CurrentDensity.STANDARD, 7, 5, 4, False),
            36: (CurrentDensity.STANDARD, 7, 6, 4, False),
            38: (CurrentDensity.STANDARD, 7, 8, 4, False),
            40: (CurrentDensity.STANDARD, 7, 8, 6, False),
            58: (CurrentDensity.STANDARD, 7, 8, 6, True),
        }
        for height, values in expected.items():
            with self.subTest(height=height):
                budget = weather_layout_for(100, height, has_warnings=True)
                actual = (
                    budget.current_density,
                    budget.current_height,
                    len(budget.hourly_rows),
                    budget.daily_row_count,
                    budget.show_context_matrix,
                )
                self.assertEqual(actual, values)

    def test_intermediate_width_buffers_small_current_conditions(self) -> None:
        six_rows = weather_layout_for(79, 27, has_warnings=True)
        seven_rows = weather_layout_for(79, 28, has_warnings=True)

        self.assertEqual(six_rows.current_density, CurrentDensity.SMALL)
        self.assertEqual(six_rows.current_height, 6)
        self.assertEqual(len(six_rows.detail_rows), 4)
        self.assertEqual(seven_rows.current_density, CurrentDensity.SMALL)
        self.assertEqual(seven_rows.current_height, 7)
        self.assertEqual(len(seven_rows.detail_rows), 5)

    def test_width_controls_current_density_and_daily_columns(self) -> None:
        narrow = weather_layout_for(73, 60)
        medium = weather_layout_for(74, 60)
        standard = weather_layout_for(80, 60)

        self.assertEqual(narrow.current_density, CurrentDensity.SMALLEST)
        self.assertEqual(medium.current_density, CurrentDensity.SMALL)
        self.assertEqual(standard.current_density, CurrentDensity.STANDARD)
        self.assertFalse(weather_layout_for(101, 60).full_detail_labels)
        self.assertTrue(weather_layout_for(102, 60).full_detail_labels)

        essential = (
            DailyColumn.DATE,
            DailyColumn.CONDITION,
            DailyColumn.TEMPERATURE,
            DailyColumn.RAIN,
            DailyColumn.WIND,
        )
        for width, expected_columns in (
            (60, essential),
            (61, essential[:4] + (DailyColumn.PRECIPITATION, DailyColumn.WIND)),
            (
                66,
                essential[:4]
                + (DailyColumn.PRECIPITATION, DailyColumn.WIND, DailyColumn.GUST),
            ),
            (
                73,
                essential[:4]
                + (
                    DailyColumn.PRECIPITATION,
                    DailyColumn.WIND,
                    DailyColumn.GUST,
                    DailyColumn.SUNRISE,
                ),
            ),
            (
                80,
                essential[:4]
                + (
                    DailyColumn.PRECIPITATION,
                    DailyColumn.WIND,
                    DailyColumn.GUST,
                    DailyColumn.SUNRISE,
                    DailyColumn.SUNSET,
                ),
            ),
            (
                101,
                essential[:4]
                + (
                    DailyColumn.PRECIPITATION,
                    DailyColumn.WIND,
                    DailyColumn.GUST,
                    DailyColumn.SUNRISE,
                    DailyColumn.SUNSET,
                ),
            ),
            (
                102,
                (
                    DailyColumn.DATE,
                    DailyColumn.CONDITION,
                    DailyColumn.TEMPERATURE,
                    DailyColumn.RAIN,
                    DailyColumn.PRECIPITATION,
                    DailyColumn.WIND,
                    DailyColumn.WIND_DIRECTION,
                    DailyColumn.SUNRISE,
                    DailyColumn.SUNSET,
                ),
            ),
        ):
            with self.subTest(width=width):
                self.assertEqual(
                    weather_layout_for(width, 40).daily_columns,
                    expected_columns,
                )

    def test_daily_widths_release_combined_field_space_when_split(self) -> None:
        essential = (
            DailyColumn.DATE,
            DailyColumn.CONDITION,
            DailyColumn.TEMPERATURE,
            DailyColumn.RAIN,
            DailyColumn.WIND,
        )
        split = essential[:4] + (
            DailyColumn.PRECIPITATION,
            DailyColumn.WIND,
            DailyColumn.GUST,
        )

        self.assertEqual(daily_column_widths(essential), (8, 4, 10, 15, 18))
        self.assertEqual(daily_column_widths(split), (8, 4, 10, 6, 9, 15, 8))
        self.assertEqual(daily_table_width(essential), 55)
        self.assertEqual(daily_table_width(split), 60)

    def test_wide_daily_layout_restores_full_legacy_columns(self) -> None:
        columns = weather_layout_for(102, 40).daily_columns

        self.assertEqual(
            daily_column_widths(columns),
            (13, 31, 8, 5, 7, 13, 5, 7, 7),
        )
        self.assertEqual(daily_table_width(columns), 96)

    def test_sidebar_promotion_preserves_an_eighty_column_canvas(self) -> None:
        both_fit = weather_layout_for(
            164,
            40,
            locations_requested=True,
            warning_details_requested=True,
        )
        one_fits = weather_layout_for(
            163,
            40,
            locations_requested=True,
            warning_details_requested=True,
        )
        neither_fits = weather_layout_for(
            121,
            40,
            locations_requested=True,
            warning_details_requested=True,
        )

        self.assertEqual(both_fit.usable_width, 80)
        self.assertEqual(
            both_fit.warning_details_presentation,
            AuxiliaryPresentation.SIDEBAR,
        )
        self.assertEqual(
            both_fit.locations_presentation,
            AuxiliaryPresentation.SIDEBAR,
        )
        self.assertEqual(one_fits.usable_width, 121)
        self.assertEqual(
            one_fits.warning_details_presentation,
            AuxiliaryPresentation.SIDEBAR,
        )
        self.assertEqual(
            one_fits.locations_presentation,
            AuxiliaryPresentation.MODAL,
        )
        self.assertEqual(neither_fits.usable_width, 121)
        self.assertEqual(
            neither_fits.warning_details_presentation,
            AuxiliaryPresentation.MODAL,
        )
        self.assertEqual(
            neither_fits.locations_presentation,
            AuxiliaryPresentation.MODAL,
        )

    def test_terminal_matrix_never_exceeds_the_content_height(self) -> None:
        for width, terminal_height in TERMINAL_MATRIX:
            for has_warnings in (False, True):
                for auxiliaries_requested in (False, True):
                    with self.subTest(
                        size=(width, terminal_height),
                        has_warnings=has_warnings,
                        auxiliaries_requested=auxiliaries_requested,
                    ):
                        content_height = terminal_height - 2
                        budget = weather_layout_for(
                            width,
                            content_height,
                            has_warnings=has_warnings,
                            locations_requested=auxiliaries_requested,
                            warning_details_requested=auxiliaries_requested,
                        )
                        self.assertLessEqual(budget.used_rows, content_height)
                        if not (has_warnings and content_height == 22):
                            self.assertIn(HourlyRow.RAIN, budget.hourly_rows)
                            self.assertIn(HourlyRow.WIND, budget.hourly_rows)
                        self.assertIn(HourlyRow.CONDITION, budget.hourly_rows)
                        self.assertIn(HourlyRow.TEMPERATURE, budget.hourly_rows)
                        self.assertIn(HourlyRow.TIME, budget.hourly_rows)
                        self.assertIn(budget.daily_row_count, (0, 2, 3, 4, 5, 6))

    def test_rain_is_added_before_wind(self) -> None:
        rain_only = weather_layout_for(80, 23, has_warnings=True)
        rain_and_wind = weather_layout_for(80, 24, has_warnings=True)

        self.assertIn(HourlyRow.RAIN, rain_only.hourly_rows)
        self.assertNotIn(HourlyRow.WIND, rain_only.hourly_rows)
        self.assertIn(HourlyRow.RAIN, rain_and_wind.hourly_rows)
        self.assertIn(HourlyRow.WIND, rain_and_wind.hourly_rows)

    def test_fixture_set_has_stable_forecast_warning_and_map_shapes(self) -> None:
        update = weather_update()
        geometry = location_map_geometry()

        self.assertEqual(len(update.hourly.forecast_timeseries), 72)
        self.assertEqual(len(update.daily.forecast_timeseries), 7)
        self.assertEqual([alert.id for alert in update.alerts], [
            'fixture-heat',
            'fixture-beach',
        ])
        self.assertEqual(geometry.location_name, 'Chicago')
        self.assertGreaterEqual(len(geometry.places), 4)


class _GeometryTestApp(App):
    """Minimal host used to measure the real WeatherScreen content region."""

    def __init__(self) -> None:
        super().__init__()
        self.location = None
        self.saved_locations = []

    def on_mount(self) -> None:
        self.push_screen(WeatherScreen())


class RenderedViewportGeometryTests(unittest.IsolatedAsyncioTestCase):
    async def test_weather_screen_viewport_matches_terminal_matrix(self) -> None:
        for width, terminal_height in TERMINAL_MATRIX:
            with self.subTest(size=(width, terminal_height)):
                app = _GeometryTestApp()
                async with app.run_test(size=(width, terminal_height)) as pilot:
                    await pilot.pause()
                    screen = app.screen
                    self.assertIsInstance(screen, WeatherScreen)
                    screen.main_panel.display = True
                    await pilot.pause()

                    self.assertEqual(screen.main_panel.region.width, width)
                    self.assertEqual(
                        screen.main_panel.region.height,
                        terminal_height - 2,
                    )
                    budget = weather_layout_for(
                        screen.main_panel.region.width,
                        screen.main_panel.region.height,
                        has_warnings=True,
                    )
                    self.assertLessEqual(
                        budget.used_rows,
                        screen.main_panel.region.height,
                    )


if __name__ == '__main__':
    unittest.main()
