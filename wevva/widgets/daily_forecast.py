"""Daily forecast widget.

Shows a daily summary table and emits day selection messages.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.widgets import DataTable

from wevva.messages import DaySelected, WeatherUpdated
from wevva.widgets.daily_summary import DailySummaryTable


class DailyForecast(Container):
    """Daily summary table for the selected location."""

    # Reactive state
    daily_model: reactive[Any | None] = reactive(None)

    DEFAULT_CSS = """
    DailyForecast {
        layout: horizontal;
        height: auto;
        # width: auto;
        align-horizontal: center;
        align-vertical: middle;
        content-align: center middle;
        hatch: right $background-lighten-1;
    }

    #forecast-tabs {
        align-horizontal: center;
        align-vertical: middle;
        height: auto;
        width: auto;
        border: round $primary;
        border-title-color: $primary;
        border-title-align: center;
        # margin-right: 2;
    }

    """

    def compose(self) -> ComposeResult:  # type: ignore[override]
        """Compose the daily summary table."""
        daily_wrap = Container(id="forecast-tabs")
        daily_wrap.border_title = "Daily Forecast"
        with daily_wrap:
            yield DailySummaryTable()

    # Property accessors for child widgets
    @property
    def daily(self) -> DailySummaryTable:
        return self.query_one(DailySummaryTable)

    def on_mount(self) -> None:
        """Trigger initial display after mounting."""
        if self.daily_model is not None:
            self.daily.daily_model = self.daily_model

    # Reactive watchers ---------------------------------------------------
    def watch_daily_model(self, model: Any | None) -> None:
        """React to daily model changes."""
        if model is not None and self.is_mounted:
            self.daily.daily_model = model

    # Events --------------------------------------------------------------
    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:  # type: ignore[override]
        """Emit a DaySelected message for the highlighted daily row index."""
        if event.data_table.id == "min-max-spread-table" and event.data_table.has_focus:
            # Emit a domain message for other components that may care
            self.post_message(DaySelected(event.cursor_row))

    # Messages ------------------------------------------------------------
    async def on_weather_updated(self, event: WeatherUpdated) -> None:  # type: ignore[override]
        """Rebuild table whenever fresh weather arrives."""
        self.daily_model = event.daily
