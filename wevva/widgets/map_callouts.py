"""Pure terminal-cell placement for directional native map callouts."""

from __future__ import annotations

from collections.abc import Collection, Hashable, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar


CalloutKey = TypeVar('CalloutKey', bound=Hashable)
Cell = tuple[int, int]


@dataclass(frozen=True, slots=True)
class DirectionalCalloutCandidate(Generic[CalloutKey]):
    """One ranked callout described without widget or domain state."""

    key: CalloutKey
    anchor: Cell
    width: int
    preferred_avoidance: frozenset[Cell] = frozenset()
    fallback_width: int | None = None


@dataclass(frozen=True, slots=True)
class DirectionalCalloutPolicy:
    """Shared choices which callers must make for a ranked collection."""

    allow_row_shift: bool
    protect_remaining_anchors: bool = True
    retain_higher_priority: bool = True


@dataclass(frozen=True, slots=True)
class DirectionalCalloutPlacement(Generic[CalloutKey]):
    """Collision-free terminal placement and marker direction."""

    column: int
    row: int
    width: int
    marker_on_right: bool
    key: CalloutKey | None = None
    used_fallback: bool = False


def plan_directional_callouts(
    candidates: Sequence[DirectionalCalloutCandidate[CalloutKey]],
    *,
    canvas_width: int,
    canvas_height: int,
    occupied: Collection[Cell] = (),
    policy: DirectionalCalloutPolicy,
) -> tuple[DirectionalCalloutPlacement[CalloutKey], ...]:
    """Place ranked callouts while preferring to preserve later anchors."""

    placed: list[DirectionalCalloutPlacement[CalloutKey]] = []
    used = set(occupied)
    for index, candidate in enumerate(candidates):
        remaining = (
            {item.anchor for item in candidates[index + 1 :]}
            if policy.protect_remaining_anchors
            else set()
        )
        blockers = [used | remaining]
        if policy.retain_higher_priority and remaining:
            blockers.append(used)
        placement = next(
            (
                result
                for blocked in blockers
                if (
                    result := place_directional_callout(
                        anchor=candidate.anchor,
                        label_width=candidate.width,
                        canvas_width=canvas_width,
                        canvas_height=canvas_height,
                        occupied=set(blocked),
                        preferred_avoidance=set(candidate.preferred_avoidance),
                        allow_row_shift=policy.allow_row_shift,
                    )
                )
                is not None
            ),
            None,
        )
        used_fallback = False
        if placement is None and candidate.fallback_width is not None:
            placement = place_directional_callout(
                anchor=candidate.anchor,
                label_width=candidate.fallback_width,
                canvas_width=canvas_width,
                canvas_height=canvas_height,
                occupied=used | remaining,
                allow_row_shift=False,
            )
            used_fallback = placement is not None
        if placement is None:
            continue
        result = DirectionalCalloutPlacement(
            key=candidate.key,
            column=placement.column,
            row=placement.row,
            width=placement.width,
            marker_on_right=placement.marker_on_right,
            used_fallback=used_fallback,
        )
        placed.append(result)
        used.update(_placement_cells(result))
    return tuple(placed)


def place_directional_callout(
    *,
    anchor: Cell,
    label_width: int,
    canvas_width: int,
    canvas_height: int,
    occupied: set[Cell],
    preferred_avoidance: set[Cell] | None = None,
    allow_row_shift: bool,
) -> DirectionalCalloutPlacement[None] | None:
    """Place one callout, with vertical movement explicitly enabled or disabled."""

    if canvas_width < 1 or canvas_height < 1:
        return None
    label_width = max(1, int(label_width))
    if label_width > canvas_width:
        return None
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


def _placement_cells(placement: DirectionalCalloutPlacement[object]) -> set[Cell]:
    return {
        (placement.column + offset, placement.row)
        for offset in range(placement.width)
    }


__all__ = [
    'DirectionalCalloutCandidate',
    'DirectionalCalloutPlacement',
    'DirectionalCalloutPolicy',
    'place_directional_callout',
    'plan_directional_callouts',
]
