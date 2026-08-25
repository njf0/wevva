"""Shared sizing for compact two-column tropical information tables."""

from __future__ import annotations

from textual.events import Resize
from textual.widgets import DataTable


class TropicalInfoTable(DataTable):
    """Two-column table whose value column consumes all remaining width."""

    def __init__(self, *, field_width: int, id: str) -> None:
        super().__init__(show_header=False, cursor_type='none', id=id)
        self._field_width = field_width
        self.add_column('Field', key='field', width=field_width)
        self._value_column_key = self.add_column('Value', key='value', width=1)

    def on_mount(self) -> None:
        self._sync_value_column_width()

    def on_resize(self, event: Resize) -> None:
        del event
        self._sync_value_column_width()

    def _sync_value_column_width(self) -> None:
        content_width = self.content_size.width
        if content_width <= 0:
            return
        padding_width = self.cell_padding * 2
        value_width = max(1, content_width - self._field_width - padding_width * 2)
        column = self.columns[self._value_column_key]
        if column.width == value_width:
            return
        column.width = value_width
        self._require_update_dimensions = True
        self.refresh(layout=True)


__all__ = ['TropicalInfoTable']
