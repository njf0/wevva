"""Concise application help with an active-workspace section."""

from __future__ import annotations

from typing import Literal

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Markdown


HelpContext = Literal[
    'weather',
    'dashboard',
    'world-map',
    'tropical-systems',
    'alerts-centre',
]


GENERAL_HELP = """
## General Wevva help

- Dashboard is Wevva's home screen. It brings forecasts, saved places, tropical systems, and weather alerts together.
- Use Tab and Shift+Tab to move between controls. Use the arrow keys to move within lists, tables, maps, and tabs.
- Press Enter or Space to open the selected item or confirm a choice. Most controls can also be clicked.
- When the terminal is smaller, Wevva divides the same information across tabs so that it remains usable.

### Keys available throughout Wevva

- `u` — Open Settings to change units, appearance, warning language, or the saved default location.
- `h` — Open Help for the screen you are currently using.
- `?` — Open the same contextual Help as `h`.
- `c` — Open Credits and data-source information.
- `q` — Quit Wevva.
- `Esc` — Close the current pop-up without applying an action.
"""


CONTEXT_HELP: dict[HelpContext, tuple[str, str]] = {
    'weather': (
        'Weather',
        """
- Move through the hourly and daily forecasts to update the conditions shown above them.
- Use Saved Locations to choose another saved forecast. Warning Details shows the complete alert.

### Weather keys

- `s` — Search for a different forecast location.
- `r` — Refresh the forecast for the current location.
- `a` — Add the current location to Saved Locations.
- `d` — Delete the location currently selected in Saved Locations.
- `l` — Move to Saved Locations so you can choose another forecast.
- `i` — Open Warning Details for the current location.
- `b` — Return to Dashboard.
""",
    ),
    'dashboard': (
        'Dashboard',
        """
- Select a saved place on the map to see its forecast without leaving Dashboard.
- Select a storm or alert to see its map and details.
- On a smaller terminal, use the Forecast, Map, Tropical, Selected Alert, and Recent Alerts tabs.

### Dashboard keys

- `w` — Open the complete Weather forecast for the current location.
- `m` — Open the World Map of saved locations.
- `t` — Open Tropical Systems to investigate active storms.
- `g` — Open Alerts Centre to browse warnings by country.
- `r` — Check the Dashboard for updated weather alerts.
- `Left` — Move to the previous selectable label on the map.
- `Right` — Move to the next selectable label on the map.
""",
    ),
    'world-map': (
        'World Map',
        """
- The map shows your saved places and their latest available temperatures.
- Open a place to view its complete Weather forecast.

### World Map keys

- `Left` — Move to the previous saved place on the map.
- `Right` — Move to the next saved place on the map.
- `Enter` — Open the selected place in Weather.
- `Space` — Open the selected place in Weather.
- `b` — Return to Dashboard.
""",
    ),
    'tropical-systems': (
        'Tropical Systems',
        """
- Choose a storm, then choose a weather agency when more than one is reporting it.
- Use Track and Cone or an available advisory tab to read that agency's information.
- Open a labelled place on the storm map to view its Weather forecast.

### Tropical Systems keys

- `r` — Refresh the active storms, agency reports, and available advisories.
- `Enter` — Open a selected map place in Weather.
- `Space` — Open a selected map place in Weather.
- `b` — Return to Dashboard.
""",
    ),
    'alerts-centre': (
        'Alerts Centre',
        """
- Choose a country, then use Filters to narrow the list or change its order.
- Move through alerts to preview each warning area. Open one to keep it selected and read the full alert.
- Open a labelled place on the map to view its Weather forecast.

### Alerts Centre keys

- `r` — Check the selected country for updated alerts.
- `Enter` — Open the selected alert or map place.
- `Space` — Open the selected alert or map place.
- `b` — Return to Dashboard.
""",
    ),
}


def help_markdown(context: HelpContext) -> str:
    """Return common help followed by one explicit workspace section."""

    title, content = CONTEXT_HELP[context]
    return f"""## {title}

{content}

{GENERAL_HELP}
"""


class HelpScreen(ModalScreen[None]):
    """Scrollable common help plus guidance for the opening workspace."""

    BINDINGS = [('escape', 'dismiss', 'Close')]

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
        background: $background;
        hatch: right $background-lighten-1;
    }

    HelpScreen > #help-container {
        width: 78;
        max-width: 96%;
        height: auto;
        max-height: 100%;
        padding: 0;
        overflow-y: auto;
        border: round $primary;
        border-title-color: $primary;
        border-title-align: left;
        background: $panel;
    }

    #help-content {
        width: 100%;
        height: auto;
        background: $panel;
    }
    """

    def __init__(self, context: HelpContext = 'dashboard') -> None:
        super().__init__()
        self.context = context

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with VerticalScroll(id='help-container') as container:
            container.border_title = 'Help'
            yield Markdown(help_markdown(self.context), id='help-content')
        yield Footer()
