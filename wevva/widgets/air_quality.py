"""Air Quality widget: displays AQI, PM2.5, PM10, Ozone and Grass Pollen.

This mirrors the style of `CurrentDetailTable` — a compact `DataTable`
with a reactive pattern for hourly_model, location, and hour_index.
"""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import DataTable

# AQI Thresholds: (max_value, level_name, theme_key)
_US_AQI_LEVELS = [
    (50, "Good", "success"),
    (100, "Moderate", "text-success"),
    (150, "UFSG", "text-warning"),
    (200, "Unhealthy", "warning"),
    (300, "Very Unhealthy", "text-error"),
]

_EUROPEAN_AQI_LEVELS = [
    (20, "Good", "success"),
    (40, "Fair", "text-success"),
    (60, "Moderate", "text-warning"),
    (80, "Poor", "warning"),
    (100, "Very Poor", "text-error"),
]

# Pollen Thresholds: (max_value, level_name, theme_key)
_POLLEN_LEVELS = [
    (0, "None", "success"),
    (4, "Low", "text-success"),
    (19, "Moderate", "text-warning"),
    (199, "High", "warning"),
]


class AirQualityWidget(DataTable):
    """DataTable showing air quality details for a specific hour."""

    # Reactive properties (set by parent ContextBar)
    hourly_model: reactive[Any | None] = reactive(None)
    location: reactive[Any | None] = reactive(None)
    hour_index: reactive[int] = reactive(0)

    DEFAULT_CSS = """
    AirQualityWidget {
        height: auto;
        # width: 36;
        # min-width: 36;
        # max-width: 36;
        border: round $primary;
        border-title-color: $primary;
        border-title-align: left;
    }

    #air-quality-table {
        # width: 100%;
    }
    """

    def __init__(
        self,
        *,
        id: str = "air-quality-table",
        classes: str = "weather-widget",
    ) -> None:
        """Initialize the Air Quality widget with predefined columns and rows.

        Parameters
        ----------
        id : str
            The unique identifier for this widget instance.
        classes : str
            Space-separated string of CSS classes to apply to this widget.

        """
        super().__init__(show_header=False, cursor_type="none", id=id, classes=classes)
        self.border_title = "Air Quality"
        self.add_column("Field", key="field", width=5)
        self.add_column("Value", key="value", width=17)
        self.add_row(Text("AQI", style="dim"), Text("", style="bold"), key="aqi")
        self.add_row(Text("PM2.5", style="dim"), Text("", style="bold"), key="pm25")
        self.add_row(Text("PM10", style="dim"), Text("", style="bold"), key="pm10")
        self.add_row(Text("Ozone", style="dim"), Text("", style="bold"), key="ozone")
        self.add_row(Text("Poll", style="dim"), Text("", style="bold"), key="pollen")

    def on_mount(self) -> None:
        """Trigger initial display after mounting."""
        if self._can_update():
            self._update_display()

    def watch_hourly_model(self, model: Any | None) -> None:
        """React to hourly model changes."""
        if self.is_mounted and self._can_update():
            self._update_display()

    def watch_location(self, location: Any | None) -> None:
        """React to location changes."""
        if self.is_mounted and self._can_update():
            self._update_display()

    def watch_hour_index(self, index: int) -> None:
        """React to hour index changes."""
        if self.is_mounted and self._can_update():
            self._update_display()

    def _can_update(self) -> bool:
        """Check if widget has all required data to update."""
        return self.hourly_model is not None and self.location is not None

    def _update_display(self) -> None:
        """Populate rows from the hourly model for the given hour."""
        theme_vars = getattr(self.app, "theme_variables", {})
        idx = self.hour_index

        # Get values and units
        is_europe, aqi, aqi_label = self._get_aqi_data()
        values = {
            "aqi": self._format_aqi(aqi, is_europe, theme_vars, aqi_label),
            "pm25": self._format_pollutant(
                self.hourly_model.get_pm2_5(idx), "pm2_5", theme_vars
            ),
            "pm10": self._format_pollutant(
                self.hourly_model.get_pm10(idx), "pm10", theme_vars
            ),
            "ozone": self._format_pollutant(
                self.hourly_model.get_ozone(idx), "ozone", theme_vars
            ),
            "pollen": self._format_pollen(
                self.hourly_model.get_grass_pollen(idx), "grass_pollen", theme_vars
            ),
        }

        # Update all cells
        for key, text in values.items():
            self.update_cell(key, "value", text, update_width=False)
        self.refresh()

    def _get_aqi_data(self) -> tuple[bool, Any, str]:
        """Get AQI value and label based on location region."""
        region = getattr(self.location, "tz_identifier", "").split("/")[0]
        is_europe = region == "Europe"

        if is_europe:
            aqi = self.hourly_model.get_european_aqi(self.hour_index)
            return True, aqi, "EAQI"
        else:
            aqi = self.hourly_model.get_us_aqi(self.hour_index)
            return False, aqi, "US AQI"

    # Internal formatting helpers -------------------------------------
    def _format_aqi(
        self, value: Any, is_europe: bool, theme_vars: dict[str, str], label: str
    ) -> Text:
        """Return a styled Text for AQI value with level name."""
        if value is None:
            return Text("N/A", style="dim")

        if not isinstance(value, (int, float)):
            return Text(str(value), style=theme_vars.get("primary"))

        v = int(value)
        levels = _EUROPEAN_AQI_LEVELS if is_europe else _US_AQI_LEVELS

        # Find matching threshold
        for threshold, level, key in levels:
            if v <= threshold:
                colour = theme_vars.get(key)
                return Text.from_markup(
                    f"[bold {colour}]{v}[/] [italic {colour}]{level}[/]"
                )

        # Fallback (shouldn't reach here due to inf threshold)
        return Text(str(v), style=theme_vars.get("primary"))

    def _format_pollutant(
        self, value: Any, unit_key: str, theme_vars: dict[str, str]
    ) -> Text:
        """Format PM2.5 / PM10 / Ozone values with units."""
        if value is None:
            return Text("N/A", style="dim")

        v = float(value)
        unit = self.hourly_model.forecast_units.get(unit_key, "µg/m³")
        colour = theme_vars.get("accent")

        return Text.from_markup(f"[bold {colour}]{v:g}[/][{colour}]{unit}[/]")

    def _format_pollen(
        self, value: Any, unit_key: str, theme_vars: dict[str, str]
    ) -> Text:
        """Map grass pollen counts to levels and style them."""
        if value is None:
            return Text("N/A", style="dim")

        v = int(value)
        unit = self.hourly_model.forecast_units.get(unit_key, "grains/m³")

        # Find matching threshold
        for threshold, level, key in _POLLEN_LEVELS:
            if v <= threshold:
                colour = theme_vars.get(key)
                return Text.from_markup(
                    f"[bold {colour}]{v}[/][{colour}]{unit}[/] [italic {colour}]{level}[/]"
                )

        # Fallback
        return Text(str(v), style=theme_vars.get("primary"))
