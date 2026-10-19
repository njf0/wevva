"""Pure responsive layout budgeting for the country alerts centre."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AlertsCentrePresentation(StrEnum):
    """Workspace arrangement selected for the available terminal cells."""

    WIDE = 'wide'
    STACKED = 'stacked'
    TABBED = 'tabbed'
    SINGLE = 'single'


@dataclass(frozen=True, slots=True)
class AlertsCentreLayoutBudget:
    """One deterministic alerts-centre arrangement."""

    presentation: AlertsCentrePresentation
    navigation_width: int
    settlement_label_limit: int


def alerts_centre_layout_for(
    width: int,
    height: int,
) -> AlertsCentreLayoutBudget:
    """Allocate useful panes from terminal width and height together.

    ``height`` is the full terminal height. Header and footer consumption is
    intentionally included in these thresholds so callers can pass Resize
    dimensions directly.
    """

    width = max(0, int(width))
    height = max(0, int(height))
    if width >= 124 and height >= 26:
        presentation = AlertsCentrePresentation.WIDE
    elif width >= 92 and height >= 28:
        presentation = AlertsCentrePresentation.STACKED
    elif width >= 80 and height >= 24:
        presentation = AlertsCentrePresentation.TABBED
    else:
        presentation = AlertsCentrePresentation.SINGLE

    if presentation is AlertsCentrePresentation.WIDE:
        navigation_width = min(44, max(34, width // 4))
    elif presentation in {
        AlertsCentrePresentation.STACKED,
        AlertsCentrePresentation.TABBED,
    }:
        navigation_width = min(34, max(28, width // 3))
    else:
        navigation_width = max(0, width)

    settlement_label_limit = (
        2
        if presentation in {
            AlertsCentrePresentation.TABBED,
            AlertsCentrePresentation.SINGLE,
        }
        else 8
    )
    return AlertsCentreLayoutBudget(
        presentation,
        navigation_width,
        settlement_label_limit,
    )


__all__ = [
    'AlertsCentreLayoutBudget',
    'AlertsCentrePresentation',
    'alerts_centre_layout_for',
]
