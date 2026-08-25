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
    """Bordered six-row current-weather region for the selected source centre."""

    DEFAULT_CSS = """
    TropicalCentreWeather {
        width: 100%;
        min-width: 100%;
        max-width: 100%;
        height: 8;
        min-height: 8;
        max-height: 8;
        margin: 0 0 1 0;
        border: round $secondary;
        border-title-color: $secondary;
        border-title-align: left;
        overflow-y: hidden;
    }

    TropicalCentreWeather > #tropical-centre-weather-content {
        width: 100%;
        min-width: 100%;
        max-width: 100%;
        height: 6;
        min-height: 6;
        max-height: 6;
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
        self.border_title = 'Current weather near centre'
        self.display = False

    def compose(self) -> ComposeResult:
        yield self.table

    def show_loading(self) -> None:
        """Keep the titled frame visible while its six-row body loads."""
        self.table.clear()
        self.display = True
        self.table.loading = True

    def show_unavailable(self) -> None:
        """Keep a failed independent weather lookup compact and non-fatal."""
        self.table.loading = False
        self.table.clear()
        self.table.add_row(
            Text('Weather', style='dim'),
            Text('Temporarily unavailable', style='dim italic'),
            key='weather',
        )
        self.display = True

    def hide_weather(self) -> None:
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
        self.table.loading = False
        self.table.clear()
        for label, value in rows:
            self.table.add_row(
                Text(label, style='dim'),
                value,
                key=label.casefold().replace(' ', '-'),
            )
        if not rows:
            self.table.add_row(
                Text('Weather', style='dim'),
                Text('No current observations', style='dim italic'),
                key='weather',
            )
        self.display = True

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
