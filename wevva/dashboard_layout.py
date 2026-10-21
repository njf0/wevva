"""Pure responsive decisions for the unified dashboard."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class DashboardPresentation(StrEnum):
    """Named dashboard size bands used by one stable widget tree."""

    WIDE = 'wide'
    MEDIUM = 'medium'
    COMPACT = 'compact'
    SHORT = 'short'


@dataclass(frozen=True, slots=True)
class DashboardLayoutBudget:
    """Presentation-only dashboard budget for one terminal viewport."""

    presentation: DashboardPresentation
    simultaneous: bool
    stage_padding: tuple[int, int]
    forecast_width: int = 34
    alert_width: int = 30
    gutter: int = 2
    map_height: int | None = None
    daily_rows: int = 3
    current_summary_height: int = 4
    hourly_min_height: int = 8
    show_open_hint: bool = True


_BASELINE_WIDTH = 120
_WORLD_VIEWPORT_ASPECT = 360 / 168


def _wide_dashboard_budget(width: int, height: int) -> DashboardLayoutBudget:
    """Spend large-screen surplus on both rails and an aspect-aware map."""

    surplus = max(0, width - _BASELINE_WIDTH)
    forecast_width = min(54, 34 + surplus // 6)
    alert_width = min(46, 30 + surplus // 8)
    stage_padding = (1, 2)
    gutter = 2
    central_width = max(
        20,
        width
        - stage_padding[1] * 2
        - forecast_width
        - alert_width
        - gutter * 2,
    )
    map_height = None
    if width >= 180 and height >= 40:
        usable_height = max(8, height - 2 - stage_padding[0] * 2)
        map_content_width = max(1, central_width - 2)
        natural_height = math.ceil(
            map_content_width / (2.0 * _WORLD_VIEWPORT_ASPECT)
        ) + 2
        map_height = min(usable_height, max(20, natural_height))
    daily_rows = 6 if height >= 38 else 4 if height >= 34 else 3
    return DashboardLayoutBudget(
        DashboardPresentation.WIDE,
        simultaneous=True,
        stage_padding=stage_padding,
        forecast_width=forecast_width,
        alert_width=alert_width,
        gutter=gutter,
        map_height=map_height,
        daily_rows=daily_rows,
    )


def dashboard_layout_for(
    viewport_width: int,
    viewport_height: int,
) -> DashboardLayoutBudget:
    """Return a deterministic budget without inspecting widgets or data."""

    width = max(1, int(viewport_width))
    height = max(1, int(viewport_height))
    if width >= 120 and height >= 30:
        return _wide_dashboard_budget(width, height)
    if height < 20:
        return DashboardLayoutBudget(
            DashboardPresentation.SHORT,
            simultaneous=False,
            stage_padding=(0, 0),
            daily_rows=1,
            current_summary_height=2,
            hourly_min_height=4,
            show_open_hint=False,
        )
    if width < 100 or height < 24:
        return DashboardLayoutBudget(
            DashboardPresentation.COMPACT,
            simultaneous=False,
            stage_padding=(0, 1),
            daily_rows=2,
            current_summary_height=3,
            hourly_min_height=6,
            show_open_hint=False,
        )
    return DashboardLayoutBudget(
        DashboardPresentation.MEDIUM,
        simultaneous=False,
        stage_padding=(1, 2),
        daily_rows=4 if height >= 30 else 2,
        current_summary_height=3,
        show_open_hint=False,
    )


__all__ = [
    'DashboardLayoutBudget',
    'DashboardPresentation',
    'dashboard_layout_for',
]
