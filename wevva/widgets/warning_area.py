"""Compact selected-CAP-warning area scope using shared geographic rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rich.text import Text
from textual.events import Resize
from textual.widgets import Static

from wevva.alerts import Alert
from wevva.geography import (
    GeographicViewport,
    ProjectedPoint,
    geojson_polygons,
    polygon_points,
    project_polygons,
    select_geographic_unit,
    viewport_from_lonlat,
)
from wevva.widgets.geographic_scope import (
    GeographicCanvas,
    ProjectedPolygon,
    preferred_geographic_height,
)

_MIN_CONTENT_HEIGHT = 8
_MAX_CONTENT_HEIGHT = 20
_BORDER_ROWS = 2


@dataclass(frozen=True, slots=True)
class WarningAreaGeometry:
    """Projected geographic context and one selected warning polygon set."""

    viewport: GeographicViewport
    land: tuple[ProjectedPolygon, ...]
    warning: tuple[ProjectedPolygon, ...]
    location: ProjectedPoint
    location_name: str


@dataclass(frozen=True, slots=True)
class WarningAreaPalette:
    land: str | None = None
    warning: str | None = None
    location: str | None = None


def build_warning_area_geometry(
    alert: Alert,
    *,
    location_latitude: float | None,
    location_longitude: float | None,
    location_name: str,
    country_code: str | None,
) -> WarningAreaGeometry | None:
    """Build a stable whole-context viewport for one real warning geometry."""
    if not _valid_coordinate(location_latitude, latitude=True) or not _valid_coordinate(
        location_longitude,
        latitude=False,
    ):
        return None
    warning = geojson_polygons(alert.geometry)
    if not warning:
        return None

    location_latitude = float(location_latitude)
    location_longitude = float(location_longitude)
    unit = select_geographic_unit(
        country_code,
        latitude=location_latitude,
        longitude=location_longitude,
    )
    land = unit.polygons if unit is not None else ()
    # CAP maps remain stable at the complete selected context. Warning geometry
    # affects bounds only when Natural Earth has no matching map unit.
    bounds_geometry = land or warning
    viewport = viewport_from_lonlat(
        [*polygon_points(bounds_geometry), (location_longitude, location_latitude)],
        origin_latitude=location_latitude,
        origin_longitude=location_longitude,
        padding=0.08,
    )
    if viewport is None:
        return None
    return WarningAreaGeometry(
        viewport=viewport,
        land=project_polygons(land, viewport),
        warning=project_polygons(warning, viewport),
        location=viewport.project(location_longitude, location_latitude),
        location_name=location_name,
    )


def render_warning_area(
    scope: WarningAreaGeometry,
    *,
    width: int,
    height: int,
    palette: WarningAreaPalette = WarningAreaPalette(),
) -> Text:
    """Render Natural Earth land, one warning fill, and the forecast location."""
    canvas = GeographicCanvas(max(12, width), max(5, height), scope.viewport)
    canvas.fill_polygons(scope.land, layer='land')
    canvas.fill_polygons(scope.warning, layer='warning')
    frame = canvas.frame(
        (('land', palette.land), ('warning', palette.warning)),
        solid_braille_layers=('land', 'warning'),
    )
    location_cell = frame.marker(scope.location, '✦', palette.location)
    occupied = {location_cell}
    frame.label(location_cell, scope.location_name, palette.location, occupied, gap=1)
    return frame.to_text()


class WarningAreaScope(Static):
    """Sibling sidebar panel for the currently selected ordinary warning."""

    DEFAULT_CSS = """
    WarningAreaScope {
        width: 100%;
        height: 10;
        margin: 1 0 0 0;
        padding: 0;
        background: $background;
        border: round $secondary;
        border-title-color: $secondary;
        border-title-style: bold;
    }
    """

    def __init__(self, *, id: str = 'warning-area-scope') -> None:
        super().__init__('', id=id)
        self.border_title = 'Warning Area'
        self.styles.border_title_align = 'left'
        self._scope: WarningAreaGeometry | None = None
        self._warning_color: str | None = None
        self._preferred_content_height: int | None = None
        self.display = False

    def update_alert(
        self,
        alert: Alert,
        *,
        location_latitude: float | None,
        location_longitude: float | None,
        location_name: str,
        country_code: str | None,
        warning_color: str | None,
    ) -> None:
        self._scope = build_warning_area_geometry(
            alert,
            location_latitude=location_latitude,
            location_longitude=location_longitude,
            location_name=location_name,
            country_code=country_code,
        )
        self._warning_color = warning_color
        self.display = self._scope is not None
        self._sync_preferred_height()
        self.refresh(layout=True)

    def clear(self) -> None:
        self._scope = None
        self._warning_color = None
        self._preferred_content_height = None
        self.display = False
        self.refresh(layout=True)

    def on_resize(self, event: Resize) -> None:
        self._sync_preferred_height()
        self.refresh()

    def _sync_preferred_height(self) -> None:
        """Update explicit height only when width or projected aspect requires it."""
        if self._scope is None:
            return
        available_width = self.content_size.width
        if available_width <= 0 and self.parent is not None:
            available_width = max(1, self.parent.content_size.width - 2)
        if available_width <= 0:
            return
        content_height = preferred_geographic_height(
            self._scope.viewport,
            available_width=available_width,
            minimum=_MIN_CONTENT_HEIGHT,
            maximum=_MAX_CONTENT_HEIGHT,
        )
        if content_height == self._preferred_content_height:
            return
        self._preferred_content_height = content_height
        self.styles.height = content_height + _BORDER_ROWS
        self.refresh(layout=True)

    def render(self) -> Text:
        if self._scope is None:
            return Text()
        theme = self.app.theme_variables
        secondary = theme.get('text-secondary')
        return render_warning_area(
            self._scope,
            width=max(12, self.content_size.width),
            height=max(5, self.content_size.height),
            palette=WarningAreaPalette(
                land=theme.get('secondary') or secondary,
                warning=self._warning_color or theme.get('text-accent'),
                location=theme.get('text-success') or theme.get('text-primary'),
            ),
        )


def _valid_coordinate(value: Any, *, latitude: bool) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    return -90.0 <= float(value) <= 90.0 if latitude else -360.0 <= float(value) <= 360.0


__all__ = [
    'WarningAreaGeometry',
    'WarningAreaPalette',
    'WarningAreaScope',
    'build_warning_area_geometry',
    'render_warning_area',
]
