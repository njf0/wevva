"""Geographically aware tropical track scope built on shared map primitives."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable

from rich.text import Text
from textual.events import Resize
from textual.widgets import Static

from wevva.geography import (
    GeographicViewport,
    MultiPolygon,
    ProjectedPoint,
    geojson_polygons,
    geojson_polylines,
    map_unit,
    polygon_points,
    project_visible_polygons,
    resolve_display_geography,
    viewport_from_lonlat,
    world_map_unit_polygons,
    wrapped_longitude_delta,
)
from wevva.utils.country_codes import get_country_name_by_alpha2
from wevva.widgets.geographic_scope import (
    GeographicCanvas,
    ProjectedPolygon,
    preferred_geographic_height,
)

_MIN_CONTENT_HEIGHT = 7
_MAX_CONTENT_HEIGHT = 16
_BORDER_ROWS = 0
_TRACK_VIEWPORT_PADDING = 0.10


@dataclass(frozen=True, slots=True)
class GeoTrackPoint:
    """One current or forecast storm position in geographic coordinates."""

    latitude: float
    longitude: float
    label: str = ''
    forecast_marker: bool = False


@dataclass(frozen=True, slots=True)
class StormScopeGeometry:
    """Projected, renderer-independent layers for one storm scope."""

    viewport: GeographicViewport
    land: tuple[ProjectedPolygon, ...]
    storm: tuple[ProjectedPoint, ...]
    forecast_marker_indices: tuple[int, ...]
    geography: ProjectedPoint | None
    geography_name: str
    geography_polygons: MultiPolygon = ()
    cone: tuple[ProjectedPolygon, ...] = ()


@dataclass(frozen=True, slots=True)
class ScopePalette:
    """Resolved Textual theme styles used by the terminal renderer."""

    land: str | None = None
    cone: str | None = None
    current: str | None = None
    forecast: str | None = None
    geography: str | None = None


def extract_storm_track(system: Any) -> tuple[GeoTrackPoint, ...]:
    """Return current position, smooth track vertices, and 24-hour markers."""
    current = _geo_point(getattr(system, 'center_lat', None), getattr(system, 'center_lon', None))
    if current is None:
        return ()

    geometries = getattr(system, 'geometries', None)
    if not isinstance(geometries, dict):
        return ()
    geometry = next(
        (value for key in ('forecast_track', 'track') if isinstance((value := geometries.get(key)), dict)),
        None,
    )
    paths = _geometry_paths(geometry) if geometry is not None else []
    if not paths:
        return ()

    # Collections from NHC/CPHC include both placemark points and connected
    # lines. Prefer the longest path nearest the provider's current centre.
    path = min(
        paths,
        key=lambda candidate: (
            min(_local_distance_squared(current, point) for point in candidate),
            -len(candidate),
        ),
    )
    closest = min(range(len(path)), key=lambda index: _local_distance_squared(current, path[index]))
    if closest == len(path) - 1 and len(path) > 1:
        path = list(reversed(path))
        closest = 0
    elif closest > 0:
        path = path[closest:]

    future_coordinates: list[GeoTrackPoint] = []
    previous = current
    for point in path:
        if _local_distance_squared(previous, point) < 1e-8:
            continue
        future_coordinates.append(point)
        previous = point
    if not future_coordinates:
        return ()

    future = tuple(
        GeoTrackPoint(
            point.latitude,
            point.longitude,
            forecast_marker=_is_24_hour_marker(system, index),
        )
        for index, point in enumerate(future_coordinates, start=1)
    )
    return (current, *future)


def project_track_locally(
    points: Iterable[GeoTrackPoint],
    *,
    location_latitude: float,
    location_longitude: float,
) -> tuple[ProjectedPoint, ...]:
    """Project latitude/longitude to a local plane around the forecast point."""
    projected = []
    for point in points:
        delta_lon = wrapped_longitude_delta(point.longitude, location_longitude)
        mean_latitude = math.radians((point.latitude + location_latitude) / 2.0)
        projected.append(
            ProjectedPoint(
                x=delta_lon * math.cos(mean_latitude),
                y=point.latitude - location_latitude,
            )
        )
    return tuple(projected)


def build_storm_scope_geometry(
    system: Any,
    *,
    location_latitude: float | None = None,
    location_longitude: float | None = None,
    location_name: str = '',
    country_code: str | None = None,
) -> StormScopeGeometry | None:
    """Build a track-fitted scope over the shared global land backdrop."""
    del location_latitude, location_longitude, location_name, country_code
    track = extract_storm_track(system)
    if not track:
        return None

    current_latitude = track[0].latitude
    current_longitude = track[0].longitude
    geometries = getattr(system, 'geometries', None)
    cone_geometry = geometries.get('cone') if isinstance(geometries, dict) else None
    cone = geojson_polygons(cone_geometry)
    viewport = viewport_from_lonlat(
        [
            *((point.longitude, point.latitude) for point in track),
            *polygon_points(cone),
        ],
        origin_latitude=current_latitude,
        origin_longitude=current_longitude,
        padding=_TRACK_VIEWPORT_PADDING,
        minimum_span=0.1,
    )
    if viewport is None:
        return None
    geography_polygons, geography_name = _source_geography_context(system)
    visible_geography = project_visible_polygons(geography_polygons, viewport)
    geography = _visible_geography_label_point(visible_geography, viewport)
    return StormScopeGeometry(
        viewport=viewport,
        land=_visible_world_polygons(viewport),
        storm=tuple(viewport.project(point.longitude, point.latitude) for point in track),
        forecast_marker_indices=tuple(index for index, point in enumerate(track) if index > 0 and point.forecast_marker),
        geography=geography,
        geography_name=geography_name,
        geography_polygons=geography_polygons,
        cone=project_visible_polygons(cone, viewport),
    )


def render_braille_scope(
    scope: StormScopeGeometry,
    *,
    width: int,
    height: int,
    palette: ScopePalette = ScopePalette(),
    show_track: bool = True,
    show_cone: bool = True,
) -> Text:
    """Render optional official cone and discrete positions over global land."""
    canvas = GeographicCanvas(max(12, width), max(5, height), scope.viewport)
    canvas.fill_polygons(_visible_world_polygons(canvas.viewport), layer='land')
    # Keep the complete scope available for stable raster placement even when
    # the cone is hidden; visibility must not move or crop forecast markers.
    canvas.fill_polygons(scope.cone, layer='cone')
    layers = [('land', palette.land)]
    if show_cone:
        layers.append(('cone', palette.cone))
    frame = canvas.frame(
        layers,
        centering_layers=('land', 'cone'),
    )

    geography = scope.geography
    if scope.geography_polygons:
        visible_geography = project_visible_polygons(scope.geography_polygons, canvas.viewport)
        geography = _visible_geography_label_point(visible_geography, canvas.viewport)

    markers: list[tuple[tuple[int, int], str, str, str | None]] = []
    if geography is not None and scope.geography_name:
        geography_cell = frame.marker(geography, '✦', palette.geography)
        markers.append((geography_cell, '✦', scope.geography_name, palette.geography))
    if show_track:
        for index in reversed(scope.forecast_marker_indices):
            cell = frame.marker(scope.storm[index], '●', palette.forecast)
            markers.append((cell, '●', '', palette.forecast))
        current_cell = frame.marker(scope.storm[0], '●', palette.current)
        markers.append((current_cell, '●', '', palette.current))

    occupied = {cell for cell, _glyph, _label, _style in markers}
    if geography is not None and scope.geography_name:
        frame.label(
            geography_cell,
            scope.geography_name,
            palette.geography,
            occupied,
            gap=1,
        )
    return frame.to_text()


class TropicalStormTrackScope(Static):
    """Compact geographic storm-track instrument for the right sidebar."""

    DEFAULT_CSS = """
    TropicalStormTrackScope {
        width: 100%;
        height: 9;
        margin: 1 0 0 0;
        padding: 0;
        background: $background;
        border: none;
    }
    """

    def __init__(self, *, id: str = 'tropical-storm-track-scope') -> None:
        super().__init__('', id=id)
        self._scope: StormScopeGeometry | None = None
        self._preferred_content_height: int | None = None
        self._track_visible = True
        self._cone_visible = True
        self.display = False

    @property
    def track_visible(self) -> bool:
        return self._track_visible

    @property
    def cone_visible(self) -> bool:
        return self._cone_visible

    def toggle_track(self) -> None:
        """Toggle current and forecast position markers without changing scope."""
        self._track_visible = not self._track_visible
        self.refresh()

    def toggle_cone(self) -> None:
        """Toggle the source-provided forecast cone without changing scope."""
        self._cone_visible = not self._cone_visible
        self.refresh()

    def update_system(
        self,
        system: Any,
        *,
        location_latitude: float | None = None,
        location_longitude: float | None = None,
        location_name: str = '',
        country_code: str | None = None,
    ) -> None:
        """Update or collapse the scope for the selected tropical system."""
        self._scope = build_storm_scope_geometry(
            system,
            location_latitude=location_latitude,
            location_longitude=location_longitude,
            location_name=location_name,
            country_code=country_code,
        )
        self.display = self._scope is not None
        self._sync_preferred_height()
        self.refresh(layout=True)

    def clear(self) -> None:
        self._scope = None
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
        palette = ScopePalette(
            land=f'dim {secondary}' if secondary else 'dim',
            cone=theme.get('secondary'),
            current=theme.get('text-error'),
            forecast=theme.get('text-warning'),
            geography=theme.get('text-success') or theme.get('text-primary'),
        )
        return render_braille_scope(
            self._scope,
            width=max(12, self.content_size.width),
            height=max(5, self.content_size.height),
            palette=palette,
            show_track=self._track_visible,
            show_cone=self._cone_visible,
        )


class LargeTropicalStormTrackScope(TropicalStormTrackScope):
    """Storm scope that consumes a dedicated screen pane instead of auto-sizing."""

    DEFAULT_CSS = """
    LargeTropicalStormTrackScope {
        width: 100%;
        height: 1fr;
        min-height: 8;
        margin: 0;
        padding: 0 1;
        background: $background;
        border: none;
    }
    """

    def _sync_preferred_height(self) -> None:
        """Let the parent pane allocate height; projection fitting stays aspect-safe."""


def _source_geography_context(system: Any) -> tuple[MultiPolygon, str]:
    """Resolve source context for labeling against the final fitted viewport."""
    source_info = getattr(system, 'source_info', None)
    display_geography = getattr(system, 'display_geography', None)
    if display_geography is None:
        display_geography = getattr(source_info, 'display_geography', None)
    issuer_code = getattr(source_info, 'issuer_country_code', None)
    if display_geography is not None:
        unit = resolve_display_geography(display_geography)
        label = getattr(display_geography, 'name', None)
        fallback_code = getattr(display_geography, 'code', None)
    elif isinstance(issuer_code, str):
        unit = map_unit(issuer_code)
        label = get_country_name_by_alpha2(issuer_code.strip().upper())
        fallback_code = issuer_code
    else:
        return (), ''
    if unit is None:
        return (), ''
    if not isinstance(label, str) or not label.strip():
        normalized_code = fallback_code.strip().upper() if isinstance(fallback_code, str) else ''
        label = get_country_name_by_alpha2(normalized_code) or next(iter(reversed(unit.names)), '')
    return unit.polygons, label.strip() if isinstance(label, str) else ''


@lru_cache(maxsize=128)
def _visible_world_polygons(viewport: GeographicViewport) -> tuple[ProjectedPolygon, ...]:
    """Project the global backdrop once for each fitted viewport."""
    return project_visible_polygons(world_map_unit_polygons(), viewport)


def _visible_geography_label_point(
    polygons: tuple[ProjectedPolygon, ...],
    viewport: GeographicViewport,
) -> ProjectedPoint | None:
    """Choose a stable in-frame point on the visible source geography."""
    if not polygons:
        return None
    candidates = [
        point
        for polygon in polygons
        for point in polygon[0]
        if viewport.min_x <= point.x <= viewport.max_x and viewport.min_y <= point.y <= viewport.max_y
    ]
    if not candidates:
        return ProjectedPoint(
            (viewport.min_x + viewport.max_x) / 2.0,
            (viewport.min_y + viewport.max_y) / 2.0,
        )
    centre_x = (viewport.min_x + viewport.max_x) / 2.0
    centre_y = (viewport.min_y + viewport.max_y) / 2.0
    return min(
        candidates,
        key=lambda point: (point.x - centre_x) ** 2 + (point.y - centre_y) ** 2,
    )


def _geometry_paths(geometry: dict[str, Any]) -> list[list[GeoTrackPoint]]:
    return [
        [GeoTrackPoint(latitude, longitude) for longitude, latitude in line] for line in geojson_polylines(geometry) if line
    ]


def _geo_point(latitude: Any, longitude: Any, label: str = '') -> GeoTrackPoint | None:
    if not _valid_coordinate(latitude, latitude=True) or not _valid_coordinate(longitude, latitude=False):
        return None
    longitude = ((float(longitude) + 180.0) % 360.0) - 180.0
    return GeoTrackPoint(float(latitude), longitude, label)


def _valid_coordinate(value: Any, *, latitude: bool) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return False
    return -90.0 <= float(value) <= 90.0 if latitude else -360.0 <= float(value) <= 360.0


def _local_distance_squared(first: GeoTrackPoint, second: GeoTrackPoint) -> float:
    delta_lon = wrapped_longitude_delta(second.longitude, first.longitude)
    mean_latitude = math.radians((first.latitude + second.latitude) / 2.0)
    x = delta_lon * math.cos(mean_latitude)
    y = second.latitude - first.latitude
    return x * x + y * y


def _is_24_hour_marker(system: Any, index: int) -> bool:
    """Separate smooth intermediate fixes from visible daily forecast dots."""
    source = str(getattr(system, 'source', '') or '').casefold()
    if source.startswith(('nhc_gis_', 'cphc_gis_')):
        hour = index * 12 if index <= 6 else 72 + (index - 6) * 24
        return hour % 24 == 0
    return True


__all__ = [
    'GeoTrackPoint',
    'LargeTropicalStormTrackScope',
    'ScopePalette',
    'StormScopeGeometry',
    'TropicalStormTrackScope',
    'build_storm_scope_geometry',
    'extract_storm_track',
    'project_track_locally',
    'render_braille_scope',
]
