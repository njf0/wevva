"""Weather summary widget.

Displays a concise summary line for the selected hour
using the latest models and the app's selected location.
"""

from __future__ import annotations

from typing import Any

from rich.markup import escape
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.widgets import Static

from wevva.conditions import get_condition
from wevva.messages import HourHighlighted, WeatherUpdated
from wevva.utils import normalize_emoji


class WeatherSummary(Container):
    """Compact summary composed of separate static parts: place, datetime, condition."""

    # Reactive state
    metadata: reactive[Any | None] = reactive(None)
    hourly: reactive[Any | None] = reactive(None)
    current: reactive[Any | None] = reactive(None)
    selected_index: reactive[int] = reactive(0)

    DEFAULT_CSS = """
    WeatherSummary {
        layout: horizontal;
        height: auto;
        max-width: 100;
        align-horizontal: center;
        align-vertical: middle;
        content-align: center middle;
        border: round $primary;
        border-title-color: $primary;
        border-title-align: center;
        # hatch: right $background-lighten-1;
    }
    # child pieces
    #weather-summary-place {
        width: auto;
    }

    #weather-summary-datetime {
        width: auto;
    }

    #weather-summary-condition {
        width: auto;
    }
    """

    def __init__(self) -> None:
        """Initialize child statics."""
        super().__init__(id='weather-summary')
        self.border_title = 'Weather Summary'

    def compose(self) -> ComposeResult:  # type: ignore[override]
        yield Static('', id='weather-summary-condition')
        yield Static('', id='weather-summary-place')
        yield Static('', id='weather-summary-datetime')

    # Property accessors for child widgets
    @property
    def place(self) -> Static:
        return self.query_one('#weather-summary-place', Static)

    @property
    def datetime(self) -> Static:
        return self.query_one('#weather-summary-datetime', Static)

    @property
    def condition(self) -> Static:
        return self.query_one('#weather-summary-condition', Static)

    def on_mount(self) -> None:
        """Trigger initial display after mounting."""
        if self.hourly is not None:
            self._update_summary()

    # Reactive watchers ---------------------------------------------------
    def watch_hourly(self, model: Any | None) -> None:
        """React to hourly model changes."""
        if model is not None and self.is_mounted:
            self._update_summary()

    def watch_selected_index(self, index: int) -> None:
        """React to selected hour changes."""
        if self.hourly is not None and self.is_mounted:
            self._update_summary()

    # Messages ------------------------------------------------------------
    async def on_weather_updated(self, event: WeatherUpdated) -> None:  # type: ignore[override]
        """Cache models and refresh summary when data arrives."""
        self.metadata = event.metadata
        self.hourly = event.hourly
        self.current = event.current

    async def on_hour_highlighted(self, message: HourHighlighted) -> None:  # type: ignore[override]
        """Update the summary when a different hour is highlighted."""
        self.selected_index = message.index

    # Internals -----------------------------------------------------------
    def _update_summary(self) -> None:
        """Build a summary string and update the widget content."""
        idx = self.selected_index
        theme = self.app.theme_variables

        place = self.app.location.name or 'Selected place'
        # Set tooltip with full location hierarchy
        self.place.tooltip = self._build_location_tooltip()

        date_str, time_str = self._resolve_time(idx)
        emoji, cond_name, cond_color = self._condition_parts(idx, theme)

        # Format: '{condition} in {location} on {date} at {time}'
        self.condition.update(Text.from_markup(f'[bold italic {cond_color}]{cond_name}[/]'))
        self.place.update(Text.from_markup(self._build_place_markup(place)))
        self.datetime.update(f'[dim][i] on [/dim][b]{date_str}[/b] [dim][i]at [/dim][b]{time_str}[/b]')

    def _build_location_tooltip(self) -> str:
        """Build detailed location info for tooltip."""
        loc = self.app.location

        # Build unique admin hierarchy (exclude name from admin parts)
        admin_parts = [p for p in loc.admin.split(';') if p and p != loc.name]
        location_parts = [loc.name, *admin_parts, loc.country]

        return f'[i][b]{", ".join(location_parts)}[/b][/i]'

    def _build_place_markup(self, place: str) -> str:
        """Return plain styled place markup."""
        escaped_place = escape(place)
        return f'[dim][i] in [/dim][b {self.app.theme_variables.get("foreground")}]{escaped_place}[/]'

    def _resolve_time(self, idx: int) -> tuple[str, str]:
        pt = self.hourly.get_point(idx)
        dt = pt.get('time')
        return dt.strftime('%A %d %B %Y'), dt.strftime('%H:%M')

    def _condition_parts(self, idx: int, theme: dict) -> tuple[str, str, str]:
        """Get emoji, name, and color for the weather condition at given hour."""
        emoji = normalize_emoji(self.hourly.get_condition_emoji(idx)) if self.app.emoji_enabled else ''
        cond_name = self.hourly.get_weather_code(idx, return_emoji=False)

        # Get theme color from condition's color_var
        pt = self.hourly.get_point(idx)
        code = pt.get('weather_code')
        condition = get_condition(code)
        cond_color = theme.get(condition.color_var) if (condition and condition.color_var) else theme.get('primary')

        return emoji, cond_name, cond_color
