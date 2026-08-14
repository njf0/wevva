"""Geographically aware tropical track scope built on shared map primitives."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable

from rich.text import Text
from textual.events import Resize
from textual.widgets import Static

from wevva.geography import (
    GeographicViewport,
    MultiPolygon,
    ProjectedPoint,
    geojson_polylines,
    polygon_points,
    project_polygons,
    select_geographic_unit,
    viewport_from_lonlat,
    wrapped_longitude_delta,
)
from wevva.widgets.geographic_scope import (
    GeographicCanvas,
    ProjectedPolygon,
    preferred_geographic_height,
)

_MAX_FORECAST_MARKERS = 3
_MIN_CONTENT_HEIGHT = 7
_MAX_CONTENT_HEIGHT = 16
_BORDER_ROWS = 2


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
    location: ProjectedPoint
    location_name: str


@dataclass(frozen=True, slots=True)
class ScopePalette:
    """Resolved Textual theme styles used by the terminal renderer."""

    land: str | None = None
    track: str | None = None
    current: str | None = None
    forecast: str | None = None
    location: str | None = None


def extract_storm_track(system: Any) -> tuple[GeoTrackPoint, ...]:
    """Return current position, smooth track vertices, and 24-hour markers."""
    current = _geo_point(getattr(system, 'center_lat', None), getattr(system, 'center_lon', None), 'NOW')
    if current is None:
        return ()

    geometries = getattr(system, 'geometries', None)
    if not isinstance(geometries, dict):
        return ()
    geometry = next(
        (
            value
            for key in ('forecast_track', 'track')
            if isinstance((value := geometries.get(key)), dict)
        ),
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
    location_latitude: float | None,
    location_longitude: float | None,
    location_name: str,
    country_code: str | None,
) -> StormScopeGeometry | None:
    """Build shared geographic layers and a storm-specific inclusive viewport."""
    if not _valid_coordinate(location_latitude, latitude=True) or not _valid_coordinate(
        location_longitude,
        latitude=False,
    ):
        return None
    location_latitude = float(location_latitude)
    location_longitude = float(location_longitude)
    track = extract_storm_track(system)
    if not track:
        return None
    marker_indices = [index for index, point in enumerate(track) if index > 0 and point.forecast_marker]
    if marker_indices:
        last_useful_index = marker_indices[min(_MAX_FORECAST_MARKERS, len(marker_indices)) - 1]
        track = track[: last_useful_index + 1]

    unit = select_geographic_unit(
        country_code,
        latitude=location_latitude,
        longitude=location_longitude,
    )
    land: MultiPolygon = unit.polygons if unit is not None else ()
    bounds_points = [
        *(polygon_points(land)),
        *((point.longitude, point.latitude) for point in track),
        (location_longitude, location_latitude),
    ]
    viewport = viewport_from_lonlat(
        bounds_points,
        origin_latitude=location_latitude,
        origin_longitude=location_longitude,
        padding=0.08,
    )
    if viewport is None:
        return None
    return StormScopeGeometry(
        viewport=viewport,
        land=project_polygons(land, viewport),
        storm=tuple(viewport.project(point.longitude, point.latitude) for point in track),
        forecast_marker_indices=tuple(
            index for index, point in enumerate(track) if index > 0 and point.forecast_marker
        ),
        location=viewport.project(location_longitude, location_latitude),
        location_name=location_name,
    )


def render_braille_scope(
    scope: StormScopeGeometry,
    *,
    width: int,
    height: int,
    palette: ScopePalette = ScopePalette(),
) -> Text:
    """Render land and a delicate trajectory through shared Braille output."""
    canvas = GeographicCanvas(max(12, width), max(5, height), scope.viewport)
    canvas.fill_polygons(scope.land, layer='land')
    canvas.polyline(scope.storm, layer='track')
    frame = canvas.frame(
        (('land', palette.land), ('track', palette.track)),
    )

    markers: list[tuple[tuple[int, int], str, str, str | None]] = []
    location_cell = frame.marker(scope.location, '✦', palette.location)
    markers.append((location_cell, '✦', scope.location_name, palette.location))
    for index in reversed(scope.forecast_marker_indices):
        cell = frame.marker(scope.storm[index], '•', palette.forecast)
        markers.append((cell, '•', '', palette.forecast))
    current_cell = frame.marker(scope.storm[0], '●', palette.current)
    markers.append((current_cell, '●', 'NOW', palette.current))

    occupied = {cell for cell, _glyph, _label, _style in markers}
    # Only the two orientation labels remain: the current end and actual place.
    frame.label(current_cell, 'NOW', palette.current, occupied)
    frame.label(location_cell, scope.location_name, palette.location, occupied, gap=1)
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
        border: round $secondary;
        border-title-color: $secondary;
        border-title-style: bold;
    }
    """

    def __init__(self, *, id: str = 'tropical-storm-track-scope') -> None:
        super().__init__('', id=id)
        self.border_title = 'Storm Track Scope'
        self.styles.border_title_align = 'left'
        self._scope: StormScopeGeometry | None = None
        self._preferred_content_height: int | None = None
        self.display = False

    def update_system(
        self,
        system: Any,
        *,
        location_latitude: float | None,
        location_longitude: float | None,
        location_name: str,
        country_code: str | None,
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
            track=theme.get('text-primary'),
            current=theme.get('text-error'),
            forecast=theme.get('text-warning'),
            location=theme.get('text-success') or theme.get('text-primary'),
        )
        return render_braille_scope(
            self._scope,
            width=max(12, self.content_size.width),
            height=max(5, self.content_size.height),
            palette=palette,
        )


def _geometry_paths(geometry: dict[str, Any]) -> list[list[GeoTrackPoint]]:
    return [
        [GeoTrackPoint(latitude, longitude) for longitude, latitude in line]
        for line in geojson_polylines(geometry)
        if line
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
    'ScopePalette',
    'StormScopeGeometry',
    'TropicalStormTrackScope',
    'build_storm_scope_geometry',
    'extract_storm_track',
    'project_track_locally',
    'render_braille_scope',
]
