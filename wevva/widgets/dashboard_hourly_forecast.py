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


class DashboardHourlyForecast(Container):
    """One row per hour with no horizontal navigation requirement."""

    DEFAULT_CSS = """
    DashboardHourlyForecast {
        width: 100%;
        height: 2fr;
        min-height: 8;
        border: round $primary;
        border-title-color: $primary;
        border-title-align: left;
        background: $background;
    }

    DashboardHourlyForecast DataTable {
        width: 100%;
        height: 100%;
        scrollbar-size-horizontal: 0;
        scrollbar-size-vertical: 1;
        background: $background;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._hourly_model: Any | None = None
        self._indices: list[int] = []
        self._wide_columns = False

    def compose(self) -> ComposeResult:
        yield DataTable(
            show_header=True,
            cursor_type='row',
            cell_padding=0,
            zebra_stripes=True,
            id='dashboard-hourly-table',
        )

    @property
    def table(self) -> DataTable:
        return self.query_one('#dashboard-hourly-table', DataTable)

    def on_mount(self) -> None:
        self.border_title = 'Hourly Forecast'
        self._rebuild()

    def on_resize(self, event: Resize) -> None:
        event.stop()
        wide_columns = event.size.width >= 46
        if wide_columns != self._wide_columns:
            self._wide_columns = wide_columns
            self._rebuild()

    def update_forecast(self, event: WeatherUpdated) -> None:
        """Render the next 24 hours from an app-owned forecast snapshot."""

        self._hourly_model = event.hourly
        if self.is_mounted:
            self._rebuild()

    def _rebuild(self) -> None:
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

        self._wide_columns = self.content_size.width >= 46
        for label, key, width in self._column_specs(model):
            table.add_column(label, key=key, width=width)

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

    def _column_specs(self, model: Any) -> tuple[tuple[str, str, int], ...]:
        precip_unit = model.forecast_units.get('precipitation', 'mm')
        wind_unit = model.forecast_units.get('wind_speed_10m', '')
        temp_unit = model.forecast_units.get('temperature_2m', '°')
        self.border_subtitle = f'{precip_unit} · wind {wind_unit}'.strip()
        if self._wide_columns:
            return (
                ('Hour', 'hour', 7),
                ('Cond', 'condition', 5),
                (f'T{temp_unit}', 'temperature', 5),
                ('P%', 'probability', 4),
                ('Rain', 'amount', 6),
                ('Wind', 'wind', 7),
                ('Gust', 'gust', 7),
                ('Dir', 'direction', 5),
            )
        return (
            ('Hr', 'hour', 3),
            ('Wx', 'condition', 3),
            (temp_unit, 'temperature', 4),
            ('P%', 'probability', 4),
            (precip_unit, 'amount', 4),
            ('W', 'wind', 3),
            ('G', 'gust', 4),
            ('Dir', 'direction', 3),
        )

    def _row_cells(self, index: int) -> tuple[Text, ...]:
        model = self._hourly_model
        point = model.get_point(index) or {}
        theme = self.app.theme_variables
        temperature = model.get_temperature(index)
        probability = model.get_precipitation_probability(index)
        amount = model.get_precipitation(index)
        wind = model.get_wind_speed(index)
        gust = model.get_wind_gust(index)
        condition = get_condition(point.get('weather_code'))
        temp_style = (
            temp_colour(
                temperature,
                scale='theme_temperature',
                hex=True,
                unit=self.app.temperature_unit,
                theme_colours=theme,
            )
            if _is_number(temperature)
            else 'dim'
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
        wind_style = (
            wind_colour(
                wind,
                hex=True,
                min_colour=theme['foreground'],
                max_colour=theme['secondary'],
            )
            if _is_number(wind)
            else 'dim'
        )
        gust_style = (
            wind_colour(
                gust,
                hex=True,
                min_colour=theme['foreground'],
                max_colour=theme['secondary'],
            )
            if _is_number(gust)
            else 'dim'
        )
        condition_style = (
            f'bold {theme.get(condition.color_var)}'
            if condition is not None and condition.color_var
            else 'bold'
        )
        time = point.get('time')
        hour = (
            time.strftime('%a %H')
            if self._wide_columns and time is not None
            else time.strftime('%H') if time is not None else '--'
        )
        direction = (model.get_wind_direction(index) or '--').replace(' ', '')
        return (
            Text(hour, style='dim'),
            Text(condition.abbr if condition is not None else '--', style=condition_style),
            Text(_number(temperature, suffix='°'), style=temp_style),
            Text(_number(probability), style=rain_style),
            Text(_amount(amount), style=rain_style),
            Text(_number(wind), style=wind_style),
            Text(_number(gust), style=gust_style),
            Text(direction, style='dim'),
        )

    def on_data_table_row_highlighted(
        self,
        event: DataTable.RowHighlighted,
    ) -> None:
        """Keep the fixed current summary aligned with the selected row."""

        if (
            event.data_table is self.table
            and event.data_table.has_focus
            and 0 <= event.cursor_row < len(self._indices)
        ):
            self.post_message(HourHighlighted(self._indices[event.cursor_row]))


def _number(value: object, *, suffix: str = '') -> str:
    if not _is_number(value):
        return '--'
    assert isinstance(value, (int, float))
    return f'{round(value):.0f}{suffix}'


def _amount(value: object) -> str:
    if not _is_number(value):
        return '--'
    assert isinstance(value, (int, float))
    return f'{value:.1f}' if abs(value) < 10 else f'{round(value):.0f}'


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


__all__ = ['DashboardHourlyForecast']
