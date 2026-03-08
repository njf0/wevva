"""Precipitation widget (WeatherWidget-style).

Shows precipitation probability as big digits and, below, the dominant
precipitation type (rain/showers/snow) with its amount.
"""

from __future__ import annotations

from typing import Any

from textual.reactive import reactive

from wevva.utils import rain_colour
from wevva.widgets.weather_widget import WeatherWidget

# Precipitation type configuration: (type_name, getter_method, theme_var_key)
_PRECIP_TYPES = [
    ("rain", "get_rain", "primary"),
    ("showers", "get_showers", "secondary"),
    ("snow", "get_snowfall", "foreground"),
]


class PrecipWidget(WeatherWidget):
    """WeatherWidget-style precipitation tile for a specific hour."""

    # Reactive state
    hourly_model: reactive[Any | None] = reactive(None)
    hour_index: reactive[int] = reactive(0)

    def __init__(self, *, id: str = "ww-precip", classes: str = "weather-widget"):
        """Initialize the precipitation widget with a title and styling."""
        super().__init__(title="Precipitation", id=id, classes=classes)

    def on_mount(self) -> None:
        """Trigger initial display after mounting."""
        if self.hourly_model is not None:
            self.watch_hourly_model(self.hourly_model)

    def watch_hourly_model(self, hourly_model: Any | None) -> None:
        """Update display when hourly model changes."""
        if hourly_model is None or not self.is_mounted:
            return
        self._update_display()

    def watch_hour_index(self, hour_index: int) -> None:
        """Update display when selected hour changes."""
        if self.hourly_model is None or not self.is_mounted:
            return
        self._update_display()

    def _update_display(self) -> None:
        """Update digits to precip probability and lower text to dominant type."""
        theme_vars = self.app.theme_variables
        prob = self.hourly_model.get_precipitation_probability(self.hour_index) or 0

        # Get dominant precipitation type and its amount
        label, amount, colour_hex = self._get_dominant_precip_type(theme_vars)

        # Get precipitation unit from forecast
        precip_unit = self.hourly_model.forecast_units.get("precipitation", "mm")

        # Colour digits by probability
        prob_colour = rain_colour(
            prob,
            hex=True,
            min_colour=theme_vars["foreground"],
            max_colour=theme_vars.get("primary"),
        )

        # Build lower text showing dominant type and amount
        lower = f"[i][{colour_hex}]{amount}{precip_unit}/hr[/] {label}[/]"
        self.set(prob, lower_text=lower, colour=prob_colour, units="%")
        self.refresh()

    def _get_dominant_precip_type(self, theme_vars: dict) -> tuple[str, float, str]:
        """Determine which precipitation type has the highest amount.

        Returns:
            Tuple of (type_name, amount, colour_hex)

        """
        precip_data = []
        for type_name, getter_name, theme_key in _PRECIP_TYPES:
            getter = getattr(self.hourly_model, getter_name)
            amount = getter(self.hour_index) or 0
            colour = theme_vars.get(theme_key)
            precip_data.append((type_name, amount, colour))

        # Return the type with maximum amount
        # return max(precip_data, key=lambda t: t[1])
        # If all amounts are zero, return 'precip.'
        max_type = max(precip_data, key=lambda t: t[1])
        if max_type[1] == 0:
            return "precip.", 0, self.app.theme_variables.get("foreground")
        return max_type
