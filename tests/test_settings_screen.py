"""Settings modal result and guidance regressions."""

from __future__ import annotations

import unittest

from textual.app import App
from textual.widgets import Button, Static

from wevva.screens.settings_screen import SettingsScreen


def _screen(*, saved_default_location: str | None = None) -> SettingsScreen:
    return SettingsScreen(
        theme_name='textual-dark',
        emoji_enabled=False,
        warning_language='auto',
        temperature_unit='celsius',
        wind_speed_unit='kmh',
        precipitation_unit='mm',
        saved_default_location=saved_default_location,
        current_location_label='Edinburgh, Scotland, United Kingdom',
    )


class _SettingsApp(App[None]):
    def __init__(self, screen: SettingsScreen) -> None:
        super().__init__()
        self.settings_screen = screen
        self.results: list[dict | None] = []

    def on_mount(self) -> None:
        self.push_screen(self.settings_screen, callback=self.results.append)


class SettingsCopyTests(unittest.TestCase):
    def test_default_location_copy_handles_missing_saved_default(self) -> None:
        self.assertEqual(
            _screen()._default_location_options()[0],
            ('Keep no saved default location', 'keep'),
        )
        self.assertEqual(
            _screen(saved_default_location='Glasgow')._default_location_options()[0],
            ('Keep saved (Glasgow)', 'keep'),
        )


class SettingsResultTests(unittest.IsolatedAsyncioTestCase):
    async def _press(self, button_id: str) -> tuple[dict, dict[str, str]]:
        screen = _screen()
        app = _SettingsApp(screen)
        notes: dict[str, str] = {}
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0)
            for note_id in (
                'settings-save-note',
                'emoji-note',
                'warning-language-note',
                'default-location-note',
            ):
                notes[note_id] = str(screen.query_one(f'#{note_id}', Static).render())

            button = screen.query_one(f'#{button_id}', Button)
            screen.on_button_pressed(Button.Pressed(button))
            await pilot.pause(0)

        self.assertEqual(len(app.results), 1)
        result = app.results[0]
        assert result is not None
        return result, notes

    async def test_apply_returns_session_only_payload(self) -> None:
        result, notes = await self._press('apply-button')

        self.assertFalse(result['save_defaults'])
        self.assertIn('Apply changes this session', notes['settings-save-note'])
        self.assertIn('provider default', notes['warning-language-note'])
        self.assertIn('terminal, font, and locale', notes['emoji-note'])
        self.assertIn('only when you choose Save Defaults', notes['default-location-note'])

    async def test_save_defaults_returns_persistent_payload(self) -> None:
        result, _notes = await self._press('save-button')

        self.assertTrue(result['save_defaults'])
        self.assertEqual(result['default_location_action'], 'keep')
        self.assertEqual(result['warning_language'], 'auto')


if __name__ == '__main__':
    unittest.main()
