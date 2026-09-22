"""Country-scale map for the currently selected forecast location."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from rich.text import Text
from textual.events import Resize
from textual.widgets import Static

from wevva.geography import (
    GeographicViewport,
    PopulatedPlace,
    ProjectedPoint,
    point_in_polygon,
    polygon_points,
    project_polygons,
    select_geographic_unit,
    viewport_from_lonlat,
    world_populated_places,
)
from wevva.utils import temp_colour
from wevva.widgets.geographic_scope import (
    GeographicCanvas,
    ProjectedPolygon,
    preferred_geographic_height,
)

_MIN_CONTENT_HEIGHT = 12
_MAX_CONTENT_HEIGHT = 26
_BORDER_ROWS = 2
_VIEWPORT_PADDING = 0.08
_MAX_PLACE_LABELS = 8
_MAX_PLACE_CANDIDATES = 8

PlaceKey = tuple[float, float]
TemperatureLabel = tuple[str, str | None]


@dataclass(frozen=True, slots=True)
class LocationMapGeometry:
    """Projected country component, current location, and ranked city labels."""

    viewport: GeographicViewport
    land: tuple[ProjectedPolygon, ...]
    location: ProjectedPoint
    location_name: str
    places: tuple[tuple[PopulatedPlace, ProjectedPoint], ...]


@dataclass(frozen=True, slots=True)
class LocationMapPalette:
    """Resolved terminal styles for one location map."""

    land: str | None = None
    place: str | None = None
    location: str | None = None
    location_label: str | None = None


def build_location_map_geometry(
    *,
    latitude: float | None,
    longitude: float | None,
    location_name: str,
    country_code: str | None,
) -> LocationMapGeometry | None:
    """Build a country-component view centred on a forecast location."""
    if not _valid_coordinate(latitude, latitude=True) or not _valid_coordinate(
        longitude,
        latitude=False,
    ):
        return None

    latitude = float(latitude)
    longitude = float(longitude)
    unit = select_geographic_unit(
        country_code,
        latitude=latitude,
        longitude=longitude,
    )
    if unit is None:
        return None

    viewport = viewport_from_lonlat(
        [*polygon_points(unit.polygons), (longitude, latitude)],
        origin_latitude=latitude,
        origin_longitude=longitude,
        padding=_VIEWPORT_PADDING,
    )
    if viewport is None:
        return None

    places = []
    for place in world_populated_places():
        projected = viewport.project(place.longitude, place.latitude)
        if not (
            viewport.min_x <= projected.x <= viewport.max_x
            and viewport.min_y <= projected.y <= viewport.max_y
        ):
            continue
        if not any(
            point_in_polygon(place.longitude, place.latitude, polygon)
            for polygon in unit.polygons
        ):
            continue
        places.append((place, projected))

    location_key = _normalized_place_name(location_name)
    places = [
        candidate
        for candidate in places
        if _normalized_place_name(candidate[0].name) != location_key
    ]
    places.sort(
        key=lambda candidate: (
            candidate[0].scale_rank,
            candidate[0].label_rank,
            -candidate[0].population,
            candidate[0].name,
        )
    )
    return LocationMapGeometry(
        viewport=viewport,
        land=project_polygons(unit.polygons, viewport),
        location=viewport.project(longitude, latitude),
        location_name=location_name.strip() or 'Current location',
        places=tuple(places[:_MAX_PLACE_CANDIDATES]),
    )


def render_location_map(
    scope: LocationMapGeometry,
    *,
    width: int,
    height: int,
    palette: LocationMapPalette = LocationMapPalette(),
    temperature_labels: Mapping[PlaceKey, TemperatureLabel] | None = None,
    location_label: str | None = None,
) -> Text:
    """Render country land, major-city labels, and the current location."""
    canvas = GeographicCanvas(max(12, width), max(5, height), scope.viewport)
    canvas.fill_polygons(scope.land, layer='land')
    frame = canvas.frame((('land', palette.land),), solid_braille_layers=('land',))

    location_style = palette.location_label or palette.location
    location_cell = frame.marker(scope.location, '✦', location_style)
    occupied = {location_cell}
    frame.label(
        location_cell,
        location_label or scope.location_name,
        location_style,
        occupied,
        gap=1,
        gap_style=location_style,
    )

    labels_added = 0
    for place, point in scope.places:
        reading = (temperature_labels or {}).get(_place_key(place))
        place_label = place.name if reading is None else f'{place.name} {reading[0]}'
        place_style = palette.place if reading is None else reading[1]
        place_cell = canvas.cell_position(point)
        if place_cell in occupied:
            continue
        candidate_occupied = set(occupied)
        candidate_occupied.add(place_cell)
        if not frame.label(
            place_cell,
            place_label,
            place_style,
            candidate_occupied,
            gap=1,
        ):
            continue
        frame.marker(point, '•', place_style)
        occupied = candidate_occupied
        labels_added += 1
        if labels_added == _MAX_PLACE_LABELS:
            break
    return frame.to_text()


class LocationMap(Static):
    """Prominent country map shown with the primary weather instruments."""

    DEFAULT_CSS = """
    LocationMap {
        width: 98;
        height: 20;
        margin: 0 0 1 0;
        padding: 0 1;
        background: $background;
        border: round $primary;
        border-title-color: $primary;
        border-title-align: left;
    }
    """

    def __init__(self, *, id: str = 'location-map') -> None:
        super().__init__('', id=id)
        self.border_title = 'Location Map'
        self._scope: LocationMapGeometry | None = None
        self._temperatures: dict[PlaceKey, float] = {}
        self._temperature_unit = 'celsius'
        self._current_temperature: float | None = None
        self._preferred_content_height: int | None = None
        self.display = False

    def update_location(
        self,
        location: object | None,
        *,
        current_temperature: float | None = None,
        temperature_unit: str = 'celsius',
    ) -> None:
        """Show the appropriate country component for a location."""
        self._scope = build_location_map_geometry(
            latitude=getattr(location, 'latitude', None),
            longitude=getattr(location, 'longitude', None),
            location_name=getattr(location, 'name', '') or '',
            country_code=getattr(location, 'country_code', None),
        )
        country = getattr(location, 'country', '') or ''
        self._temperatures = {}
        self._current_temperature = (
            float(current_temperature)
            if isinstance(current_temperature, (int, float))
            and not isinstance(current_temperature, bool)
            else None
        )
        self._temperature_unit = temperature_unit
        self.border_title = f'Location Map — {country}' if country else 'Location Map'
        self.display = self._scope is not None
        self._sync_preferred_height()
        self.refresh(layout=True)

    @property
    def city_coordinates(self) -> tuple[PlaceKey, ...]:
        """Coordinates for the ranked city labels eligible for display."""
        if self._scope is None:
            return ()
        return tuple(_place_key(place) for place, _point in self._scope.places)

    def update_temperatures(
        self,
        temperatures: Mapping[PlaceKey, float],
        *,
        temperature_unit: str,
    ) -> None:
        """Apply non-blocking current-temperature enrichment to city labels."""
        self._temperatures = {
            key: float(value)
            for key, value in temperatures.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        self._temperature_unit = temperature_unit
        self.refresh()

    def clear(self) -> None:
        self._scope = None
        self._temperatures = {}
        self._current_temperature = None
        self._preferred_content_height = None
        self.display = False
        self.refresh(layout=True)

    def on_resize(self, event: Resize) -> None:
        del event
        self._sync_preferred_height()
        self.refresh()

    def _sync_preferred_height(self) -> None:
        if self._scope is None:
            return
        available_width = self.content_size.width
        if available_width <= 0:
            available_width = 96
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
        unit_symbol = '°F' if self._temperature_unit == 'fahrenheit' else '°C'
        location_label_style = None
        location_label = self._scope.location_name
        if self._current_temperature is not None:
            location_colour = temp_colour(
                self._current_temperature,
                scale='theme_temperature',
                hex=True,
                unit=self._temperature_unit,
                theme_colours=theme,
            )
            foreground = theme.get('background') or '#000000'
            location_label_style = f'bold {foreground} on {location_colour}'
            location_label = (
                f'{location_label} {round(self._current_temperature):.0f}{unit_symbol}'
            )
        temperature_labels = {}
        for key, temperature in self._temperatures.items():
            colour = temp_colour(
                temperature,
                scale='theme_temperature',
                hex=True,
                unit=self._temperature_unit,
                theme_colours=theme,
            )
            temperature_labels[key] = (
                f'{round(temperature):.0f}{unit_symbol}',
                f'bold {colour}',
            )
        return render_location_map(
            self._scope,
            width=max(12, self.content_size.width),
            height=max(5, self.content_size.height),
            palette=LocationMapPalette(
                land=f'dim {secondary}' if secondary else 'dim',
                place=theme.get('text-warning') or theme.get('text-primary'),
                location=theme.get('text-accent') or theme.get('text-success'),
                location_label=location_label_style,
            ),
            temperature_labels=temperature_labels,
            location_label=location_label,
        )


def _valid_coordinate(value: Any, *, latitude: bool) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    return -90.0 <= float(value) <= 90.0 if latitude else -360.0 <= float(value) <= 360.0


def _place_key(place: PopulatedPlace) -> PlaceKey:
    return place.latitude, place.longitude


def _normalized_place_name(name: str) -> str:
    return ' '.join(name.split()).casefold()


__all__ = [
    'LocationMap',
    'LocationMapGeometry',
    'LocationMapPalette',
    'build_location_map_geometry',
    'render_location_map',
]
