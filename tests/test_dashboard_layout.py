"""Pure responsive budget checks for the Dashboard."""

import unittest

from wevva.dashboard_layout import DashboardPresentation, dashboard_layout_for
from wevva.widgets.dashboard_hourly_forecast import (
    _measure,
    _wind_measure,
)


class DashboardLayoutTests(unittest.TestCase):
    def test_qualification_size_matrix_uses_only_the_documented_bands(self) -> None:
        expected = {
            (80, 24): (DashboardPresentation.COMPACT, False, 2, 0),
            (100, 30): (DashboardPresentation.MEDIUM, False, 4, 0),
            (120, 30): (DashboardPresentation.WIDE, True, 3, 1),
            (140, 40): (DashboardPresentation.WIDE, True, 6, 2),
            (250, 70): (DashboardPresentation.WIDE, True, 6, 5),
        }

        for size, values in expected.items():
            with self.subTest(size=size):
                budget = dashboard_layout_for(*size)
                self.assertEqual(
                    (
                        budget.presentation,
                        budget.simultaneous,
                        budget.daily_rows,
                        budget.context_rows,
                    ),
                    values,
                )
                if budget.simultaneous:
                    usable_height = size[1] - 2 - budget.stage_padding[0] * 2
                    self.assertEqual(
                        budget.map_height
                        + budget.detail_gutter
                        + budget.detail_height,
                        usable_height,
                    )
                    self.assertGreaterEqual(budget.map_height, 14)
                    self.assertGreaterEqual(budget.detail_height, 9)

    def test_full_dashboard_requires_both_baseline_dimensions(self) -> None:
        wide = dashboard_layout_for(120, 30)
        self.assertEqual(wide.presentation, DashboardPresentation.WIDE)
        self.assertTrue(wide.simultaneous)
        self.assertEqual(
            120
            - wide.stage_padding[1] * 2
            - wide.forecast_width
            - wide.alert_width
            - wide.gutter * 2,
            48,
        )
        self.assertEqual(wide.daily_rows, 3)
        self.assertEqual(wide.current_conditions_height, 5)
        self.assertEqual(wide.hourly_min_height, 5)
        self.assertEqual(wide.context_rows, 1)
        self.assertEqual(wide.map_height, 14)
        self.assertEqual(wide.detail_height, 11)
        self.assertEqual(wide.detail_gutter, 1)

        self.assertFalse(dashboard_layout_for(119, 30).simultaneous)
        self.assertFalse(dashboard_layout_for(120, 29).simultaneous)

    def test_large_surplus_widens_rails_and_caps_map_height(self) -> None:
        baseline = dashboard_layout_for(120, 30)
        large = dashboard_layout_for(250, 70)

        self.assertGreater(large.forecast_width, baseline.forecast_width)
        self.assertGreater(large.alert_width, baseline.alert_width)
        self.assertEqual(large.forecast_width, 54)
        self.assertEqual(large.alert_width, 46)
        self.assertIsNotNone(large.map_height)
        self.assertLess(large.map_height, 66)
        self.assertGreaterEqual(large.detail_height, 9)
        self.assertEqual(
            large.map_height + large.detail_gutter + large.detail_height,
            66,
        )
        self.assertEqual(large.daily_rows, 6)
        self.assertEqual(large.context_rows, 5)

    def test_fallback_bands_keep_one_stable_pane_model(self) -> None:
        self.assertEqual(
            dashboard_layout_for(110, 28).presentation,
            DashboardPresentation.MEDIUM,
        )
        self.assertEqual(
            dashboard_layout_for(80, 24).presentation,
            DashboardPresentation.COMPACT,
        )
        self.assertEqual(
            dashboard_layout_for(140, 19).presentation,
            DashboardPresentation.SHORT,
        )
        self.assertFalse(dashboard_layout_for(80, 24).simultaneous)
        compact = dashboard_layout_for(80, 24)
        short = dashboard_layout_for(140, 19)
        self.assertEqual(compact.daily_rows, 2)
        self.assertEqual(compact.current_conditions_height, 5)
        self.assertEqual(compact.context_rows, 0)
        self.assertEqual(short.daily_rows, 1)
        self.assertEqual(short.current_conditions_height, 3)
        self.assertEqual(short.hourly_min_height, 4)
        self.assertEqual(short.context_rows, 0)
        medium = dashboard_layout_for(110, 28)
        self.assertEqual(medium.daily_rows, 2)
        self.assertEqual(medium.current_conditions_height, 5)
        self.assertEqual(medium.context_rows, 0)


class DashboardForecastFormattingTests(unittest.TestCase):
    def test_supported_units_inherit_value_colours(self) -> None:
        temperature = _measure(
            72,
            unit='°F',
            style='red',
        )
        rain = _measure(
            85,
            unit='%',
            style='cyan',
        )
        wind = _wind_measure(
            12,
            'ENE ↙',
            unit='mp/h',
            wind_style='green',
        )

        self.assertEqual(temperature.plain, '72°F')
        self.assertEqual(rain.plain, '85%')
        self.assertEqual(wind.plain, '12mp/h ENE ↙')
        self.assertEqual(
            [(span.start, span.end) for span in temperature.spans],
            [(0, 4)],
        )
        self.assertEqual(
            [(span.start, span.end) for span in rain.spans],
            [(0, 3)],
        )
        self.assertEqual(
            [(span.start, span.end) for span in wind.spans],
            [(0, 6), (7, 12)],
        )
        for value in (temperature, rain, wind):
            self.assertTrue(
                all('bold' in str(span.style) for span in value.spans),
                value,
            )


if __name__ == '__main__':
    unittest.main()
