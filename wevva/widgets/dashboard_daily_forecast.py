"""Borderless standard daily forecast for the Dashboard rail."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.events import Resize

from wevva.layout import DailyColumn
from wevva.messages import WeatherUpdated
from wevva.widgets.daily_summary import DailySummaryTable


_DASHBOARD_COLUMNS = (
    DailyColumn.DATE,
    DailyColumn.CONDITION,
    DailyColumn.TEMPERATURE,
    DailyColumn.RAIN,
    DailyColumn.WIND,
)


class DashboardDailyForecast(Container):
    """Standard combined daily cells fitted to the Dashboard rail."""

    DEFAULT_CSS = """
    DashboardDailyForecast {
        width: 100%;
        height: 3;
        border: none;
        background: $background;
        overflow: hidden hidden;
    }

    DashboardDailyForecast DailySummaryTable {
        width: 100%;
        height: 100%;
        scrollbar-size-horizontal: 0;
        scrollbar-size-vertical: 1;
        background: $background;
    }

    DashboardDailyForecast DailySummaryTable > .datatable--even-row {
        background: $background-lighten-1;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._row_count = 3
        self._layout_pending = False

    def compose(self) -> ComposeResult:
        table = DailySummaryTable(
            id='dashboard-daily-table',
            show_compact_precipitation=False,
            show_compact_gust=False,
            align_wind_direction=True,
            fit_columns_to_content=True,
        )
        # The application's generic DataTable rule uses auto width. Fit these
        # columns to the rail viewport, not to a previously empty table.
        table.styles.width = '100%'
        table.styles.min_width = 0
        yield table

    @property
    def table(self) -> DailySummaryTable:
        return self.query_one('#dashboard-daily-table', DailySummaryTable)

    def on_mount(self) -> None:
        self._schedule_layout()

    def on_resize(self, event: Resize) -> None:
        event.stop()
        self._schedule_layout()

    def set_row_count(self, row_count: int) -> None:
        """Set the number of standard future-day rows retained here."""

        row_count = max(0, int(row_count))
        self.styles.height = row_count
        self.display = row_count > 0
        if row_count != self._row_count:
            self._row_count = row_count
            self._schedule_layout()

    def update_forecast(self, event: WeatherUpdated) -> None:
        """Render future days from the shared daily model."""

        self.table.daily_model = event.daily

    def _schedule_layout(self) -> None:
        """Coalesce parent-budget and child-resize layout requests."""

        if not self.is_mounted or self._layout_pending:
            return
        self._layout_pending = True
        self.call_after_refresh(self._apply_layout)

    def _apply_layout(self) -> None:
        self._layout_pending = False
        if not self.is_mounted:
            return
        self.table.set_layout(
            _DASHBOARD_COLUMNS,
            self._row_count,
            force=True,
        )


__all__ = ['DashboardDailyForecast']
