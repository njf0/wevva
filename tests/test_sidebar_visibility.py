"""Sidebar visibility and shortcut-state checks."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from textual.app import App

from wevva.screens.weather_screen import WeatherScreen


class _SidebarTestApp(App):
    """Minimal host for exercising screen bindings without a weather fetch."""

    def __init__(self) -> None:
        super().__init__()
        self.location = None
        self.saved_locations = []

    def on_mount(self) -> None:
        self.push_screen(WeatherScreen())


class SidebarVisibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.screen = WeatherScreen()
        self.screen.saved_locations_sidebar = SimpleNamespace(display=False)
        self.screen.alert_details_sidebar = SimpleNamespace(display=False)

    def test_initial_visibility_defaults_follow_terminal_width(self) -> None:
        self.assertEqual(
            WeatherScreen._sidebar_defaults_for_width(143),
            (False, False),
        )
        self.assertEqual(
            WeatherScreen._sidebar_defaults_for_width(144),
            (True, False),
        )
        self.assertEqual(
            WeatherScreen._sidebar_defaults_for_width(191),
            (True, False),
        )
        self.assertEqual(
            WeatherScreen._sidebar_defaults_for_width(192),
            (True, True),
        )

    def test_location_binding_reflects_current_visibility(self) -> None:
        self.screen._locations_sidebar_has_content = True

        self.screen.set_saved_locations_sidebar_visible(True)

        self.assertTrue(self.screen.saved_locations_sidebar_visible)
        self.assertTrue(self.screen.check_action('hide_saved_locations', ()))
        self.assertFalse(self.screen.check_action('show_saved_locations', ()))

        self.screen.set_saved_locations_sidebar_visible(False)

        self.assertFalse(self.screen.saved_locations_sidebar_visible)
        self.assertFalse(self.screen.check_action('hide_saved_locations', ()))
        self.assertTrue(self.screen.check_action('show_saved_locations', ()))

    def test_details_binding_reflects_current_visibility(self) -> None:
        self.screen._alert_details_sidebar_has_content = True

        self.screen.set_alert_details_sidebar_visible(True)

        self.assertTrue(self.screen.alert_details_sidebar_visible)
        self.assertTrue(self.screen.check_action('hide_alert_details', ()))
        self.assertFalse(self.screen.check_action('show_alert_details', ()))

        self.screen.set_alert_details_sidebar_visible(False)

        self.assertFalse(self.screen.alert_details_sidebar_visible)
        self.assertFalse(self.screen.check_action('hide_alert_details', ()))
        self.assertTrue(self.screen.check_action('show_alert_details', ()))

    def test_sidebar_bindings_use_state_specific_labels(self) -> None:
        labels = {action: label for _, action, label in WeatherScreen.BINDINGS}

        self.assertEqual(labels['show_saved_locations'], 'Show locations')
        self.assertEqual(labels['hide_saved_locations'], 'Hide locations')
        self.assertEqual(labels['show_alert_details'], 'Show details')
        self.assertEqual(labels['hide_alert_details'], 'Hide details')


class SidebarBindingIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_footer_binding_text_changes_after_each_toggle(self) -> None:
        app = _SidebarTestApp()

        async with app.run_test(size=(200, 60)) as pilot:
            await pilot.pause()
            screen = app.screen
            self.assertIsInstance(screen, WeatherScreen)
            screen._locations_sidebar_has_content = True
            screen._alert_details_sidebar_has_content = True
            screen._sync_sidebar_visibility()

            active_bindings = screen.active_bindings
            self.assertEqual(active_bindings['l'].binding.description, 'Hide locations')
            self.assertEqual(active_bindings['i'].binding.description, 'Hide details')

            await pilot.press('l', 'i')
            await pilot.pause()

            active_bindings = screen.active_bindings
            self.assertFalse(screen.saved_locations_sidebar_visible)
            self.assertFalse(screen.alert_details_sidebar_visible)
            self.assertEqual(active_bindings['l'].binding.description, 'Show locations')
            self.assertEqual(active_bindings['i'].binding.description, 'Show details')

    async def test_resize_collapses_and_restores_sidebars_that_no_longer_fit(self) -> None:
        app = _SidebarTestApp()

        async with app.run_test(size=(200, 60)) as pilot:
            await pilot.pause()
            screen = app.screen
            self.assertIsInstance(screen, WeatherScreen)
            screen._locations_sidebar_has_content = True
            screen._alert_details_sidebar_has_content = True
            screen._sync_sidebar_visibility()

            await pilot.resize_terminal(191, 60)
            await pilot.pause()
            self.assertTrue(screen.saved_locations_sidebar_visible)
            self.assertFalse(screen.alert_details_sidebar_visible)

            await pilot.resize_terminal(143, 60)
            await pilot.pause()
            self.assertFalse(screen.saved_locations_sidebar_visible)
            self.assertFalse(screen.alert_details_sidebar_visible)

            await pilot.resize_terminal(200, 60)
            await pilot.pause()
            self.assertTrue(screen.saved_locations_sidebar_visible)
            self.assertTrue(screen.alert_details_sidebar_visible)


if __name__ == '__main__':
    unittest.main()
