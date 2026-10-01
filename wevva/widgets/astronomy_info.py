"""Astronomy info table.

Shows sunrise, daylight duration, sunset, moon illumination and phase.
Keeps a compact two-column DataTable.
"""

from __future__ import annotations

import datetime
import math
from typing import Any

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import DataTable
from zoneinfo import ZoneInfo

# Moon phase calculation constants
_LUNATION_DAYS = 29.53058867  # Average lunar month duration
_MOON_EPOCH = datetime.datetime(2000, 1, 6, 18, 14, tzinfo=datetime.timezone.utc)  # Known new moon

# Moon phase names (8 phases)
_MOON_PHASE_NAMES = [
    'New Moon',
    'Waxing Crescent',
    'First Quarter',
    'Waxing Gibbous',
    'Full Moon',
    'Waning Gibbous',
    'Last Quarter',
    'Waning Crescent',
]

# Moon phase emoji (corresponding to names above)
_MOON_PHASE_EMOJI = ['🌚', '🌒', '🌓', '🌔', '🌝', '🌖', '🌗', '🌘']

_ASTRONOMY_ROWS = (
    ('sunrise', 'Rise'),
    ('sunset', 'Set'),
    ('moon_phase', 'Phase'),
    ('daylight', 'Day'),
    ('moon_illum', 'Moon'),
)


class AstronomyInfo(DataTable):
    """Two-column astronomy details for the forecast location."""

    # Reactive properties (set by parent ContextBar)
    forecast_metadata: reactive[Any | None] = reactive(None)
    daily_model: reactive[Any | None] = reactive(None)

    DEFAULT_CSS = """
    AstronomyInfo {
        height: auto;
        # width: auto;
        margin-right: 2;
        border: round $primary;
        border-title-color: $primary;
        border-title-align: left;
    }
    """

    def __init__(
        self,
        *,
        id: str = 'astronomy-info',
        classes: str = 'weather-widget',
    ):
        """Initialize the astronomy info table.

        Parameters
        ----------
        id : str
            Unique identifier for the widget (default: 'astronomy-info').
        classes : str
            CSS classes for styling (default: 'weather-widget').

        """
        super().__init__(show_header=False, cursor_type='none', id=id, classes=classes)
        self.border_title = 'Sun & Moon'
        self._visible_rows = tuple(key for key, _label in _ASTRONOMY_ROWS)
        self._build_rows()

    def _build_rows(self) -> None:
        """Build the complete astronomy fields selected by the context layout."""

        self.clear(columns=True)
        self.add_column('Field', key='field', width=5)
        self.add_column('Value', key='value', width=19)
        for key, label in _ASTRONOMY_ROWS:
            if key in self._visible_rows:
                self.add_row(
                    Text(label, style='dim'),
                    Text('', style='bold'),
                    key=key,
                )

    def set_row_count(self, row_count: int) -> None:
        """Show the requested number of fields in priority order."""

        rows = tuple(
            key for key, _label in _ASTRONOMY_ROWS[: max(1, min(5, row_count))]
        )
        if rows == self._visible_rows:
            return
        self._visible_rows = rows
        self._build_rows()
        if self.is_mounted and self._can_update():
            self._update_display()

    def set_compact(self, compact: bool) -> None:
        """Retain the legacy compact/full control for standalone callers."""

        self.set_row_count(3 if compact else 5)

    def on_mount(self) -> None:
        """Trigger initial display after mounting."""
        if self._can_update():
            self._update_display()

    def watch_forecast_metadata(self, metadata: Any | None) -> None:
        """React to forecast metadata changes."""
        if self.is_mounted and self._can_update():
            self._update_display()

    def watch_daily_model(self, model: Any | None) -> None:
        """React to daily model changes."""
        if self.is_mounted and self._can_update():
            self._update_display()

    def refresh_display(self) -> None:
        """Public method to force a display refresh (called by timer for time updates)."""
        if self.is_mounted and self._can_update():
            self._update_display()

    def _can_update(self) -> bool:
        """Check if widget has all required data to update."""
        return self.forecast_metadata is not None and self.daily_model is not None

    def _update_display(self) -> None:
        """Populate astronomy rows using forecast metadata and daily model."""
        theme_vars = self.app.theme_variables
        tzinfo = self._get_timezone()

        # Get sun times and format with deltas
        sunrise_dt = self._ensure_timezone(self.daily_model.get_sunrise(0), tzinfo)
        sunset_dt = self._ensure_timezone(self.daily_model.get_sunset(0), tzinfo)
        now = datetime.datetime.now(tzinfo)

        values = {
            'sunrise': self._format_sun_time(
                sunrise_dt,
                now,
                theme_vars.get('text-warning'),
            ),
            'daylight': self._format_daylight(),
            'sunset': self._format_sun_time(
                sunset_dt,
                now,
                theme_vars.get('text-error'),
            ),
        }

        # Moon calculations
        moon_illum = self._calculate_moon_illumination()
        moon_phase = self._format_moon_phase(theme_vars)

        values['moon_illum'] = Text(moon_illum, style='bold dim')
        values['moon_phase'] = moon_phase
        for key, value in values.items():
            if key in self._visible_rows:
                self.update_cell(key, 'value', value, update_width=True)
        self.refresh()

    # Helper methods --------------------------------------------------
    def _get_timezone(self) -> datetime.tzinfo:
        """Get timezone from metadata or fall back to local timezone."""
        tz_name = self.forecast_metadata.timezone if self.forecast_metadata else None
        if tz_name:
            return ZoneInfo(tz_name)
        return datetime.datetime.now().astimezone().tzinfo

    def _ensure_timezone(self, dt: datetime.datetime, tzinfo: datetime.tzinfo) -> datetime.datetime:
        """Ensure datetime has timezone info."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=tzinfo)
        return dt

    def _format_time_delta(self, target: datetime.datetime, now: datetime.datetime) -> str:
        """Format time delta as human-readable string like '(in 2h 15m)' or '(30m ago)'."""
        seconds = int((target - now).total_seconds())

        if seconds == 0:
            return '(now)'

        is_future = seconds > 0
        seconds = abs(seconds)
        hours, rem = divmod(seconds, 3600)
        minutes = rem // 60

        time_part = f'{hours}h ' if hours > 0 else ''
        time_part += f'{minutes}m'

        return f'(in {time_part})' if is_future else f'({time_part} ago)'

    def _format_sun_time(self, dt: datetime.datetime, now: datetime.datetime, colour: str) -> Text:
        """Format sunrise/sunset time with relative delta."""
        time_str = dt.strftime('%H:%M')
        delta_str = self._format_time_delta(dt, now)
        return Text.from_markup(f'[bold {colour}]{time_str}[/] [{colour}]{delta_str}[/]')

    def _format_daylight(self) -> Text:
        """Format daylight duration as hours and minutes."""
        ddur = self.daily_model.get_daylight_duration(0) or 0

        if not ddur:
            return Text.from_markup(f'[bold {self.app.theme_variables.get("text-accent")}]N/A[/]')

        hours = int(ddur // 3600)
        minutes = int((ddur % 3600) // 60)
        daylight_text = f'{hours}h {minutes}m'

        return Text.from_markup(f'[bold {self.app.theme_variables.get("text-accent")}]{daylight_text}[/]')

    def _calculate_moon_illumination(self) -> str:
        """Calculate current moon illumination percentage."""
        phase = self._get_moon_phase_value()
        illum = 0.5 * (1 - math.cos(2 * math.pi * phase)) * 100
        return f'{illum:.0f}%'

    def _get_moon_phase_value(self) -> float:
        """Calculate moon phase as a value between 0 and 1."""
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        diff = now_utc - _MOON_EPOCH
        days = diff.total_seconds() / 86400.0
        lunations = days / _LUNATION_DAYS
        return lunations % 1.0

    def _format_moon_phase(self, theme_vars: dict[str, str]) -> Text:
        """Format moon phase name with optional emoji."""
        phase = self._get_moon_phase_value()
        index = int((phase * 8) + 0.5) % 8

        name = _MOON_PHASE_NAMES[index]
        colour = theme_vars.get('text-warning')

        if self.app.emoji_enabled:
            emoji = _MOON_PHASE_EMOJI[index]
            return Text.from_markup(f'{emoji} [italic {colour}]{name}[/]')
        else:
            return Text.from_markup(f'[italic {colour}]{name}[/]')
