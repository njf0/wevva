"""Compact Open-Meteo conditions for a tropical-system centre."""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container

from wevva.conditions import get_condition
from wevva.utils import bearing_to_direction, rain_colour, temp_colour, wind_colour
from wevva.widgets.tropical_info_table import TropicalInfoTable


class TropicalCentreWeather(Container):
    """Bordered, density-aware weather near the selected source centre."""

    DEFAULT_CSS = """
    TropicalCentreWeather {
        width: 100%;
        min-width: 100%;
        max-width: 100%;
        height: 0;
        min-height: 0;
        margin: 0;
        border: round $secondary;
        border-title-color: $secondary;
        border-title-align: left;
        overflow-y: hidden;
    }

    TropicalCentreWeather > #tropical-centre-weather-content {
        width: 100%;
        min-width: 100%;
        max-width: 100%;
        height: 1fr;
        min-height: 0;
        padding: 0;
        border: none;
        overflow-y: hidden;
    }
    """

    def __init__(self, *, id: str = 'tropical-centre-weather') -> None:
        super().__init__(id=id)
        self.table = TropicalInfoTable(
            field_width=16,
            id='tropical-centre-weather-content',
        )
        self._rows_cache: tuple[tuple[str, Text], ...] = ()
        self._visible_row_count = 0
        self._weather_available = False
        self._state = 'hidden'
        self.border_title = 'Current weather near centre'
        self.display = False

    def compose(self) -> ComposeResult:
        yield self.table

    def show_loading(self) -> None:
        """Retain a local loading state without overriding layout visibility."""
        self._state = 'loading'
        self._weather_available = True
        self._rows_cache = ()
        self.table.clear()
        self.table.loading = True
        self._sync_display()

    def show_unavailable(self) -> None:
        """Keep a failed independent weather lookup compact and non-fatal."""
        self._state = 'unavailable'
        self._weather_available = True
        self._rows_cache = (
            (
                'Weather',
                Text('Temporarily unavailable', style='dim italic'),
            ),
        )
        self.table.loading = False
        self._render_rows()
        self._sync_display()

    def hide_weather(self) -> None:
        self._state = 'hidden'
        self._weather_available = False
        self._rows_cache = ()
        self.table.loading = False
        self.table.clear()
        self.display = False

    def update_weather(self, response: dict[str, Any]) -> None:
        """Render available current fields without reserving empty rows."""
        current = response.get('current')
        units = response.get('current_units')
        if not isinstance(current, dict):
            self.show_unavailable()
            return
        if not isinstance(units, dict):
            units = {}

        rows = self._rows(response, current, units)
        self._state = 'ready'
        self._weather_available = True
        self._rows_cache = tuple(rows)
        self.table.loading = False
        if not rows:
            self._rows_cache = (
                (
                    'Weather',
                    Text('No current observations', style='dim italic'),
                ),
            )
        self._render_rows()
        self._sync_display()

    def set_layout(self, *, row_count: int, height: int) -> None:
        """Apply a complete-row tier without discarding cached weather data."""
        self._visible_row_count = max(0, int(row_count))
        height = max(0, int(height))
        self.styles.height = height
        self.table.styles.height = max(0, height - 2)
        self._render_rows()
        self._sync_display()

    @property
    def available_row_count(self) -> int:
        return len(self._rows_cache)

    @property
    def visible_row_count(self) -> int:
        return min(self._visible_row_count, len(self._rows_cache))

    @property
    def weather_available(self) -> bool:
        return self._weather_available

    def _sync_display(self) -> None:
        self.display = bool(
            self._weather_available
            and self._visible_row_count
            and self.styles.height.value
        )

    def _render_rows(self) -> None:
        if self._state == 'loading':
            return
        self.table.clear()
        for label, value in self._rows_cache[: self._visible_row_count]:
            self.table.add_row(
                Text(label, style='dim'),
                value,
                key=label.casefold().replace(' ', '-'),
            )

    def _rows(
        self,
        response: dict[str, Any],
        current: dict[str, Any],
        units: dict[str, Any],
    ) -> list[tuple[str, Text]]:
        theme = self.app.theme_variables
        rows: list[tuple[str, Text]] = []

        code = current.get('weather_code')
        condition = get_condition(int(code)) if isinstance(code, (int, float)) else None
        if condition is not None:
            colour = theme.get(condition.color_var or 'text-primary')
            value = Text()
            if getattr(self.app, 'emoji_enabled', True):
                value.append(condition.day_emoji if current.get('is_day') != 0 else condition.night_emoji)
                value.append(' ')
            value.append(condition.name, style=colour)
            rows.append(('Condition', value))
        elif code is not None:
            rows.append(('Condition', Text(f'WMO {code}', style=theme.get('text-primary'))))

        temperature = _number(current.get('temperature_2m'))
        feels = _number(current.get('apparent_temperature'))
        if temperature is not None or feels is not None:
            unit = str(units.get('temperature_2m') or '°C')
            preference = getattr(self.app, 'temperature_unit', 'celsius')
            value = Text()
            if temperature is not None:
                temperature = round(temperature)
                colour = temp_colour(
                    temperature,
                    scale='theme_temperature',
                    hex=True,
                    unit=preference,
                    theme_colours=theme,
                )
                value.append(f'{temperature}', style=_bold(colour))
                value.append(unit, style=colour)
            if feels is not None:
                if value:
                    value.append(' · ')
                feels = round(feels)
                colour = temp_colour(
                    feels,
                    scale='theme_temperature',
                    hex=True,
                    unit=preference,
                    theme_colours=theme,
                )
                value.append('feels ', style='dim')
                value.append(f'{feels}', style=_bold(colour))
                value.append(unit, style=colour)
            rows.append(('Temperature', value))

        speed = _number(current.get('wind_speed_10m'))
        gust = _number(current.get('wind_gusts_10m'))
        direction = _number(current.get('wind_direction_10m'))
        if speed is not None or gust is not None:
            unit = str(units.get('wind_speed_10m') or 'km/h')
            maximum = theme.get('secondary') or theme.get('primary')
            minimum = theme.get('foreground') or theme.get('text')
            value = Text()
            if speed is not None:
                speed = round(speed)
                colour = wind_colour(speed, hex=True, min_colour=minimum, max_colour=maximum)
                value.append(f'{speed}', style=_bold(colour))
                value.append(f' {unit}', style=colour)
                if direction is not None:
                    value.append(f' {bearing_to_direction(direction)}')
            if gust is not None:
                if value:
                    value.append(' · ')
                gust = round(gust)
                colour = wind_colour(gust, hex=True, min_colour=minimum, max_colour=maximum)
                value.append('gusts ', style='dim')
                value.append(f'{gust}', style=_bold(colour))
                value.append(f' {unit}', style=colour)
            rows.append(('Wind', value))

        probability = _number(current.get('precipitation_probability'))
        amount = _number(current.get('precipitation'))
        if probability is not None or amount is not None:
            value = Text()
            if probability is not None:
                colour = rain_colour(
                    probability,
                    hex=True,
                    min_colour=theme.get('foreground'),
                    max_colour=theme.get('primary'),
                )
                value.append(f'{probability:g}', style=_bold(colour))
                value.append('%', style=colour)
            if amount is not None:
                if value:
                    value.append(' · ')
                unit = str(units.get('precipitation') or 'mm')
                colour = theme.get('text-primary')
                value.append(f'{amount:g}', style=_bold(colour))
                value.append(f' {unit}/hr', style=colour)
            rows.append(('Precipitation', value))

        pressure = _number(current.get('surface_pressure'))
        if pressure is not None:
            unit = str(units.get('surface_pressure') or 'hPa')
            colour = theme.get('text-error')
            value = Text(f'{round(pressure)}', style=_bold(colour))
            value.append(f' {unit}', style=colour)
            rows.append(('Surface pressure', value))

        latitude = _number(response.get('latitude'))
        longitude = _number(response.get('longitude'))
        if latitude is not None and longitude is not None:
            rows.append(('Forecast coords', Text(_coordinates(latitude, longitude), style='italic')))
        return rows


def _number(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _bold(colour: str | None) -> str:
    return f'bold {colour}' if colour else 'bold'


def _coordinates(latitude: float, longitude: float) -> str:
    return (
        f'{abs(latitude):.2f}°{"N" if latitude >= 0 else "S"} '
        f'{abs(longitude):.2f}°{"E" if longitude >= 0 else "W"}'
    )


__all__ = ['TropicalCentreWeather']
