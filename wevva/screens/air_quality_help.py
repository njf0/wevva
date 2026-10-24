"""Focused help for the air-quality context card."""

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Markdown


AIR_QUALITY_HELP = """
## Measures and units

- **AQI — Air Quality Index** (`index`): an aggregate view of overall air quality. Wevva displays the European AQI in Europe and the US AQI elsewhere.
- **PM2.5 — Fine particulate matter** (`µg/m³`): particles smaller than 2.5 micrometres.
- **PM10 — Coarse particulate matter** (`µg/m³`): particles smaller than 10 micrometres, including dust and pollen.
- **Ozone** (`µg/m³`): ground-level ozone concentration.
- **Poll — Grass pollen** (`grains/m³`): grass-pollen concentration, available only in Europe.

Values are hourly Open-Meteo air-quality data aligned with the selected forecast hour. A missing measure is shown as unavailable.
"""


class AirQualityHelp(ModalScreen[None]):
    """Responsive, scrollable glossary for displayed air-quality measures."""

    BINDINGS = [('escape', 'dismiss', 'Close')]

    DEFAULT_CSS = """
    AirQualityHelp {
        align: center middle;
        background: $background;
        hatch: right $background-lighten-1;
    }

    AirQualityHelp > #air-quality-help-container {
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

    #air-quality-help-content {
        width: 100%;
        height: auto;
        background: $panel;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with VerticalScroll(id='air-quality-help-container') as container:
            container.border_title = 'Air Quality Help'
            yield Markdown(AIR_QUALITY_HELP, id='air-quality-help-content')
        yield Footer()
