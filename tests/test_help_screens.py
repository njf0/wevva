"""Focused checks for contextual help and the shared modal presentation."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static

from wevva.app import Wevva
from wevva.screens.air_quality_help import AIR_QUALITY_HELP, AirQualityHelp
from wevva.screens.alerts_centre_screen import AlertsCentreScreen
from wevva.screens.author_screen import CREDITS, AuthorScreen
from wevva.screens.dashboard_screen import DashboardScreen
from wevva.screens.help import CONTEXT_HELP, HelpScreen, help_markdown
from wevva.screens.settings_screen import SettingsScreen
from wevva.screens.tropical_systems_screen import TropicalSystemsScreen
from wevva.screens.world_locations_screen import WorldLocationsScreen


def _settings_screen() -> SettingsScreen:
    return SettingsScreen(
        theme_name='textual-dark',
        emoji_enabled=False,
        warning_language='auto',
        temperature_unit='celsius',
        wind_speed_unit='kmh',
        precipitation_unit='mm',
        saved_default_location=None,
        current_location_label='Edinburgh, Scotland, United Kingdom',
    )


class _ModalApp(App[None]):
    def __init__(self, modal) -> None:
        super().__init__()
        self.modal = modal
        self.results: list[object] = []
        self.underlay: Static | None = None

    def compose(self) -> ComposeResult:
        self.underlay = Static('underlying workspace', id='underlying-workspace')
        yield self.underlay

    def on_mount(self) -> None:
        self.push_screen(self.modal, callback=self.results.append)


class HelpContentTests(unittest.TestCase):
    def test_each_workspace_gets_only_its_context_section(self) -> None:
        for context, (heading, _content) in CONTEXT_HELP.items():
            with self.subTest(context=context):
                rendered = help_markdown(context)
                self.assertIn('## General Wevva help', rendered)
                self.assertIn('### Keys available throughout Wevva', rendered)
                self.assertIn(f'## {heading}', rendered)
                self.assertLess(rendered.index(f'## {heading}'), rendered.index('## General Wevva help'))
                for other_context, (other_heading, _other_content) in CONTEXT_HELP.items():
                    if other_context != context and other_heading != heading:
                        self.assertNotIn(f'## {other_heading}\n', rendered)

    def test_help_uses_user_language_instead_of_layout_terms(self) -> None:
        for context in CONTEXT_HELP:
            with self.subTest(context=context):
                rendered = help_markdown(context).lower()
                for implementation_term in ('rail', 'modal', 'workspace', 'catalogue'):
                    self.assertNotIn(implementation_term, rendered)

    def test_shared_keys_have_separate_descriptions(self) -> None:
        rendered = help_markdown('dashboard')
        for key in ('u', 'h', '?', 'c', 'q', 'Esc'):
            with self.subTest(key=key):
                self.assertIn(f'- `{key}` — ', rendered)

    def test_air_quality_help_retains_terms_and_units(self) -> None:
        for expected in ('AQI', 'PM2.5', 'PM10', 'Ozone', 'Grass pollen', 'µg/m³', 'grains/m³'):
            with self.subTest(expected=expected):
                self.assertIn(expected, AIR_QUALITY_HELP)

    def test_credits_name_primary_sources(self) -> None:
        for expected in ('Open-Meteo', 'wevva-warnings', 'Natural Earth', 'Textual'):
            with self.subTest(expected=expected):
                self.assertIn(expected, CREDITS)

    def test_app_action_selects_the_active_workspace_context(self) -> None:
        expected_contexts = (
            (DashboardScreen, 'dashboard'),
            (WorldLocationsScreen, 'world-map'),
            (TropicalSystemsScreen, 'tropical-systems'),
            (AlertsCentreScreen, 'alerts-centre'),
        )
        for screen_type, expected in expected_contexts:
            with self.subTest(screen=screen_type.__name__):
                app = Mock(spec=Wevva)
                app.screen = Mock(spec=screen_type)
                app.weather_screen = Mock()
                app.push_screen = Mock()

                Wevva.action_help(app)

                opened = app.push_screen.call_args.args[0]
                self.assertIsInstance(opened, HelpScreen)
                self.assertEqual(opened.context, expected)

    def test_weather_keeps_its_focused_help_refinement(self) -> None:
        app = Mock(spec=Wevva)
        app.weather_screen = Mock()
        app.screen = app.weather_screen

        Wevva.action_help(app)

        app.weather_screen.action_help.assert_called_once_with()
        app.push_screen.assert_not_called()


class ModalPresentationTests(unittest.IsolatedAsyncioTestCase):
    async def test_modal_family_is_contained_at_supported_sizes(self) -> None:
        modal_specs = (
            (lambda: HelpScreen('dashboard'), '#help-container', 'Help'),
            (AirQualityHelp, '#air-quality-help-container', 'Air Quality Help'),
            (AuthorScreen, '#author-box', 'Credits'),
            (_settings_screen, '#settings-dialog', 'Settings'),
        )
        for size in ((80, 24), (120, 40)):
            for factory, selector, title in modal_specs:
                with self.subTest(size=size, modal=factory.__name__):
                    app = _ModalApp(factory())
                    async with app.run_test(size=size) as pilot:
                        await pilot.pause(0)
                        screen = app.screen
                        panel = screen.query_one(selector)

                        self.assertEqual(len(screen.query(Header)), 1)
                        self.assertEqual(len(screen.query(Footer)), 1)
                        self.assertTrue(screen.query_one(Header)._show_clock)
                        self.assertEqual(panel.border_title, title)
                        self.assertEqual(str(panel.styles.border_title_align), 'left')
                        self.assertTrue(panel.can_focus)
                        self.assertEqual(str(panel.styles.overflow_y), 'auto')
                        self.assertGreaterEqual(panel.region.x, 0)
                        self.assertGreaterEqual(panel.region.y, 1)
                        self.assertLessEqual(panel.region.right, size[0])
                        self.assertLessEqual(panel.region.bottom, size[1] - 1)

    async def test_long_modal_content_scrolls_inside_its_panel(self) -> None:
        for factory, selector in (
            (lambda: HelpScreen('alerts-centre'), '#help-container'),
            (_settings_screen, '#settings-dialog'),
        ):
            with self.subTest(modal=factory.__name__):
                app = _ModalApp(factory())
                async with app.run_test(size=(80, 24)) as pilot:
                    await pilot.pause(0)
                    panel = app.screen.query_one(selector)
                    panel.focus()
                    await pilot.press('pagedown')
                    await pilot.pause(0)

                    self.assertGreater(panel.scroll_y, 0)
                    self.assertEqual(panel.region.y, 1)
                    self.assertEqual(panel.region.bottom, 23)

    async def test_escape_closes_each_modal_without_replacing_underlay(self) -> None:
        for factory in (lambda: HelpScreen('weather'), AirQualityHelp, AuthorScreen, _settings_screen):
            with self.subTest(modal=factory.__name__):
                app = _ModalApp(factory())
                async with app.run_test(size=(80, 24)) as pilot:
                    underlay = app.screen_stack[0]
                    await pilot.press('escape')
                    await pilot.pause(0)

                    self.assertIs(app.screen, underlay)
                    self.assertEqual(app.results, [None])
                    self.assertEqual(str(app.underlay.render()), 'underlying workspace')


if __name__ == '__main__':
    unittest.main()
