"""Hourly forecast widget.

Shows the next 24 hours in a compact table and sends
an `HourHighlighted` message when you move across columns.
"""

from __future__ import annotations

import datetime
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.widgets import DataTable, Tab, Tabs

from wevva.conditions import get_condition
from wevva.constants import HOURS_WINDOW, MAX_TAB_DAYS
from wevva.messages import DaySelected, HourHighlighted, WeatherUpdated
from wevva.utils import (
    create_rain_blocks,
    create_temp_blocks,
    rain_colour,
    temp_colour,
    wind_colour,
)


class HourlyForecast(Container):
    """Owns the next-24-hours table and column highlight behavior."""

    DEFAULT_CSS = """
    HourlyForecast {
        layout: vertical;
        height: auto;
        width: 98;
        border: round $primary;
        border-title-color: $primary;
        border-title-align: center;
        align-horizontal: center;
        hatch: right $background-lighten-1;
    }

    #next-24-hours-datatable {
        width: 98;
    }



    """

    # Reactive state
    hourly_model: reactive[Any | None] = reactive(None)
    daily_model: reactive[Any | None] = reactive(None)

    def compose(self) -> ComposeResult:  # type: ignore[override]
        # Compose once: create Tabs and DataTable widgets
        yield Tabs(id='hourly-tabs')
        table = DataTable(
            show_header=False,
            cursor_type='column',
            cell_padding=0,
            id='next-24-hours-datatable',
        )
        yield table
        # Internal state for tab/column mapping
        self._active_tab_id = None
        self._tab_date_map = {}
        self._col_keys = []
        self._col_indices = []

    # Properties for widget access (posting pattern)
    @property
    def tabs(self) -> Tabs:
        return self.query_one(Tabs)

    @property
    def table(self) -> DataTable:
        return self.query_one(DataTable)

    def on_mount(self) -> None:
        """Trigger initial display after mounting."""
        # Set container border title so the widget's outer box shows the label
        self.border_title = 'Hourly Forecast'

        # If models were set before mounting, trigger watchers now
        if self.hourly_model is not None:
            # Re-trigger the watcher now that we're mounted
            self.watch_hourly_model(self.hourly_model)

    # Reactive watchers
    def watch_hourly_model(self, hourly_model: Any | None) -> None:
        """Update tabs and table when hourly model changes."""
        if hourly_model is None or not self.is_mounted:
            return
        times = hourly_model.forecast_timeseries
        if not times:
            self.table.clear(columns=True)
            return

        # Extract distinct dates (up to MAX_TAB_DAYS)
        dates = self._extract_dates(times)

        # Reconcile tabs to match dates
        self._reconcile_tabs(dates)

        # Ensure we have a valid active tab
        desired_ids = [f'day-{d.isoformat()}' for d in dates]
        self._ensure_valid_active_tab(desired_ids)

        # Rebuild table for active date
        if self._active_tab_id and self._active_tab_id in self._tab_date_map:
            self._update_for_date(self._tab_date_map[self._active_tab_id])

    def _extract_dates(self, times: list[dict]) -> list[datetime.date]:
        """Extract up to MAX_TAB_DAYS distinct dates from timeseries."""
        dates = []
        for entry in times:
            d = entry['time'].date()
            if d not in dates and len(dates) < MAX_TAB_DAYS:
                dates.append(d)
        return dates

    def _reconcile_tabs(self, dates: list[datetime.date]) -> None:
        """Add/remove/update tabs to match desired dates."""
        desired_ids = [f'day-{d.isoformat()}' for d in dates]
        id_to_tab = {tab.id: tab for tab in self.tabs.query(Tab)}

        # Remove obsolete tabs
        for tab_id in list(id_to_tab.keys()):
            if tab_id not in desired_ids:
                self.tabs.remove_tab(tab_id)
                id_to_tab.pop(tab_id, None)

        # Add missing tabs and update labels on existing ones
        self._tab_date_map = {}
        for d in dates:
            tab_id = f'day-{d.isoformat()}'
            label = self._build_tab_label_for_date(d)
            tab = id_to_tab.get(tab_id)
            if tab is None:
                tab = Tab(label=label, id=tab_id)
                self.tabs.add_tab(tab)
            else:
                tab.label = label
            self._tab_date_map[tab_id] = d

    def _ensure_valid_active_tab(self, desired_ids: list[str]) -> None:
        """Ensure active tab is valid; pick first available if not."""
        id_to_tab = {tab.id: tab for tab in self.tabs.query(Tab)}

        # Check if current active tab still exists
        if self._active_tab_id not in id_to_tab:
            self._active_tab_id = next((tid for tid in desired_ids if tid in id_to_tab), None)

        # Final validation and activation
        if not self._active_tab_id or self._active_tab_id not in self._tab_date_map:
            self._active_tab_id = next((tid for tid in desired_ids if tid in id_to_tab), None)

        if self._active_tab_id:
            self.tabs.active = self._active_tab_id

    def _build_tab_label_for_date(self, d: datetime.date) -> Text:
        """Build a tab label for a given date (updates min/max colors)."""
        first_date = self.hourly_model.forecast_timeseries[0]['time'].date()
        if d == first_date:
            horizon = min(HOURS_WINDOW, len(self.hourly_model.forecast_timeseries))
            temps = [self.hourly_model.get_temperature(i) for i in range(horizon)]
            temps = [t for t in temps if t is not None]

            temp_unit = getattr(self.app, 'temperature_unit', 'celsius')
            tmin = min(temps)
            tmax = max(temps)
            cmin = temp_colour(tmin, hex=True, unit=temp_unit)
            cmax = temp_colour(tmax, hex=True, unit=temp_unit)
            return Text.from_markup(f'Next 24 Hours [bold {cmin}]{int(tmin)}°[/]-[bold {cmax}]{int(tmax)}°[/]')

        date_str = d.strftime('%A')
        daily_ts = self.daily_model.forecast_timeseries
        row_index = next((i for i, day in enumerate(daily_ts) if day.get('time') == d), None)
        if row_index is not None:
            temp_unit = getattr(self.app, 'temperature_unit', 'celsius')
            tmin = self.daily_model.get_temperature_min(row_index)
            tmax = self.daily_model.get_temperature_max(row_index)
            cmin = temp_colour(tmin, hex=True, unit=temp_unit)
            cmax = temp_colour(tmax, hex=True, unit=temp_unit)
            return Text.from_markup(f"""{date_str} [bold {cmin}]{int(tmin)}°[/]-[bold {cmax}]{int(tmax)}°[/]""")

    def _update_for_date(self, date: Any) -> None:
        """Update columns and rows for the given date."""
        hourly_model = self.hourly_model
        tbl = self.table
        tbl.clear(columns=True)
        self._col_keys = []
        self._col_indices = []

        # Determine indices for the selected date
        day_indices_abs = self._get_day_indices(date)

        # Add columns and track keys/indices
        self._setup_columns(day_indices_abs)

        # Precompute all row data
        temps = [hourly_model.get_temperature(i) for i in self._col_indices]
        rains = [hourly_model.get_precipitation_probability(i) for i in self._col_indices]
        winds = [hourly_model.get_wind_speed(i) for i in self._col_indices]

        # Create empty rows
        row_keys = [
            'emoji',
            'temp_blocks',
            'temp_values',
            'rain_blocks',
            'rain_values',
            'wind_blocks',
            'wind_values',
            'footer',
        ]
        for rk in row_keys:
            tbl.add_row(*['' for _ in self._col_keys], key=rk)

        # Populate rows
        self._update_emoji_row()
        self._update_temp_rows(temps)
        self._update_rain_rows(rains)
        self._update_wind_rows(winds)
        self._update_footer_row()

        tbl.refresh()

    def _setup_columns(self, day_indices_abs: list[int]) -> None:
        """Add columns for the selected day's hours."""
        for abs_idx in day_indices_abs:
            entry = self.hourly_model.forecast_timeseries[abs_idx]
            col_key = f'h{abs_idx:02}'
            self._col_keys.append(col_key)
            self._col_indices.append(abs_idx)
            self.table.add_column(
                Text(text=entry['time'].strftime('%H'), style='bold', justify='center'),
                key=col_key,
                width=4,
            )

    def _update_emoji_row(self) -> None:
        """Update condition emoji/abbreviation row."""
        show_emoji = self.app.emoji_enabled
        theme_vars = self.app.theme_variables

        for i, abs_idx in enumerate(self._col_indices):
            col_key = self._col_keys[i]
            point = self.hourly_model.get_point(abs_idx)
            code = point.get('weather_code') if point else None
            cond = get_condition(code) if code is not None else None

            # Choose emoji based on is_day flag for clear/night handling
            if show_emoji and cond:
                is_day = point.get('is_day') if point is not None else None
                cell = cond.night_emoji if is_day == 0 else cond.day_emoji
            else:
                cell = cond.abbr if cond else ''

            style = f'bold {theme_vars.get(cond.color_var)}' if (cond and cond.color_var) else 'bold'
            self.table.update_cell('emoji', col_key, Text(cell, style=style, justify='center'))

    def _update_temp_rows(self, temps: list[float]) -> None:
        """Update temperature blocks and values rows."""
        tblocks = create_temp_blocks(temps, width=4)
        tunit = self.hourly_model.forecast_units.get('temperature_2m', '°C')
        temp_unit = getattr(self.app, 'temperature_unit', 'celsius')

        for i, t in enumerate(temps):
            col_key = self._col_keys[i]
            colour = temp_colour(t, hex=True, unit=temp_unit)
            self.table.update_cell(
                'temp_blocks',
                col_key,
                Text(tblocks[i], style=f'bold {colour}', justify='center'),
            )
            self.table.update_cell(
                'temp_values',
                col_key,
                Text(f'{t:.0f}{tunit[0]}', style=f'bold {colour}', justify='center'),
            )

    def _update_rain_rows(self, rains: list[float]) -> None:
        """Update precipitation blocks and values rows."""
        theme_vars = self.app.theme_variables
        rblocks = create_rain_blocks(rains, width=4)
        runit = self.hourly_model.forecast_units.get('precipitation_probability', '%')
        rain_max = theme_vars['primary']

        for i, r in enumerate(rains):
            col_key = self._col_keys[i]
            colour = rain_colour(r, hex=True, min_colour=theme_vars['foreground'], max_colour=rain_max)
            self.table.update_cell(
                'rain_blocks',
                col_key,
                Text(rblocks[i], style=f'bold {colour}', justify='center'),
            )
            self.table.update_cell(
                'rain_values',
                col_key,
                Text(f'{r:.0f}{runit}', style=f'bold {colour}', justify='center'),
            )

    def _update_wind_rows(self, winds: list[float]) -> None:
        """Update wind blocks and values rows."""
        theme_vars = self.app.theme_variables
        wblocks = create_temp_blocks(winds, width=4)
        wunit = self.hourly_model.forecast_units.get('wind_speed_10m', 'mph')
        wind_max = theme_vars['accent']

        for i, wv in enumerate(winds):
            col_key = self._col_keys[i]
            colour = wind_colour(wv, hex=True, min_colour=theme_vars['foreground'], max_colour=wind_max)
            self.table.update_cell(
                'wind_blocks',
                col_key,
                Text(wblocks[i], style=f'bold {colour}', justify='center'),
            )
            wdir = self.hourly_model.get_wind_direction(self._col_indices[i])
            suffix = wdir[-1] if isinstance(wdir, str) and wdir else ''
            disp = f'{wv:.0f}{suffix}' if suffix else f'{wv:.0f}{wunit}'
            self.table.update_cell(
                'wind_values',
                col_key,
                Text(disp, style=f'bold {colour}', justify='center'),
            )

    def _update_footer_row(self) -> None:
        """Update footer row with hour labels."""
        for i, abs_idx in enumerate(self._col_indices):
            col_key = self._col_keys[i]
            hour_time = self.hourly_model.get_point(abs_idx).get('time')
            hour_label = hour_time.strftime('%H') if hour_time else ''
            self.table.update_cell('footer', col_key, Text(hour_label, style='bold', justify='center'))

    # Event handlers ------------------------------------------------------
    def on_data_table_column_highlighted(self, event: DataTable.ColumnHighlighted) -> None:  # type: ignore[override]
        """Send `HourHighlighted` mapped to absolute index for the selected date."""
        if not self._col_indices:
            return
        rel_index = event.cursor_column
        if 0 <= rel_index < len(self._col_indices):
            abs_index = self._col_indices[rel_index]
            self.post_message(HourHighlighted(abs_index))

    # Messages ------------------------------------------------------------
    async def on_weather_updated(self, event: WeatherUpdated) -> None:  # type: ignore[override]
        """Rebuild the table when fresh hourly data arrives."""
        # Set reactive properties - this triggers watch_hourly_model
        self.daily_model = event.daily
        self.hourly_model = event.hourly

    def on_day_selected(self, event: DaySelected) -> None:
        """Switch to the corresponding day tab when a daily row is selected."""
        if not self.daily_model or not self.is_mounted:
            return

        # The event.index is the display row (0 = first visible row = tomorrow)
        # Convert to model index (daily table skips today at index 0)
        model_idx = event.index + 1

        # Get the date from the daily model
        if model_idx < len(self.daily_model.forecast_timeseries):
            day = self.daily_model.forecast_timeseries[model_idx]
            selected_date = day['time']

            # Ensure it's a date object (should already be from the model)
            if isinstance(selected_date, datetime.datetime):
                selected_date = selected_date.date()

            # Find and activate the corresponding tab
            tab_id = f'day-{selected_date.isoformat()}'
            if tab_id in self._tab_date_map and self.tabs.active != tab_id:
                self.tabs.active = tab_id

    # Tabs events --------------------------------------------------------
    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:  # type: ignore[override]
        """Switch the table to the selected day's subset when a tab is activated."""
        tab_id = event.tab.id
        self._active_tab_id = tab_id
        date = self._tab_date_map.get(tab_id)
        if date:
            self._update_for_date(date)

    # Helpers ------------------------------------------------------------
    def _get_day_indices(self, date: datetime.date) -> list[int]:
        """Return absolute indices for the selected date (capped by HOURS_WINDOW)."""
        ts = self.hourly_model.forecast_timeseries
        first_date = ts[0]['time'].date()
        if date == first_date:
            return list(range(0, min(HOURS_WINDOW, len(ts))))
        return [i for i, e in enumerate(ts) if e['time'].date() == date][:HOURS_WINDOW]
