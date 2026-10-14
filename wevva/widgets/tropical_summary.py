"""Compact source-observation summary for the tropical workspace."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from rich.text import Text

from wevva.widgets.tropical_info_table import TropicalInfoTable


class TropicalStormSummary(TropicalInfoTable):
    """Content-driven two-column table for source meteorology."""

    DEFAULT_CSS = """
    TropicalStormSummary {
        width: 100%;
        min-width: 100%;
        max-width: 100%;
        height: auto;
        min-height: 3;
        margin: 0 0 1 0;
        padding: 0;
        border: round $secondary;
        border-title-color: $secondary;
        border-title-align: left;
        overflow-y: hidden;
    }
    """

    def __init__(self, *, id: str = 'tropical-current-summary') -> None:
        super().__init__(field_width=16, id=id)
        self._rows: tuple[tuple[str, Any], ...] = ()
        self._visible_row_count = 0
        self.border_title = 'Summary'

    def update_rows(self, rows: Iterable[tuple[str, Any]]) -> None:
        """Retain all available rows and render the allocated leading subset."""
        self._rows = tuple(rows)
        self._render_rows()

    def set_layout(self, *, row_count: int, height: int) -> None:
        """Show only complete priority-ordered rows within ``height`` cells."""
        row_count = max(0, min(int(row_count), len(self._rows)))
        height = max(0, int(height))
        changed = row_count != self._visible_row_count
        self._visible_row_count = row_count
        self.display = bool(row_count and height)
        self.styles.height = height
        if changed:
            self._render_rows()

    @property
    def available_row_count(self) -> int:
        return len(self._rows)

    @property
    def visible_row_count(self) -> int:
        return self._visible_row_count

    def _render_rows(self) -> None:
        self.clear()
        for label, value in self._rows[: self._visible_row_count]:
            self.add_row(
                Text(label, style='dim', justify='right'),
                value,
                key=label.casefold().replace(' ', '-'),
            )


__all__ = ['TropicalStormSummary']
