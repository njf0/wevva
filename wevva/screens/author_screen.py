"""Project credits and primary data-source acknowledgements."""

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Markdown


CREDITS = """
[Wevva](https://github.com/njf0/wevva)

Created by **Nick Ferguson** — <nick.ferguson@ed.ac.uk>

Weather, geocoding, and air-quality data are provided by [Open-Meteo](https://open-meteo.com/). Weather warnings and tropical products are normalised by [wevva-warnings](https://github.com/njf0/wevva-warnings) from participating official providers.

Maps use public-domain [Natural Earth](https://www.naturalearthdata.com/) data. The terminal interface is built with [Textual](https://textual.textualize.io/).
"""


class AuthorScreen(ModalScreen[None]):
    """Compact credits screen."""

    BINDINGS = [('escape', 'dismiss', 'Close')]

    DEFAULT_CSS = """
    AuthorScreen {
        align: center middle;
        background: $background;
        hatch: right $background-lighten-1;
    }

    AuthorScreen > #author-box {
        width: 64;
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

    #credits-content {
        width: 100%;
        height: auto;
        background: $panel;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with VerticalScroll(id='author-box') as container:
            container.border_title = 'Credits'
            yield Markdown(CREDITS, id='credits-content')
        yield Footer()
