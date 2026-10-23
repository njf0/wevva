"""Focused binding ownership checks for the Dashboard navigation hub."""

import unittest

from textual.binding import Binding

from wevva.app import Wevva
from wevva.screens.alerts_centre_screen import AlertsCentreScreen
from wevva.screens.dashboard_screen import DashboardScreen
from wevva.screens.tropical_systems_screen import TropicalSystemsScreen
from wevva.screens.weather_screen import WeatherScreen
from wevva.screens.world_locations_screen import WorldLocationsScreen


WORKSPACE_LABELS = {
    'Weather',
    'World Map',
    'Tropical Systems',
    'Alerts Centre',
    'Dashboard',
}


def _visible_bindings(bindings) -> list[tuple[str, str, str]]:
    visible = []
    for binding in bindings:
        if isinstance(binding, Binding):
            if binding.show:
                visible.append(
                    (binding.key, binding.action, binding.description)
                )
        else:
            visible.append(binding)
    return visible


class NavigationBindingTests(unittest.TestCase):
    def test_shared_utilities_have_one_consistent_order(self) -> None:
        self.assertEqual(
            _visible_bindings(Wevva.BINDINGS),
            [
                ('u', 'settings', 'Settings'),
                ('h', 'help', 'Help'),
                ('c', 'credits', 'Credits'),
                ('q', 'quit', 'Quit'),
            ],
        )

    def test_dashboard_exposes_every_workspace_in_navigation_order(self) -> None:
        visible = _visible_bindings(DashboardScreen.BINDINGS)

        self.assertEqual(
            [binding for binding in visible if binding[2] in WORKSPACE_LABELS],
            [
                ('w', 'back', 'Weather'),
                ('m', 'world_map', 'World Map'),
                ('t', 'tropical_systems', 'Tropical Systems'),
                ('g', 'alerts_centre', 'Alerts Centre'),
            ],
        )

    def test_other_workspaces_only_link_to_dashboard(self) -> None:
        for screen in (
            WeatherScreen,
            WorldLocationsScreen,
            TropicalSystemsScreen,
            AlertsCentreScreen,
        ):
            with self.subTest(screen=screen.__name__):
                visible = _visible_bindings(screen.BINDINGS)
                self.assertEqual(
                    [
                        (binding[0], binding[2])
                        for binding in visible
                        if binding[2] in WORKSPACE_LABELS
                    ],
                    [('b', 'Dashboard')],
                )


if __name__ == '__main__':
    unittest.main()
