"""Current conditions widget.

Shows temperature, precipitation, wind, and a small detail table.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Container
from textual.reactive import reactive

from wevva.messages import HourHighlighted, WeatherUpdated
from wevva.utils import temp_colour, wind_colour
from wevva.widgets.current_detail import CurrentDetailTable
from wevva.widgets.precip_info import PrecipWidget
from wevva.widgets.weather_widget import WeatherWidget


class CurrentConditions(Container):
    """Three tiles and a detail table for the selected hour (default now)."""

    # Reactive state
    hourly_model: reactive[Any | None] = reactive(None)
    hour_index: reactive[int] = reactive(0)

    DEFAULT_CSS = """
    CurrentConditions {
        layout: horizontal;
        align-horizontal: center;
        margin-bottom: 1;
        height: auto;
        hatch: right $background-lighten-1;
    }
    """

    def compose(self) -> ComposeResult:
        """Create the temp/rain/wind tiles and the detail table."""
        yield WeatherWidget('Temperature', id='ww-temp')
        yield PrecipWidget()
        yield WeatherWidget('Wind', id='ww-wind')
        yield CurrentDetailTable()

    # Property accessors for child widgets
    @property
    def temp(self) -> WeatherWidget:
        return self.query_one('#ww-temp', WeatherWidget)

    @property
    def precip(self) -> PrecipWidget:
        return self.query_one(PrecipWidget)

    @property
    def wind(self) -> WeatherWidget:
        return self.query_one('#ww-wind', WeatherWidget)

    @property
    def detail(self) -> CurrentDetailTable:
        return self.query_one(CurrentDetailTable)

    def on_mount(self) -> None:
        """Trigger initial display after mounting."""
        if self.hourly_model is not None:
            self._update_display()

    def watch_hourly_model(self, model: Any | None) -> None:
        """React to hourly model changes."""
        if model is not None and self.is_mounted:
            self._update_display()

    def watch_hour_index(self, index: int) -> None:
        """React to hour index changes."""
        if self.is_mounted and self.hourly_model is not None:
            self._update_display()

    def _update_display(self) -> None:
        """Update tiles and details for the current hour using the hourly model."""
        # Update temperature tile
        self._update_temperature_tile()

        # Update precipitation tile (via reactive properties)
        self.precip.hourly_model = self.hourly_model
        self.precip.hour_index = self.hour_index

        # Update wind tile
        self._update_wind_tile()

        # Update details table (via reactive properties)
        self.detail.hourly_model = self.hourly_model
        self.detail.hour_index = self.hour_index
        self.refresh()

    # Helper methods ------------------------------------------------------
    def _update_temperature_tile(self) -> None:
        """Update temperature tile with current values and colours."""
        t = round(self.hourly_model.get_temperature(self.hour_index))
        feels = self.hourly_model.get_feels_temperature(self.hour_index)

        # Get temperature unit from app for color scale
        theme_vars = self.app.theme_variables
        temp_unit = getattr(self.app, 'temperature_unit', 'celsius')
        colour = temp_colour(
            t,
            scale='theme_temperature',
            hex=True,
            unit=temp_unit,
            theme_colours=theme_vars,
        )
        feels_colour = temp_colour(
            feels,
            scale='theme_temperature',
            hex=True,
            unit=temp_unit,
            theme_colours=theme_vars,
        )

        t_unit = self.hourly_model.forecast_units.get('temperature_2m', '°C')

        self.temp.set(
            t,
            f'[i]Feels like [{feels_colour}]{feels}{t_unit}[/]',
            colour=colour,
            units=t_unit,
        )

    def _update_wind_tile(self) -> None:
        """Update wind tile with speed, gusts, and direction."""
        ws = round(self.hourly_model.get_wind_speed(self.hour_index))
        gust = self.hourly_model.get_wind_gust(self.hour_index)
        wdir = self.hourly_model.get_wind_direction(self.hour_index)

        ws_unit = self.hourly_model.forecast_units.get('wind_speed_10m', 'mph')
        theme_vars = self.app.theme_variables

        # Colour based on wind speed
        wind_max = theme_vars['secondary']
        s_colour = wind_colour(ws, hex=True, min_colour=theme_vars['foreground'], max_colour=wind_max)
        g_colour = wind_colour(gust, hex=True, min_colour=theme_vars['foreground'], max_colour=wind_max)

        self.wind.set(
            ws,
            f'[i]Gusts of [{g_colour}]{gust}{ws_unit}[/]',
            colour=s_colour,
            units=f'{ws_unit} {wdir}',
        )

    # Messages ------------------------------------------------------------
    async def on_weather_updated(self, event: WeatherUpdated) -> None:
        """Update current conditions when new data arrives (defaults to first hour)."""
        self.hourly_model = event.hourly
        self.hour_index = 0

    async def on_hour_highlighted(self, message: HourHighlighted) -> None:
        """Update tiles/details when the user selects a specific hour in the hourly table."""
        self.hour_index = message.index
