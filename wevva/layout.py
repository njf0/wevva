"""Pure layout budgeting for the responsive weather screen.

This module deliberately contains no Textual widgets.  It describes which
pieces of weather information fit in an available viewport so that resize
decisions can be tested independently from rendering.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class CurrentDensity(StrEnum):
    """Presentation used by the current-condition instrument row."""

    SMALLEST = "smallest"
    SMALL = "small"
    STANDARD = "standard"


class WarningDensity(StrEnum):
    """Presentation used by the warning region."""

    HIDDEN = "hidden"
    SUMMARY = "summary"
    TABBED = "tabbed"


class ContextPresentation(StrEnum):
    """Placement used by location, astronomy, air-quality, and map context."""

    HIDDEN = "hidden"
    BOTTOM = "bottom"
    SIDECAR = "sidecar"


class HourlyRow(StrEnum):
    """Rows which may appear in the hourly forecast table."""

    CONDITION = "condition"
    TEMPERATURE_BAR = "temperature_bar"
    TEMPERATURE = "temperature"
    RAIN_BAR = "rain_bar"
    RAIN = "rain"
    WIND_BAR = "wind_bar"
    WIND = "wind"
    TIME = "time"


class DailyColumn(StrEnum):
    """Columns which may appear in the daily forecast table."""

    DATE = "date"
    CONDITION = "condition"
    TEMPERATURE = "temperature"
    RAIN = "rain"
    WIND = "wind"
    PRECIPITATION = "precipitation"
    GUST = "gust"
    WIND_DIRECTION = "wind_direction"
    SUNRISE = "sunrise"
    SUNSET = "sunset"


class DetailRow(StrEnum):
    """Rows in the current-weather detail instrument, in priority order."""

    HUMIDITY = "humidity"
    VISIBILITY = "visibility"
    PRESSURE = "pressure"
    UV_INDEX = "uv_index"
    CLOUD_COVER = "cloud_cover"


class AuxiliaryPresentation(StrEnum):
    """How an auxiliary surface should be presented when requested."""

    MODAL = "modal"
    SIDEBAR = "sidebar"


@dataclass(frozen=True)
class LayoutMetrics:
    """Measured row costs and width thresholds for the target layout.

    Row costs include the cells occupied by borders and tabs, rather than
    only the data painted inside them.  The 80x24 supported baseline has 22
    content rows after Textual's one-row header and footer are removed.
    """

    outer_vertical_padding: int = 2
    outer_horizontal_padding: int = 4
    instrument_gutter: int = 1
    summary_card_rows: int = 3
    summary_rows: int = 4  # bordered card plus one separating hatch row
    warning_card_rows: int = 3
    warning_rows: int = 4  # bordered card plus one separating hatch row
    warning_tabbed_card_rows: int = 6
    warning_tabbed_rows: int = 7  # tabbed card plus one separating hatch row

    current_smallest_rows: int = 3
    current_small_rows: int = 5
    current_standard_rows: int = 7
    current_small_min_width: int = 74
    current_standard_min_width: int = 80
    current_full_detail_min_width: int = 102

    hourly_chrome_rows: int = 5  # border, two-row tabs, and scrollbar
    daily_chrome_rows: int = 2  # top and bottom border cells
    context_card_chrome_rows: int = 2
    context_card_count: int = 3
    context_sidecar_card_count: int = 2
    context_card_gutter_rows: int = 1
    context_min_detail_rows: int = 2
    context_max_detail_rows: int = 5
    # At the supported 80-column terminal width, outer panel padding leaves a
    # 76-cell context frame: two 37-cell columns separated by a two-cell gutter.
    context_min_width: int = 80
    context_sidecar_gutter_rows: int = 1
    context_sidecar_min_viewport_height: int = 31
    context_sidecar_min_map_rows: int = 14
    context_sidecar_max_map_rows: int = 27
    context_sidecar_place_labels: int = 4

    precipitation_column_width: int = 61
    gust_column_width: int = 66
    sunrise_column_width: int = 73
    sunset_column_width: int = 80
    daily_wide_min_width: int = 102

    sidebar_width: int = 42
    minimum_central_width: int = 102


DEFAULT_LAYOUT_METRICS = LayoutMetrics()

_HOURLY_DISPLAY_ORDER = (
    HourlyRow.CONDITION,
    HourlyRow.TEMPERATURE_BAR,
    HourlyRow.TEMPERATURE,
    HourlyRow.RAIN_BAR,
    HourlyRow.RAIN,
    HourlyRow.WIND_BAR,
    HourlyRow.WIND,
    HourlyRow.TIME,
)
_REQUIRED_HOURLY_ROWS = {
    HourlyRow.CONDITION,
    HourlyRow.TEMPERATURE,
    HourlyRow.TIME,
}
_DETAIL_ROW_ORDER = tuple(DetailRow)
_ESSENTIAL_DAILY_COLUMNS = (
    DailyColumn.DATE,
    DailyColumn.CONDITION,
    DailyColumn.TEMPERATURE,
    DailyColumn.RAIN,
    DailyColumn.WIND,
)
_DAILY_DISPLAY_ORDER = (
    DailyColumn.DATE,
    DailyColumn.CONDITION,
    DailyColumn.TEMPERATURE,
    DailyColumn.RAIN,
    DailyColumn.PRECIPITATION,
    DailyColumn.WIND,
    DailyColumn.GUST,
    DailyColumn.WIND_DIRECTION,
    DailyColumn.SUNRISE,
    DailyColumn.SUNSET,
)
_WIDE_DAILY_COLUMNS = (
    DailyColumn.DATE,
    DailyColumn.CONDITION,
    DailyColumn.TEMPERATURE,
    DailyColumn.RAIN,
    DailyColumn.PRECIPITATION,
    DailyColumn.WIND,
    DailyColumn.WIND_DIRECTION,
    DailyColumn.SUNRISE,
    DailyColumn.SUNSET,
)


def daily_column_widths(columns: tuple[DailyColumn, ...]) -> tuple[int, ...]:
    """Return compact widths for a complete set of daily fields.

    Rain and wind retain enough room for their combined compact forms. Once
    precipitation amount or gusts receive dedicated columns, the originating
    value column gives that space back.
    """

    visible = set(columns)
    if (
        DailyColumn.WIND_DIRECTION in visible
        and DailyColumn.GUST not in visible
    ):
        wide_widths = {
            DailyColumn.DATE: 13,
            DailyColumn.CONDITION: 31,
            DailyColumn.TEMPERATURE: 8,
            DailyColumn.RAIN: 5,
            DailyColumn.PRECIPITATION: 7,
            DailyColumn.WIND: 13,
            DailyColumn.WIND_DIRECTION: 5,
            DailyColumn.SUNRISE: 7,
            DailyColumn.SUNSET: 7,
        }
        return tuple(wide_widths[column] for column in columns)

    widths = {
        DailyColumn.DATE: 8,
        DailyColumn.CONDITION: 4,
        DailyColumn.TEMPERATURE: 10,
        DailyColumn.RAIN: 6 if DailyColumn.PRECIPITATION in visible else 15,
        DailyColumn.WIND: 15 if DailyColumn.GUST in visible else 18,
        DailyColumn.PRECIPITATION: 9,
        DailyColumn.GUST: 8,
        DailyColumn.WIND_DIRECTION: 5,
        DailyColumn.SUNRISE: 7,
        DailyColumn.SUNSET: 7,
    }
    return tuple(widths[column] for column in columns)


def daily_table_width(columns: tuple[DailyColumn, ...]) -> int:
    """Return the content width occupied by the selected daily columns."""

    return sum(daily_column_widths(columns))


@dataclass(frozen=True)
class WeatherLayoutBudget:
    """A complete, immutable decision for one weather-screen viewport."""

    viewport_width: int
    viewport_height: int
    usable_width: int
    usable_height: int
    current_density: CurrentDensity
    current_height: int
    warning_density: WarningDensity
    warning_card_height: int
    warning_height: int
    detail_rows: tuple[DetailRow, ...]
    full_detail_labels: bool
    hourly_rows: tuple[HourlyRow, ...]
    daily_columns: tuple[DailyColumn, ...]
    daily_row_count: int
    show_summary: bool
    show_context_matrix: bool
    context_presentation: ContextPresentation
    context_detail_rows: int
    context_table_height: int
    context_map_height: int
    context_height: int
    locations_presentation: AuxiliaryPresentation
    warning_details_presentation: AuxiliaryPresentation
    used_rows: int

    @property
    def remaining_rows(self) -> int:
        """Rows intentionally left as background after whole upgrades fit."""

        return max(0, self.usable_height - self.used_rows)


def _daily_columns(width: int, metrics: LayoutMetrics) -> tuple[DailyColumn, ...]:
    if width >= metrics.daily_wide_min_width:
        return _WIDE_DAILY_COLUMNS

    columns = set(_ESSENTIAL_DAILY_COLUMNS)
    for threshold, column in (
        (metrics.precipitation_column_width, DailyColumn.PRECIPITATION),
        (metrics.gust_column_width, DailyColumn.GUST),
        (metrics.sunrise_column_width, DailyColumn.SUNRISE),
        (metrics.sunset_column_width, DailyColumn.SUNSET),
    ):
        if width >= threshold:
            columns.add(column)
    return tuple(column for column in _DAILY_DISPLAY_ORDER if column in columns)


def _row_cost(
    *,
    warning_height: int,
    show_summary: bool,
    current_height: int,
    hourly_row_count: int,
    daily_row_count: int,
    context_height: int,
    metrics: LayoutMetrics,
) -> int:
    bordered_regions = [
        current_height,
        metrics.hourly_chrome_rows + hourly_row_count,
    ]
    if daily_row_count:
        bordered_regions.append(metrics.daily_chrome_rows + daily_row_count)
    if context_height:
        bordered_regions.append(context_height)

    return (
        metrics.outer_vertical_padding
        + (metrics.summary_rows if show_summary else 0)
        + warning_height
        + sum(bordered_regions)
        + metrics.instrument_gutter * (len(bordered_regions) - 1)
    )


def weather_layout_for(
    viewport_width: int,
    viewport_height: int,
    *,
    has_warnings: bool = False,
    locations_requested: bool = False,
    warning_details_requested: bool = False,
    metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
) -> WeatherLayoutBudget:
    """Return the highest-priority layout that fits a content viewport.

    ``viewport_height`` is the weather screen's content height, after the
    application header and footer have been docked. Wide, sufficiently tall
    viewports reserve their first surplus-width unit for forecast context.
    Available auxiliary surfaces become sidebars only after that sidecar and
    the full 102-column central canvas remain; otherwise their actions resolve
    to modal screens.

    Upgrades are intentionally strict and monotonic.  If the next eligible
    upgrade does not fit, lower-priority upgrades are not substituted into
    the spare row, avoiding resize jitter where a larger window can display
    fewer daily rows than a smaller one.
    """

    viewport_width = max(1, int(viewport_width))
    viewport_height = max(1, int(viewport_height))

    context_sidecar = context_sidecar_eligible(
        viewport_width,
        viewport_height,
        metrics=metrics,
    )
    (
        usable_width,
        locations_presentation,
        warning_presentation,
    ) = auxiliary_presentations_for(
        viewport_width,
        locations_available=locations_requested,
        warning_details_available=warning_details_requested,
        context_sidecar=context_sidecar,
        metrics=metrics,
    )

    current_density = CurrentDensity.SMALLEST
    current_height = metrics.current_smallest_rows
    warning_density = (
        WarningDensity.SUMMARY if has_warnings else WarningDensity.HIDDEN
    )
    warning_card_height = metrics.warning_card_rows if has_warnings else 0
    warning_height = metrics.warning_rows if has_warnings else 0
    hourly_rows = set(_REQUIRED_HOURLY_ROWS)
    daily_row_count = 0
    show_summary = True
    context_presentation = ContextPresentation.HIDDEN
    context_detail_rows = 0
    context_map_height = 0

    def context_height(*, card_count: int | None = None) -> int:
        if context_detail_rows == 0:
            return 0
        if card_count is None:
            card_count = metrics.context_card_count
        return (
            card_count * (metrics.context_card_chrome_rows + context_detail_rows)
            + (card_count - 1) * metrics.context_card_gutter_rows
        )

    def bottom_context_height() -> int:
        if context_presentation is ContextPresentation.BOTTOM:
            return context_height()
        return 0

    def cost() -> int:
        return _row_cost(
            warning_height=warning_height,
            show_summary=show_summary,
            current_height=current_height,
            hourly_row_count=len(hourly_rows),
            daily_row_count=daily_row_count,
            context_height=bottom_context_height(),
            metrics=metrics,
        )

    def add_hourly(row: HourlyRow) -> bool:
        hourly_rows.add(row)
        if cost() <= viewport_height:
            return True
        hourly_rows.remove(row)
        return False

    def add_daily_row() -> bool:
        nonlocal daily_row_count
        daily_row_count += 1
        if cost() <= viewport_height:
            return True
        daily_row_count -= 1
        return False

    def add_daily_pair() -> bool:
        """Add the daily table only when two useful rows fit atomically."""

        nonlocal daily_row_count
        old_count = daily_row_count
        daily_row_count += 2
        if cost() <= viewport_height:
            return True
        daily_row_count = old_count
        return False

    def try_current_small() -> bool:
        nonlocal current_density, current_height
        if usable_width < metrics.current_small_min_width:
            return True
        old_density, old_height = current_density, current_height
        current_density = CurrentDensity.SMALL
        current_height = metrics.current_small_rows
        if cost() <= viewport_height:
            return True
        current_density, current_height = old_density, old_height
        return False

    def try_current_standard_or_buffer() -> bool:
        nonlocal current_density, current_height
        if current_density is not CurrentDensity.SMALL:
            return True
        if usable_width >= metrics.current_standard_min_width:
            old_density, old_height = current_density, current_height
            current_density = CurrentDensity.STANDARD
            current_height = metrics.current_standard_rows
            if cost() <= viewport_height:
                return True
            current_density, current_height = old_density, old_height
            return False

        # At intermediate widths the static-number variant may grow by blank
        # buffer rows, keeping the instrument row balanced without digits.
        while current_height < metrics.current_standard_rows:
            current_height += 1
            if cost() > viewport_height:
                current_height -= 1
                return False
        return True

    def try_tabbed_warning() -> bool:
        nonlocal warning_density, warning_card_height, warning_height
        if not has_warnings:
            return True
        warning_density = WarningDensity.TABBED
        warning_card_height = metrics.warning_tabbed_card_rows
        warning_height = metrics.warning_tabbed_rows
        if cost() <= viewport_height:
            return True
        warning_density = WarningDensity.SUMMARY
        warning_card_height = metrics.warning_card_rows
        warning_height = metrics.warning_rows
        return False

    # Preserve value rows ahead of large-number presentation. On contraction,
    # Digits therefore collapse before rain or wind disappears.
    baseline_complete = add_hourly(HourlyRow.RAIN)
    if baseline_complete:
        baseline_complete = add_hourly(HourlyRow.WIND)

    if baseline_complete:
        upgrades: tuple[Callable[[], bool], ...] = (
            try_current_small,
            try_current_standard_or_buffer,
            try_tabbed_warning,
            add_daily_pair,
            add_daily_row,
            add_daily_row,
            lambda: add_hourly(HourlyRow.TEMPERATURE_BAR),
            lambda: add_hourly(HourlyRow.RAIN_BAR),
            lambda: add_hourly(HourlyRow.WIND_BAR),
            add_daily_row,
            add_daily_row,
        )
        for upgrade in upgrades:
            if not upgrade():
                break

    elif HourlyRow.RAIN in hourly_rows:
        # Rain outranks wind; density upgrades still follow any value rows
        # which fit at this height.
        for upgrade in (try_current_small, try_current_standard_or_buffer):
            if not upgrade():
                break

    if context_sidecar:
        context_presentation = ContextPresentation.SIDECAR
        context_detail_rows = metrics.context_min_detail_rows
        available_height = viewport_height - metrics.outer_vertical_padding
        while context_detail_rows < metrics.context_max_detail_rows:
            next_detail_rows = context_detail_rows + 1
            next_table_height = (
                metrics.context_sidecar_card_count
                * (metrics.context_card_chrome_rows + next_detail_rows)
                + (metrics.context_sidecar_card_count - 1)
                * metrics.context_card_gutter_rows
            )
            if (
                next_table_height
                + metrics.context_sidecar_gutter_rows
                + metrics.context_sidecar_min_map_rows
                > available_height
            ):
                break
            context_detail_rows = next_detail_rows
        context_map_height = min(
            metrics.context_sidecar_max_map_rows,
            available_height
            - context_height(card_count=metrics.context_sidecar_card_count)
            - metrics.context_sidecar_gutter_rows,
        )
    elif daily_row_count >= 6 and usable_width >= metrics.context_min_width:
        context_presentation = ContextPresentation.BOTTOM
        context_detail_rows = metrics.context_min_detail_rows
        if cost() <= viewport_height:
            while context_detail_rows < metrics.context_max_detail_rows:
                context_detail_rows += 1
                if cost() > viewport_height:
                    context_detail_rows -= 1
                    break
        else:
            context_detail_rows = 0
            context_presentation = ContextPresentation.HIDDEN

    ordered_hourly_rows = tuple(
        row for row in _HOURLY_DISPLAY_ORDER if row in hourly_rows
    )
    detail_count = max(1, min(len(_DETAIL_ROW_ORDER), current_height - 2))
    context_table_height = context_height(
        card_count=(
            metrics.context_sidecar_card_count
            if context_presentation is ContextPresentation.SIDECAR
            else metrics.context_card_count
        )
    )
    if context_presentation is ContextPresentation.BOTTOM:
        context_map_height = context_table_height
    context_total_height = context_table_height
    if context_presentation is ContextPresentation.SIDECAR:
        context_total_height += (
            metrics.context_sidecar_gutter_rows + context_map_height
        )
    used_rows = cost()

    return WeatherLayoutBudget(
        viewport_width=viewport_width,
        viewport_height=viewport_height,
        usable_width=usable_width,
        usable_height=viewport_height,
        current_density=current_density,
        current_height=current_height,
        warning_density=warning_density,
        warning_card_height=warning_card_height,
        warning_height=warning_height,
        detail_rows=_DETAIL_ROW_ORDER[:detail_count],
        full_detail_labels=usable_width >= metrics.current_full_detail_min_width,
        hourly_rows=ordered_hourly_rows,
        daily_columns=_daily_columns(usable_width, metrics),
        daily_row_count=daily_row_count,
        show_summary=show_summary,
        show_context_matrix=context_presentation is not ContextPresentation.HIDDEN,
        context_presentation=context_presentation,
        context_detail_rows=context_detail_rows,
        context_table_height=context_table_height,
        context_map_height=context_map_height,
        context_height=context_total_height,
        locations_presentation=locations_presentation,
        warning_details_presentation=warning_presentation,
        used_rows=used_rows,
    )


def auxiliary_presentations_for(
    viewport_width: int,
    *,
    locations_available: bool,
    warning_details_available: bool,
    context_sidecar: bool = False,
    metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
) -> tuple[int, AuxiliaryPresentation, AuxiliaryPresentation]:
    """Allocate automatic auxiliary rails without squeezing the main canvas.

    A selected context sidecar receives the first surplus-width unit. Warning
    detail then receives the first auxiliary rail when both surfaces have
    content. Any surface which does not fit remains available through its modal
    presentation.
    """

    usable_width = max(1, int(viewport_width))
    warning_presentation = AuxiliaryPresentation.MODAL
    locations_presentation = AuxiliaryPresentation.MODAL

    if (
        context_sidecar
        and usable_width - metrics.sidebar_width >= metrics.minimum_central_width
    ):
        usable_width -= metrics.sidebar_width

    if (
        warning_details_available
        and usable_width - metrics.sidebar_width >= metrics.minimum_central_width
    ):
        warning_presentation = AuxiliaryPresentation.SIDEBAR
        usable_width -= metrics.sidebar_width
    if (
        locations_available
        and usable_width - metrics.sidebar_width >= metrics.minimum_central_width
    ):
        locations_presentation = AuxiliaryPresentation.SIDEBAR
        usable_width -= metrics.sidebar_width

    return usable_width, locations_presentation, warning_presentation


def context_sidecar_eligible(
    viewport_width: int,
    viewport_height: int,
    *,
    metrics: LayoutMetrics = DEFAULT_LAYOUT_METRICS,
) -> bool:
    """Return whether useful context fits beside the full forecast canvas."""

    return (
        int(viewport_width)
        >= metrics.minimum_central_width + metrics.sidebar_width
        and int(viewport_height) >= metrics.context_sidecar_min_viewport_height
    )
