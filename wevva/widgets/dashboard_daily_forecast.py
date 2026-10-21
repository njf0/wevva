"""Compact daily forecast for the Dashboard weather rail."""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.events import Resize
from textual.widgets import DataTable

from wevva.conditions import get_condition
from wevva.messages import WeatherUpdated
from wevva.utils import rain_colour, temp_colour, wind_colour


class DashboardDailyForecast(Container):
    """Future days in a vertical table sized for the narrow Dashboard rail."""

    DEFAULT_CSS = """
    DashboardDailyForecast {
        width: 100%;
        height: 6;
        border: round $primary;
        border-title-color: $primary;
        border-title-align: left;
        background: $background;
    }

    DashboardDailyForecast DataTable {
        width: 100%;
        height: 100%;
        scrollbar-size-horizontal: 0;
        scrollbar-size-vertical: 1;
        background: $background;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._daily_model: Any | None = None
        self._indices: list[int] = []
        self._row_count = 3
        self._wide_columns = False

    def compose(self) -> ComposeResult:
        yield DataTable(
            show_header=True,
            cursor_type='row',
            cell_padding=0,
            zebra_stripes=True,
            id='dashboard-daily-table',
        )

    @property
    def table(self) -> DataTable:
        return self.query_one('#dashboard-daily-table', DataTable)

    def on_mount(self) -> None:
        self.border_title = 'Daily Forecast'
        self._rebuild()

    def on_resize(self, event: Resize) -> None:
        event.stop()
        wide_columns = event.size.width >= 46
        if wide_columns != self._wide_columns:
            self._wide_columns = wide_columns
            self._rebuild()

    def set_row_count(self, row_count: int) -> None:
        """Set the number of future days retained in this presentation."""

        row_count = max(0, int(row_count))
        self.styles.height = row_count + 3
        if row_count != self._row_count:
            self._row_count = row_count
            self._rebuild()

    def update_forecast(self, event: WeatherUpdated) -> None:
        """Render future days from the same app-owned forecast snapshot."""

        self._daily_model = event.daily
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
        model = self._daily_model
        if model is None or not model.forecast_timeseries or self._row_count == 0:
            return

        self._wide_columns = self.content_size.width >= 46
        for label, key, width in self._column_specs(model):
            table.add_column(label, key=key, width=width)

        available = max(0, len(model.forecast_timeseries) - 1)
        self._indices = list(range(1, min(available, self._row_count) + 1))
        for index in self._indices:
            table.add_row(*self._row_cells(index), key=f'day-{index}')
        if self._indices:
            row = (
                self._indices.index(selected_index)
                if selected_index in self._indices
                else 0
            )
            table.move_cursor(row=row, animate=False, scroll=False)
        table.refresh()

    def _column_specs(self, model: Any) -> tuple[tuple[str, str, int], ...]:
        temp_unit = model.forecast_units.get('temperature_2m_min', '°C')
        precip_unit = model.forecast_units.get('precipitation_sum', 'mm')
        wind_unit = model.forecast_units.get('wind_speed_10m_max', '')
        self.border_subtitle = f'{temp_unit} · {precip_unit} · {wind_unit}'.strip()
        if self._wide_columns:
            return (
                ('Day', 'day', 7),
                ('Cond', 'condition', 5),
                ('Low', 'low', 5),
                ('High', 'high', 5),
                ('P%', 'probability', 4),
                ('Rain', 'amount', 6),
                ('Wind', 'wind', 6),
                ('Gust', 'gust', 6),
                ('Dir', 'direction', 4),
            )
        return (
            ('Day', 'day', 4),
            ('Wx', 'condition', 3),
            ('Lo', 'low', 4),
            ('Hi', 'high', 4),
            ('P%', 'probability', 4),
            ('W', 'wind', 3),
            ('G', 'gust', 3),
            ('Dir', 'direction', 3),
        )

    def _row_cells(self, index: int) -> tuple[Text, ...]:
        model = self._daily_model
        point = model.forecast_timeseries[index]
        theme = self.app.theme_variables
        low = model.get_temperature_min(index)
        high = model.get_temperature_max(index)
        probability = model.get_precipitation_probability(index)
        amount = model.get_precipitation(index)
        wind = model.get_wind_speed(index)
        gust = model.get_wind_gust(index)
        direction = (model.get_wind_direction(index) or '--').replace(' ', '')
        condition = get_condition(point.get('weather_code'))
        low_style = self._temperature_style(low, theme)
        high_style = self._temperature_style(high, theme)
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
        wind_style = self._wind_style(wind, theme)
        gust_style = self._wind_style(gust, theme)
        condition_style = (
            f'bold {theme.get(condition.color_var)}'
            if condition is not None and condition.color_var
            else 'bold'
        )
        date = point.get('time')
        day = (
            date.strftime('%a %d')
            if self._wide_columns and date is not None
            else date.strftime('%a') if date is not None else '--'
        )
        common = (
            Text(day, style='dim'),
            Text(condition.abbr if condition is not None else '--', style=condition_style),
            Text(_number(low, suffix='°'), style=low_style),
            Text(_number(high, suffix='°'), style=high_style),
            Text(_number(probability), style=rain_style),
        )
        if self._wide_columns:
            return common + (
                Text(_amount(amount), style=rain_style),
                Text(_number(wind), style=wind_style),
                Text(_number(gust), style=gust_style),
                Text(direction, style='dim'),
            )
        return common + (
            Text(_number(wind), style=wind_style),
            Text(_number(gust), style=gust_style),
            Text(direction, style='dim'),
        )

    def _temperature_style(self, value: object, theme: dict[str, str]) -> str:
        if not _is_number(value):
            return 'dim'
        return temp_colour(
            value,
            scale='theme_temperature',
            hex=True,
            unit=self.app.temperature_unit,
            theme_colours=theme,
        )

    @staticmethod
    def _wind_style(value: object, theme: dict[str, str]) -> str:
        if not _is_number(value):
            return 'dim'
        return wind_colour(
            value,
            hex=True,
            min_colour=theme['foreground'],
            max_colour=theme['secondary'],
        )


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


__all__ = ['DashboardDailyForecast']
