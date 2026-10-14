"""Country-scale map for the currently selected forecast location."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from rich.cells import cell_len
from rich.text import Text
from textual.binding import Binding
from textual.containers import Container
from textual.events import Click, Resize
from textual.widgets import Static

from wevva.location_metadata import LocationMetadata
from wevva.messages import PlaceSelected
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
from wevva.widgets.map_callouts import place_directional_callout

_MIN_CONTENT_HEIGHT = 12
_MAX_CONTENT_HEIGHT = 26
_BORDER_ROWS = 2
_DEFAULT_CONTENT_WIDTH = 96
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


@dataclass(frozen=True, slots=True)
class LocationMapPlacement:
    """One collision-free terminal placement for a map callout."""

    key: str
    column: int
    row: int
    width: int
    marker_on_right: bool


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
    max_place_labels: int = _MAX_PLACE_LABELS,
) -> Text:
    """Render country land, major-city labels, and the current location."""
    canvas = GeographicCanvas(max(12, width), max(5, height), scope.viewport)
    canvas.fill_polygons(scope.land, layer='land')
    frame = canvas.frame((('land', palette.land),), solid_braille_layers=('land',))

    location_style = palette.location_label or palette.location
    location_cell = frame.marker(scope.location, '•', location_style)
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
        if labels_added >= max(0, int(max_place_labels)):
            break
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
    return frame.to_text()


class LocationMapLabel(Static, can_focus=True):
    """Native Textual callout for the current location or a nearby city."""

    BINDINGS = [
        Binding('enter', 'select_location', 'Open', show=False),
        Binding('space', 'select_location', 'Open', show=False),
    ]

    DEFAULT_CSS = """
    LocationMapLabel {
        position: absolute;
        layer: labels;
        width: auto;
        min-width: 1;
        height: 1;
        background: $background;
        text-style: bold;
        pointer: pointer;
    }

    LocationMapLabel.current-location,
    LocationMapLabel:hover,
    LocationMapLabel:focus {
        text-style: bold reverse;
    }
    """

    def __init__(
        self,
        location: LocationMetadata,
        *,
        current: bool = False,
    ) -> None:
        super().__init__('', markup=False)
        self.location = location
        self.current = current
        self._body_text = ''
        self._marker_on_right = False
        self.label_text = ''
        self.set_class(current, 'current-location')

    def update_label(
        self,
        location: LocationMetadata,
        *,
        reading: str | None,
        colour: str | None,
        current: bool,
    ) -> None:
        """Update content without replacing the interactive widget."""

        self.location = location
        self.current = current
        self.set_class(current, 'current-location')
        self._body_text = location.name
        if reading:
            self._body_text = f'{self._body_text} {reading}'
        self.set_marker_on_right(self._marker_on_right)
        if colour:
            self.styles.color = colour

    def set_marker_on_right(self, marker_on_right: bool) -> None:
        """Keep the marker at the geographic end of the callout."""

        self._marker_on_right = marker_on_right
        self.label_text = (
            f'{self._body_text} •'
            if marker_on_right
            else f'• {self._body_text}'
        )
        self.update(self.label_text)

    def on_click(self, event: Click) -> None:
        event.stop()
        self.focus()
        self.action_select_location()

    def action_select_location(self) -> None:
        """Open the ordinary forecast for this callout."""

        self.post_message(PlaceSelected(location=self.location))


class LocationMap(Container):
    """Prominent country map shown with the primary weather instruments."""

    DEFAULT_CSS = """
    LocationMap {
        layers: map labels;
        width: 98;
        height: 20;
        margin: 0 0 1 0;
        padding: 0;
        background: $background;
        border: round $primary;
        border-title-color: $primary;
        border-title-align: left;
        overflow: hidden hidden;
    }
    """

    def __init__(self, *, id: str = 'location-map') -> None:
        super().__init__(id=id)
        self.border_title = 'Location Map'
        self._scope: LocationMapGeometry | None = None
        self._temperatures: dict[PlaceKey, float] = {}
        self._temperature_unit = 'celsius'
        self._current_temperature: float | None = None
        self._preferred_content_height: int | None = None
        self._layout_height: int | None = None
        self._max_place_labels = _MAX_PLACE_LABELS
        self._country = ''
        self._country_code = ''
        self._current_location: LocationMetadata | None = None
        self._labels: dict[str, LocationMapLabel] = {}
        self._placements: dict[str, LocationMapPlacement] = {}
        self._reflow_pending = False
        self.display = False

    @property
    def available(self) -> bool:
        """Whether a country component is available for display."""

        return self._scope is not None

    @property
    def placements(self) -> tuple[LocationMapPlacement, ...]:
        """Current visible callout placements, primarily for inspection/tests."""

        return tuple(self._placements.values())

    def set_layout_height(
        self,
        height: int | None,
        *,
        max_place_labels: int | None = None,
    ) -> None:
        """Set responsive height and the number of city labels to render."""

        self._layout_height = None if height is None else max(5, int(height))
        self._max_place_labels = (
            _MAX_PLACE_LABELS
            if max_place_labels is None
            else max(0, int(max_place_labels))
        )
        self._sync_preferred_height()
        self._schedule_reflow()

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
        country_code = getattr(location, 'country_code', '') or ''
        self._country = country
        self._country_code = country_code
        self._current_location = (
            LocationMetadata(
                latitude=float(getattr(location, 'latitude')),
                longitude=float(getattr(location, 'longitude')),
                name=(getattr(location, 'name', '') or '').strip() or 'Current location',
                admin=getattr(location, 'admin', '') or '',
                country=country,
                country_code=country_code,
                timezone=getattr(location, 'timezone', '') or '',
                timezone_abbreviation=(
                    getattr(location, 'timezone_abbreviation', '') or ''
                ),
            )
            if self._scope is not None
            else None
        )
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
        if self.is_mounted:
            self._sync_label_widgets()
        self._sync_preferred_height()
        self.refresh(layout=True)
        self._schedule_reflow()

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
        if self.is_mounted:
            self._sync_label_widgets()
        self.refresh()
        self._schedule_reflow()

    def clear(self) -> None:
        self._scope = None
        self._temperatures = {}
        self._current_temperature = None
        self._preferred_content_height = None
        self._current_location = None
        self._placements = {}
        if self.is_mounted:
            self._sync_label_widgets()
        self.display = False
        self.refresh(layout=True)

    def on_resize(self, event: Resize) -> None:
        del event
        self._sync_preferred_height()
        self.refresh()
        self._schedule_reflow()

    def on_mount(self) -> None:
        self._sync_label_widgets()
        self._schedule_reflow()

    def _sync_preferred_height(self) -> None:
        if self._scope is None:
            return
        if self._layout_height is not None:
            content_height = max(5, self._layout_height - _BORDER_ROWS)
            self._preferred_content_height = content_height
            self.styles.height = self._layout_height
            self.refresh(layout=True)
            self._schedule_reflow()
            return
        available_width = self._render_width()
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

    def render(self) -> Text:
        if self._scope is None:
            return Text()
        theme = self.app.theme_variables
        secondary = theme.get('text-secondary')
        canvas = GeographicCanvas(
            self._render_width(),
            max(5, self.content_size.height),
            self._scope.viewport,
        )
        canvas.fill_polygons(self._scope.land, layer='land')
        return canvas.frame(
            (('land', f'dim {secondary}' if secondary else 'dim'),),
            solid_braille_layers=('land',),
        ).to_text()

    def _schedule_reflow(self) -> None:
        if not self.is_mounted or self._reflow_pending:
            return
        self._reflow_pending = True
        self.call_after_refresh(self._reflow)

    def _sync_label_widgets(self) -> None:
        specs = self._label_specs()
        keys = {key for key, _location, _point, _current in specs}
        for key in tuple(self._labels):
            if key not in keys:
                self._labels.pop(key).remove()

        theme = self.app.theme_variables
        unit_symbol = '°F' if self._temperature_unit == 'fahrenheit' else '°C'
        for key, location, _point, current in specs:
            label = self._labels.get(key)
            if label is None:
                label = LocationMapLabel(location, current=current)
                self._labels[key] = label
                self.mount(label)
            temperature = (
                self._current_temperature
                if current
                else self._temperatures.get((location.latitude, location.longitude))
            )
            if temperature is not None:
                reading = f'{round(temperature):.0f}{unit_symbol}'
                colour = temp_colour(
                    temperature,
                    scale='theme_temperature',
                    hex=True,
                    unit=self._temperature_unit,
                    theme_colours=theme,
                )
            else:
                reading = None
                colour = (
                    theme.get('text-accent') or theme.get('text-success')
                    if current
                    else theme.get('text-warning') or theme.get('text-primary')
                )
            label.update_label(
                location,
                reading=reading,
                colour=colour,
                current=current,
            )

    def _label_specs(
        self,
    ) -> list[tuple[str, LocationMetadata, ProjectedPoint, bool]]:
        if self._scope is None or self._current_location is None:
            return []
        specs = [('current', self._current_location, self._scope.location, True)]
        for place, point in self._scope.places:
            key = _label_key(place)
            specs.append(
                (
                    key,
                    LocationMetadata(
                        latitude=place.latitude,
                        longitude=place.longitude,
                        name=place.name,
                        country=self._country,
                        country_code=self._country_code,
                    ),
                    point,
                    False,
                )
            )
        return specs

    def _reflow(self) -> None:
        self._reflow_pending = False
        if self._scope is None or not self.is_mounted:
            return
        width = self.content_size.width
        height = self.content_size.height
        if width < 1 or height < 1:
            return

        canvas = GeographicCanvas(width, height, self._scope.viewport)
        occupied: set[tuple[int, int]] = set()
        placements: dict[str, LocationMapPlacement] = {}
        city_labels = 0
        for key, _location, point, current in self._label_specs():
            label = self._labels.get(key)
            if label is None:
                continue
            if not current and city_labels >= self._max_place_labels:
                label.display = False
                continue
            placement = _place_callout(
                key,
                anchor=canvas.cell_position(point),
                label_width=cell_len(label.label_text),
                canvas_width=width,
                canvas_height=height,
                occupied=occupied,
            )
            if placement is None:
                label.display = False
                continue
            label.set_marker_on_right(placement.marker_on_right)
            label.display = True
            label.styles.offset = (placement.column, placement.row)
            placements[key] = placement
            if not current:
                city_labels += 1
        self._placements = placements

    def _render_width(self) -> int:
        """Return a useful width even while a responsive parent is hidden.

        Textual gives descendants of a hidden container a minimal placeholder
        region. The map is still rendered while its city temperatures load, so
        use its normal content width until the parent participates in layout.
        """

        ancestor = self.parent
        while ancestor is not None:
            if getattr(ancestor, 'display', True) is False:
                return _DEFAULT_CONTENT_WIDTH
            ancestor = ancestor.parent
        return max(12, self.content_size.width)


def _valid_coordinate(value: Any, *, latitude: bool) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    return -90.0 <= float(value) <= 90.0 if latitude else -360.0 <= float(value) <= 360.0


def _place_key(place: PopulatedPlace) -> PlaceKey:
    return place.latitude, place.longitude


def _label_key(place: PopulatedPlace) -> str:
    return f'{place.latitude:.6f},{place.longitude:.6f}'


def _place_callout(
    key: str,
    *,
    anchor: tuple[int, int],
    label_width: int,
    canvas_width: int,
    canvas_height: int,
    occupied: set[tuple[int, int]],
) -> LocationMapPlacement | None:
    """Place one native callout near its projected city cell."""
    placement = place_directional_callout(
        anchor=anchor,
        label_width=label_width,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        occupied=occupied,
    )
    if placement is None:
        return None
    return LocationMapPlacement(
        key=key,
        column=placement.column,
        row=placement.row,
        width=placement.width,
        marker_on_right=placement.marker_on_right,
    )


def _normalized_place_name(name: str) -> str:
    return ' '.join(name.split()).casefold()


__all__ = [
    'LocationMap',
    'LocationMapGeometry',
    'LocationMapLabel',
    'LocationMapPalette',
    'LocationMapPlacement',
    'build_location_map_geometry',
    'render_location_map',
]
