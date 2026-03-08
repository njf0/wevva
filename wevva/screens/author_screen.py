"""Author / credits screen.

Shows project author information and credits.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Static


class AuthorScreen(ModalScreen[None]):
    """Simple screen showing author info and credits."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]

    DEFAULT_CSS = """
    AuthorScreen {
        align: center middle;
        hatch: right $background-lighten-1;
        align-horizontal: center;
        align-vertical: middle;
        content-align: center middle;
    }

    #author-box {
        width: 70;
        height: auto;
        border: panel $primary;
        padding: 2 4;
        background: $panel;
        align-horizontal: center;
        align-vertical: middle;
        content-align: center middle;
    }

    #title {
        text-align: center;
        text-style: bold;
        color: $accent;
        padding-bottom: 1;
    }

    #author-info {
        text-align: center;
        padding: 1 0 2 0;
        border-bottom: solid $primary;
    }

    #credits {
        text-align: center;
        padding-top: 2;
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        theme = self.app.theme_variables
        yield Header(show_clock=True)
        with Container(id="author-box"):
            yield Static("Wevva", id="title")

            # Author info
            author_text = Text.from_markup(
                f"[bold {theme.get('primary')}]Nick Ferguson[/]\n[dim]nick.ferguson@ed.ac.uk[/]"
            )
            yield Static(author_text, id="author-info")

            # Credits
            credits_text = Text.from_markup(
                f'[bold {theme.get("secondary")}]Credits[/]\n\nWeather data from [@click=app.open_url("https://open-meteo.com")]Open-Meteo[/]'
            )
            yield Static(credits_text, id="credits")
        yield Footer()

    def action_pop_screen(self) -> None:
        """Close the author screen."""
        self.app.pop_screen()
