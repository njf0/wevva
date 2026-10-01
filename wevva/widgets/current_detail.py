"""Detail table for the selected hour.

Shows cloud cover, humidity, UV, visibility, and pressure.
Keeps legacy id and classes.
"""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import DataTable

from wevva.layout import DetailRow


_DETAIL_FIELDS = {
    DetailRow.HUMIDITY: (
        'Hum.',
        'Humidity',
        'get_humidity',
        'text-secondary',
        'relative_humidity_2m',
        None,
    ),
    DetailRow.VISIBILITY: (
        'Vis.',
        'Visibility',
        'get_visibility',
        'text-warning',
        None,
        'km',
    ),
    DetailRow.PRESSURE: (
        'Pres.',
        'Pressure',
        'get_surface_pressure',
        'text-error',
        'surface_pressure',
        None,
    ),
    DetailRow.UV_INDEX: ('UV', 'UV Index', 'get_uv_index', 'text-accent', 'uv_index', None),
    DetailRow.CLOUD_COVER: (
        'Cld.',
        'Cloud Cover',
        'get_cloud_cover',
        'text-primary',
        'cloud_cover',
        None,
    ),
}


class CurrentDetailTable(DataTable):
    """DataTable showing current condition details for a specific hour."""

    # Reactive properties (set by parent CurrentConditions)
    hourly_model: reactive[Any | None] = reactive(None)
    hour_index: reactive[int] = reactive(0)

    DEFAULT_CSS = """
    CurrentDetailTable {
        height: 7;
        width: 1fr;
        min-width: 0;
        border: round $primary;
        border-title-color: $primary;
        border-title-align: left;
        scrollbar-size-horizontal: 0;
    }
    """

    def __init__(
        self,
        *,
        id: str = 'current-weather-detail-table',
        classes: str = 'weather-widget',
    ):
        super().__init__(show_header=False, cursor_type='none', id=id, classes=classes)
        self.border_title = 'Detail'
        self._visible_rows = tuple(DetailRow)
        self._full_labels = False
        self._build_rows()

    def _build_rows(self) -> None:
        """Build only the complete rows selected by the layout budget."""

        self.clear(columns=True)
        self.add_column(
            'Field',
            key='field',
            width=11 if self._full_labels else 5,
        )
        self.add_column('Value', key='value', width=7)
        for row in self._visible_rows:
            compact_label, full_label, *_ = _DETAIL_FIELDS[row]
            label = full_label if self._full_labels else compact_label
            self.add_row(
                Text(label, style='dim'),
                Text('', style='bold'),
                key=row.value,
            )

    def set_layout(
        self,
        rows: tuple[DetailRow, ...],
        height: int,
        full_labels: bool,
    ) -> None:
        """Select complete detail rows and an exact bordered height."""

        rows = tuple(rows)
        full_labels = bool(full_labels)
        changed = (
            rows != self._visible_rows
            or full_labels != self._full_labels
        )
        self._visible_rows = rows
        self._full_labels = full_labels
        self.styles.height = height
        if changed:
            self._build_rows()
            if self.hourly_model is not None and self.is_mounted:
                self._update_display()

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

        for row in self._visible_rows:
            (
                _,
                _,
                getter_name,
                color_key,
                unit_key,
                display_unit,
            ) = _DETAIL_FIELDS[row]
            self._update_detail_cell(
                row.value,
                getter_name,
                theme_vars.get(color_key),
                unit_key,
                display_unit,
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
            unit = self.hourly_model.forecast_units.get(unit_key, '')
        else:
            unit = ''

        text = Text.from_markup(f'[bold {colour}]{value}[/][{colour}]{unit}[/]')
        self.update_cell(row_key, 'value', text, update_width=True)
