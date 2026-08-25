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
        self.border_title = 'Summary'

    def update_rows(self, rows: Iterable[tuple[str, Any]]) -> None:
        self.clear()
        for label, value in rows:
            self.add_row(
                Text(label, style='dim', justify='right'),
                value,
                key=label.casefold().replace(' ', '-'),
            )


__all__ = ['TropicalStormSummary']
