"""Fit formatted forecast rows without expanding their content columns."""

from rich.text import Text


def fit_forecast_rows(
    rows: list[tuple[Text, ...]],
    available: int,
    *,
    extra_gap_after: tuple[int, ...] = (),
) -> tuple[int, tuple[int, ...], list[tuple[Text, ...]]]:
    """Prefer native cell padding, retaining separators in a compact table."""
    widths = [max(row[index].cell_len for row in rows) for index in range(len(rows[0]))]
    if sum(widths) + 2 * len(widths) <= available:
        return 1, tuple(widths), rows

    gaps = [1] * (len(widths) - 1) + [0]
    for index in extra_gap_after:
        if sum(widths) + sum(gaps) < available:
            gaps[index] += 1

    # Align the content before adding its separator: Rich's right justification
    # can otherwise consume trailing whitespace on shorter values.
    compact_rows = []
    for row in rows:
        cells = tuple(cell.copy() for cell in row)
        for index, cell in enumerate(cells[:-1]):
            cell.align(cell.justify or 'left', widths[index])
            cell.append(' ' * gaps[index])
            cell.justify = 'left'
        compact_rows.append(cells)
    widths = [width + gap for width, gap in zip(widths, gaps, strict=True)]
    # At exceptionally tight sizes let the last field clip inside the viewport
    # rather than creating an inaccessible horizontal scroll range.
    widths[-1] = max(1, widths[-1] - max(0, sum(widths) - available))
    return 0, tuple(widths), compact_rows
