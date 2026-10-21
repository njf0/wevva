"""Pure responsive budget checks for Dashboard Slice A."""

import unittest

from wevva.dashboard_layout import DashboardPresentation, dashboard_layout_for


class DashboardLayoutTests(unittest.TestCase):
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
        self.assertEqual(wide.current_summary_height, 4)
        self.assertEqual(wide.hourly_min_height, 8)

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
        self.assertEqual(large.daily_rows, 6)

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
        self.assertEqual(compact.current_summary_height, 3)
        self.assertFalse(compact.show_open_hint)
        self.assertEqual(short.daily_rows, 1)
        self.assertEqual(short.current_summary_height, 2)
        self.assertEqual(short.hourly_min_height, 4)
        medium = dashboard_layout_for(110, 28)
        self.assertEqual(medium.daily_rows, 2)
        self.assertEqual(medium.current_summary_height, 3)
        self.assertFalse(medium.show_open_hint)


if __name__ == '__main__':
    unittest.main()
