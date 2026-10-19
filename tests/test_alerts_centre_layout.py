"""Slice C responsive budgeting and mounted-pane behavior."""

from __future__ import annotations

import unittest

from textual.app import App
from textual.containers import Container
from textual.widgets import Tabs
from wevva_warnings import Alert

from wevva.alerts_centre_layout import (
    AlertsCentrePresentation,
    alerts_centre_layout_for,
)
from wevva.screens.alerts_centre_screen import AlertsCentreScreen
from wevva.services.country_alerts import SupportedAlertCountry


GERMANY = SupportedAlertCountry('DE', 'Germany')


class AlertsCentreLayoutBudgetTests(unittest.TestCase):
    def test_representative_terminal_sizes_select_each_topology(self) -> None:
        expected = {
            (180, 50): AlertsCentrePresentation.WIDE,
            (140, 40): AlertsCentrePresentation.WIDE,
            (100, 30): AlertsCentrePresentation.STACKED,
            (80, 24): AlertsCentrePresentation.TABBED,
            (79, 24): AlertsCentrePresentation.SINGLE,
            (100, 23): AlertsCentrePresentation.SINGLE,
        }
        for size, presentation in expected.items():
            with self.subTest(size=size):
                self.assertEqual(
                    alerts_centre_layout_for(*size).presentation,
                    presentation,
                )

    def test_navigation_is_slightly_wider_without_overrunning_compact_layouts(self) -> None:
        expected = {
            (180, 50): 44,
            (140, 40): 35,
            (100, 30): 33,
            (80, 24): 28,
        }
        for size, navigation_width in expected.items():
            with self.subTest(size=size):
                self.assertEqual(
                    alerts_centre_layout_for(*size).navigation_width,
                    navigation_width,
                )

class _EmptyService:
    last_country_code: str | None = None

    async def get_alerts(self, *_args, **_kwargs):
        return [
            Alert(
                id='responsive-warning',
                source='fixture',
                event='Wind Warning',
                headline='Responsive warning',
                severity='Moderate',
                description='Provider document.',
            )
        ]


class _LayoutApp(App[None]):
    def __init__(self, screen: AlertsCentreScreen) -> None:
        super().__init__()
        self.test_screen = screen

    async def on_mount(self) -> None:
        await self.push_screen(self.test_screen)


class AlertsCentreResponsiveScreenTests(unittest.IsolatedAsyncioTestCase):
    async def test_tabs_and_resizes_keep_the_same_mounted_panes(self) -> None:
        screen = AlertsCentreScreen(
            service=_EmptyService(),  # type: ignore[arg-type]
            countries=[GERMANY],
        )
        app = _LayoutApp(screen)

        async with app.run_test(size=(80, 24)) as pilot:
            for _ in range(3):
                await pilot.pause()
            navigation = screen.query_one('#alerts-centre-navigation', Container)
            map_pane = screen.query_one('#alerts-centre-map-pane', Container)
            document = screen.query_one('#alerts-centre-document-pane', Container)
            pane_ids = tuple(map(id, (navigation, map_pane, document)))

            self.assertEqual(screen._presentation, AlertsCentrePresentation.TABBED)
            self.assertTrue(screen.country_select.compact)
            self.assertEqual(screen.country_select.region.height, 1)
            self.assertEqual(screen.alert_filter_button.region.height, 1)
            self.assertEqual(screen.alert_filter_button.variant, 'primary')
            self.assertEqual(screen.country_map.max_city_labels, 2)
            self.assertIsNone(screen.selected_alert_key)
            self.assertEqual(document.border_title, 'Alert Detail')
            self.assertEqual(
                screen.country_map.border_title,
                'Map of Alerts for Germany',
            )
            self.assertTrue(navigation.display)
            self.assertTrue(map_pane.display)
            self.assertFalse(document.display)

            workspace_tabs = screen.query_one('#alerts-centre-workspace-tabs', Tabs)
            workspace_tabs.active = 'alerts-centre-workspace-details'
            await pilot.pause()
            self.assertFalse(map_pane.display)
            self.assertTrue(document.display)

            await pilot.resize_terminal(72, 20)
            await pilot.pause()
            self.assertEqual(screen._presentation, AlertsCentrePresentation.SINGLE)
            self.assertTrue(navigation.display)
            self.assertFalse(screen.query_one('#alerts-centre-right', Container).display)

            pane_tabs = screen.query_one('#alerts-centre-pane-tabs', Tabs)
            pane_tabs.active = 'alerts-centre-pane-map'
            await pilot.pause()
            self.assertFalse(navigation.display)
            self.assertTrue(map_pane.display)

            await pilot.resize_terminal(140, 40)
            await pilot.pause()
            self.assertEqual(screen._presentation, AlertsCentrePresentation.WIDE)
            self.assertTrue(navigation.display)
            self.assertTrue(map_pane.display)
            self.assertTrue(document.display)
            self.assertFalse(screen.country_select.compact)
            self.assertEqual(screen.country_map.max_city_labels, 8)
            self.assertEqual(navigation.region.width, document.region.width)
            self.assertIsNotNone(
                screen.query_one('#alerts-centre-body', Container).styles.hatch
            )
            self.assertIsNotNone(
                screen.query_one(
                    '#alerts-centre-right-content',
                    Container,
                ).styles.hatch
            )
            self.assertEqual(tuple(map(id, (navigation, map_pane, document))), pane_ids)
            self.assertIsNone(screen.selected_alert_key)


if __name__ == '__main__':
    unittest.main()
