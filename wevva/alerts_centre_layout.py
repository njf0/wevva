"""Pure responsive layout budgeting for the country alerts centre."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from wevva.layout import HourlyRow


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
    map_workspace_height: int
    place_forecast_height: int
    place_forecast_rows: tuple[HourlyRow, ...]
    settlement_label_limit: int


def alerts_centre_layout_for(
    width: int,
    height: int,
    *,
    place_forecast_state: str = 'idle',
    place_forecast_has_data: bool = False,
    place_forecast_retained_height: int = 0,
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

    # Header, footer, and the stage's one-row vertical padding consume four
    # rows. Tabbed/single presentations use another two for their native tabs;
    # the stacked map owns 55% of the right-hand workspace.
    stage_height = max(0, height - 4)
    if presentation is AlertsCentrePresentation.STACKED:
        map_workspace_height = stage_height * 55 // 100
    elif presentation in {
        AlertsCentrePresentation.TABBED,
        AlertsCentrePresentation.SINGLE,
    }:
        map_workspace_height = max(0, stage_height - 2)
    else:
        map_workspace_height = stage_height

    place_forecast_height, place_forecast_rows = _place_forecast_budget(
        map_workspace_height,
        state=place_forecast_state,
        has_data=place_forecast_has_data,
        retained_height=place_forecast_retained_height,
    )
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
        map_workspace_height,
        place_forecast_height,
        place_forecast_rows,
        settlement_label_limit,
    )


def _place_forecast_budget(
    workspace_height: int,
    *,
    state: str,
    has_data: bool,
    retained_height: int,
) -> tuple[int, tuple[HourlyRow, ...]]:
    """Fit a complete forecast peer within one quarter of the map workspace."""

    maximum_height = max(0, workspace_height) // 4
    if state == 'idle':
        return 0, ()
    if state == 'loading' and retained_height > 0 and maximum_height >= 3:
        return min(max(3, retained_height), maximum_height), ()
    if state != 'ready' or not has_data:
        return (3, ()) if maximum_height >= 3 else (0, ())

    # Two border rows plus temperature and time are the minimum useful strip.
    if maximum_height < 4:
        return 0, ()
    content_rows = min(7, maximum_height - 2)
    admitted = [HourlyRow.TEMPERATURE, HourlyRow.TIME]
    if content_rows >= 3:
        admitted.insert(-1, HourlyRow.RAIN)
    if content_rows >= 4:
        admitted.insert(-1, HourlyRow.WIND)
    if content_rows >= 5:
        admitted.insert(0, HourlyRow.TEMPERATURE_BAR)
    if content_rows >= 6:
        admitted.insert(admitted.index(HourlyRow.RAIN), HourlyRow.RAIN_BAR)
    if content_rows >= 7:
        admitted.insert(admitted.index(HourlyRow.WIND), HourlyRow.WIND_BAR)
    return content_rows + 2, tuple(admitted)


__all__ = [
    'AlertsCentreLayoutBudget',
    'AlertsCentrePresentation',
    'alerts_centre_layout_for',
]
