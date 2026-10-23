"""Vertical hourly forecast for the Dashboard rail."""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.events import Resize
from textual.widgets import DataTable

from wevva.conditions import get_condition
from wevva.constants import HOURS_WINDOW
from wevva.messages import HourHighlighted, WeatherUpdated
from wevva.utils import rain_colour, temp_colour, wind_colour


_MINIMUM_WIDTHS = (5, 3, 5, 4, 9)
_PREFERRED_WIDTHS = (6, 5, 8, 6, 16)
_COLUMN_COUNT = len(_MINIMUM_WIDTHS)


class DashboardHourlyForecast(Container):
    """One formatted row per hour with no horizontal navigation."""

    DEFAULT_CSS = """
    DashboardHourlyForecast {
        width: 100%;
        height: 1fr;
        max-height: 24;
        min-height: 5;
        border: none;
        background: $background;
        overflow: hidden hidden;
    }

    DashboardHourlyForecast DataTable {
        width: 100%;
        height: 100%;
        scrollbar-size-horizontal: 0;
        scrollbar-size-vertical: 1;
        background: $background;
    }

    DashboardHourlyForecast DataTable > .datatable--even-row {
        background: $background-lighten-1;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._hourly_model: Any | None = None
        self._indices: list[int] = []
        self._column_widths: tuple[int, ...] = ()
        self._cell_padding = 0
        self._rebuild_pending = False

    def compose(self) -> ComposeResult:
        table = DataTable(
            show_header=False,
            cursor_type='row',
            cell_padding=0,
            zebra_stripes=True,
            id='dashboard-hourly-table',
        )
        # The application stylesheet makes generic DataTables auto-width.
        # This table is the rail's viewport, so keep that rule from collapsing
        # it to its column content during the first layout pass.
        table.styles.width = '100%'
        table.styles.min_width = 0
        yield table

    @property
    def table(self) -> DataTable:
        return self.query_one('#dashboard-hourly-table', DataTable)

    def on_mount(self) -> None:
        self._schedule_rebuild()

    def on_resize(self, event: Resize) -> None:
        event.stop()
        padding, widths = _fitted_layout(max(1, event.size.width - 1))
        if padding != self._cell_padding or widths != self._column_widths:
            self._schedule_rebuild()

    def update_forecast(self, event: WeatherUpdated) -> None:
        """Render the next 24 hours from an app-owned forecast snapshot."""

        self._hourly_model = event.hourly
        self._schedule_rebuild()

    def _schedule_rebuild(self) -> None:
        """Coalesce model and size changes delivered in the same frame."""

        if not self.is_mounted or self._rebuild_pending:
            return
        self._rebuild_pending = True
        self.call_after_refresh(self._rebuild)

    def _rebuild(self) -> None:
        self._rebuild_pending = False
        if not self.is_mounted:
            return
        table = self.table
        selected_index = None
        if self._indices and 0 <= table.cursor_row < len(self._indices):
            selected_index = self._indices[table.cursor_row]
        table.clear(columns=True)
        self._indices = []
        model = self._hourly_model
        if model is None or not model.forecast_timeseries:
            return

        self._cell_padding, self._column_widths = _fitted_layout(
            max(1, self.content_size.width - 1)
        )
        table.cell_padding = self._cell_padding
        for key, width in zip(
            ('hour', 'condition', 'temperature', 'rain', 'wind'),
            self._column_widths,
            strict=True,
        ):
            table.add_column('', key=key, width=width)

        self._indices = list(
            range(min(HOURS_WINDOW, len(model.forecast_timeseries)))
        )
        for index in self._indices:
            table.add_row(*self._row_cells(index), key=f'hour-{index}')
        if self._indices:
            row = (
                self._indices.index(selected_index)
                if selected_index in self._indices
                else 0
            )
            table.move_cursor(row=row, animate=False, scroll=False)
        table.refresh()

    def _row_cells(self, index: int) -> tuple[Text, ...]:
        model = self._hourly_model
        point = model.get_point(index) or {}
        theme = self.app.theme_variables
        temperature = model.get_temperature(index)
        probability = model.get_precipitation_probability(index)
        wind = model.get_wind_speed(index)
        condition = get_condition(point.get('weather_code'))
        temperature_style = _temperature_style(
            temperature,
            unit=self.app.temperature_unit,
            theme=theme,
        )
        rain_style = (
            rain_colour(
                probability,
                hex=True,
                min_colour=theme['foreground'],
                max_colour=theme['primary'],
            )
            if _is_number(probability)
            else 'dim'
        )
        wind_style = _wind_style(wind, theme)
        condition_style = (
            f'bold {theme.get(condition.color_var)}'
            if condition is not None and condition.color_var
            else 'bold'
        )
        time = point.get('time')
        hour = time.strftime('%H:%M') if time is not None else '--:--'
        temp_unit = model.forecast_units.get('temperature_2m', '°C')
        wind_unit = model.forecast_units.get('wind_speed_10m', '')
        direction = model.get_wind_direction(index) or '--'
        return (
            Text(hour, style='dim'),
            Text(
                condition.abbr if condition is not None else '--',
                style=condition_style,
            ),
            _measure(
                temperature,
                unit=temp_unit,
                style=temperature_style,
            ),
            _measure(
                probability,
                unit='%',
                style=rain_style,
            ),
            _wind_measure(
                wind,
                direction,
                unit=wind_unit,
                wind_style=wind_style,
            ),
        )

    def on_data_table_row_highlighted(
        self,
        event: DataTable.RowHighlighted,
    ) -> None:
        """Keep current instruments and AQI aligned with the selected row."""

        if (
            event.data_table is self.table
            and event.data_table.has_focus
            and 0 <= event.cursor_row < len(self._indices)
        ):
            self.post_message(HourHighlighted(self._indices[event.cursor_row]))


def _measure(
    value: object,
    *,
    unit: str,
    style: str,
) -> Text:
    text = Text()
    value_style = style if not _is_number(value) else f'bold {style}'
    text.append(f'{_number(value)}{unit}', style=value_style)
    return text


def _wind_measure(
    wind: object,
    direction: str,
    *,
    unit: str,
    wind_style: str,
) -> Text:
    text = Text()
    value_style = wind_style if not _is_number(wind) else f'bold {wind_style}'
    text.append(f'{_number(wind)}{unit}', style=value_style)
    text.append(' ')
    text.append(direction, style=value_style if direction != '--' else 'dim')
    return text


def _temperature_style(
    value: object,
    *,
    unit: str,
    theme: dict[str, str],
) -> str:
    if not _is_number(value):
        return 'dim'
    return temp_colour(
        value,
        scale='theme_temperature',
        hex=True,
        unit=unit,
        theme_colours=theme,
    )


def _wind_style(value: object, theme: dict[str, str]) -> str:
    if not _is_number(value):
        return 'dim'
    return wind_colour(
        value,
        hex=True,
        min_colour=theme['foreground'],
        max_colour=theme['secondary'],
    )


def _number(value: object) -> str:
    if not _is_number(value):
        return '--'
    assert isinstance(value, (int, float))
    return f'{round(value):.0f}'


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _fitted_widths(available: int) -> tuple[int, ...]:
    widths = list(_MINIMUM_WIDTHS)
    remaining = max(0, available - sum(widths))
    for index in (4, 2, 3, 1, 0):
        addition = min(remaining, _PREFERRED_WIDTHS[index] - widths[index])
        widths[index] += addition
        remaining -= addition
        if remaining == 0:
            break
    return tuple(widths)


def _fitted_layout(available: int) -> tuple[int, tuple[int, ...]]:
    """Add even cell padding only when the rail can retain every field."""

    padding = 1 if available >= sum(_MINIMUM_WIDTHS) + 2 * _COLUMN_COUNT else 0
    content_width = max(1, available - 2 * padding * _COLUMN_COUNT)
    return padding, _fitted_widths(content_width)


__all__ = ['DashboardHourlyForecast']
