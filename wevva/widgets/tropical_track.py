"""Geographically aware tropical track scope built on shared map primitives."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable, Sequence

from rich.cells import cell_len
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.events import Click, Resize
from textual.widgets import Static
from wevva_warnings import TropicalProduct

from wevva.geography import (
    GeographicViewport,
    PopulatedPlace,
    ProjectedPoint,
    geojson_polygons,
    geojson_polylines,
    polygon_points,
    project_visible_polygons,
    viewport_from_lonlat,
    world_map_unit_polygons,
    world_populated_places,
    wrapped_longitude_delta,
)
from wevva.location_metadata import LocationMetadata
from wevva.messages import PlaceSelected
from wevva.widgets.geographic_scope import (
    GeographicCanvas,
    GeographicFrame,
    ProjectedPolygon,
    preferred_geographic_height,
)
from wevva.widgets.map_callouts import place_directional_callout

_MIN_CONTENT_HEIGHT = 7
_MAX_CONTENT_HEIGHT = 16
_BORDER_ROWS = 0
_TRACK_VIEWPORT_PADDING = 0.10
_TRACK_VIEWPORT_MINIMUM_SPAN = 12.0
_MAX_PLACE_LABELS = 3
_MAX_PLACE_CANDIDATES = 12
_FIX_MARKER = '◆'
_PLACE_MARKER = '•'


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
    fix_labels: tuple[tuple[int, str], ...] = ()
    cone: tuple[ProjectedPolygon, ...] = ()
    places: tuple[PopulatedPlace, ...] = ()


@dataclass(frozen=True, slots=True)
class ScopePalette:
    """Resolved Textual theme styles used by the terminal renderer."""

    land: str | None = None
    cone: str | None = None
    track: str | None = None
    current: str | None = None
    forecast: str | None = None
    place: str | None = None


def extract_storm_track(
    system: Any,
    products: Sequence[TropicalProduct] = (),
) -> tuple[GeoTrackPoint, ...]:
    """Return track geometry with labels only for data-backed forecast fixes."""
    current = _geo_point(
        getattr(system, 'center_lat', None),
        getattr(system, 'center_lon', None),
        'Now',
    )
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

    explicit_fixes = _explicit_forecast_fixes(products)
    matched_leads = [
        (point, _explicit_lead_for_point(point, explicit_fixes))
        for point in future_coordinates
    ]
    use_daily_fixes = any(
        lead is not None and _is_daily_forecast_lead(lead)
        for _point, lead in matched_leads
    )
    future = []
    for point, lead in matched_leads:
        forecast_marker = not use_daily_fixes or (
            lead is not None and _is_daily_forecast_lead(lead)
        )
        future.append(
            GeoTrackPoint(
                point.latitude,
                point.longitude,
                label=f'{lead:g}h' if lead is not None and forecast_marker else '',
                forecast_marker=forecast_marker,
            )
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
    products: Sequence[TropicalProduct] = (),
    location_latitude: float | None = None,
    location_longitude: float | None = None,
    location_name: str = '',
    country_code: str | None = None,
) -> StormScopeGeometry | None:
    """Build a track-fitted scope over the shared global land backdrop."""
    del location_latitude, location_longitude, location_name, country_code
    track = extract_storm_track(system, products)
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
        minimum_span=_TRACK_VIEWPORT_MINIMUM_SPAN,
    )
    if viewport is None:
        return None
    return StormScopeGeometry(
        viewport=viewport,
        land=_visible_world_polygons(viewport),
        storm=tuple(viewport.project(point.longitude, point.latitude) for point in track),
        forecast_marker_indices=tuple(index for index, point in enumerate(track) if index > 0 and point.forecast_marker),
        fix_labels=tuple(
            (index, point.label)
            for index, point in enumerate(track)
            if index == 0 or point.forecast_marker
        ),
        cone=project_visible_polygons(cone, viewport),
        places=world_populated_places(),
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
    """Render the legacy non-interactive scope for compact/sidebar consumers."""
    frame = _scope_frame(
        scope,
        width=max(12, width),
        height=max(5, height),
        palette=palette,
        show_track=show_track,
        show_cone=show_cone,
    )
    canvas = frame.canvas

    # Reserve every track position even when markers are hidden so toggling
    # them cannot make place labels jump into their cells.
    occupied = {canvas.cell_position(point) for point in scope.storm}
    if show_track:
        for index in reversed(scope.forecast_marker_indices):
            frame.marker(scope.storm[index], _FIX_MARKER, palette.forecast)
        frame.marker(scope.storm[0], _FIX_MARKER, palette.current)

    labels_added = 0
    for place, point in _visible_place_candidates(scope.places, canvas.viewport, scope.storm):
        place_cell = canvas.cell_position(point)
        if place_cell in occupied:
            continue
        candidate_occupied = set(occupied)
        candidate_occupied.add(place_cell)
        if not frame.label(
            place_cell,
            place.name,
            palette.place,
            candidate_occupied,
            gap=1,
        ):
            continue
        frame.marker(point, _PLACE_MARKER, palette.place)
        occupied = candidate_occupied
        labels_added += 1
        if labels_added == _MAX_PLACE_LABELS:
            break
    return frame.to_text()


def _scope_frame(
    scope: StormScopeGeometry,
    *,
    width: int,
    height: int,
    palette: ScopePalette,
    show_track: bool = True,
    show_cone: bool = True,
) -> GeographicFrame:
    """Build the shared raster and preserve identical overlay projection."""
    canvas = GeographicCanvas(max(1, width), max(1, height), scope.viewport)
    canvas.fill_polygons(_visible_world_polygons(canvas.viewport), layer='land')
    canvas.fill_polygons(scope.cone, layer='cone')
    # Keep supplied fixes in the fitted/centred extent without joining them
    # into an inferred continuous path. Native and legacy renderers add the
    # discrete markers after the backdrop has been composed.
    for point in scope.storm:
        canvas.point(point, layer='track-positions')
    layers = [('land', palette.land)]
    if show_cone:
        layers.append(('cone', palette.cone))
    return canvas.frame(
        layers,
        centering_layers=('land', 'cone', 'track-positions'),
    )


@dataclass(frozen=True, slots=True)
class TropicalMapPlacement:
    """One native fix or city callout placed over the storm raster."""

    key: str
    kind: str
    column: int
    row: int
    width: int
    marker_on_right: bool


class TropicalCityLabel(Static, can_focus=True):
    """Directional tropical-map city callout using ordinary place selection."""

    BINDINGS = [
        Binding('enter', 'select_location', 'Open', show=False),
        Binding('space', 'select_location', 'Open', show=False),
    ]

    DEFAULT_CSS = """
    TropicalCityLabel {
        position: absolute;
        layer: labels;
        width: auto;
        min-width: 1;
        height: 1;
        background: $background;
        color: $text-success;
        text-style: bold;
        pointer: pointer;
    }

    TropicalCityLabel:hover,
    TropicalCityLabel:focus {
        text-style: bold reverse;
    }
    """

    def __init__(self, place: PopulatedPlace) -> None:
        super().__init__('', markup=False)
        self.place = place
        self.location = LocationMetadata(
            latitude=place.latitude,
            longitude=place.longitude,
            name=place.name,
            country_code=place.country_code,
        )
        self._marker_on_right = False
        self.label_text = ''
        self.set_marker_on_right(False)

    def set_marker_on_right(self, marker_on_right: bool) -> None:
        self._marker_on_right = marker_on_right
        self.label_text = (
            f'{self.place.name} {_PLACE_MARKER}'
            if marker_on_right
            else f'{_PLACE_MARKER} {self.place.name}'
        )
        self.update(self.label_text)

    def on_click(self, event: Click) -> None:
        event.stop()
        self.focus()
        self.action_select_location()

    def action_select_location(self) -> None:
        self.post_message(PlaceSelected(location=self.location))


class TropicalFixLabel(Static):
    """Passive native callout for the current or an official forecast fix."""

    DEFAULT_CSS = """
    TropicalFixLabel {
        position: absolute;
        layer: labels;
        width: auto;
        min-width: 1;
        height: 1;
        background: $background;
        text-style: bold;
    }

    TropicalFixLabel.current-fix {
        color: $error;
    }

    TropicalFixLabel.forecast-fix {
        color: $warning;
    }
    """

    def __init__(self, label: str, *, current: bool) -> None:
        super().__init__('', markup=False)
        self._body_text = label
        self._marker_on_right = False
        self._marker_only = False
        self.label_text = ''
        self.set_class(current, 'current-fix')
        self.set_class(not current, 'forecast-fix')
        self.set_marker_on_right(False)

    def update_fix(self, label: str, *, current: bool) -> None:
        self._body_text = label
        self.set_class(current, 'current-fix')
        self.set_class(not current, 'forecast-fix')
        self.set_marker_on_right(self._marker_on_right)

    def set_marker_on_right(self, marker_on_right: bool) -> None:
        self._marker_on_right = marker_on_right
        if self._marker_only or not self._body_text:
            self.label_text = _FIX_MARKER
        else:
            self.label_text = (
                f'{self._body_text} {_FIX_MARKER}'
                if marker_on_right
                else f'{_FIX_MARKER} {self._body_text}'
            )
        self.update(self.label_text)

    def set_marker_only(self, marker_only: bool) -> None:
        """Collapse a callout to its exact supplied fix when space is tight."""
        self._marker_only = marker_only
        self.set_marker_on_right(self._marker_on_right)


class TropicalStormTrackScope(Container):
    """Braille storm geometry with native fix and interactive city callouts."""

    DEFAULT_CSS = """
    TropicalStormTrackScope {
        layers: map labels;
        width: 100%;
        height: 9;
        margin: 1 0 0 0;
        padding: 0;
        background: $background;
        border: none;
        overflow: hidden hidden;
    }

    .tropical-track-backdrop {
        position: absolute;
        layer: map;
        offset: 0 0;
        width: 100%;
        height: 100%;
        background: $background;
    }
    """

    def __init__(self, *, id: str = 'tropical-storm-track-scope') -> None:
        super().__init__(id=id)
        self._scope: StormScopeGeometry | None = None
        self._preferred_content_height: int | None = None
        self._layout_visible = True
        self._city_labels: dict[str, TropicalCityLabel] = {}
        self._fix_labels: dict[str, TropicalFixLabel] = {}
        self._placements: dict[str, TropicalMapPlacement] = {}
        self._reflow_pending = False
        self.display = False

    def compose(self) -> ComposeResult:
        yield Static('', classes='tropical-track-backdrop')

    @property
    def available(self) -> bool:
        """Return whether the selected source supplied a renderable track."""
        return self._scope is not None

    @property
    def cone_available(self) -> bool:
        """Return whether the selected source supplied a renderable cone."""
        return self._scope is not None and bool(self._scope.cone)

    @property
    def placements(self) -> tuple[TropicalMapPlacement, ...]:
        """Current visible native callouts, primarily for inspection/tests."""
        return tuple(self._placements.values())

    def update_system(
        self,
        system: Any,
        *,
        products: Sequence[TropicalProduct] = (),
        location_latitude: float | None = None,
        location_longitude: float | None = None,
        location_name: str = '',
        country_code: str | None = None,
    ) -> None:
        """Update or collapse the scope for the selected tropical system."""
        self._scope = build_storm_scope_geometry(
            system,
            products=products,
            location_latitude=location_latitude,
            location_longitude=location_longitude,
            location_name=location_name,
            country_code=country_code,
        )
        self.display = self._scope is not None and self._layout_visible
        if self.is_mounted:
            self._sync_label_widgets()
        self._sync_preferred_height()
        self.refresh(layout=True)
        self._schedule_reflow()

    def clear(self) -> None:
        self._scope = None
        self._preferred_content_height = None
        self._placements = {}
        if self.is_mounted:
            self._sync_label_widgets()
        self.display = False
        self.refresh(layout=True)

    def set_layout(self, *, visible: bool, height: int) -> None:
        """Apply screen allocation while retaining projected storm geometry."""
        self._layout_visible = bool(visible)
        self.styles.height = max(0, int(height))
        self.display = self._scope is not None and self._layout_visible
        self.refresh(layout=True)
        self._schedule_reflow()

    def on_mount(self) -> None:
        self._sync_label_widgets()
        self._schedule_reflow()

    def on_resize(self, event: Resize) -> None:
        self._sync_preferred_height()
        self.refresh()
        self._schedule_reflow()

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
        self._schedule_reflow()

    def _schedule_reflow(self) -> None:
        if not self.is_mounted or self._reflow_pending:
            return
        self._reflow_pending = True
        self.call_after_refresh(self._reflow)

    def _city_specs(self) -> tuple[tuple[PopulatedPlace, ProjectedPoint], ...]:
        if self._scope is None:
            return ()
        return _visible_place_candidates(
            self._scope.places,
            self._scope.viewport,
            self._scope.storm,
        )

    def _sync_label_widgets(self) -> None:
        city_specs = self._city_specs()
        cities = {_place_key(place): place for place, _point in city_specs}
        for key in tuple(self._city_labels):
            if key not in cities:
                self._city_labels.pop(key).remove()
        for key, place in cities.items():
            if key not in self._city_labels:
                self._city_labels[key] = TropicalCityLabel(place)
                self.mount(self._city_labels[key])

        fixes = dict(self._scope.fix_labels) if self._scope is not None else {}
        fix_keys = {f'fix-{index}' for index in fixes}
        for key in tuple(self._fix_labels):
            if key not in fix_keys:
                self._fix_labels.pop(key).remove()
        for index, label_text in fixes.items():
            key = f'fix-{index}'
            label = self._fix_labels.get(key)
            if label is None:
                label = TropicalFixLabel(label_text, current=index == 0)
                self._fix_labels[key] = label
                self.mount(label)
            else:
                label.update_fix(label_text, current=index == 0)

    def _reflow(self) -> None:
        self._reflow_pending = False
        if self._scope is None or not self.is_mounted:
            return
        width = self.content_size.width
        height = self.content_size.height
        if width < 1 or height < 1:
            return
        theme = self.app.theme_variables
        secondary = theme.get('text-secondary')
        warning = theme.get('text-warning')
        palette = ScopePalette(
            land=f'dim {secondary}' if secondary else 'dim',
            cone=f'dim {warning}' if warning else 'dim yellow',
            track=warning,
            current=theme.get('text-error'),
            forecast=warning,
            place=theme.get('text-success') or theme.get('text-primary'),
        )
        frame = _scope_frame(
            self._scope,
            width=width,
            height=height,
            palette=palette,
            show_track=True,
            show_cone=True,
        )
        self.query_one('.tropical-track-backdrop', Static).update(
            frame.to_text(),
            layout=False,
        )
        cone_cells = frame.canvas.layer_cells(('cone',))

        fix_cells = {
            index: frame.canvas.cell_position(self._scope.storm[index])
            for index, _label_text in self._scope.fix_labels
            if index < len(self._scope.storm)
        }
        # A lead callout may move around its own anchor, but must never cover
        # another provider-supplied fix.
        occupied: set[tuple[int, int]] = set(fix_cells.values())
        placements: dict[str, TropicalMapPlacement] = {}
        for index, _label_text in self._scope.fix_labels:
            key = f'fix-{index}'
            label = self._fix_labels.get(key)
            if label is None or index >= len(self._scope.storm):
                continue
            anchor = fix_cells[index]
            occupied.discard(anchor)
            label.set_marker_only(False)
            if not label._body_text:
                label.set_marker_on_right(False)
                label.display = True
                label.styles.offset = anchor
                occupied.add(anchor)
                placements[key] = TropicalMapPlacement(
                    key=key,
                    kind='fix',
                    column=anchor[0],
                    row=anchor[1],
                    width=1,
                    marker_on_right=False,
                )
                continue
            placement = place_directional_callout(
                anchor=anchor,
                label_width=cell_len(label.label_text),
                canvas_width=width,
                canvas_height=height,
                occupied=occupied,
            )
            if placement is None:
                label.set_marker_only(True)
                label.display = True
                label.styles.offset = anchor
                occupied.add(anchor)
                placements[key] = TropicalMapPlacement(
                    key=key,
                    kind='fix',
                    column=anchor[0],
                    row=anchor[1],
                    width=1,
                    marker_on_right=False,
                )
                continue
            label.set_marker_on_right(placement.marker_on_right)
            label.display = True
            label.styles.offset = (placement.column, placement.row)
            placements[key] = TropicalMapPlacement(
                key=key,
                kind='fix',
                column=placement.column,
                row=placement.row,
                width=placement.width,
                marker_on_right=placement.marker_on_right,
            )

        for label in self._city_labels.values():
            label.display = False
        labels_added = 0
        for place, point in _visible_place_candidates(
            self._scope.places,
            frame.canvas.viewport,
            self._scope.storm,
        ):
            if labels_added >= _MAX_PLACE_LABELS:
                break
            key = _place_key(place)
            label = self._city_labels.get(key)
            if label is None:
                continue
            anchor = frame.canvas.cell_position(point)
            placement = place_directional_callout(
                anchor=anchor,
                label_width=cell_len(label.label_text),
                canvas_width=width,
                canvas_height=height,
                occupied=occupied,
                # The city marker belongs at its geographic anchor even when
                # that point lies inside the cone; prefer to keep its name off
                # the cone while retaining a collision-safe fallback.
                preferred_avoidance=cone_cells - {anchor},
            )
            if placement is None:
                continue
            label.set_marker_on_right(placement.marker_on_right)
            label.display = True
            label.styles.offset = (placement.column, placement.row)
            placements[key] = TropicalMapPlacement(
                key=key,
                kind='city',
                column=placement.column,
                row=placement.row,
                width=placement.width,
                marker_on_right=placement.marker_on_right,
            )
            labels_added += 1
        self._placements = placements


class LargeTropicalStormTrackScope(TropicalStormTrackScope):
    """Storm scope that consumes a dedicated screen pane instead of auto-sizing."""

    DEFAULT_CSS = """
    LargeTropicalStormTrackScope {
        width: 100%;
        height: 0;
        min-height: 0;
        margin: 0;
        padding: 0;
        background: $background;
        border: none;
    }
    """

    def _sync_preferred_height(self) -> None:
        """Let the parent pane allocate height; projection fitting stays aspect-safe."""


@lru_cache(maxsize=128)
def _visible_world_polygons(viewport: GeographicViewport) -> tuple[ProjectedPolygon, ...]:
    """Project the global backdrop once for each fitted viewport."""
    return project_visible_polygons(world_map_unit_polygons(), viewport)


def _visible_place_candidates(
    places: tuple[PopulatedPlace, ...],
    viewport: GeographicViewport,
    storm: tuple[ProjectedPoint, ...],
) -> tuple[tuple[PopulatedPlace, ProjectedPoint], ...]:
    """Choose prominent visible places, favouring those near the storm track."""
    candidates = []
    for place in places:
        point = viewport.project(place.longitude, place.latitude)
        if not (
            viewport.min_x <= point.x <= viewport.max_x
            and viewport.min_y <= point.y <= viewport.max_y
        ):
            continue
        distance = min(
            (
                (point.x - storm_point.x) ** 2 + (point.y - storm_point.y) ** 2
                for storm_point in storm
            ),
            default=0.0,
        )
        candidates.append((place, point, distance))
    candidates.sort(
        key=lambda candidate: (
            candidate[0].scale_rank,
            candidate[0].label_rank,
            candidate[2],
            -candidate[0].population,
            candidate[0].name,
        )
    )
    return tuple(
        (place, point)
        for place, point, _distance in candidates[:_MAX_PLACE_CANDIDATES]
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


def _explicit_forecast_fixes(
    products: Sequence[TropicalProduct],
) -> tuple[tuple[GeoTrackPoint, float], ...]:
    """Extract only provider-supplied lead hours from structured products."""
    fixes: list[tuple[GeoTrackPoint, float]] = []
    for product in products:
        data = product.data
        points = data.get('points') if isinstance(data, dict) else None
        if not isinstance(points, list):
            continue
        for value in points:
            if not isinstance(value, dict):
                continue
            point = _geo_point(value.get('latitude'), value.get('longitude'))
            lead = value.get('lead_hours')
            if (
                point is None
                or not isinstance(lead, (int, float))
                or isinstance(lead, bool)
                or not math.isfinite(float(lead))
                or float(lead) <= 0
            ):
                continue
            fixes.append((point, float(lead)))
    return tuple(fixes)


def _explicit_lead_for_point(
    point: GeoTrackPoint,
    fixes: tuple[tuple[GeoTrackPoint, float], ...],
) -> float | None:
    return next(
        (
            lead
            for candidate, lead in fixes
            if _local_distance_squared(point, candidate) <= 1e-6
        ),
        None,
    )


def _is_daily_forecast_lead(lead: float) -> bool:
    """Return whether an explicit provider lead falls on a 24-hour boundary."""
    return math.isclose(lead % 24.0, 0.0, abs_tol=1e-9)


def _place_key(place: PopulatedPlace) -> str:
    return f'city-{place.latitude:.6f},{place.longitude:.6f}'


__all__ = [
    'GeoTrackPoint',
    'LargeTropicalStormTrackScope',
    'ScopePalette',
    'StormScopeGeometry',
    'TropicalCityLabel',
    'TropicalFixLabel',
    'TropicalMapPlacement',
    'TropicalStormTrackScope',
    'build_storm_scope_geometry',
    'extract_storm_track',
    'project_track_locally',
    'render_braille_scope',
]
