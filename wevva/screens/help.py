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

Dashboard is the navigation hub:

- `w` Open the full Weather screen
- `m` Open the interactive saved-locations world map
- `t` Investigate active tropical systems
- `g` Open the country Alerts Centre
- `r` Refresh the severe-weather bulletin

On the Weather screen:

- `s` Search for a place
- `r` Refresh weather for current location
- `a` Save the current location
- `d` Delete the highlighted saved location
- `l` Focus saved locations or open their modal
- `i` Focus warning details or open their modal
- `b` Return to the Dashboard

Shared throughout the application:

- `u` Open settings
- `h` or `?` Open this help screen
- `c` Open credits
- `q` Quit
- `Esc` Close modal screens

## Navigation Notes

- Use arrow keys/tab to move focus across tables and widgets.
- On the World Map, use left/right to move between locations and Enter to open one.
- On the World Map, Tropical Systems, and Alerts Centre, press `b` for Dashboard.
- Country-map city labels can be clicked or focused and activated with Enter.
- On Tropical Systems, `r` refreshes active systems and their source products.
- Highlighting rows/columns updates linked weather context.
- If a fetch fails, use `r` to retry or `s` to choose another place.

## Alerts

- Current and upcoming weather alerts appear as a one-line summary on the main weather screen.
- Alerts load separately from the main forecast, so slower warning providers do not hold up the rest of the UI.
- Activate the summary with the mouse, Enter, or Space to open the tabbed warning reader; its provider document scrolls independently.
- Press `g` for country-level discovery, warning polygons, provider documents, and selectable settlement forecasts.
- Where a provider includes an official warning URL, `wevva` shows a direct link on the alert panel.
- Warning maps use full Braille cells for filled interiors and partial Braille cells along geographic edges.
- The Tropical Systems screen keeps global storm investigation separate from location-specific alerts and loads official issuing-centre products only when selected.

## CLI Highlights

- `wevva setup` launches guided setup for defaults.
- `wevva setup --no-launch` saves setup and exits.
- `wevva --location "Edinburgh"` starts directly at a location.
- `wevva --theme gruvbox` overrides your saved theme for one run.
- `wevva --emoji/--no-emoji` toggles emoji for one run.

## Preferences

Saved preferences are stored in:
`~/.config/wevva/config.json`

This includes units, theme, emoji toggle, warning-map renderer, and default location.

## Emoji Notice

Emoji rendering depends on your terminal, font, and locale settings.
If symbols look misaligned, try `--no-emoji`.
"""
            )
        yield Footer()
