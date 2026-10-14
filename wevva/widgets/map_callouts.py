"""Small shared placement primitive for directional native map callouts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DirectionalCalloutPlacement:
    """Collision-free terminal placement with its marker on the map anchor."""

    column: int
    row: int
    width: int
    marker_on_right: bool


def place_directional_callout(
    *,
    anchor: tuple[int, int],
    label_width: int,
    canvas_width: int,
    canvas_height: int,
    occupied: set[tuple[int, int]],
    preferred_avoidance: set[tuple[int, int]] | None = None,
    allow_row_shift: bool = True,
) -> DirectionalCalloutPlacement | None:
    """Place a callout, optionally keeping its marker on the anchor row."""

    if canvas_width < 1 or canvas_height < 1:
        return None
    label_width = min(max(1, int(label_width)), canvas_width)
    anchor_column, anchor_row = anchor
    row_offsets = [0]
    if allow_row_shift:
        for distance in range(1, canvas_height):
            row_offsets.extend((-distance, distance))

    avoidance_passes = (
        (preferred_avoidance, set())
        if preferred_avoidance
        else (set(),)
    )
    for avoided in avoidance_passes:
        for row_offset in row_offsets:
            row = anchor_row + row_offset
            if not 0 <= row < canvas_height:
                continue
            for column, marker_on_right in (
                (anchor_column, False),
                (anchor_column - label_width + 1, True),
            ):
                if column < 0 or column + label_width > canvas_width:
                    continue
                cells = {(column + offset, row) for offset in range(label_width)}
                if cells & occupied or cells & avoided:
                    continue
                occupied.update(cells)
                return DirectionalCalloutPlacement(
                    column=column,
                    row=row,
                    width=label_width,
                    marker_on_right=marker_on_right,
                )
    return None


__all__ = ['DirectionalCalloutPlacement', 'place_directional_callout']
