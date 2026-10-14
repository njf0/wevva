"""Pure responsive layout budgeting for the tropical-systems workspace."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TropicalTopology(StrEnum):
    """Workspace arrangement selected for the available terminal cells."""

    COMPACT_STACK = 'compact_stack'
    SPLIT = 'split'


@dataclass(frozen=True, slots=True)
class TropicalLayoutMetrics:
    """Explicit terminal, frame, pane, and instrument costs."""

    terminal_chrome_rows: int = 2
    stage_vertical_padding: int = 2
    stage_horizontal_padding: int = 4
    frame_border_rows: int = 2
    frame_border_columns: int = 2
    tab_rows: int = 2
    pane_border_rows: int = 2
    pane_gutter_columns: int = 2
    instrument_gutter_rows: int = 1
    minimum_left_pane_width: int = 48
    minimum_information_width: int = 48
    minimum_summary_rows: int = 3
    enhanced_summary_rows: int = 6
    minimum_information_body_rows: int = 3
    preferred_information_body_rows: int = 8
    minimum_track_height: int = 8
    unavailable_track_height: int = 3
    minimum_centre_weather_rows: int = 3
    enhanced_centre_weather_rows: int = 5


DEFAULT_TROPICAL_LAYOUT_METRICS = TropicalLayoutMetrics()


@dataclass(frozen=True, slots=True)
class TropicalLayoutBudget:
    """One complete, immutable tropical workspace allocation."""

    topology: TropicalTopology
    frame_width: int
    frame_height: int
    workspace_height: int
    left_pane_width: int
    left_pane_height: int
    summary_rows: int
    summary_height: int
    centre_weather_rows: int
    centre_weather_height: int
    track_visible: bool
    track_height: int
    information_tabs_visible: bool
    information_height: int
    information_body_height: int
    source_tabs_visible: bool


def tropical_layout_for(
    width: int,
    height: int,
    *,
    multiple_sources: bool,
    track_available: bool,
    centre_weather_available: bool,
    information_choice_count: int,
    rich_information: bool,
    summary_available_rows: int = 8,
    centre_weather_available_rows: int = 6,
    metrics: TropicalLayoutMetrics = DEFAULT_TROPICAL_LAYOUT_METRICS,
) -> TropicalLayoutBudget:
    """Allocate complete tropical instruments from full terminal dimensions.

    The calculation is presentation-only. Availability inputs describe data
    already held by the screen and never cause provider or weather requests.
    """

    width = max(0, int(width))
    height = max(0, int(height))
    summary_available_rows = max(0, int(summary_available_rows))
    centre_weather_available_rows = max(0, int(centre_weather_available_rows))
    information_choice_count = max(0, int(information_choice_count))

    frame_width = max(0, width - metrics.stage_horizontal_padding)
    frame_height = max(
        0,
        height
        - metrics.terminal_chrome_rows
        - metrics.stage_vertical_padding,
    )
    frame_content_width = max(0, frame_width - metrics.frame_border_columns)
    source_tabs_visible = bool(multiple_sources)
    navigation_rows = metrics.tab_rows * (1 + int(source_tabs_visible))
    workspace_height = max(
        0,
        frame_height - metrics.frame_border_rows - navigation_rows,
    )
    information_tabs_visible = information_choice_count > 1
    information_chrome = metrics.pane_border_rows + (
        metrics.tab_rows if information_tabs_visible else 0
    )
    minimum_information_body_rows = (
        metrics.minimum_information_body_rows
        + (0 if information_tabs_visible else metrics.tab_rows)
    )
    minimum_information_height = min(
        workspace_height,
        information_chrome + minimum_information_body_rows,
    )
    minimum_summary_rows = min(
        metrics.minimum_summary_rows,
        summary_available_rows,
    )
    minimum_table_rows = max(
        minimum_summary_rows,
        min(
            metrics.minimum_centre_weather_rows,
            centre_weather_available_rows,
        )
        if centre_weather_available
        else 0,
    )
    minimum_table_height = (
        minimum_table_rows + metrics.pane_border_rows
        if minimum_table_rows
        else 0
    )
    minimum_track_height = (
        metrics.minimum_track_height
        if track_available
        else metrics.unavailable_track_height
    )
    minimum_lower_height = max(
        minimum_information_height,
        minimum_track_height,
    )
    split_minimum_width = (
        metrics.minimum_left_pane_width
        + metrics.pane_gutter_columns
        + metrics.minimum_information_width
    )
    split_minimum_height = (
        minimum_table_height
        + metrics.instrument_gutter_rows
        + minimum_lower_height
    )
    topology = (
        TropicalTopology.SPLIT
        if frame_content_width >= split_minimum_width
        and workspace_height >= split_minimum_height
        else TropicalTopology.COMPACT_STACK
    )

    if topology is TropicalTopology.SPLIT:
        usable_width = max(
            0,
            frame_content_width - metrics.pane_gutter_columns,
        )
        left_pane_width = usable_width // 2

        desired_summary_rows = min(
            metrics.enhanced_summary_rows,
            summary_available_rows,
        )
        desired_weather_rows = (
            min(
                metrics.enhanced_centre_weather_rows,
                centre_weather_available_rows,
            )
            if centre_weather_available
            else 0
        )
        desired_table_rows = max(
            desired_summary_rows,
            desired_weather_rows,
        )
        maximum_table_height = max(
            minimum_table_height,
            workspace_height
            - metrics.instrument_gutter_rows
            - minimum_lower_height,
        )
        table_rows = min(
            desired_table_rows,
            max(0, maximum_table_height - metrics.pane_border_rows),
        )
        table_height = (
            table_rows + metrics.pane_border_rows
            if table_rows
            else 0
        )
        lower_height = max(
            0,
            workspace_height
            - table_height
            - (metrics.instrument_gutter_rows if table_height else 0),
        )
        summary_rows = min(summary_available_rows, table_rows)
        summary_height = table_height if summary_rows else 0
        centre_weather_rows = (
            min(centre_weather_available_rows, table_rows)
            if centre_weather_available
            else 0
        )
        centre_weather_height = table_height if centre_weather_rows else 0
        track_visible = lower_height >= minimum_track_height
        track_height = lower_height if track_visible else 0
        information_height = lower_height
        left_pane_height = workspace_height
    else:
        left_pane_width = frame_content_width
        reserved_information = minimum_information_height + (
            metrics.instrument_gutter_rows
            if minimum_information_height
            else 0
        )
        summary_capacity = max(
            0,
            workspace_height
            - reserved_information
            - metrics.pane_border_rows,
        )
        summary_rows = min(
            metrics.enhanced_summary_rows,
            summary_available_rows,
            summary_capacity,
        )
        summary_height = (
            summary_rows + metrics.pane_border_rows
            if summary_rows
            else 0
        )
        available_information_height = max(
            0,
            workspace_height
            - summary_height
            - (
                metrics.instrument_gutter_rows
                if summary_height
                else 0
            ),
        )
        if rich_information:
            information_height = available_information_height
        else:
            preferred_information_height = information_chrome + (
                metrics.preferred_information_body_rows
                if information_tabs_visible
                else minimum_information_body_rows
            )
            information_height = min(
                available_information_height,
                preferred_information_height,
            )
        centre_weather_rows = 0
        centre_weather_height = 0
        track_visible = False
        track_height = 0
        left_pane_height = 0

    information_body_height = max(0, information_height - information_chrome)
    return TropicalLayoutBudget(
        topology=topology,
        frame_width=frame_width,
        frame_height=frame_height,
        workspace_height=workspace_height,
        left_pane_width=left_pane_width,
        left_pane_height=left_pane_height,
        summary_rows=summary_rows,
        summary_height=summary_height,
        centre_weather_rows=centre_weather_rows,
        centre_weather_height=centre_weather_height,
        track_visible=track_visible,
        track_height=track_height,
        information_tabs_visible=information_tabs_visible,
        information_height=information_height,
        information_body_height=information_body_height,
        source_tabs_visible=source_tabs_visible,
    )


__all__ = [
    'DEFAULT_TROPICAL_LAYOUT_METRICS',
    'TropicalLayoutBudget',
    'TropicalLayoutMetrics',
    'TropicalTopology',
    'tropical_layout_for',
]
