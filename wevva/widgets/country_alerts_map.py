"""Whole-country warning map with native ranked-city callouts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache

from rich.cells import cell_len
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.events import Click, Enter, Leave, Resize
from textual.message import Message
from textual.widgets import Static
from wevva_warnings import Alert

from wevva.geography import (
    GeographicViewport,
    MultiPolygon,
    PopulatedPlace,
    ProjectedPoint,
    detailed_world_populated_places,
    geojson_polygons,
    map_unit,
    point_in_polygon,
    polygon_points,
    project_visible_polygons,
    viewport_from_lonlat,
)
from wevva.services.country_alerts import country_alert_identity
from wevva.widgets.geographic_scope import (
    GeographicCanvas,
    GeographicFrame,
    ProjectedPolygon,
)
from wevva.widgets.map_callouts import (
    DirectionalCalloutCandidate,
    DirectionalCalloutPlacement,
    DirectionalCalloutPolicy,
    plan_directional_callouts,
)
from wevva.widgets.weather_alerts import (
    alert_severity_color,
    alert_severity_surface_color,
)


PlaceKey = tuple[float, float]
AlertKey = tuple[str, str]
RegionKey = tuple[str, str]

_VIEWPORT_PADDING = 0.02
_ALERT_VIEWPORT_PADDING = 0.05
_ALERT_VIEWPORT_MINIMUM_SPAN = 0.2
_MAX_CITY_CANDIDATES = 32
_MAX_CITY_LABELS = 8


@dataclass(frozen=True, slots=True)
class CountryAlertRegionAnnotation:
    """One Natural Earth Admin-1 label represented in the focused view."""

    key: RegionKey
    text: str
    point: ProjectedPoint


@dataclass(frozen=True, slots=True)
class CountryAlertsMapGeometry:
    """Projected active viewport and retained source geometry."""

    country_code: str
    viewport: GeographicViewport
    land: tuple[ProjectedPolygon, ...]
    places: tuple[tuple[PopulatedPlace, ProjectedPoint], ...]
    component_count: int
    country_polygons: MultiPolygon
    selected_alert_polygons: MultiPolygon = ()
    selected_alert_key: AlertKey | None = None
    region_annotations: tuple[CountryAlertRegionAnnotation, ...] = ()


@dataclass(frozen=True, slots=True)
class _CountryAlertsMapSource:
    country_code: str
    viewport: GeographicViewport
    polygons: MultiPolygon
    places: tuple[PopulatedPlace, ...]


@dataclass(frozen=True, slots=True)
class CountryAlertPolygonLayer:
    """One alert's provider-issued polygons projected into the country view."""

    key: AlertKey
    alert: Alert
    polygons: tuple[ProjectedPolygon, ...]


CountryAlertsMapPlacement = DirectionalCalloutPlacement[PlaceKey]


@lru_cache(maxsize=256)
def _country_alerts_map_source(
    country_code: str,
) -> _CountryAlertsMapSource | None:
    """Load reusable unprojected country geometry and settlement candidates."""

    normalized_country = country_code.strip().upper()
    unit = map_unit(normalized_country)
    if unit is None:
        return None
    points = tuple(polygon_points(unit.polygons))
    if not points:
        return None
    latitudes = [latitude for _longitude, latitude in points]
    origin_latitude = (min(latitudes) + max(latitudes)) / 2.0
    origin_longitude = _compact_longitude_origin(
        longitude for longitude, _latitude in points
    )
    viewport = viewport_from_lonlat(
        points,
        origin_latitude=origin_latitude,
        origin_longitude=origin_longitude,
        padding=_VIEWPORT_PADDING,
    )
    if viewport is None:
        return None

    all_places = detailed_world_populated_places()
    places = [
        place for place in all_places if place.country_code == normalized_country
    ]
    if not places:
        places = [
            place
            for place in all_places
            if any(
                point_in_polygon(place.longitude, place.latitude, polygon)
                for polygon in unit.polygons
            )
        ]
    places.sort(
        key=lambda place: (
            place.scale_rank,
            place.label_rank,
            -place.population,
            place.name.casefold(),
        )
    )
    return _CountryAlertsMapSource(
        country_code=normalized_country,
        viewport=viewport,
        polygons=unit.polygons,
        places=tuple(places),
    )


@lru_cache(maxsize=256)
def build_country_alerts_map_geometry(
    country_code: str,
) -> CountryAlertsMapGeometry | None:
    """Build the truthful whole-country fallback view."""

    source = _country_alerts_map_source(country_code)
    if source is None:
        return None
    return _build_country_alerts_map_view(source, None, ())


def build_country_alerts_map_view(
    country_code: str,
    alerts: Sequence[Alert],
    selected_alert_key: AlertKey | None,
) -> CountryAlertsMapGeometry | None:
    """Build a whole-country or selected-alert-focused geographic view."""

    source = _country_alerts_map_source(country_code)
    if source is None:
        return None
    selected_alert = next(
        (
            alert
            for alert in alerts
            if country_alert_identity(alert) == selected_alert_key
        ),
        None,
    )
    selected_polygons = (
        geojson_polygons(selected_alert.geometry)
        if selected_alert is not None
        else ()
    )
    return _build_country_alerts_map_view(
        source,
        selected_alert,
        selected_polygons,
    )


def _build_country_alerts_map_view(
    source: _CountryAlertsMapSource,
    selected_alert: Alert | None,
    selected_polygons: MultiPolygon,
) -> CountryAlertsMapGeometry:
    viewport = _alert_viewport(selected_polygons) or source.viewport
    focused = bool(selected_polygons)
    candidates = detailed_world_populated_places() if focused else source.places
    ranked_places: list[tuple[bool, PopulatedPlace, ProjectedPoint]] = []
    for place in candidates:
        projected = viewport.project(place.longitude, place.latitude)
        if not _point_in_viewport(projected, viewport):
            continue
        inside = any(
            point_in_polygon(place.longitude, place.latitude, polygon)
            for polygon in selected_polygons
        )
        ranked_places.append((inside, place, projected))
    ranked_places.sort(
        key=lambda candidate: (
            not candidate[0],
            candidate[1].scale_rank,
            candidate[1].label_rank,
            -candidate[1].population,
            candidate[1].name.casefold(),
        )
    )
    alert_key = (
        country_alert_identity(selected_alert)
        if selected_alert is not None and selected_polygons
        else None
    )
    return CountryAlertsMapGeometry(
        country_code=source.country_code,
        viewport=viewport,
        land=project_visible_polygons(source.polygons, viewport),
        places=tuple(
            (place, point)
            for _inside, place, point in ranked_places[:_MAX_CITY_CANDIDATES]
        ),
        component_count=len(source.polygons),
        country_polygons=source.polygons,
        selected_alert_polygons=selected_polygons,
        selected_alert_key=alert_key,
        region_annotations=(
            _region_annotations(ranked_places) if focused else ()
        ),
    )


def build_country_alert_polygon_layers(
    alerts: Sequence[Alert],
    viewport: GeographicViewport,
) -> tuple[CountryAlertPolygonLayer, ...]:
    """Project only real provider polygons, retaining alert identity."""

    layers: list[CountryAlertPolygonLayer] = []
    for alert in alerts:
        polygons = geojson_polygons(alert.geometry)
        if not polygons:
            continue
        projected = project_visible_polygons(polygons, viewport)
        if not projected:
            continue
        layers.append(
            CountryAlertPolygonLayer(
                key=country_alert_identity(alert),
                alert=alert,
                polygons=projected,
            )
        )
    return tuple(layers)


def render_country_alerts_map(
    scope: CountryAlertsMapGeometry,
    alert_layers: Sequence[CountryAlertPolygonLayer],
    *,
    width: int,
    height: int,
    land_style: str | None,
    alert_styles: Mapping[AlertKey, str | None],
    alert_land_styles: Mapping[AlertKey, str | None],
    selected_alert_key: AlertKey | None,
    preview_alert_key: AlertKey | None = None,
) -> Text:
    """Render warnings with distinct sea and true land-intersection styles."""

    return _country_alerts_map_frame(
        scope,
        alert_layers,
        width=width,
        height=height,
        land_style=land_style,
        alert_styles=alert_styles,
        alert_land_styles=alert_land_styles,
        selected_alert_key=selected_alert_key,
        preview_alert_key=preview_alert_key,
    ).to_text()


def _country_alerts_map_frame(
    scope: CountryAlertsMapGeometry,
    alert_layers: Sequence[CountryAlertPolygonLayer],
    *,
    width: int,
    height: int,
    land_style: str | None,
    alert_styles: Mapping[AlertKey, str | None],
    alert_land_styles: Mapping[AlertKey, str | None],
    selected_alert_key: AlertKey | None,
    preview_alert_key: AlertKey | None = None,
) -> GeographicFrame:
    """Build the rendered map while retaining its fitted placement canvas."""

    canvas = GeographicCanvas(max(1, width), max(1, height), scope.viewport)
    canvas.fill_polygons(scope.land, layer='land')
    emphasized_keys = {selected_alert_key, preview_alert_key} - {None}
    context = [layer for layer in alert_layers if layer.key not in emphasized_keys]
    selected = [
        layer
        for layer in alert_layers
        if layer.key == selected_alert_key and layer.key != preview_alert_key
    ]
    previewed = [layer for layer in alert_layers if layer.key == preview_alert_key]
    ordered_layers = [*context, *selected, *previewed]
    layers: list[tuple[str, str | None]] = [('land', land_style)]
    solid_layers = ['land']
    overlap_styles: dict[tuple[str, str], str | None] = {}
    seen_polygons: dict[str, set[ProjectedPolygon]] = {}
    previous_signature: tuple[str | None, bool, str | None] | None = None
    layer_name = ''
    for layer in ordered_layers:
        alert_style = alert_styles.get(layer.key)
        has_land_style = layer.key in alert_land_styles
        alert_land_style = alert_land_styles.get(layer.key)
        signature = (alert_style, has_land_style, alert_land_style)
        if signature != previous_signature:
            layer_name = f'alert-{len(solid_layers) - 1}'
            layers.append((layer_name, alert_style))
            if has_land_style:
                overlap_styles[(layer_name, 'land')] = alert_land_style
            solid_layers.append(layer_name)
            previous_signature = signature
        seen = seen_polygons.setdefault(layer_name, set())
        unique_polygons = [
            polygon for polygon in layer.polygons if polygon not in seen
        ]
        seen.update(unique_polygons)
        canvas.fill_polygons(unique_polygons, layer=layer_name)
    return canvas.frame(
        layers,
        solid_braille_layers=solid_layers,
        centering_layers=() if scope.selected_alert_polygons else ('land',),
        overlap_styles=overlap_styles,
    )


class CountryAlertRegionLabel(Static):
    """Passive Natural Earth Admin-1 context with no point marker."""

    DEFAULT_CSS = """
    CountryAlertRegionLabel {
        position: absolute;
        layer: labels;
        width: auto;
        height: 1;
        background: $background;
        color: $text-muted;
        text-style: italic;
        display: none;
    }
    """


class CountryAlertSettlementSelected(Message):
    """A focused-map settlement was activated for full weather navigation."""

    def __init__(self, *, place: PopulatedPlace) -> None:
        super().__init__()
        self.place = place


class CountryAlertSettlementPreviewRequested(Message):
    """A focused-map settlement needs compact current weather for its tooltip."""

    def __init__(self, *, label: CountryAlertCityLabel) -> None:
        super().__init__()
        self.label = label
        self.place = label.place


class CountryAlertSettlementPreviewCancelled(Message):
    """The pointer left a settlement before its preview was useful."""

    def __init__(self, *, label: CountryAlertCityLabel) -> None:
        super().__init__()
        self.label = label


class CountryAlertCityLabel(Static, can_focus=True):
    """Native directional callout for one Alerts Centre settlement."""

    BINDINGS = [
        Binding('enter', 'select_settlement', 'Weather', show=False),
        Binding('space', 'select_settlement', 'Weather', show=False),
    ]

    DEFAULT_CSS = """
    CountryAlertCityLabel {
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

    CountryAlertCityLabel:hover,
    CountryAlertCityLabel:focus {
        text-style: bold reverse;
    }
    """

    def __init__(self, place: PopulatedPlace) -> None:
        super().__init__('', markup=False)
        self.place = place
        self._body_text = place.name
        self._marker_on_right = False
        self.label_text = ''
        self.set_marker_on_right(False)
        self.reset_tooltip()

    def set_marker_on_right(self, marker_on_right: bool) -> None:
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
        self.action_select_settlement()

    def on_enter(self, event: Enter) -> None:
        if event.node is self:
            self.post_message(CountryAlertSettlementPreviewRequested(label=self))

    def on_leave(self, event: Leave) -> None:
        if event.node is self:
            self.post_message(CountryAlertSettlementPreviewCancelled(label=self))

    def reset_tooltip(self) -> None:
        """Restore the lightweight state shown before current weather arrives."""

        tooltip = Text()
        tooltip.append(self.place.name, style='bold')
        if self.place.region_name:
            tooltip.append(f', {self.place.region_name}', style='dim')
        tooltip.append('\nLoading current weather…', style='dim italic')
        tooltip.append('\nClick for full forecast', style='dim')
        self.tooltip = tooltip

    def action_select_settlement(self) -> None:
        """Request the complete weather view for this settlement."""

        self.post_message(CountryAlertSettlementSelected(place=self.place))

class CountryAlertsMap(Container):
    """Whole-country Braille backdrop with a small set of city labels."""

    DEFAULT_CSS = """
    CountryAlertsMap {
        layers: map labels;
        width: 100%;
        height: 100%;
        min-width: 18;
        min-height: 8;
        padding: 0;
        border: round $primary;
        border-title-color: $primary;
        border-title-align: left;
        background: $background;
        overflow: hidden hidden;
    }

    #country-alerts-map-backdrop {
        position: absolute;
        layer: map;
        offset: 0 0;
        width: 100%;
        height: 100%;
        background: $background;
        content-align: center middle;
        color: $text-muted;
        text-align: center;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.border_title = 'Map of Alerts'
        self._country_code = ''
        self._country_name = ''
        self._alerts: tuple[Alert, ...] = ()
        self._scope: CountryAlertsMapGeometry | None = None
        self._alert_layers: tuple[CountryAlertPolygonLayer, ...] = ()
        self._selected_alert_key: AlertKey | None = None
        self._preview_alert_key: AlertKey | None = None
        self._labels: dict[PlaceKey, CountryAlertCityLabel] = {}
        self._region_labels: dict[RegionKey, CountryAlertRegionLabel] = {}
        self._placements: dict[PlaceKey, CountryAlertsMapPlacement] = {}
        self._max_city_labels = _MAX_CITY_LABELS
        self._reflow_pending = False

    def compose(self) -> ComposeResult:
        yield Static('Select a country to show its warning map.', id='country-alerts-map-backdrop')

    @property
    def geometry(self) -> CountryAlertsMapGeometry | None:
        return self._scope

    @property
    def alert_layers(self) -> tuple[CountryAlertPolygonLayer, ...]:
        return self._alert_layers

    @property
    def placements(self) -> tuple[CountryAlertsMapPlacement, ...]:
        return tuple(self._placements.values())

    @property
    def max_city_labels(self) -> int:
        return self._max_city_labels

    def set_max_city_labels(self, count: int) -> None:
        """Limit visible city callouts without changing fetched city data."""

        maximum = max(0, int(count))
        if maximum == self._max_city_labels:
            return
        self._max_city_labels = maximum
        self._schedule_reflow()

    def update_country(
        self,
        country_code: str,
        country_name: str,
        alerts: Sequence[Alert],
        *,
        selected_alert_key: AlertKey | None = None,
    ) -> None:
        """Install one country result while retaining reusable city widgets."""

        normalized_country = country_code.strip().upper()
        self._country_code = normalized_country
        self._country_name = country_name.strip() or normalized_country
        self._alerts = tuple(alerts)
        self._selected_alert_key = selected_alert_key
        self._preview_alert_key = None
        self._rebuild_view()
        self.border_title = f'Map of Alerts for {self._country_name}'
        if self.is_mounted:
            self._sync_label_widgets()
        self.refresh()
        self._schedule_reflow()

    def update_selected_alert(self, alert_key: AlertKey | None) -> None:
        """Fit the map to selected provider geometry, or restore the country."""

        if alert_key == self._selected_alert_key:
            return
        self._selected_alert_key = alert_key
        self._rebuild_view()
        if self.is_mounted:
            self._sync_label_widgets()
        self.refresh()
        self._schedule_reflow()

    def update_preview_alert(self, alert_key: AlertKey | None) -> None:
        """Emphasize a row's polygon without changing selection or viewport."""

        if alert_key == self._preview_alert_key:
            return
        self._preview_alert_key = alert_key
        self._schedule_reflow()

    def refresh_theme(self) -> None:
        """Reapply theme-derived map and polygon colours in place."""

        self._schedule_reflow()

    def reset_city_tooltips(self) -> None:
        """Discard rendered previews after unit or theme changes."""

        for label in self._labels.values():
            label.reset_tooltip()

    def clear(self, *, country_name: str = '') -> None:
        self._country_code = ''
        self._country_name = country_name
        self._alerts = ()
        self._scope = None
        self._alert_layers = ()
        self._selected_alert_key = None
        self._preview_alert_key = None
        self._placements = {}
        self.border_title = (
            f'Map of Alerts for {country_name}' if country_name else 'Map of Alerts'
        )
        if self.is_mounted:
            self._sync_label_widgets()
            self.query_one('#country-alerts-map-backdrop', Static).update(
                'Country map unavailable.' if country_name else 'Select a country to show its warning map.'
            )
        self.refresh()

    def on_mount(self) -> None:
        self._sync_label_widgets()
        self._schedule_reflow()

    def on_resize(self, event: Resize) -> None:
        del event
        self._schedule_reflow()

    def _sync_label_widgets(self) -> None:
        specs = self._scope.places if self._scope is not None else ()
        region_specs = self._scope.region_annotations if self._scope is not None else ()
        region_by_key = {annotation.key: annotation for annotation in region_specs}
        for key in tuple(self._region_labels):
            if key not in region_by_key:
                self._region_labels.pop(key).remove()
        for annotation in region_specs:
            label = self._region_labels.get(annotation.key)
            if label is None:
                label = CountryAlertRegionLabel(annotation.text, markup=False)
                self._region_labels[annotation.key] = label
                self.mount(label)
            else:
                label.update(annotation.text)

        place_by_key = {_place_key(place): place for place, _point in specs}
        for key in tuple(self._labels):
            if key not in place_by_key:
                self._labels.pop(key).remove()

        for place, _point in specs:
            key = _place_key(place)
            label = self._labels.get(key)
            if label is None:
                label = CountryAlertCityLabel(place)
                self._labels[key] = label
                self.mount(label)

    def _rebuild_view(self) -> None:
        self._scope = build_country_alerts_map_view(
            self._country_code,
            self._alerts,
            self._selected_alert_key,
        )
        self._alert_layers = (
            build_country_alert_polygon_layers(self._alerts, self._scope.viewport)
            if self._scope is not None
            else ()
        )

    def _schedule_reflow(self) -> None:
        if not self.is_mounted or self._reflow_pending:
            return
        self._reflow_pending = True
        self.call_after_refresh(self._reflow)

    def _reflow(self) -> None:
        self._reflow_pending = False
        width = self.content_size.width
        height = self.content_size.height
        if width < 1 or height < 1 or not self.is_mounted:
            return
        backdrop = self.query_one('#country-alerts-map-backdrop', Static)
        if self._scope is None:
            backdrop.update(
                (
                    f'Country map unavailable for {self._country_name}.'
                    if self._country_name
                    else 'Select a country to show its warning map.'
                )
            )
            self._placements = {}
            return

        theme = self.app.theme_variables
        secondary = theme.get('text-secondary')
        alert_styles: dict[AlertKey, str | None] = {}
        alert_land_styles: dict[AlertKey, str | None] = {}
        for layer in self._alert_layers:
            colour = alert_severity_color(theme, layer.alert) or theme.get('text-accent')
            land_colour = (
                alert_severity_surface_color(theme, layer.alert)
                or theme.get('accent')
                or colour
            )
            emphasized = layer.key in {
                self._selected_alert_key,
                self._preview_alert_key,
            }
            alert_styles[layer.key] = (
                colour
                if emphasized
                else f'dim {colour}' if colour else 'dim'
            )
            alert_land_styles[layer.key] = (
                land_colour
                if emphasized
                else f'dim {land_colour}' if land_colour else 'dim'
            )
        frame = _country_alerts_map_frame(
            self._scope,
            self._alert_layers,
            width=width,
            height=height,
            land_style=f'dim {secondary}' if secondary else 'dim',
            alert_styles=alert_styles,
            alert_land_styles=alert_land_styles,
            selected_alert_key=self._selected_alert_key,
            preview_alert_key=self._preview_alert_key,
        )
        backdrop.update(
            frame.to_text(),
            layout=False,
        )

        canvas = frame.canvas
        occupied: set[tuple[int, int]] = set()
        for annotation in self._scope.region_annotations:
            label = self._region_labels.get(annotation.key)
            if label is None:
                continue
            column, row = _plain_label_placement(
                anchor=canvas.cell_position(annotation.point),
                label_width=cell_len(annotation.text),
                canvas_width=width,
                canvas_height=height,
                occupied=occupied,
            )
            label.styles.offset = (column, row)
            label.display = True
        city_limit = country_alert_city_label_budget(
            width,
            height,
            maximum=self._max_city_labels,
        )
        candidates = []
        for place, point in self._scope.places:
            key = _place_key(place)
            label = self._labels.get(key)
            if label is None:
                continue
            candidates.append(
                DirectionalCalloutCandidate(
                    key=key,
                    anchor=canvas.cell_position(point),
                    width=cell_len(label.label_text),
                )
            )
        planned = plan_directional_callouts(
            candidates,
            canvas_width=width,
            canvas_height=height,
            occupied=occupied,
            policy=DirectionalCalloutPolicy(allow_row_shift=False),
        )[:city_limit]
        placements = {placement.key: placement for placement in planned}
        for label in self._labels.values():
            label.display = False
        for key, placement in placements.items():
            label = self._labels[key]
            label.set_marker_on_right(placement.marker_on_right)
            label.display = True
            label.styles.offset = (placement.column, placement.row)
        self._placements = placements


def country_alert_city_label_budget(
    width: int,
    height: int,
    *,
    maximum: int = _MAX_CITY_LABELS,
) -> int:
    """Return a sparse collision budget scaled to the live map dimensions."""

    if width < 1 or height < 1 or maximum < 1:
        return 0
    return min(maximum, max(1, min(width // 12, height // 3)))


def _alert_viewport(polygons: MultiPolygon) -> GeographicViewport | None:
    points = tuple(polygon_points(polygons))
    if not points:
        return None
    latitudes = [latitude for _longitude, latitude in points]
    return viewport_from_lonlat(
        points,
        origin_latitude=(min(latitudes) + max(latitudes)) / 2.0,
        origin_longitude=_compact_longitude_origin(
            longitude for longitude, _latitude in points
        ),
        padding=_ALERT_VIEWPORT_PADDING,
        minimum_span=_ALERT_VIEWPORT_MINIMUM_SPAN,
    )


def _point_in_viewport(
    point: ProjectedPoint,
    viewport: GeographicViewport,
) -> bool:
    return (
        viewport.min_x <= point.x <= viewport.max_x
        and viewport.min_y <= point.y <= viewport.max_y
    )


def _region_annotations(
    places: Sequence[tuple[bool, PopulatedPlace, ProjectedPoint]],
) -> tuple[CountryAlertRegionAnnotation, ...]:
    grouped: dict[RegionKey, list[ProjectedPoint]] = {}
    display_names: dict[RegionKey, str] = {}
    for _inside, place, point in places:
        name = ' '.join(place.region_name.split())
        if not name:
            continue
        key = (place.country_code, name.casefold())
        grouped.setdefault(key, []).append(point)
        display_names.setdefault(key, name)
    return tuple(
        CountryAlertRegionAnnotation(
            key=key,
            text=display_names[key],
            point=ProjectedPoint(
                sum(point.x for point in points) / len(points),
                sum(point.y for point in points) / len(points),
            ),
        )
        for key, points in sorted(
            grouped.items(),
            key=lambda item: (item[0][0], item[0][1]),
        )
    )


def _plain_label_placement(
    *,
    anchor: tuple[int, int],
    label_width: int,
    canvas_width: int,
    canvas_height: int,
    occupied: set[tuple[int, int]],
) -> tuple[int, int]:
    label_width = min(max(1, label_width), canvas_width)
    anchor_column, anchor_row = anchor
    preferred_column = min(
        max(0, anchor_column - label_width // 2),
        canvas_width - label_width,
    )
    row_offsets = [0]
    for distance in range(1, canvas_height):
        row_offsets.extend((-distance, distance))
    for row_offset in row_offsets:
        row = anchor_row + row_offset
        if not 0 <= row < canvas_height:
            continue
        cells = {
            (preferred_column + offset, row)
            for offset in range(label_width)
        }
        if cells & occupied:
            continue
        occupied.update(cells)
        return preferred_column, row
    # Preserve every contextual region label even in a pathologically dense
    # viewport; overlap is preferable to silently losing administrative context.
    return preferred_column, min(max(0, anchor_row), canvas_height - 1)


def _compact_longitude_origin(longitudes: Iterable[float]) -> float:
    """Return the centre of the smallest circular arc containing longitudes."""

    values = sorted(float(value) % 360.0 for value in longitudes)
    if not values:
        return 0.0
    if len(values) == 1:
        centre = values[0]
    else:
        gaps = [
            ((values[(index + 1) % len(values)] - value) % 360.0, index)
            for index, value in enumerate(values)
        ]
        largest_gap, gap_index = max(gaps)
        occupied_start = values[(gap_index + 1) % len(values)]
        centre = (occupied_start + (360.0 - largest_gap) / 2.0) % 360.0
    return centre - 360.0 if centre > 180.0 else centre


def _place_key(place: PopulatedPlace) -> PlaceKey:
    return place.latitude, place.longitude


__all__ = [
    'CountryAlertRegionAnnotation',
    'CountryAlertRegionLabel',
    'CountryAlertCityLabel',
    'CountryAlertSettlementPreviewCancelled',
    'CountryAlertSettlementPreviewRequested',
    'CountryAlertSettlementSelected',
    'CountryAlertPolygonLayer',
    'CountryAlertsMap',
    'CountryAlertsMapGeometry',
    'CountryAlertsMapPlacement',
    'build_country_alert_polygon_layers',
    'build_country_alerts_map_geometry',
    'build_country_alerts_map_view',
    'country_alert_city_label_budget',
    'render_country_alerts_map',
]
