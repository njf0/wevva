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
_DASHBOARD_MINIMUM_WIDTHS = (3, 2, 7, 4, 9)
_DASHBOARD_PREFERRED_WIDTHS = (6, 4, 9, 6, 14)
_COLUMN_COUNT = len(_DASHBOARD_COLUMNS)


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
        yield DailySummaryTable(
            id='dashboard-daily-table',
            show_compact_precipitation=False,
            show_compact_gust=False,
        )

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
        available = max(1, self.content_size.width - 1)
        padding = (
            1
            if available
            >= sum(_DASHBOARD_MINIMUM_WIDTHS) + 2 * _COLUMN_COUNT
            else 0
        )
        self.table.cell_padding = padding
        content_width = max(1, available - 2 * padding * _COLUMN_COUNT)
        columns, widths = _fitted_layout(content_width)
        self.table.set_layout(
            columns,
            self._row_count,
            column_widths=widths,
        )


def _fitted_layout(
    available: int,
) -> tuple[tuple[DailyColumn, ...], tuple[int, ...]]:
    """Fit the dashboard's five useful daily fields without scrolling."""

    return _DASHBOARD_COLUMNS, _fitted_widths(
        available,
        _DASHBOARD_MINIMUM_WIDTHS,
        _DASHBOARD_PREFERRED_WIDTHS,
        (4, 3, 2, 0, 1),
    )


def _fitted_widths(
    available: int,
    minimums: tuple[int, ...],
    preferred: tuple[int, ...],
    priority: tuple[int, ...],
) -> tuple[int, ...]:
    """Fit standard field groups without introducing horizontal scrolling."""

    widths = list(minimums)
    remaining = max(0, available - sum(widths))
    for index in priority:
        addition = min(remaining, preferred[index] - widths[index])
        widths[index] += addition
        remaining -= addition
        if remaining == 0:
            break
    return tuple(widths)


__all__ = ['DashboardDailyForecast']
