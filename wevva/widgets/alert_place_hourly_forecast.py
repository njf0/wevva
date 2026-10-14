"""Fixed-width hourly forecast strip for an Alerts Centre settlement."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.events import Resize
from textual.widgets import LoadingIndicator, Static

from wevva.layout import HourlyRow
from wevva.openmeteo import HourlyOpenMeteoForecast
from wevva.utils import (
    create_rain_blocks,
    create_temp_blocks,
    rain_colour,
    temp_colour,
    wind_colour,
)


class AlertPlaceHourlyForecast(Container):
    """Render consecutive hours with no tabs, cursor, or scrolling."""

    HOUR_COLUMN_WIDTH = 4
    MAX_HOURS = 24

    DEFAULT_CSS = """
    AlertPlaceHourlyForecast {
        display: none;
        width: 100%;
        min-width: 0;
        height: 0;
        border: round $primary;
        border-title-color: $primary;
        border-title-align: center;
        overflow: hidden hidden;
        background: $background;
    }

    #alert-place-hourly-loading,
    #alert-place-hourly-content {
        width: 100%;
        height: 1fr;
        min-width: 0;
        content-align: center middle;
        text-align: center;
        text-wrap: nowrap;
        text-overflow: clip;
        overflow: hidden hidden;
    }

    #alert-place-hourly-loading {
        display: none;
        color: $primary;
    }

    AlertPlaceHourlyForecast.failed > #alert-place-hourly-content {
        color: $text-error;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.place_name: str | None = None
        self.forecast: HourlyOpenMeteoForecast | None = None
        self.state = 'idle'
        self.visible_rows: tuple[HourlyRow, ...] = ()
        self.hour_count = 0
        self.column_widths: tuple[int, ...] = ()
        self._available_width = 0

    def compose(self) -> ComposeResult:
        yield LoadingIndicator(id='alert-place-hourly-loading')
        yield Static('', id='alert-place-hourly-content')

    @property
    def content(self) -> Static:
        return self.query_one('#alert-place-hourly-content', Static)

    @property
    def loading_indicator(self) -> LoadingIndicator:
        return self.query_one(
            '#alert-place-hourly-loading',
            LoadingIndicator,
        )

    def set_layout(self, height: int, rows: tuple[HourlyRow, ...]) -> None:
        """Apply a complete-row budget supplied by the screen allocator."""

        self.visible_rows = tuple(rows)
        self.styles.height = max(0, height)
        self.display = height > 0
        self._render_forecast()

    def set_state(
        self,
        *,
        place_name: str | None,
        state: str,
        forecast: HourlyOpenMeteoForecast | None,
    ) -> None:
        self.place_name = place_name
        self.state = state
        self.forecast = forecast
        self.border_title = f'Hourly forecast — {place_name}' if place_name else 'Hourly forecast'
        self.set_class(state == 'failed', 'failed')
        self._render_forecast()

    def refresh_theme(self) -> None:
        """Rebuild semantic colours after an application theme change."""

        self._render_forecast()

    def on_mount(self) -> None:
        self._available_width = max(0, self.size.width)
        self._render_forecast()

    def on_resize(self, event: Resize) -> None:
        event.stop()
        self._available_width = max(0, event.size.width - 2)
        self._render_forecast()

    def _render_forecast(self) -> None:
        if not self.is_mounted:
            return
        loading = self.loading_indicator
        loading.display = self.state == 'loading'
        self.content.display = self.state != 'loading'
        if self.state == 'loading':
            self.hour_count = 0
            self.column_widths = ()
            self.content.update('')
            return
        if self.state == 'failed':
            self.hour_count = 0
            self.column_widths = ()
            self.content.update('Hourly forecast unavailable. Press r to retry.')
            return
        if self.state != 'ready' or self.forecast is None:
            self.hour_count = 0
            self.column_widths = ()
            self.content.update('')
            return

        points = self.forecast.forecast_timeseries
        if not points:
            self.hour_count = 0
            self.column_widths = ()
            self.content.update('No hourly forecast is available.')
            return
        count = min(
            self.MAX_HOURS,
            len(points),
            self._available_width // self.HOUR_COLUMN_WIDTH,
        )
        if count <= 0:
            self.hour_count = 0
            self.column_widths = ()
            self.content.update('')
            return
        self.hour_count = count
        base_width, remainder = divmod(self._available_width, count)
        self.column_widths = tuple(
            base_width + (1 if index < remainder else 0)
            for index in range(count)
        )
        self.content.update(self._build_renderable(count))

    def _build_renderable(self, count: int) -> Text:
        model = self.forecast
        assert model is not None
        temperatures = [_number(model.get_temperature(index)) for index in range(count)]
        rain = [_number(model.get_precipitation_probability(index)) for index in range(count)]
        wind = [_number(model.get_wind_speed(index)) for index in range(count)]
        temp_blocks = _blocks(temperatures, create_temp_blocks)
        rain_blocks = _blocks(rain, create_rain_blocks)
        wind_blocks = _blocks(wind, create_temp_blocks)
        output = Text(no_wrap=True, overflow='crop')
        for row_index, row in enumerate(self.visible_rows):
            if row_index:
                output.append('\n')
            cells = self._row_cells(
                row,
                count,
                temperatures,
                rain,
                wind,
                temp_blocks,
                rain_blocks,
                wind_blocks,
            )
            for (value, style), width in zip(cells, self.column_widths, strict=True):
                output.append(_centred(value, width), style=style)
        return output

    def _row_cells(
        self,
        row: HourlyRow,
        count: int,
        temperatures: list[float | None],
        rain: list[float | None],
        wind: list[float | None],
        temp_blocks: list[str],
        rain_blocks: list[str],
        wind_blocks: list[str],
    ) -> list[tuple[str, str]]:
        model = self.forecast
        assert model is not None
        theme = self.app.theme_variables
        temp_unit = getattr(self.app, 'temperature_unit', 'celsius')
        temp_suffix = str(model.forecast_units.get('temperature_2m', '°C'))[:1]
        rain_unit = str(model.forecast_units.get('precipitation_probability', '%'))
        cells: list[tuple[str, str]] = []
        for index in range(count):
            temperature = temperatures[index]
            rainfall = rain[index]
            wind_speed = wind[index]
            temp_style = _temperature_style(temperature, temp_unit, theme)
            rain_style = _rain_style(rainfall, theme)
            wind_style = _wind_style(wind_speed, theme)
            if row is HourlyRow.TEMPERATURE_BAR:
                cells.append((temp_blocks[index], temp_style))
            elif row is HourlyRow.TEMPERATURE:
                cells.append((f'{temperature:.0f}{temp_suffix}' if temperature is not None else '', temp_style))
            elif row is HourlyRow.RAIN_BAR:
                cells.append((rain_blocks[index], rain_style))
            elif row is HourlyRow.RAIN:
                cells.append((f'{rainfall:.0f}{rain_unit}' if rainfall is not None else '', rain_style))
            elif row is HourlyRow.WIND_BAR:
                cells.append((wind_blocks[index], wind_style))
            elif row is HourlyRow.WIND:
                direction = model.get_wind_direction(index)
                suffix = direction[-1] if isinstance(direction, str) and direction else ''
                cells.append((f'{wind_speed:.0f}{suffix}' if wind_speed is not None else '', wind_style))
            else:
                point = model.get_point(index)
                hour = point.get('time') if point else None
                cells.append((hour.strftime('%H') if hour is not None else '', 'bold'))
        return cells


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _blocks(values: list[float | None], builder) -> list[str]:
    present = [value for value in values if value is not None]
    if not present:
        return [''] * len(values)
    built = builder(present, width=4)
    iterator = iter(built)
    return [next(iterator) if value is not None else '' for value in values]


def _temperature_style(value: float | None, unit: str, theme: dict[str, str]) -> str:
    if value is None:
        return ''
    colour = temp_colour(
        value,
        scale='theme_temperature',
        hex=True,
        unit=unit,
        theme_colours=theme,
    )
    return f'bold {colour}'


def _rain_style(value: float | None, theme: dict[str, str]) -> str:
    if value is None:
        return ''
    colour = rain_colour(
        value,
        hex=True,
        min_colour=theme['foreground'],
        max_colour=theme['primary'],
    )
    return f'bold {colour}'


def _wind_style(value: float | None, theme: dict[str, str]) -> str:
    if value is None:
        return ''
    colour = wind_colour(
        value,
        hex=True,
        min_colour=theme['foreground'],
        max_colour=theme['secondary'],
    )
    return f'bold {colour}'


def _centred(value: str, width: int) -> str:
    value = value[:width]
    left = max(0, (width - len(value)) // 2)
    return f'{" " * left}{value}{" " * (width - len(value) - left)}'


__all__ = ['AlertPlaceHourlyForecast']
