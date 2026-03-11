"""Settings screen for session and default preferences."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.theme import BUILTIN_THEMES
from textual.widgets import Button, Footer, Header, Label, Select, Static


class SettingsScreen(ModalScreen[dict[str, Any] | None]):
    """Modal screen for adjusting display, unit, and default-location preferences."""

    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
        content-align: center middle;
        align-horizontal: center;
        align-vertical: middle;
    }

    #settings-dialog {
        align: center middle;
        align-horizontal: center;
        align-vertical: middle;
        content-align: center middle;
        width: 60;
        height: auto;
        padding: 2 4;
        border: thick $primary;
        background: $panel;
    }

    #settings-dialog Label {
        margin: 1 0;
    }

    #settings-dialog Select {
        width: 100%;
        margin-bottom: 1;
    }

    #settings-dialog .button-row {
        layout: horizontal;
        width: 100%;
        height: auto;
        margin-top: 2;
        align-horizontal: center;
    }

    #settings-dialog Button {
        margin: 0 1;
    }
    """

    BINDINGS = [('escape', 'dismiss', 'Close')]

    def __init__(
        self,
        *,
        theme_name: str,
        emoji_enabled: bool,
        temperature_unit: str,
        wind_speed_unit: str,
        precipitation_unit: str,
        saved_default_location: str | None,
        current_location_label: str | None,
    ):
        """Initialize settings screen with current in-app and saved preferences."""
        super().__init__()
        self.theme_name = theme_name
        self.emoji_enabled = emoji_enabled
        self.temperature_unit = temperature_unit
        self.wind_speed_unit = wind_speed_unit
        self.precipitation_unit = precipitation_unit
        self.saved_default_location = saved_default_location
        self.current_location_label = current_location_label

    def compose(self) -> ComposeResult:
        """Build settings UI."""
        yield Header(show_clock=True, id='settings-header')

        with Container(id='settings-dialog'):
            yield Static('[bold]Settings[/]', id='settings-title')
            yield Label('Theme:')
            yield Select(
                options=self._theme_options(),
                value=self.theme_name,
                id='theme-select',
            )

            yield Label('Emoji Rendering:')
            yield Select(
                options=[
                    ('Enabled', 'enabled'),
                    ('Disabled', 'disabled'),
                ],
                value='enabled' if self.emoji_enabled else 'disabled',
                id='emoji-select',
            )
            yield Static(
                '[dim]Emoji rendering varies by terminal, font, and locale.[/]',
                id='emoji-note',
            )

            yield Label('Temperature Unit:')
            yield Select(
                options=[
                    ('Celsius (°C)', 'celsius'),
                    ('Fahrenheit (°F)', 'fahrenheit'),
                ],
                value=self.temperature_unit,
                id='temp-select',
            )

            yield Label('Wind Speed Unit:')
            yield Select(
                options=[
                    ('Kilometers per hour (km/h)', 'kmh'),
                    ('Meters per second (m/s)', 'ms'),
                    ('Miles per hour (mph)', 'mph'),
                    ('Knots (kn)', 'kn'),
                ],
                value=self.wind_speed_unit,
                id='wind-select',
            )

            yield Label('Precipitation Unit:')
            yield Select(
                options=[
                    ('Millimeters (mm)', 'mm'),
                    ('Inches (in)', 'inch'),
                ],
                value=self.precipitation_unit,
                id='precip-select',
            )

            yield Label('Default Location:')
            yield Select(
                options=self._default_location_options(),
                value='keep',
                id='default-location-select',
            )

            with Container(classes='button-row'):
                yield Button('Apply', variant='primary', id='apply-button')
                yield Button('Save Defaults', variant='success', id='save-button')
                yield Button('Cancel', id='cancel-button')

        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks and return a normalized settings payload."""
        if event.button.id == 'cancel-button':
            self.dismiss(None)
            return

        settings = self._collect_settings()
        settings['save_defaults'] = event.button.id == 'save-button'
        self.dismiss(settings)

    def _collect_settings(self) -> dict[str, Any]:
        """Collect selected values from all controls."""
        return {
            'theme': self.query_one('#theme-select', Select).value,
            'emoji_enabled': self.query_one('#emoji-select', Select).value == 'enabled',
            'temperature_unit': self.query_one('#temp-select', Select).value,
            'wind_speed_unit': self.query_one('#wind-select', Select).value,
            'precipitation_unit': self.query_one('#precip-select', Select).value,
            'default_location_action': self.query_one('#default-location-select', Select).value,
        }

    def _theme_options(self) -> list[tuple[str, str]]:
        """Return built-in themes with current theme first."""
        ordered = sorted(BUILTIN_THEMES)
        if self.theme_name in ordered:
            ordered.remove(self.theme_name)
            ordered.insert(0, self.theme_name)
        else:
            ordered.insert(0, self.theme_name)
        return [(name, name) for name in ordered]

    def _default_location_options(self) -> list[tuple[str, str]]:
        """Return default-location actions for this session context."""
        options = [(f'Keep saved ({self.saved_default_location})', 'keep')]
        if self.current_location_label:
            options.append(('Set to current location', 'use_current'))
        options.append(('Clear saved default location', 'clear'))
        return options
