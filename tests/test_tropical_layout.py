"""Pure responsive-budget regressions for the tropical workspace."""

from __future__ import annotations

import unittest

from wevva.tropical_layout import TropicalTopology, tropical_layout_for


def _rich_budget(width: int, height: int):
    return tropical_layout_for(
        width,
        height,
        multiple_sources=True,
        track_available=True,
        centre_weather_available=True,
        information_choice_count=2,
        rich_information=True,
        summary_available_rows=8,
        centre_weather_available_rows=6,
    )


class TropicalLayoutBudgetTests(unittest.TestCase):
    def test_representative_dimensions_select_constraint_driven_topologies(self) -> None:
        expected = {
            (80, 24): TropicalTopology.COMPACT_STACK,
            (100, 30): TropicalTopology.COMPACT_STACK,
            (126, 45): TropicalTopology.SPLIT,
            (131, 24): TropicalTopology.SPLIT,
            (140, 45): TropicalTopology.SPLIT,
            (240, 80): TropicalTopology.SPLIT,
        }
        for size, topology in expected.items():
            with self.subTest(size=size):
                self.assertEqual(_rich_budget(*size).topology, topology)

    def test_80_by_24_retains_navigation_summary_and_scrolling_body(self) -> None:
        budget = _rich_budget(80, 24)

        self.assertEqual(budget.frame_width, 76)
        self.assertEqual(budget.frame_height, 20)
        self.assertTrue(budget.source_tabs_visible)
        self.assertTrue(budget.information_tabs_visible)
        self.assertEqual(budget.workspace_height, 14)
        self.assertEqual(budget.summary_rows, 4)
        self.assertEqual(budget.summary_height, 6)
        self.assertEqual(budget.information_height, 7)
        self.assertEqual(budget.information_body_height, 3)
        self.assertFalse(budget.track_visible)
        self.assertEqual(budget.centre_weather_rows, 0)

    def test_single_information_choice_returns_tab_rows_to_document_body(self) -> None:
        tabbed = _rich_budget(80, 24)
        direct = tropical_layout_for(
            80,
            24,
            multiple_sources=True,
            track_available=True,
            centre_weather_available=True,
            information_choice_count=1,
            rich_information=True,
            summary_available_rows=8,
        )

        self.assertFalse(direct.information_tabs_visible)
        self.assertEqual(
            direct.information_body_height,
            tabbed.information_body_height + 2,
        )
        self.assertEqual(direct.information_height, tabbed.information_height)

    def test_complete_optional_regions_arrive_in_priority_order(self) -> None:
        short = _rich_budget(100, 30)
        medium = _rich_budget(126, 45)
        wide = _rich_budget(240, 80)

        self.assertFalse(short.track_visible)
        self.assertEqual(short.centre_weather_rows, 0)
        self.assertTrue(medium.track_visible)
        self.assertGreaterEqual(medium.track_height, 8)
        self.assertGreaterEqual(medium.centre_weather_rows, 3)
        self.assertGreater(wide.track_height, medium.track_height)
        self.assertEqual(wide.centre_weather_height, wide.summary_height)

    def test_split_lower_panes_share_height_for_rich_and_basic_information(self) -> None:
        rich = _rich_budget(140, 45)
        basic = tropical_layout_for(
            140,
            45,
            multiple_sources=True,
            track_available=True,
            centre_weather_available=True,
            information_choice_count=1,
            rich_information=False,
            summary_available_rows=8,
        )

        self.assertEqual(rich.information_height, rich.track_height)
        self.assertFalse(basic.information_tabs_visible)
        self.assertEqual(basic.information_height, basic.track_height)
        self.assertEqual(basic.information_height, rich.information_height)

    def test_wide_frame_and_columns_fill_stage_with_balanced_lower_panes(self) -> None:
        budget = _rich_budget(240, 80)

        self.assertEqual(budget.frame_width, 236)
        self.assertEqual(budget.frame_height, 76)
        self.assertEqual(budget.left_pane_width, 116)
        self.assertEqual(budget.information_height, budget.track_height)
        self.assertEqual(
            budget.summary_height + 1 + budget.information_height,
            budget.workspace_height,
        )

    def test_single_source_reclaims_the_source_tab_rows(self) -> None:
        multiple = _rich_budget(80, 24)
        single = tropical_layout_for(
            80,
            24,
            multiple_sources=False,
            track_available=True,
            centre_weather_available=True,
            information_choice_count=2,
            rich_information=True,
            summary_available_rows=8,
        )

        self.assertFalse(single.source_tabs_visible)
        self.assertEqual(single.workspace_height, multiple.workspace_height + 2)
        self.assertGreaterEqual(single.summary_rows, multiple.summary_rows)


if __name__ == '__main__':
    unittest.main()
