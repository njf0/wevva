"""Small shared geographic data, geometry, projection, and viewport helpers."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import gzip
from importlib.resources import files
import json
import math
from typing import Any, Iterable

from wevva_warnings import DisplayGeography


LonLat = tuple[float, float]
LinearRing = tuple[LonLat, ...]
Polygon = tuple[LinearRing, ...]
MultiPolygon = tuple[Polygon, ...]

_EARTH_RADIUS_KM = 6371.0088
_SMALL_UNIT_CLUSTER_KM = 750.0
_LARGE_COMPONENT_CLUSTER_KM = 250.0
_LARGE_COMPONENT_SPAN_KM = 2000.0

# The compact Admin-0 resource contains the Hawaiian polygons as part of the
# US map unit, but does not retain Natural Earth's subdivision identifiers.
# Keep this geography-level fallback here rather than teaching storm sources
# about coordinates.
_SUBUNIT_ANCHORS: dict[str, tuple[str, float, float]] = {
    'US-HI': ('US', 19.7297, -155.09),
}


@dataclass(frozen=True, slots=True)
class GeographicUnit:
    """ISO-keyed Natural Earth geometry selected for one forecast location."""

    code: str
    names: tuple[str, ...]
    polygons: MultiPolygon


@dataclass(frozen=True, slots=True)
class ProjectedPoint:
    """A point in a local equirectangular coordinate plane."""

    x: float
    y: float


@dataclass(frozen=True, slots=True)
class GeographicViewport:
    """Local projected bounds with preserved longitude origin and latitude scale."""

    origin_latitude: float
    origin_longitude: float
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    def project(self, longitude: float, latitude: float) -> ProjectedPoint:
        delta_lon = wrapped_longitude_delta(longitude, self.origin_longitude)
        mean_latitude = math.radians((latitude + self.origin_latitude) / 2.0)
        return ProjectedPoint(
            x=delta_lon * math.cos(mean_latitude),
            y=latitude - self.origin_latitude,
        )

    def fitted(self, aspect: float) -> GeographicViewport:
        """Expand bounds to an output aspect ratio without distorting geography."""
        if aspect <= 0.0 or self.width <= 0.0 or self.height <= 0.0:
            return self
        centre_x = (self.min_x + self.max_x) / 2.0
        centre_y = (self.min_y + self.max_y) / 2.0
        width = self.width
        height = self.height
        if width / height < aspect:
            width = height * aspect
        else:
            height = width / aspect
        return GeographicViewport(
            self.origin_latitude,
            self.origin_longitude,
            centre_x - width / 2.0,
            centre_y - height / 2.0,
            centre_x + width / 2.0,
            centre_y + height / 2.0,
        )


def short_location_name(location: object | None) -> str:
    """Return the application's canonical locality name in compact form."""
    name = getattr(location, 'name', '')
    if isinstance(name, str) and name.strip():
        return name.strip()
    latitude = getattr(location, 'latitude', None)
    longitude = getattr(location, 'longitude', None)
    if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
        return f'{latitude:.2f}, {longitude:.2f}'
    return 'Location'


@lru_cache(maxsize=1)
def _map_units() -> dict[str, Any]:
    resource = files('wevva.data').joinpath('natural_earth_50m_map_units.json.gz')
    try:
        with resource.open('rb') as raw_file, gzip.GzipFile(fileobj=raw_file) as archive:
            payload = json.load(archive)
    except (EOFError, OSError, UnicodeError, json.JSONDecodeError):
        return {}
    units = payload.get('units') if isinstance(payload, dict) else None
    return units if isinstance(units, dict) else {}


@lru_cache(maxsize=256)
def map_unit(country_code: str) -> GeographicUnit | None:
    """Load one complete Natural Earth map unit by ISO alpha-2 code."""
    code = country_code.strip().upper()
    raw = _map_units().get(code)
    if not isinstance(raw, dict):
        return None
    polygons = _coerce_polygons(raw.get('polygons'))
    if not polygons:
        return None
    names = tuple(name for name in raw.get('names', ()) if isinstance(name, str) and name)
    return GeographicUnit(code=code, names=names, polygons=polygons)


@lru_cache(maxsize=1)
def world_map_unit_polygons() -> MultiPolygon:
    """Return the checked-in Natural Earth land polygons for every map unit."""
    return tuple(
        polygon
        for raw_unit in _map_units().values()
        if isinstance(raw_unit, dict)
        for polygon in _coerce_polygons(raw_unit.get('polygons'))
    )


def select_geographic_unit(
    country_code: str | None,
    *,
    latitude: float,
    longitude: float,
) -> GeographicUnit | None:
    """Select the human-useful local cluster of a country/map-unit geometry."""
    if not isinstance(country_code, str) or not country_code.strip():
        return None
    unit = map_unit(country_code)
    if unit is None:
        return None

    containing = [polygon for polygon in unit.polygons if point_in_polygon(longitude, latitude, polygon)]
    anchor = containing[0] if containing else min(
        unit.polygons,
        key=lambda polygon: _polygon_distance_km(polygon, latitude, longitude),
    )
    anchor_span = _polygon_span_km(anchor, latitude, longitude)
    cluster_radius = (
        _LARGE_COMPONENT_CLUSTER_KM
        if anchor_span >= _LARGE_COMPONENT_SPAN_KM
        else _SMALL_UNIT_CLUSTER_KM
    )
    selected = tuple(
        polygon
        for polygon in unit.polygons
        if polygon is anchor or _polygon_distance_km(polygon, latitude, longitude) <= cluster_radius
    )
    return GeographicUnit(code=unit.code, names=unit.names, polygons=selected)


@lru_cache(maxsize=64)
def subunit(code: str) -> GeographicUnit | None:
    """Resolve an ISO 3166-2 subdivision from the compact Natural Earth data."""
    normalized = code.strip().upper()
    fallback = _SUBUNIT_ANCHORS.get(normalized)
    if fallback is None:
        return None
    parent_code, latitude, longitude = fallback
    selected = select_geographic_unit(
        parent_code,
        latitude=latitude,
        longitude=longitude,
    )
    if selected is None:
        return None
    return GeographicUnit(
        code=normalized,
        names=selected.names,
        polygons=selected.polygons,
    )


def resolve_display_geography(
    display_geography: DisplayGeography,
    *,
    latitude: float | None = None,
    longitude: float | None = None,
) -> GeographicUnit | None:
    """Resolve one declarative geography hint without conflating its kind."""
    if not display_geography.code.strip():
        return None
    if display_geography.kind == 'country':
        # An explicit country hint declares the land context itself. Selecting
        # a local component from the offshore storm centre can reduce that
        # country to a remote islet (for example Hernan west of Mexico).
        return map_unit(display_geography.code)
    if display_geography.kind == 'map_unit':
        return map_unit(display_geography.code)
    if display_geography.kind == 'subunit':
        return subunit(display_geography.code)
    return None


def viewport_from_lonlat(
    points: Iterable[LonLat],
    *,
    origin_latitude: float,
    origin_longitude: float,
    padding: float = 0.08,
    minimum_span: float = 0.1,
) -> GeographicViewport | None:
    """Build padded local bounds around longitude/latitude points."""
    projected = [
        _project(longitude, latitude, origin_latitude, origin_longitude)
        for longitude, latitude in points
        if _valid_lonlat(longitude, latitude)
    ]
    if not projected:
        return None
    min_x = min(point.x for point in projected)
    max_x = max(point.x for point in projected)
    min_y = min(point.y for point in projected)
    max_y = max(point.y for point in projected)
    width = max(max_x - min_x, minimum_span)
    height = max(max_y - min_y, minimum_span)
    padding = max(0.0, padding)
    centre_x = (min_x + max_x) / 2.0
    centre_y = (min_y + max_y) / 2.0
    half_width = width * (1.0 + 2.0 * padding) / 2.0
    half_height = height * (1.0 + 2.0 * padding) / 2.0
    return GeographicViewport(
        origin_latitude,
        origin_longitude,
        centre_x - half_width,
        centre_y - half_height,
        centre_x + half_width,
        centre_y + half_height,
    )


def project_polygons(polygons: MultiPolygon, viewport: GeographicViewport) -> tuple[tuple[tuple[ProjectedPoint, ...], ...], ...]:
    """Project Polygon/MultiPolygon rings into a viewport's local plane."""
    return tuple(
        tuple(
            tuple(viewport.project(longitude, latitude) for longitude, latitude in ring)
            for ring in polygon
        )
        for polygon in polygons
    )


def project_visible_polygons(
    polygons: MultiPolygon,
    viewport: GeographicViewport,
) -> tuple[tuple[tuple[ProjectedPoint, ...], ...], ...]:
    """Project only polygons whose local bounds intersect a viewport."""
    visible = []
    for polygon in polygons:
        if not polygon:
            continue
        outer, longitude_shift = _project_continuous_ring(polygon[0], viewport)
        projected = (
            outer,
            *(
                _project_continuous_ring(ring, viewport, longitude_shift)[0]
                for ring in polygon[1:]
            ),
        )
        if not projected or not projected[0]:
            continue
        outer = projected[0]
        if (
            max(point.x for point in outer) < viewport.min_x
            or min(point.x for point in outer) > viewport.max_x
            or max(point.y for point in outer) < viewport.min_y
            or min(point.y for point in outer) > viewport.max_y
        ):
            continue
        visible.append(projected)
    return tuple(visible)


def _project_continuous_ring(
    ring: LinearRing,
    viewport: GeographicViewport,
    longitude_shift: float | None = None,
) -> tuple[tuple[ProjectedPoint, ...], float]:
    """Project a ring without wrapping it across the viewport's opposite seam."""
    if not ring:
        return (), 0.0 if longitude_shift is None else longitude_shift
    first_longitude = ring[0][0]
    delta = wrapped_longitude_delta(first_longitude, viewport.origin_longitude)
    deltas = [delta]
    previous_longitude = first_longitude
    for longitude, _latitude in ring[1:]:
        delta += wrapped_longitude_delta(longitude, previous_longitude)
        deltas.append(delta)
        previous_longitude = longitude
    if longitude_shift is None:
        longitude_shift = round((sum(deltas) / len(deltas)) / 360.0) * 360.0
    projected = tuple(
        ProjectedPoint(
            x=(longitude_delta - longitude_shift)
            * math.cos(math.radians((latitude + viewport.origin_latitude) / 2.0)),
            y=latitude - viewport.origin_latitude,
        )
        for longitude_delta, (_longitude, latitude) in zip(deltas, ring)
    )
    return projected, longitude_shift


def polygon_points(polygons: MultiPolygon) -> Iterable[LonLat]:
    for polygon in polygons:
        for ring in polygon:
            yield from ring


def geojson_polygons(geometry: dict[str, Any] | None) -> MultiPolygon:
    """Extract Polygon/MultiPolygon coordinates for shared filled rendering."""
    if not isinstance(geometry, dict):
        return ()
    geometry_type = geometry.get('type')
    coordinates = geometry.get('coordinates')
    if geometry_type == 'Polygon':
        return _coerce_polygons([coordinates])
    if geometry_type == 'MultiPolygon':
        return _coerce_polygons(coordinates)
    return ()


def geojson_polylines(geometry: dict[str, Any] | None) -> tuple[tuple[LonLat, ...], ...]:
    """Extract ordered Point/Polyline primitives from GeoJSON-like geometry."""
    if not isinstance(geometry, dict):
        return ()
    geometry_type = geometry.get('type')
    coordinates = geometry.get('coordinates')
    if geometry_type == 'Point':
        point = _coerce_point(coordinates)
        return ((point,),) if point is not None else ()
    if geometry_type in {'LineString', 'MultiPoint'}:
        line = _coerce_line(coordinates)
        return (line,) if line else ()
    if geometry_type == 'MultiLineString' and isinstance(coordinates, (list, tuple)):
        return tuple(line for value in coordinates if (line := _coerce_line(value)))
    if geometry_type == 'GeometryCollection':
        return tuple(
            line
            for child in geometry.get('geometries') or ()
            if isinstance(child, dict)
            for line in geojson_polylines(child)
        )
    return ()


def point_in_polygon(longitude: float, latitude: float, polygon: Polygon) -> bool:
    if not polygon or not _point_in_ring(longitude, latitude, polygon[0]):
        return False
    return all(not _point_in_ring(longitude, latitude, hole) for hole in polygon[1:])


def wrapped_longitude_delta(longitude: float, origin: float) -> float:
    return ((longitude - origin + 180.0) % 360.0) - 180.0


def _coerce_polygons(raw_polygons: Any) -> MultiPolygon:
    polygons = []
    for raw_polygon in raw_polygons if isinstance(raw_polygons, (list, tuple)) else ():
        rings = tuple(ring for raw_ring in raw_polygon if (ring := _coerce_line(raw_ring)))
        if rings:
            polygons.append(rings)
    return tuple(polygons)


def _coerce_line(value: Any) -> LinearRing:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(point for raw_point in value if (point := _coerce_point(raw_point)) is not None)


def _coerce_point(value: Any) -> LonLat | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    longitude, latitude = value[:2]
    if not _valid_lonlat(longitude, latitude):
        return None
    return float(longitude), float(latitude)


def _valid_lonlat(longitude: Any, latitude: Any) -> bool:
    return (
        isinstance(longitude, (int, float))
        and not isinstance(longitude, bool)
        and isinstance(latitude, (int, float))
        and not isinstance(latitude, bool)
        and math.isfinite(longitude)
        and math.isfinite(latitude)
        and -360.0 <= longitude <= 360.0
        and -90.0 <= latitude <= 90.0
    )


def _project(longitude: float, latitude: float, origin_latitude: float, origin_longitude: float) -> ProjectedPoint:
    delta_lon = wrapped_longitude_delta(longitude, origin_longitude)
    mean_latitude = math.radians((latitude + origin_latitude) / 2.0)
    return ProjectedPoint(delta_lon * math.cos(mean_latitude), latitude - origin_latitude)


def _point_in_ring(longitude: float, latitude: float, ring: LinearRing) -> bool:
    if len(ring) < 3:
        return False
    point_x = 0.0
    points = [(wrapped_longitude_delta(lon, longitude), lat) for lon, lat in ring]
    inside = False
    for first, second in zip(points, (*points[1:], points[0])):
        x1, y1 = first
        x2, y2 = second
        if (y1 > latitude) == (y2 > latitude):
            continue
        intersect_x = (x2 - x1) * (latitude - y1) / (y2 - y1) + x1
        if point_x < intersect_x:
            inside = not inside
    return inside


def _polygon_distance_km(polygon: Polygon, latitude: float, longitude: float) -> float:
    if point_in_polygon(longitude, latitude, polygon):
        return 0.0
    return min(
        _haversine_km(latitude, longitude, point_lat, point_lon)
        for point_lon, point_lat in polygon[0]
    )


def _polygon_span_km(polygon: Polygon, latitude: float, longitude: float) -> float:
    local = [
        _local_xy_km(point_lat, point_lon, latitude, longitude)
        for point_lon, point_lat in polygon[0]
    ]
    return math.hypot(
        max(point[0] for point in local) - min(point[0] for point in local),
        max(point[1] for point in local) - min(point[1] for point in local),
    )


def _local_xy_km(latitude: float, longitude: float, origin_latitude: float, origin_longitude: float) -> tuple[float, float]:
    projected = _project(longitude, latitude, origin_latitude, origin_longitude)
    return (
        _EARTH_RADIUS_KM * math.radians(projected.x),
        _EARTH_RADIUS_KM * math.radians(projected.y),
    )


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(wrapped_longitude_delta(lon2, lon1))
    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    return _EARTH_RADIUS_KM * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


__all__ = [
    'GeographicUnit',
    'GeographicViewport',
    'LinearRing',
    'LonLat',
    'MultiPolygon',
    'Polygon',
    'ProjectedPoint',
    'geojson_polygons',
    'geojson_polylines',
    'map_unit',
    'point_in_polygon',
    'polygon_points',
    'project_polygons',
    'project_visible_polygons',
    'resolve_display_geography',
    'select_geographic_unit',
    'short_location_name',
    'subunit',
    'viewport_from_lonlat',
    'world_map_unit_polygons',
    'wrapped_longitude_delta',
]
