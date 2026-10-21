"""Daily summary table.

Shows min/max, rain, wind and direction by day. Keeps legacy id.
"""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import DataTable

from wevva.conditions import get_condition
from wevva.layout import DailyColumn, daily_column_widths
from wevva.utils import emoji_prefix, rain_colour, temp_colour, wind_colour


class DailySummaryTable(DataTable):
    # Reactive property (set by parent DailyForecast)
    daily_model: reactive[Any | None] = reactive(None)

    def __init__(self, *, id: str = 'min-max-spread-table') -> None:
        super().__init__(
            show_header=False,
            cursor_type='row',
            id=id,
            cell_padding=0,
            zebra_stripes=True,
        )
        self._visible_columns = tuple(
            column
            for column in DailyColumn
            if column is not DailyColumn.WIND_DIRECTION
        )
        self._row_count = 6
        self._column_widths: tuple[int, ...] | None = None

    def set_layout(
        self,
        columns: tuple[DailyColumn, ...],
        row_count: int,
        column_widths: tuple[int, ...] | None = None,
    ) -> None:
        """Select complete field groups and complete forecast days."""

        columns = tuple(columns)
        row_count = max(0, int(row_count))
        if column_widths is not None and len(column_widths) != len(columns):
            raise ValueError('column_widths must match the selected columns')
        changed = (
            columns != self._visible_columns
            or row_count != self._row_count
            or column_widths != self._column_widths
        )
        self._visible_columns = columns
        self._row_count = row_count
        self._column_widths = column_widths
        self.styles.height = row_count
        if changed and self.daily_model is not None and self.is_mounted:
            self._update_display()

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
        selected_row = self.cursor_row
        self.clear(columns=True)
        if not self.daily_model.forecast_timeseries or self._row_count == 0:
            return

        # Cache units for performance
        self._units = self.daily_model.forecast_units

        column_labels = {
            DailyColumn.DATE: 'Day',
            DailyColumn.CONDITION: 'Cond.',
            DailyColumn.TEMPERATURE: 'Min-Max',
            DailyColumn.RAIN: 'Rain',
            DailyColumn.WIND: 'Wind',
            DailyColumn.PRECIPITATION: 'Precip',
            DailyColumn.GUST: 'Gust',
            DailyColumn.WIND_DIRECTION: 'Wind Direction',
            DailyColumn.SUNRISE: 'Rise',
            DailyColumn.SUNSET: 'Set',
        }
        widths = self._column_widths or daily_column_widths(self._visible_columns)
        for column, width in zip(self._visible_columns, widths, strict=True):
            self.add_column(column_labels[column], key=column.value, width=width)

        # Skip today (index 0), show tomorrow onwards
        days = self.daily_model.forecast_timeseries[1 : self._row_count + 1]
        for display_idx, day in enumerate(days):
            self._add_daily_row(display_idx, day)
        if days:
            self.move_cursor(
                row=min(selected_row, len(days) - 1),
                animate=False,
                scroll=False,
            )
        self.refresh()

    def _day_offset(self, display_idx: int) -> int:
        """Convert display index to model index (skipping today at index 0)."""
        return display_idx + 1

    def _add_daily_row(self, display_idx: int, day: dict) -> None:
        """Add a single daily forecast row with all cells."""
        model_idx = self._day_offset(display_idx)
        theme_vars = self.app.theme_variables

        wide = (
            DailyColumn.WIND_DIRECTION in self._visible_columns
            and DailyColumn.GUST not in self._visible_columns
        )

        # === Day name cell ===
        day_name = day['time'].strftime('%A %d' if wide else '%a %d')
        day_cell = Text(day_name, style='dim', justify='left')

        # === Condition cell with optional emoji ===
        day_model = self.daily_model.forecast_timeseries[model_idx]
        cond = get_condition(day_model.get('weather_code'))
        condition_name = (
            self.daily_model.get_weather_code(model_idx, return_emoji=False)
            if wide
            else (cond.abbr if cond else '--')
        )
        condition_colour = theme_vars.get(cond.color_var) if (cond and cond.color_var) else theme_vars.get('primary')
        emphasis = 'italic' if wide else 'bold'
        condition_style = f'{emphasis} {condition_colour}' if condition_colour else emphasis
        condition_cell = Text(justify='left')
        if wide and self.app.emoji_enabled:
            condition_cell.append(
                emoji_prefix(
                    self.daily_model.get_weather_code(model_idx, return_emoji=True)
                )
            )
        condition_cell.append(condition_name, style=condition_style)

        # === Min/max temperature cell with colour ===
        min_temp = self.daily_model.get_temperature_min(model_idx)
        max_temp = self.daily_model.get_temperature_max(model_idx)
        temp_unit_pref = getattr(self.app, 'temperature_unit', 'celsius')
        min_colour = temp_colour(
            min_temp,
            scale='theme_temperature',
            hex=True,
            unit=temp_unit_pref,
            theme_colours=theme_vars,
        )
        max_colour = temp_colour(
            max_temp,
            scale='theme_temperature',
            hex=True,
            unit=temp_unit_pref,
            theme_colours=theme_vars,
        )
        temp_unit = self._units.get('temperature_2m_min', '°C')[0]
        min_max_cell = Text('')
        min_max_cell.append(f'{min_temp:.0f}{temp_unit}', style=f'bold {min_colour}')
        min_max_cell.append('-', style='dim')
        min_max_cell.append(f'{max_temp:.0f}{temp_unit}', style=f'bold {max_colour}')
        min_max_cell.justify = 'right'

        # === Rain probability ===
        rain_max = theme_vars['primary']

        rain_prob = self.daily_model.get_precipitation_probability(model_idx)
        precip = self.daily_model.get_precipitation(model_idx)
        rain_prob_unit = self._units.get('precipitation_probability_max', '%')
        precip_unit = self._units.get('precipitation_sum', 'mm')
        rain_prob_col = rain_colour(
            rain_prob,
            hex=True,
            min_colour=theme_vars['foreground'],
            max_colour=rain_max,
        )
        rain_prob_cell = Text(f'{rain_prob:.0f}{rain_prob_unit}', style=f'bold {rain_prob_col}')
        precip_cell = Text(f'{precip:.1f}{precip_unit}', style=f'{rain_prob_col}')
        combined_rain_cell = Text('', justify='right')
        combined_rain_cell.append(f'{rain_prob:.0f}{rain_prob_unit}', style=f'bold {rain_prob_col}')
        combined_rain_cell.append('/')
        combined_rain_cell.append(f'{precip:.1f}{precip_unit}', style=rain_prob_col)
        rain_prob_cell.justify = 'right'
        precip_cell.justify = 'right'

        # === Wind speed, gusts ===
        wind_max = theme_vars['secondary']
        wind_speed = self.daily_model.get_wind_speed(model_idx)
        wind_gust = self.daily_model.get_wind_gust(model_idx)
        wind_dir = self.daily_model.get_wind_direction(model_idx)
        wind_unit = self._units.get('wind_speed_10m_max', 'mph')

        wind_col = wind_colour(
            wind_speed,
            hex=True,
            min_colour=theme_vars['foreground'],
            max_colour=wind_max,
        )
        wind_speed_cell = Text('', justify='right')
        wind_speed_cell.append(f'{wind_speed:.0f}{wind_unit}', style=f'bold {wind_col}')
        if DailyColumn.GUST not in self._visible_columns:
            wind_speed_cell.append(' (')
            wind_speed_cell.append(f'{wind_gust:.0f}', style=wind_col)
            wind_speed_cell.append(')')
        if DailyColumn.WIND_DIRECTION not in self._visible_columns:
            wind_speed_cell.append(f' {wind_dir}', style=f'bold {wind_col}')
        wind_speed_cell.justify = 'right'
        gust_cell = Text(f'({wind_gust:.0f})', style=wind_col, justify='right')
        wind_dir_cell = Text(f'{wind_dir}', style=f'bold {wind_col}', justify='right')

        # Sunrise / sunset
        sunrise = self.daily_model.get_sunrise(model_idx)
        if sunrise:
            sunrise_time = sunrise.strftime('%H:%M')
            sunrise_cell = Text(f'{sunrise_time}', style=f' {theme_vars["text-warning"]}', justify='right')
        else:
            sunrise_cell = Text('--:--', justify='right')

        sunset = self.daily_model.get_sunset(model_idx)
        if sunset:
            sunset_time = sunset.strftime('%H:%M')
            sunset_cell = Text(f'{sunset_time}', style=f' {theme_vars["text-error"]}', justify='right')
        else:
            sunset_cell = Text('--:--', justify='right')

        cells_by_column = {
            DailyColumn.DATE: day_cell,
            DailyColumn.CONDITION: condition_cell,
            DailyColumn.TEMPERATURE: min_max_cell,
            DailyColumn.RAIN: (
                rain_prob_cell
                if DailyColumn.PRECIPITATION in self._visible_columns
                else combined_rain_cell
            ),
            DailyColumn.WIND: wind_speed_cell,
            DailyColumn.PRECIPITATION: precip_cell,
            DailyColumn.GUST: gust_cell,
            DailyColumn.WIND_DIRECTION: wind_dir_cell,
            DailyColumn.SUNRISE: sunrise_cell,
            DailyColumn.SUNSET: sunset_cell,
        }
        cells = [cells_by_column[column] for column in self._visible_columns]
        self.add_row(*cells, key=day_name)
