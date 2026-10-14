"""Responsive weather-screen budget and viewport geometry checks."""

from __future__ import annotations

import unittest

from textual.app import App

from tests.weather_fixtures import chicago_location, location_map_geometry, weather_update
from wevva.layout import (
    AuxiliaryPresentation,
    ContextPresentation,
    CurrentDensity,
    DailyColumn,
    DetailRow,
    HourlyRow,
    WarningDensity,
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
        self.assertEqual(budget.warning_density, WarningDensity.SUMMARY)
        self.assertEqual(budget.warning_card_height, 3)
        self.assertEqual(budget.warning_height, 4)
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
        self.assertEqual(budget.warning_density, WarningDensity.HIDDEN)
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
            31: (CurrentDensity.STANDARD, 7, 5, 0, False),
            36: (CurrentDensity.STANDARD, 7, 5, 2, False),
            38: (CurrentDensity.STANDARD, 7, 5, 4, False),
            39: (CurrentDensity.STANDARD, 7, 6, 4, False),
            41: (CurrentDensity.STANDARD, 7, 8, 4, False),
            43: (CurrentDensity.STANDARD, 7, 8, 6, False),
            58: (CurrentDensity.STANDARD, 7, 8, 6, 2),
            61: (CurrentDensity.STANDARD, 7, 8, 6, 3),
            64: (CurrentDensity.STANDARD, 7, 8, 6, 4),
            67: (CurrentDensity.STANDARD, 7, 8, 6, 5),
        }
        for height, values in expected.items():
            with self.subTest(height=height):
                budget = weather_layout_for(100, height, has_warnings=True)
                actual = (
                    budget.current_density,
                    budget.current_height,
                    len(budget.hourly_rows),
                    budget.daily_row_count,
                    budget.context_detail_rows,
                )
                self.assertEqual(actual, values)

        self.assertEqual(
            weather_layout_for(100, 30, has_warnings=True).warning_density,
            WarningDensity.SUMMARY,
        )
        self.assertEqual(
            weather_layout_for(100, 31, has_warnings=True).warning_density,
            WarningDensity.TABBED,
        )

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

    def test_sidebar_promotion_preserves_the_full_central_canvas(self) -> None:
        both_fit = weather_layout_for(
            228,
            40,
            locations_requested=True,
            warning_details_requested=True,
        )
        one_fits = weather_layout_for(
            227,
            40,
            locations_requested=True,
            warning_details_requested=True,
        )
        neither_fits = weather_layout_for(
            143,
            40,
            locations_requested=True,
            warning_details_requested=True,
        )

        self.assertEqual(both_fit.usable_width, 102)
        self.assertEqual(
            both_fit.warning_details_presentation,
            AuxiliaryPresentation.SIDEBAR,
        )
        self.assertEqual(
            both_fit.locations_presentation,
            AuxiliaryPresentation.SIDEBAR,
        )
        self.assertEqual(one_fits.usable_width, 143)
        self.assertEqual(
            one_fits.warning_details_presentation,
            AuxiliaryPresentation.SIDEBAR,
        )
        self.assertEqual(
            one_fits.locations_presentation,
            AuxiliaryPresentation.MODAL,
        )
        self.assertEqual(neither_fits.usable_width, 143)
        self.assertEqual(
            neither_fits.warning_details_presentation,
            AuxiliaryPresentation.MODAL,
        )
        self.assertEqual(
            neither_fits.locations_presentation,
            AuxiliaryPresentation.MODAL,
        )

        self.assertEqual(
            both_fit.context_presentation,
            ContextPresentation.SIDECAR,
        )
        self.assertEqual(
            one_fits.context_presentation,
            ContextPresentation.SIDECAR,
        )
        self.assertEqual(
            neither_fits.context_presentation,
            ContextPresentation.HIDDEN,
        )

    def test_context_sidecar_precedes_auxiliary_rails_when_width_and_height_fit(
        self,
    ) -> None:
        too_narrow = weather_layout_for(143, 43, has_warnings=True)
        too_short = weather_layout_for(144, 30, has_warnings=True)
        exact_fit = weather_layout_for(144, 31, has_warnings=True)
        roomy = weather_layout_for(160, 43, has_warnings=True)

        self.assertIsNot(too_narrow.context_presentation, ContextPresentation.SIDECAR)
        self.assertIsNot(too_short.context_presentation, ContextPresentation.SIDECAR)
        self.assertEqual(exact_fit.context_presentation, ContextPresentation.SIDECAR)
        self.assertEqual(exact_fit.usable_width, 102)
        self.assertEqual(exact_fit.context_detail_rows, 4)
        self.assertEqual(exact_fit.context_table_height, 13)
        self.assertEqual(exact_fit.context_map_height, 15)
        self.assertEqual(exact_fit.context_height, 29)
        self.assertEqual(roomy.context_detail_rows, 5)
        self.assertEqual(roomy.context_table_height, 15)
        self.assertEqual(roomy.context_map_height, 25)
        self.assertEqual(roomy.context_height, 41)

    def test_full_height_prefers_complete_bottom_context_over_sidecar(self) -> None:
        almost_full = weather_layout_for(267, 66, has_warnings=True)
        full = weather_layout_for(
            267,
            67,
            has_warnings=True,
            locations_requested=True,
            warning_details_requested=True,
        )

        self.assertEqual(
            almost_full.context_presentation,
            ContextPresentation.SIDECAR,
        )
        self.assertEqual(full.context_presentation, ContextPresentation.BOTTOM)
        self.assertEqual(full.context_detail_rows, 5)
        self.assertEqual(full.context_height, 23)
        self.assertEqual(full.usable_width, 183)
        self.assertEqual(
            full.warning_details_presentation,
            AuxiliaryPresentation.SIDEBAR,
        )
        self.assertEqual(
            full.locations_presentation,
            AuxiliaryPresentation.SIDEBAR,
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

    def test_context_matrix_grows_in_complete_three_card_tiers(self) -> None:
        too_narrow = weather_layout_for(79, 64, has_warnings=True)
        too_short = weather_layout_for(80, 57, has_warnings=True)
        exact_fit = weather_layout_for(80, 58, has_warnings=True)

        self.assertFalse(too_narrow.show_context_matrix)
        self.assertFalse(too_short.show_context_matrix)
        self.assertTrue(exact_fit.show_context_matrix)
        self.assertEqual(exact_fit.context_detail_rows, 2)
        self.assertEqual(exact_fit.context_height, 14)
        self.assertEqual(exact_fit.remaining_rows, 0)

        for height, rows, context_height in (
            (61, 3, 17),
            (64, 4, 20),
            (67, 5, 23),
        ):
            with self.subTest(height=height):
                budget = weather_layout_for(80, height, has_warnings=True)
                self.assertEqual(budget.context_detail_rows, rows)
                self.assertEqual(budget.context_height, context_height)
                self.assertEqual(budget.remaining_rows, 0)

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


class RenderedViewportGeometryTests(unittest.IsolatedAsyncioTestCase):
    async def test_weather_screen_viewport_matches_terminal_matrix(self) -> None:
        app = _GeometryTestApp()
        async with app.run_test(size=TERMINAL_MATRIX[0]) as pilot:
            await pilot.pause()
            screen = app.screen
            self.assertIsInstance(screen, WeatherScreen)
            update = weather_update()
            app.forecast_metadata = update.metadata
            await screen.on_weather_updated(update)
            for _ in range(4):
                await pilot.pause()

            for width, terminal_height in TERMINAL_MATRIX:
                with self.subTest(size=(width, terminal_height)):
                    await pilot.resize_terminal(width, terminal_height)
                    for _ in range(3):
                        await pilot.pause()

                    budget = screen._layout_budget
                    self.assertIsNotNone(budget)
                    assert budget is not None
                    context_width = (
                        42
                        if budget.context_presentation
                        is ContextPresentation.SIDECAR
                        else 0
                    )
                    self.assertEqual(
                        screen.main_panel.region.width,
                        budget.usable_width + context_width,
                    )
                    self.assertEqual(
                        screen.main_panel.region.height,
                        terminal_height - 2,
                    )
                    self.assertLessEqual(
                        budget.used_rows,
                        screen.main_panel.region.height,
                    )
                    self.assertEqual(screen.main_panel.max_scroll_y, 0)

                    last_region = screen.next_24_hours.region
                    if screen.daily_forecast.display:
                        last_region = screen.daily_forecast.region
                    if screen.context_row.display:
                        last_region = screen.context_row.region
                    self.assertLessEqual(
                        last_region.bottom,
                        screen.main_panel.content_region.bottom,
                    )


if __name__ == '__main__':
    unittest.main()
