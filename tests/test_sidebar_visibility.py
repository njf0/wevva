"""Sidebar visibility and shortcut-state checks."""

from __future__ import annotations

import unittest

from textual.app import App

from wevva.layout import AuxiliaryPresentation, auxiliary_presentations_for
from wevva.location_metadata import LocationMetadata
from wevva.screens.weather_screen import WeatherScreen
from wevva.widgets.saved_locations import SavedLocationsModal, SavedLocationsSidebar


class _SidebarTestApp(App):
    """Minimal host for exercising screen bindings without a weather fetch."""

    def __init__(self) -> None:
        super().__init__()
        self.location = LocationMetadata(
            latitude=51.5072,
            longitude=-0.1276,
            name='London',
            country='United Kingdom',
            country_code='GB',
        )
        self.saved_locations = [self.location]

    def on_mount(self) -> None:
        self.push_screen(WeatherScreen())


class SidebarVisibilityTests(unittest.TestCase):
    def test_automatic_rail_allocation_preserves_the_central_canvas(self) -> None:
        for width, expected in (
            (143, (143, AuxiliaryPresentation.MODAL, AuxiliaryPresentation.MODAL)),
            (144, (102, AuxiliaryPresentation.MODAL, AuxiliaryPresentation.SIDEBAR)),
            (185, (143, AuxiliaryPresentation.MODAL, AuxiliaryPresentation.SIDEBAR)),
            (186, (102, AuxiliaryPresentation.SIDEBAR, AuxiliaryPresentation.SIDEBAR)),
        ):
            with self.subTest(width=width):
                self.assertEqual(
                    auxiliary_presentations_for(
                        width,
                        locations_available=True,
                        warning_details_available=True,
                    ),
                    expected,
                )

    def test_locations_use_the_first_rail_when_there_is_no_warning(self) -> None:
        self.assertEqual(
            auxiliary_presentations_for(
                144,
                locations_available=True,
                warning_details_available=False,
            ),
            (102, AuxiliaryPresentation.SIDEBAR, AuxiliaryPresentation.MODAL),
        )

    def test_context_sidecar_consumes_surplus_before_auxiliary_rails(self) -> None:
        self.assertEqual(
            auxiliary_presentations_for(
                186,
                locations_available=True,
                warning_details_available=True,
                context_sidecar=True,
            ),
            (102, AuxiliaryPresentation.MODAL, AuxiliaryPresentation.SIDEBAR),
        )
        self.assertEqual(
            auxiliary_presentations_for(
                228,
                locations_available=True,
                warning_details_available=True,
                context_sidecar=True,
            ),
            (102, AuxiliaryPresentation.SIDEBAR, AuxiliaryPresentation.SIDEBAR),
        )

    def test_sidebar_bindings_are_access_actions_not_visibility_toggles(self) -> None:
        labels = {action: label for _, action, label in WeatherScreen.BINDINGS}

        self.assertEqual(labels['locations'], 'Locations')
        self.assertEqual(labels['alert_details'], 'Warning details')


class SidebarBindingIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_saved_location_list_uses_a_narrow_scrollbar(self) -> None:
        app = _SidebarTestApp()

        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            sidebar = app.screen.query_one(SavedLocationsSidebar)

            self.assertEqual(sidebar.locations.styles.scrollbar_size_vertical, 1)

    async def test_access_bindings_focus_automatic_rails(self) -> None:
        app = _SidebarTestApp()

        async with app.run_test(size=(240, 60)) as pilot:
            await pilot.pause()
            screen = app.screen
            self.assertIsInstance(screen, WeatherScreen)
            screen.main_panel.display = True
            screen._locations_sidebar_has_content = True
            screen._alert_details_sidebar_has_content = True
            screen._sync_sidebar_visibility()

            active_bindings = screen.active_bindings
            self.assertEqual(active_bindings['l'].binding.description, 'Locations')
            self.assertEqual(active_bindings['i'].binding.description, 'Warning details')

            await pilot.press('l')
            await pilot.pause()
            self.assertIs(app.focused, screen.saved_locations_sidebar.locations)

            await pilot.press('i')
            await pilot.pause()
            self.assertTrue(screen.saved_locations_sidebar_visible)
            self.assertTrue(screen.alert_details_sidebar_visible)

    async def test_locations_binding_uses_modal_when_no_rail_fits(self) -> None:
        app = _SidebarTestApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            screen = app.screen
            self.assertIsInstance(screen, WeatherScreen)
            screen._locations_sidebar_has_content = True
            screen._sync_sidebar_visibility()

            await pilot.press('l')
            await pilot.pause()

            self.assertIsInstance(app.screen, SavedLocationsModal)
            self.assertEqual(app.screen.selected_location(), app.location)
            self.assertEqual(screen.selected_saved_location(), app.location)

    async def test_resize_collapses_and_restores_sidebars_that_no_longer_fit(self) -> None:
        app = _SidebarTestApp()

        async with app.run_test(size=(240, 60)) as pilot:
            await pilot.pause()
            screen = app.screen
            self.assertIsInstance(screen, WeatherScreen)
            screen.main_panel.display = True
            screen._locations_sidebar_has_content = True
            screen._alert_details_sidebar_has_content = True
            screen._sync_sidebar_visibility()

            await pilot.resize_terminal(227, 60)
            await pilot.pause()
            self.assertFalse(screen.saved_locations_sidebar_visible)
            self.assertTrue(screen.alert_details_sidebar_visible)

            await pilot.resize_terminal(228, 60)
            await pilot.pause()
            self.assertTrue(screen.saved_locations_sidebar_visible)
            self.assertTrue(screen.alert_details_sidebar_visible)
            self.assertEqual(screen.main_panel.region.width, 144)

            await pilot.resize_terminal(143, 60)
            await pilot.pause()
            self.assertFalse(screen.saved_locations_sidebar_visible)
            self.assertFalse(screen.alert_details_sidebar_visible)

            await pilot.resize_terminal(240, 60)
            await pilot.pause()
            self.assertTrue(screen.saved_locations_sidebar_visible)
            self.assertTrue(screen.alert_details_sidebar_visible)


if __name__ == '__main__':
    unittest.main()
