"""Detail table for the selected hour.

Shows cloud cover, humidity, UV, visibility, and pressure.
Keeps legacy id and classes.
"""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import DataTable


class CurrentDetailTable(DataTable):
    """DataTable showing current condition details for a specific hour."""

    # Reactive properties (set by parent CurrentConditions)
    hourly_model: reactive[Any | None] = reactive(None)
    hour_index: reactive[int] = reactive(0)

    DEFAULT_CSS = """
    CurrentDetailTable {
        height: auto;
        width: 22;
        border: round $primary;
        border-title-color: $primary;
        border-title-align: left;
        # margin: 0 2 0 0;
    }
    """

    def __init__(
        self,
        *,
        id: str = "current-weather-detail-table",
        classes: str = "weather-widget",
    ):
        super().__init__(show_header=False, cursor_type="none", id=id, classes=classes)
        self.border_title = "Detail"
        self.add_column("Field", key="field")
        self.add_column("Value", key="value", width=7)
        self.add_row(
            Text("Cloud Cov.", style="dim"), Text("", style="bold"), key="cloud_cover"
        )
        self.add_row(
            Text("Humidity", style="dim"), Text("", style="bold dim"), key="humidity"
        )
        self.add_row(
            Text("UV Index", style="dim"), Text("", style="bold dim"), key="uv_index"
        )
        self.add_row(
            Text("Visibility", style="dim"),
            Text("", style="bold dim"),
            key="visibility",
        )
        self.add_row(
            Text("Pressure", style="dim"), Text("", style="bold dim"), key="pressure"
        )

    def on_mount(
        self,
    ) -> None:
        """Trigger initial display after mounting."""
        if self.hourly_model is not None:
            self._update_display()

    def watch_hourly_model(
        self,
        new_model: Any | None,
    ) -> None:
        """React to hourly model changes."""
        if self.is_mounted and new_model is not None:
            self._update_display()

    def watch_hour_index(
        self,
        new_index: int,
    ) -> None:
        """React to hour index changes."""
        if self.is_mounted and self.hourly_model is not None:
            self._update_display()

    def _update_display(
        self,
    ) -> None:
        """Populate rows from the hourly model for the given hour."""
        theme_vars = self.app.theme_variables

        # Field configuration: (row_key, getter_method_name, theme_color_key, unit_key, display_unit)
        fields = [
            ("cloud_cover", "get_cloud_cover", "foreground", "cloud_cover", None),
            ("humidity", "get_humidity", "secondary", "relative_humidity_2m", None),
            ("uv_index", "get_uv_index", "warning", "uv_index", None),
            ("visibility", "get_visibility", "accent", None, "km"),
            ("pressure", "get_surface_pressure", "error", "surface_pressure", None),
        ]

        for row_key, getter_name, color_key, unit_key, display_unit in fields:
            self._update_detail_cell(
                row_key, getter_name, theme_vars.get(color_key), unit_key, display_unit
            )

        self.refresh()

    def _update_detail_cell(
        self,
        row_key: str,
        getter_name: str,
        colour: str,
        unit_key: str | None = None,
        display_unit: str | None = None,
    ) -> None:
        """Update a single detail cell with formatted value and unit.

        Args:
            row_key: DataTable row identifier
            getter_name: Method name on hourly_model (e.g., 'get_cloud_cover')
            colour: Theme colour to use for value and unit
            unit_key: Key to look up unit in forecast_units (None = no unit from model)
            display_unit: Hardcoded unit to display (overrides unit_key)

        """
        getter = getattr(self.hourly_model, getter_name)
        value = getter(self.hour_index)

        # Determine unit to display
        if display_unit:
            unit = display_unit
        elif unit_key:
            unit = self.hourly_model.forecast_units.get(unit_key, "")
        else:
            unit = ""

        text = Text.from_markup(f"[bold {colour}]{value}[/][{colour}]{unit}[/]")
        self.update_cell(row_key, "value", text, update_width=True)
