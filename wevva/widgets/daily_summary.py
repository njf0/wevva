"""Daily summary table.

Shows min/max, rain, wind and direction by day. Keeps legacy id.
"""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import DataTable

from wevva.conditions import get_condition
from wevva.utils import rain_colour, temp_colour, wind_colour


class DailySummaryTable(DataTable):
    # Reactive property (set by parent DailyForecast)
    daily_model: reactive[Any | None] = reactive(None)

    def __init__(self, *, id: str = "min-max-spread-table") -> None:
        super().__init__(
            show_header=False,
            cursor_type="row",
            id=id,
            cell_padding=0,
            zebra_stripes=True,
        )

    def on_mount(self) -> None:
        """Trigger initial display after mounting."""
        if self.daily_model is not None:
            self._update_display()

    def watch_daily_model(self, model: Any | None) -> None:
        """React to daily model changes."""
        if model is not None and self.is_mounted:
            self._update_display()

    def _update_display(self) -> None:
        """Rebuild the daily table from the provided model."""
        self.clear(columns=True)
        min_days = 2
        if (
            not self.daily_model.forecast_timeseries
            or len(self.daily_model.forecast_timeseries) < min_days
        ):
            return

        # Cache units for performance
        self._units = self.daily_model.forecast_units

        # Columns
        self.add_column("Day", width=13)
        # if show_emoji:
        # self.add_column('Emoji', width=2)
        self.add_column("Condition", width=30)
        self.add_column("Min-Max", width=8)
        self.add_column("Rain%", width=5)
        self.add_column("Precip", width=7)
        self.add_column("Wind", width=13)
        self.add_column("Wind Direction", width=6)
        self.add_column("Sunrise", width=7)
        self.add_column("Sunset", width=7)

        # Skip today (index 0), show tomorrow onwards
        for display_idx, day in enumerate(self.daily_model.forecast_timeseries[1:]):
            self._add_daily_row(display_idx, day)
        self.refresh()

    def _day_offset(self, display_idx: int) -> int:
        """Convert display index to model index (skipping today at index 0)."""
        return display_idx + 1

    def _add_daily_row(self, display_idx: int, day: dict) -> None:
        """Add a single daily forecast row with all cells."""
        show_emoji = self.app.emoji_enabled
        model_idx = self._day_offset(display_idx)
        theme_vars = self.app.theme_variables

        # === Day name cell ===
        # use a format like Mon 03
        day_name = day["time"].strftime("%A %d")
        day_cell = Text(day_name, style="dim", justify="left")

        # === Condition cell with optional emoji ===
        day_model = self.daily_model.forecast_timeseries[model_idx]
        cond = get_condition(day_model.get("weather_code"))
        condition_text = self.daily_model.get_weather_code(
            model_idx, return_emoji=False
        )
        prefix = " " if show_emoji else ""
        condition_cell = Text(
            f"{prefix}{condition_text}",
            style=f"italic {theme_vars.get(cond.color_var)}",
            justify="left",
        )

        # === Min/max temperature cell with colour ===
        min_temp = self.daily_model.get_temperature_min(model_idx)
        max_temp = self.daily_model.get_temperature_max(model_idx)
        temp_unit_pref = getattr(self.app, "temperature_unit", "celsius")
        min_colour = temp_colour(min_temp, hex=True, unit=temp_unit_pref)
        max_colour = temp_colour(max_temp, hex=True, unit=temp_unit_pref)
        temp_unit = self._units.get("temperature_2m_min", "°C")[0]
        min_max_cell = Text("")
        min_max_cell.append(f"{min_temp:.0f}{temp_unit}", style=f"bold {min_colour}")
        min_max_cell.append("-", style="dim")
        min_max_cell.append(f"{max_temp:.0f}{temp_unit}", style=f"bold {max_colour}")
        min_max_cell.justify = "right"

        # === Rain probability ===
        rain_max = theme_vars["primary"]

        rain_prob = self.daily_model.get_precipitation_probability(model_idx)
        precip = self.daily_model.get_precipitation(model_idx)
        rain_prob_unit = self._units.get("precipitation_probability_max", "%")
        precip_unit = self._units.get("precipitation_sum", "mm")
        rain_prob_col = rain_colour(
            rain_prob,
            hex=True,
            min_colour=theme_vars["foreground"],
            max_colour=rain_max,
        )
        rain_prob_cell = Text(
            f"{rain_prob:.0f}{rain_prob_unit}", style=f"bold {rain_prob_col}"
        )
        precip_cell = Text(f"{precip:.1f}{precip_unit}", style=f"{rain_prob_col}")
        rain_prob_cell.justify = "right"
        precip_cell.justify = "right"

        # === Wind speed, gusts ===
        wind_max = theme_vars["accent"]
        wind_speed = self.daily_model.get_wind_speed(model_idx)
        wind_gust = self.daily_model.get_wind_gust(model_idx)
        wind_dir = self.daily_model.get_wind_direction(model_idx)
        wind_unit = self._units.get("wind_speed_10m_max", "mph")

        wind_col = wind_colour(
            wind_speed,
            hex=True,
            min_colour=theme_vars["foreground"],
            max_colour=wind_max,
        )
        wind_speed_cell = Text("")
        wind_speed_cell.append(f"{wind_speed:.0f}", style=f"bold {wind_col}")
        wind_speed_cell.append(f"{wind_unit}", style=f"bold {wind_col}")
        wind_speed_cell.append(" (")
        wind_speed_cell.append(f"{wind_gust:.0f}", style=f"{wind_col}")
        wind_speed_cell.append(")")
        wind_speed_cell.justify = "right"

        # === Wind direction cell with arrow ===
        wind_dir_cell = Text(f"{wind_dir}", style=f"bold {wind_col}", justify="right")

        # Sunrise / sunset
        sunrise = self.daily_model.get_sunrise(model_idx)
        if sunrise:
            sunrise_time = sunrise.strftime("%H:%M")
            sunrise_cell = Text(
                f"{sunrise_time}", style=f"dim {theme_vars['warning']}", justify="right"
            )
        else:
            sunrise_cell = Text("--:--", style="dim", justify="right")

        sunset = self.daily_model.get_sunset(model_idx)
        if sunset:
            sunset_time = sunset.strftime("%H:%M")
            sunset_cell = Text(
                f"{sunset_time}", style=f"dim {theme_vars['error']}", justify="right"
            )
        else:
            sunset_cell = Text("--:--", style="dim", justify="right")

        # Assemble row
        cells = [day_cell]
        # if show_emoji:
        #     cells.append(emoji_cell)
        cells.extend(
            [
                condition_cell,
                min_max_cell,
                rain_prob_cell,
                precip_cell,
                wind_speed_cell,
                wind_dir_cell,
                sunrise_cell,
                sunset_cell,
            ]
        )
        self.add_row(*cells, key=day_name)
