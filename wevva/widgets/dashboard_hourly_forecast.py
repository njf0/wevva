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


_MINIMUM_WIDTHS = (2, 3, 8, 7, 9)
_PREFERRED_WIDTHS = (3, 4, 12, 12, 17)


class DashboardHourlyForecast(Container):
    """One formatted row per hour with no horizontal navigation."""

    DEFAULT_CSS = """
    DashboardHourlyForecast {
        width: 100%;
        height: 2fr;
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
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._hourly_model: Any | None = None
        self._indices: list[int] = []
        self._column_widths: tuple[int, ...] = ()

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
        self._rebuild()

    def on_resize(self, event: Resize) -> None:
        event.stop()
        widths = _fitted_widths(max(1, event.size.width - 1))
        if widths != self._column_widths:
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

        self._column_widths = _fitted_widths(
            max(1, self.content_size.width - 1)
        )
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
        feels = model.get_feels_temperature(index)
        probability = model.get_precipitation_probability(index)
        amount = model.get_precipitation(index)
        wind = model.get_wind_speed(index)
        gust = model.get_wind_gust(index)
        condition = get_condition(point.get('weather_code'))
        temperature_style = _temperature_style(
            temperature,
            unit=self.app.temperature_unit,
            theme=theme,
        )
        feels_style = _temperature_style(
            feels,
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
        gust_style = _wind_style(gust, theme)
        condition_style = (
            f'bold {theme.get(condition.color_var)}'
            if condition is not None and condition.color_var
            else 'bold'
        )
        time = point.get('time')
        hour = time.strftime('%H') if time is not None else '--'
        temp_unit = model.forecast_units.get('temperature_2m', '°C')
        precip_unit = model.forecast_units.get('precipitation', 'mm')
        wind_unit = model.forecast_units.get('wind_speed_10m', '')
        direction = (model.get_wind_direction(index) or '--').replace(' ', '')
        return (
            Text(hour, style='dim'),
            Text(
                condition.abbr if condition is not None else '--',
                style=condition_style,
            ),
            _paired_measure(
                temperature,
                feels,
                unit=temp_unit,
                primary_style=temperature_style,
                secondary_style=feels_style,
            ),
            _paired_measure(
                probability,
                amount,
                unit='%',
                secondary_unit=precip_unit,
                primary_style=rain_style,
                secondary_style=rain_style,
                secondary_amount=True,
            ),
            _wind_measure(
                wind,
                direction,
                gust,
                unit=wind_unit,
                wind_style=wind_style,
                gust_style=gust_style,
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


def _paired_measure(
    primary: object,
    secondary: object,
    *,
    unit: str,
    primary_style: str,
    secondary_style: str,
    secondary_unit: str | None = None,
    secondary_amount: bool = False,
) -> Text:
    text = Text()
    text.append(_number(primary), style=primary_style)
    text.append(unit)
    text.append(' (')
    text.append(
        _amount(secondary) if secondary_amount else _number(secondary),
        style=secondary_style,
    )
    text.append(secondary_unit if secondary_unit is not None else unit)
    text.append(')')
    return text


def _wind_measure(
    wind: object,
    direction: str,
    gust: object,
    *,
    unit: str,
    wind_style: str,
    gust_style: str,
) -> Text:
    text = Text()
    text.append(_number(wind), style=wind_style)
    text.append(unit)
    text.append(' ')
    text.append(direction, style=wind_style if direction != '--' else 'dim')
    text.append(' (')
    text.append(_number(gust), style=gust_style)
    text.append(unit)
    text.append(')')
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


def _amount(value: object) -> str:
    if not _is_number(value):
        return '--'
    assert isinstance(value, (int, float))
    return f'{value:.1f}' if abs(value) < 10 else f'{round(value):.0f}'


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


__all__ = ['DashboardHourlyForecast']
