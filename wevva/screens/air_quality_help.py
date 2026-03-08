"""Help screen for Air Quality widget.

Shows a DataTable listing units: short name, full name, explanation.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, Static


class AirQualityHelp(ModalScreen[None]):
    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]

    DEFAULT_CSS = """
    AirQualityHelp {
        # width: auto;
        height: 100%;
        align: center middle;
        align-horizontal: center;
        align-vertical: middle;
        content-align: center middle;
    }

    # center help box
    #help-container {
        width: 100;
        # height: auto;
        # padding: 1 2;
        border: heavy $accent;
        border-title-color: $accent;
        border-title-style: bold;
        border-title-align: center;
        # background: $panel;
        # margin: 0 0;
        align-horizontal: center;
        align-vertical: middle;
        content-align: center middle;
    }

    #help-title {
        text-align: center;
        text-style: bold italic;
        color: $accent;
        padding-bottom: 1;
        # width: auto;
    }

    """

    def compose(self) -> ComposeResult:  # type: ignore[override]
        yield Header(show_clock=True)
        # Rows: short name, full unit name, unit, explanation
        rows = [
            (
                "AQI",
                "Air Quality Index",
                "index",
                "Aggregate air quality index describing overall air quality. Uses European Air Quality Index in Europe, US AQI elsewhere.",
            ),
            (
                "PM2.5",
                "Fine particulate matter",
                "µg/m³",
                "Particles smaller than 2.5 micrometers.",
            ),
            (
                "PM10",
                "Coarse particulate matter",
                "µg/m³",
                "Particles smaller than 10 micrometers, such as dust and pollen.",
            ),
            (
                "Ozone",
                "Ozone",
                "µg/m³",
                "Ground-level ozone.",
            ),
            (
                "Poll",
                "Grass pollen",
                "grains/m³",
                "Concentration of grass pollen grains, only available in Europe.",
            ),
        ]

        with Static(id="help-container"):
            yield Static("Air Quality — Units and explanations", id="help-title")
            table = DataTable(
                show_header=True, id="air-quality-help-table", cursor_type="none"
            )
            table.add_column("Short name", key="short", width=10)
            table.add_column("Full name", key="full", width=24)
            table.add_column("Unit", key="unit", width=10)
            table.add_column("Explanation", key="explain", width=42)

            for short, full, unit, explain in rows:
                table.add_row(
                    Text(short, style="dim"),
                    Text(full, style="bold"),
                    Text(unit, style="dim"),
                    Text(explain, style=""),
                    height=3,
                )

            # yield the table as a child of the bordered container
            yield table

        yield Footer()

    def action_pop_screen(self) -> None:
        """Action to pop the screen."""
        self.app.pop_screen()
