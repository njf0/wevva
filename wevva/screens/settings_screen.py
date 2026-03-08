"""Settings screen for configuring unit preferences."""

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Label, Select, Static

from wevva.config import save_preferences


class SettingsScreen(ModalScreen[dict | None]):
    """Modal screen for adjusting unit preferences."""

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

    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(
        self,
        temperature_unit: str,
        wind_speed_unit: str,
        precipitation_unit: str,
    ):
        """Initialize settings screen with current preferences."""
        super().__init__()
        self.temperature_unit = temperature_unit
        self.wind_speed_unit = wind_speed_unit
        self.precipitation_unit = precipitation_unit

    def compose(self) -> ComposeResult:
        """Build settings UI."""
        yield Header(show_clock=True, id="settings-header")

        with Container(id="settings-dialog"):
            yield Static("[bold]Unit Preferences[/]", id="settings-title")
            yield Label("Temperature Unit:")
            yield Select(
                options=[
                    ("Celsius (°C)", "celsius"),
                    ("Fahrenheit (°F)", "fahrenheit"),
                ],
                value=self.temperature_unit,
                id="temp-select",
            )

            yield Label("Wind Speed Unit:")
            yield Select(
                options=[
                    ("Kilometers per hour (km/h)", "kmh"),
                    ("Meters per second (m/s)", "ms"),
                    ("Miles per hour (mph)", "mph"),
                    ("Knots (kn)", "kn"),
                ],
                value=self.wind_speed_unit,
                id="wind-select",
            )

            yield Label("Precipitation Unit:")
            yield Select(
                options=[
                    ("Millimeters (mm)", "mm"),
                    ("Inches (in)", "inch"),
                ],
                value=self.precipitation_unit,
                id="precip-select",
            )

            with Vertical(classes="button-row"):
                yield Button("Apply", variant="primary", id="apply-button")
                yield Button("Save Defaults", variant="success", id="save-button")
                yield Button("Cancel", variant="default", id="cancel-button")

        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        if event.button.id == "apply-button":
            # Apply to current session without saving
            temp_unit = self.query_one("#temp-select", Select).value
            wind_unit = self.query_one("#wind-select", Select).value
            precip_unit = self.query_one("#precip-select", Select).value

            # Return new preferences to app (temporary)
            self.dismiss(
                {
                    "temperature_unit": temp_unit,
                    "wind_speed_unit": wind_unit,
                    "precipitation_unit": precip_unit,
                }
            )
        elif event.button.id == "save-button":
            # Save to config file as defaults
            temp_unit = self.query_one("#temp-select", Select).value
            wind_unit = self.query_one("#wind-select", Select).value
            precip_unit = self.query_one("#precip-select", Select).value

            save_preferences(temp_unit, wind_unit, precip_unit)

            # Show confirmation but keep screen open
            self.notify("Default units saved", severity="information")
        else:
            # Cancel - return None
            self.dismiss(None)
