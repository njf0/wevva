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
_MINIMUM_WIDTHS = (3, 3, 7, 7, 9)
_PREFERRED_WIDTHS = (6, 4, 9, 11, 14)


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
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._row_count = 3

    def compose(self) -> ComposeResult:
        yield DailySummaryTable(id='dashboard-daily-table')

    @property
    def table(self) -> DailySummaryTable:
        return self.query_one('#dashboard-daily-table', DailySummaryTable)

    def on_mount(self) -> None:
        self._apply_layout()

    def on_resize(self, event: Resize) -> None:
        event.stop()
        self._apply_layout()

    def set_row_count(self, row_count: int) -> None:
        """Set the number of standard future-day rows retained here."""

        row_count = max(0, int(row_count))
        self.styles.height = row_count
        self.display = row_count > 0
        if row_count != self._row_count:
            self._row_count = row_count
            self._apply_layout()

    def update_forecast(self, event: WeatherUpdated) -> None:
        """Render future days from the shared daily model."""

        self.table.daily_model = event.daily

    def _apply_layout(self) -> None:
        if not self.is_mounted:
            return
        available = max(1, self.content_size.width - 1)
        self.table.set_layout(
            _DASHBOARD_COLUMNS,
            self._row_count,
            column_widths=_fitted_widths(available),
        )


def _fitted_widths(available: int) -> tuple[int, ...]:
    """Fit standard field groups without introducing horizontal scrolling."""

    widths = list(_MINIMUM_WIDTHS)
    remaining = max(0, available - sum(widths))
    for index in (4, 3, 2, 0, 1):
        addition = min(remaining, _PREFERRED_WIDTHS[index] - widths[index])
        widths[index] += addition
        remaining -= addition
        if remaining == 0:
            break
    return tuple(widths)


__all__ = ['DashboardDailyForecast']
