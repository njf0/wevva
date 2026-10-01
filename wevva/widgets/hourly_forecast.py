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
from textual.events import Resize
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import DataTable, Static, Tab, Tabs

from wevva.conditions import get_condition
from wevva.constants import HOURS_WINDOW, MAX_TAB_DAYS
from wevva.layout import DEFAULT_LAYOUT_METRICS, HourlyRow
from wevva.messages import DaySelected, HourHighlighted, WeatherUpdated
from wevva.utils import (
    create_rain_blocks,
    create_temp_blocks,
    rain_colour,
    temp_colour,
    wind_colour,
)


class HourlyDataTable(DataTable):
    """DataTable which reports horizontal movement to its visual indicator."""

    class HorizontalScrollChanged(Message):
        """Posted whenever the table's horizontal viewport moves."""

    def watch_scroll_x(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_x(old_value, new_value)
        if self.is_mounted:
            self.post_message(self.HorizontalScrollChanged())


class HourlyForecast(Container):
    """Owns the next-24-hours table and column highlight behavior."""

    HOUR_COLUMN_WIDTH = 4

    DEFAULT_CSS = """
    HourlyForecast {
        layout: vertical;
        height: 13;
        width: 100%;
        max-width: 98;
        min-width: 0;
        border: round $primary;
        border-title-color: $primary;
        border-title-align: center;
        align-horizontal: center;
        hatch: right $background-lighten-1;
    }

    #next-24-hours-datatable {
        width: 100%;
        min-width: 0;
        scrollbar-size-horizontal: 0;
        scrollbar-size-vertical: 0;
    }

    #hourly-tabs {
        width: 100%;
        height: 2;
    }

    #hourly-scroll-indicator {
        width: 100%;
        height: 1;
        min-width: 0;
        text-wrap: nowrap;
        text-overflow: clip;
    }

    """

    # Reactive state
    hourly_model: reactive[Any | None] = reactive(None)
    daily_model: reactive[Any | None] = reactive(None)

    _ROW_KEYS = {
        HourlyRow.CONDITION: 'emoji',
        HourlyRow.TEMPERATURE_BAR: 'temp_blocks',
        HourlyRow.TEMPERATURE: 'temp_values',
        HourlyRow.RAIN_BAR: 'rain_blocks',
        HourlyRow.RAIN: 'rain_values',
        HourlyRow.WIND_BAR: 'wind_blocks',
        HourlyRow.WIND: 'wind_values',
        HourlyRow.TIME: 'footer',
    }

    def compose(self) -> ComposeResult:  # type: ignore[override]
        # Compose once: create Tabs and DataTable widgets
        yield Tabs(id='hourly-tabs')
        table = HourlyDataTable(
            show_header=False,
            cursor_type='column',
            cell_padding=0,
            id='next-24-hours-datatable',
        )
        # The application stylesheet deliberately gives general DataTables an
        # auto width.  This table is a viewport, though: it must fill its
        # parent so excess hourly columns overflow *inside* it and can scroll.
        # An inline style keeps that invariant above the application rule.
        table.styles.width = '100%'
        yield table
        yield Static('', id='hourly-scroll-indicator')
        # Internal state for tab/column mapping
        self._active_tab_id = None
        self._rebuilding_tabs = False
        self._tab_date_map = {}
        self._col_keys = []
        self._col_indices = []
        self._column_widths: tuple[int, ...] = ()
        self._visible_rows = tuple(HourlyRow)

    # Properties for widget access (posting pattern)
    @property
    def tabs(self) -> Tabs:
        return self.query_one(Tabs)

    @property
    def table(self) -> HourlyDataTable:
        return self.query_one(HourlyDataTable)

    @property
    def scroll_indicator(self) -> Static:
        return self.query_one('#hourly-scroll-indicator', Static)

    def on_mount(self) -> None:
        """Trigger initial display after mounting."""
        # Set container border title so the widget's outer box shows the label
        self.border_title = 'Hourly Forecast'

        # If models were set before mounting, trigger watchers now
        if self.hourly_model is not None:
            # Re-trigger the watcher now that we're mounted
            self.watch_hourly_model(self.hourly_model)

    def set_layout(self, rows: tuple[HourlyRow, ...]) -> None:
        """Show complete budgeted rows while retaining tabs and columns."""

        rows = tuple(rows)
        changed = rows != self._visible_rows
        self._visible_rows = rows
        height = DEFAULT_LAYOUT_METRICS.hourly_chrome_rows + len(rows)
        self.styles.height = height
        if self.is_mounted:
            self.table.styles.height = len(rows)
        if changed and self.hourly_model is not None and self.is_mounted:
            active_date = self._tab_date_map.get(self._active_tab_id)
            if active_date is None and self.hourly_model.forecast_timeseries:
                active_date = self.hourly_model.forecast_timeseries[0]['time'].date()
            if active_date is not None:
                self._update_for_date(active_date)
        elif self.is_mounted:
            self.call_after_refresh(self._update_scroll_indicator)

    def on_resize(self, event: Resize) -> None:
        """Refit columns to surplus width without changing represented hours."""

        event.stop()
        self.call_after_refresh(self._refit_columns)

    def _refit_columns(self) -> None:
        if not self._col_indices:
            self._update_scroll_indicator()
            return
        desired = self._desired_column_widths(len(self._col_indices))
        if desired != self._column_widths:
            active_date = self._tab_date_map.get(self._active_tab_id)
            if active_date is not None:
                self._update_for_date(active_date)
                return
        self.table.move_cursor(
            column=self.table.cursor_column,
            animate=False,
            scroll=True,
        )
        self._update_scroll_indicator()

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

        self._rebuilding_tabs = True
        try:
            # Reconcile tabs to match dates
            self._reconcile_tabs(dates)

            # Ensure we have a valid active tab
            desired_ids = [f'day-{d.isoformat()}' for d in dates]
            self._ensure_valid_active_tab(desired_ids)

            # Rebuild table for active date
            if self._active_tab_id and self._active_tab_id in self._tab_date_map:
                self._update_for_date(self._tab_date_map[self._active_tab_id])
        finally:
            self._rebuilding_tabs = False

    def _extract_dates(self, times: list[dict]) -> list[datetime.date]:
        """Extract up to MAX_TAB_DAYS distinct dates from timeseries."""
        dates = []
        for entry in times:
            d = entry['time'].date()
            if d not in dates and len(dates) < MAX_TAB_DAYS:
                dates.append(d)
        return dates

    def _reconcile_tabs(self, dates: list[datetime.date]) -> None:
        """Add, remove, and order tabs to match forecast dates."""
        desired_ids = [f'day-{d.isoformat()}' for d in dates]
        id_to_tab = {tab.id: tab for tab in self.tabs.query(Tab)}

        # Remove obsolete tabs
        for tab_id in list(id_to_tab.keys()):
            if tab_id not in desired_ids:
                self.tabs.remove_tab(tab_id)
                id_to_tab.pop(tab_id, None)

        self._tab_date_map = {}
        for index, d in enumerate(dates):
            tab_id = f'day-{d.isoformat()}'
            label = self._build_tab_label_for_date(d)
            tab = id_to_tab.get(tab_id)
            if tab is None:
                next_existing_tab = next(
                    (id_to_tab[existing_id] for existing_id in desired_ids[index + 1 :] if existing_id in id_to_tab),
                    None,
                )
                tab = Tab(label=label, id=tab_id)
                self.tabs.add_tab(tab, before=next_existing_tab)
                id_to_tab[tab_id] = tab
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
        theme_vars = self.app.theme_variables
        first_date = self.hourly_model.forecast_timeseries[0]['time'].date()
        if d == first_date:
            horizon = min(HOURS_WINDOW, len(self.hourly_model.forecast_timeseries))
            temps = [self.hourly_model.get_temperature(i) for i in range(horizon)]
            temps = [t for t in temps if t is not None]

            temp_unit = getattr(self.app, 'temperature_unit', 'celsius')
            tmin = min(temps)
            tmax = max(temps)
            cmin = temp_colour(
                tmin,
                scale='theme_temperature',
                hex=True,
                unit=temp_unit,
                theme_colours=theme_vars,
            )
            cmax = temp_colour(
                tmax,
                scale='theme_temperature',
                hex=True,
                unit=temp_unit,
                theme_colours=theme_vars,
            )
            return Text.from_markup(f'Next 24 Hours [bold {cmin}]{int(tmin)}°[/]-[bold {cmax}]{int(tmax)}°[/]')

        date_str = d.strftime('%A')
        daily_ts = self.daily_model.forecast_timeseries
        row_index = next((i for i, day in enumerate(daily_ts) if day.get('time') == d), None)
        if row_index is not None:
            temp_unit = getattr(self.app, 'temperature_unit', 'celsius')
            tmin = self.daily_model.get_temperature_min(row_index)
            tmax = self.daily_model.get_temperature_max(row_index)
            cmin = temp_colour(
                tmin,
                scale='theme_temperature',
                hex=True,
                unit=temp_unit,
                theme_colours=theme_vars,
            )
            cmax = temp_colour(
                tmax,
                scale='theme_temperature',
                hex=True,
                unit=temp_unit,
                theme_colours=theme_vars,
            )
            return Text.from_markup(f"""{date_str} [bold {cmin}]{int(tmin)}°[/]-[bold {cmax}]{int(tmax)}°[/]""")

    def _update_for_date(self, date: Any) -> None:
        """Update columns and rows for the given date."""
        hourly_model = self.hourly_model
        tbl = self.table
        selected_abs_index = None
        if self._col_indices:
            cursor_column = min(tbl.cursor_column, len(self._col_indices) - 1)
            selected_abs_index = self._col_indices[cursor_column]
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
        row_keys = [self._ROW_KEYS[row] for row in self._visible_rows]
        for rk in row_keys:
            tbl.add_row(*['' for _ in self._col_keys], key=rk)

        # Populate rows
        if HourlyRow.CONDITION in self._visible_rows:
            self._update_emoji_row()
        if {
            HourlyRow.TEMPERATURE_BAR,
            HourlyRow.TEMPERATURE,
        }.intersection(self._visible_rows):
            self._update_temp_rows(temps)
        if {HourlyRow.RAIN_BAR, HourlyRow.RAIN}.intersection(self._visible_rows):
            self._update_rain_rows(rains)
        if {HourlyRow.WIND_BAR, HourlyRow.WIND}.intersection(self._visible_rows):
            self._update_wind_rows(winds)
        if HourlyRow.TIME in self._visible_rows:
            self._update_footer_row()

        if selected_abs_index in self._col_indices:
            tbl.move_cursor(
                column=self._col_indices.index(selected_abs_index),
                animate=False,
                scroll=True,
            )

        tbl.refresh()
        self.call_after_refresh(self._update_scroll_indicator)

    def _setup_columns(self, day_indices_abs: list[int]) -> None:
        """Add columns for the selected day's hours."""
        self._column_widths = self._desired_column_widths(len(day_indices_abs))
        for abs_idx, width in zip(day_indices_abs, self._column_widths, strict=True):
            entry = self.hourly_model.forecast_timeseries[abs_idx]
            col_key = f'h{abs_idx:02}'
            self._col_keys.append(col_key)
            self._col_indices.append(abs_idx)
            self.table.add_column(
                Text(text=entry['time'].strftime('%H'), style='bold', justify='center'),
                key=col_key,
                width=width,
            )

    def _desired_column_widths(self, count: int) -> tuple[int, ...]:
        """Keep each hour at its compact four-cell width."""

        if count <= 0:
            return ()
        return (self.HOUR_COLUMN_WIDTH,) * count

    def _update_scroll_indicator(self) -> None:
        """Render an explicit thumb for the table's real scroll position."""

        if not self.is_mounted:
            return
        width = self.scroll_indicator.size.width
        maximum = int(round(self.table.max_scroll_x))
        if maximum <= 0 or width < 8:
            self.scroll_indicator.update('')
            self.border_subtitle = ''
            return

        track_width = width - 2
        virtual_width = max(1, self.table.virtual_size.width)
        viewport_width = max(1, self.table.container_size.width)
        thumb_width = max(3, round(track_width * viewport_width / virtual_width))
        thumb_width = min(track_width, thumb_width)
        travel = track_width - thumb_width
        position = min(maximum, int(round(self.table.scroll_x)))
        thumb_start = round(travel * position / maximum) if maximum else 0
        thumb_end = thumb_start + thumb_width

        theme = self.app.theme_variables
        primary = theme.get('primary', 'cyan')
        foreground = theme.get('foreground', 'white')
        bar = Text()
        bar.append('◀', style=f'bold {primary}' if position else f'dim {foreground}')
        bar.append('─' * thumb_start, style='dim')
        bar.append('━' * thumb_width, style=f'bold {primary}')
        bar.append('─' * (track_width - thumb_end), style='dim')
        bar.append(
            '▶',
            style=f'bold {primary}' if position < maximum else f'dim {foreground}',
        )
        self.scroll_indicator.update(bar)
        self.scroll_indicator.tooltip = (
            f'Hourly forecast position {position} of {maximum}; use Left/Right to scroll'
        )
        self.border_subtitle = '←/→ scroll'

    def on_hourly_data_table_horizontal_scroll_changed(
        self,
        event: HourlyDataTable.HorizontalScrollChanged,
    ) -> None:
        event.stop()
        self._update_scroll_indicator()

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
        theme_vars = self.app.theme_variables
        tblocks = create_temp_blocks(temps, width=4)
        tunit = self.hourly_model.forecast_units.get('temperature_2m', '°C')
        temp_unit = getattr(self.app, 'temperature_unit', 'celsius')

        for i, t in enumerate(temps):
            col_key = self._col_keys[i]
            colour = temp_colour(
                t,
                scale='theme_temperature',
                hex=True,
                unit=temp_unit,
                theme_colours=theme_vars,
            )
            if HourlyRow.TEMPERATURE_BAR in self._visible_rows:
                self.table.update_cell(
                    'temp_blocks',
                    col_key,
                    Text(tblocks[i], style=f'bold {colour}', justify='center'),
                )
            if HourlyRow.TEMPERATURE in self._visible_rows:
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
        previous_label = None

        for i, r in enumerate(rains):
            col_key = self._col_keys[i]
            colour = rain_colour(r, hex=True, min_colour=theme_vars['foreground'], max_colour=rain_max)
            label = f'{r:.0f}{runit}'
            display_label = '· ·' if label == previous_label and label in {'0%', '100%'} else label
            previous_label = label
            if HourlyRow.RAIN_BAR in self._visible_rows:
                self.table.update_cell(
                    'rain_blocks',
                    col_key,
                    Text(rblocks[i], style=f'bold {colour}', justify='center'),
                )
            if HourlyRow.RAIN in self._visible_rows:
                self.table.update_cell(
                    'rain_values',
                    col_key,
                    Text(display_label, style=f'bold {colour}', justify='center'),
                )

    def _update_wind_rows(self, winds: list[float]) -> None:
        """Update wind blocks and values rows."""
        theme_vars = self.app.theme_variables
        wblocks = create_temp_blocks(winds, width=4)
        wunit = self.hourly_model.forecast_units.get('wind_speed_10m', 'mph')
        wind_max = theme_vars['secondary']

        for i, wv in enumerate(winds):
            col_key = self._col_keys[i]
            colour = wind_colour(wv, hex=True, min_colour=theme_vars['foreground'], max_colour=wind_max)
            if HourlyRow.WIND_BAR in self._visible_rows:
                self.table.update_cell(
                    'wind_blocks',
                    col_key,
                    Text(wblocks[i], style=f'bold {colour}', justify='center'),
                )
            wdir = self.hourly_model.get_wind_direction(self._col_indices[i])
            suffix = wdir[-1] if isinstance(wdir, str) and wdir else ''
            disp = f'{wv:.0f}{suffix}' if suffix else f'{wv:.0f}{wunit}'
            if HourlyRow.WIND in self._visible_rows:
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
        self._active_tab_id = None
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
        if self._rebuilding_tabs:
            return
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
