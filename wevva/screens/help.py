"""Help screen.

Shows shortcuts and a quick usage note.
"""

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Footer, Markdown


class HelpScreen(ModalScreen[None]):
    # Keyboard shortcut to close
    BINDINGS = [
        ('escape', "dismiss('')", 'Close'),
    ]

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
        & > #help-container {
            width: 78;
            height: auto;
            max-height: 90%;
            padding: 1 2;
            overflow-y: auto;
            border: heavy $background-lighten-2;
            border-title-color: $text;
            border-title-background: $background;
            border-title-style: bold;
            background: $background;
        }
    }
    """

    def compose(self) -> ComposeResult:
        # Build a simple box + markdown content
        with Container(id='help-container') as container:
            container.border_title = 'Wevva Help'
            yield Markdown(
                """
## Wevva Quick Guide

`wevva` is a Textual weather TUI powered by Open-Meteo.
You can launch it directly with `uvx wevva`.

## First Steps

1. Press `s` to open place search.
2. Type a location name and choose a result.
3. The app fetches current, hourly, daily, and context data.

## Key Bindings

- `s` Search for a place
- `r` Refresh weather for current location
- `a` Save the current location
- `d` Delete the highlighted saved location
- `l` Show or hide saved locations
- `u` Open settings
- `h` Open this help screen
- `q` Quit
- `Esc` Close modal screens

## Navigation Notes

- Use arrow keys/tab to move focus across tables and widgets.
- Highlighting rows/columns updates linked weather context.
- If a fetch fails, use `r` to retry or `s` to choose another place.

## Alerts

- Active weather alerts are shown on the main weather screen when present.
- Alerts load separately from the main forecast, so slower warning providers do not hold up the rest of the UI.
- Where a provider includes an official warning URL, `wevva` shows a direct link on the alert card.

## CLI Highlights

- `wevva setup` launches guided setup for defaults.
- `wevva setup --no-launch` saves setup and exits.
- `wevva --location "Edinburgh"` starts directly at a location.
- `wevva --theme gruvbox` overrides your saved theme for one run.
- `wevva --emoji/--no-emoji` toggles emoji for one run.

## Preferences

Saved preferences are stored in:
`~/.config/wevva/config.json`

This includes units, theme, emoji toggle, and default location.

## Emoji Notice

Emoji rendering depends on your terminal, font, and locale settings.
If symbols look misaligned, try `--no-emoji`.
"""
            )
        yield Footer()
