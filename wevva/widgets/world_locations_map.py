"""Interactive full-world map of saved weather locations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import lru_cache
import math

from rich.cells import cell_len
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.events import Click, Resize
from textual.widgets import Static

from wevva.config import location_key, location_label
from wevva.geography import (
    GeographicViewport,
    project_visible_polygons,
    world_map_unit_polygons,
)
from wevva.location_metadata import LocationMetadata
from wevva.messages import SavedLocationSelected
from wevva.utils import temp_colour
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
from wevva.widgets.saved_locations import SavedLocationWeatherSummary


_WORLD_VIEWPORT = GeographicViewport(
    origin_latitude=0.0,
    origin_longitude=0.0,
    min_x=-180.0,
    # Retain the Antarctic coast and McMurdo latitude, but do not spend scarce
    # terminal rows drawing the uninhabited southern cap to the pole.
    min_y=-78.0,
    max_x=180.0,
    max_y=90.0,
)


WorldLocationPlacement = DirectionalCalloutPlacement[str]


class WorldLocationLabel(Static, can_focus=True):
    """Native Textual callout for one location on the world map."""

    BINDINGS = [
        Binding('enter', 'select_location', 'Open', show=False),
        Binding('space', 'select_location', 'Open', show=False),
    ]

    DEFAULT_CSS = """
    WorldLocationLabel {
        position: absolute;
        layer: labels;
        width: auto;
        height: 1;
        min-width: 1;
        background: $background;
        text-style: bold;
        pointer: pointer;
    }

    WorldLocationLabel:hover,
    WorldLocationLabel:focus {
        text-style: bold reverse;
    }
    """

    def __init__(self, location: LocationMetadata) -> None:
        super().__init__('', markup=False)
        self.location = location
        self._body_text = ''
        self._marker_on_right = False
        self.label_text = ''

    def update_weather(
        self,
        summary: SavedLocationWeatherSummary | None,
        *,
        temperature_unit: str,
    ) -> None:
        """Update the callout text and semantic temperature colour."""

        name = self.location.name.strip() or location_label(self.location)
        temperature = None if summary is None or summary.error else summary.temperature
        if isinstance(temperature, (int, float)) and not isinstance(temperature, bool):
            unit = (summary.temperature_unit or '').strip()
            if not unit:
                unit = '°F' if temperature_unit == 'fahrenheit' else '°C'
            reading = f'{round(temperature):.0f}{unit}'
            colour = temp_colour(
                temperature,
                scale='theme_temperature',
                hex=True,
                unit=temperature_unit,
                theme_colours=self.app.theme_variables,
            )
        else:
            reading = '--'
            colour = self.app.theme_variables.get('text-secondary')

        self._body_text = f'{name} {reading}'
        self.set_marker_on_right(self._marker_on_right)
        if colour:
            self.styles.color = colour

    def set_marker_on_right(self, marker_on_right: bool) -> None:
        """Keep the marker at the geographic end of the callout."""

        self._marker_on_right = marker_on_right
        label_text = (
            f'{self._body_text} •'
            if marker_on_right
            else f'• {self._body_text}'
        )
        if label_text != self.label_text:
            self.label_text = label_text
            self.update(label_text)

    def on_click(self, event: Click) -> None:
        event.stop()
        self.focus()
        self.action_select_location()

    def action_select_location(self) -> None:
        """Open the forecast represented by this callout."""

        self.post_message(SavedLocationSelected(location=self.location))


class WorldLocationsMap(Container):
    """Braille world backdrop with native interactive location callouts."""

    DEFAULT_CSS = """
    WorldLocationsMap {
        layers: map labels;
        width: 100%;
        height: 100%;
        min-width: 20;
        min-height: 8;
        padding: 0;
        border: round $primary;
        border-title-color: $primary;
        border-title-align: left;
        background: $background;
        overflow: hidden hidden;
    }

    #world-locations-backdrop {
        position: absolute;
        layer: map;
        offset: 0 0;
        width: 100%;
        height: 100%;
        background: $background;
    }
    """

    def __init__(
        self,
        locations: Sequence[LocationMetadata] = (),
        *,
        summaries: Mapping[str, SavedLocationWeatherSummary] | None = None,
        temperature_unit: str = 'celsius',
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self.border_title = 'Saved Locations — World'
        self._locations = list(locations)
        self._summaries = dict(summaries or {})
        self._temperature_unit = temperature_unit
        self._labels: dict[str, WorldLocationLabel] = {}
        self._placements: dict[str, WorldLocationPlacement] = {}
        self._backdrop_key: tuple[int, int, str | None] | None = None
        self._reflow_pending = False

    def compose(self) -> ComposeResult:
        yield Static('', id='world-locations-backdrop')

    @property
    def placements(self) -> tuple[WorldLocationPlacement, ...]:
        """Current visible callout placements, primarily for inspection/tests."""

        return tuple(self._placements.values())

    def update_weather_summary(
        self,
        location: LocationMetadata,
        summary: SavedLocationWeatherSummary,
    ) -> None:
        """Update one existing callout without rebuilding the map surface."""

        key = location_key(location)
        self._summaries[key] = summary
        label = self._labels.get(key)
        if label is not None:
            label.update_weather(summary, temperature_unit=self._temperature_unit)
            self._schedule_reflow()

    def set_temperature_unit(self, temperature_unit: str) -> None:
        """Recolour every callout for a changed temperature unit."""

        if temperature_unit == self._temperature_unit:
            return
        self._temperature_unit = temperature_unit
        for key, label in self._labels.items():
            label.update_weather(
                self._summaries.get(key),
                temperature_unit=temperature_unit,
            )
        self._schedule_reflow()

    def focus_location(self, location: LocationMetadata | None) -> bool:
        """Focus a visible callout for ``location`` when one exists."""

        if location is None:
            return False
        label = self._labels.get(location_key(location))
        if label is None or not label.display:
            return False
        label.focus()
        return True

    def focus_relative(self, direction: int) -> bool:
        """Move focus through visible callouts in stable location order."""

        visible: list[WorldLocationLabel] = []
        visited: set[str] = set()
        for location in self._locations:
            key = location_key(location)
            if key in visited:
                continue
            visited.add(key)
            label = self._labels.get(key)
            if label is not None and label.display:
                visible.append(label)
        if not visible:
            return False

        focused = self.app.focused
        if focused in visible:
            index = visible.index(focused)
            target = visible[(index + (1 if direction >= 0 else -1)) % len(visible)]
        else:
            target = visible[0 if direction >= 0 else -1]
        target.focus()
        return True

    def on_mount(self) -> None:
        self._sync_label_widgets()
        self._schedule_reflow()

    def on_resize(self, event: Resize) -> None:
        del event
        self._schedule_reflow()

    def _schedule_reflow(self) -> None:
        if self._reflow_pending:
            return
        self._reflow_pending = True
        self.call_after_refresh(self._reflow)

    def _sync_label_widgets(self) -> None:
        locations = {
            location_key(location): location
            for location in self._locations
            if _valid_location(location)
        }
        for key in tuple(self._labels):
            if key not in locations:
                self._labels.pop(key).remove()

        for key, location in locations.items():
            label = self._labels.get(key)
            if label is None:
                label = WorldLocationLabel(location)
                self._labels[key] = label
                self.mount(label)
            else:
                label.location = location
            label.update_weather(
                self._summaries.get(key),
                temperature_unit=self._temperature_unit,
            )

    def _reflow(self) -> None:
        self._reflow_pending = False
        width = self.content_size.width
        height = self.content_size.height
        if width < 1 or height < 1 or not self.is_mounted:
            return

        theme = self.app.theme_variables
        secondary = theme.get('text-secondary')
        land_style = f'dim {secondary}' if secondary else 'dim'
        frame = _world_frame(
            width,
            height,
            land_style=land_style,
        )
        backdrop_key = (width, height, land_style)
        if backdrop_key != self._backdrop_key:
            self.query_one('#world-locations-backdrop', Static).update(
                frame.to_text(),
                layout=False,
            )
            self._backdrop_key = backdrop_key

        visited: set[str] = set()
        candidates = []
        for location in self._locations:
            key = location_key(location)
            if key in visited:
                continue
            visited.add(key)
            label = self._labels.get(key)
            if label is None:
                continue
            point = frame.canvas.viewport.project(
                float(location.longitude),
                float(location.latitude),
            )
            candidates.append(
                DirectionalCalloutCandidate(
                    key=key,
                    anchor=frame.canvas.cell_position(point),
                    width=cell_len(label.label_text),
                )
            )
        planned = plan_directional_callouts(
            candidates,
            canvas_width=width,
            canvas_height=height,
            policy=DirectionalCalloutPolicy(allow_row_shift=False),
        )
        placements = {placement.key: placement for placement in planned}
        for key, placement in placements.items():
            label = self._labels[key]
            label.set_marker_on_right(placement.marker_on_right)
            label.display = True
            label.styles.offset = (placement.column, placement.row)
        for key, label in self._labels.items():
            if key not in placements:
                label.display = False
        self._placements = placements


@lru_cache(maxsize=1)
def _projected_world_land() -> tuple[ProjectedPolygon, ...]:
    return project_visible_polygons(world_map_unit_polygons(), _WORLD_VIEWPORT)


# Callers treat the returned frame as immutable; four entries cover the audit's
# complete resize matrix without retaining an unbounded set of raster canvases.
@lru_cache(maxsize=4)
def _world_frame(width: int, height: int, *, land_style: str | None) -> GeographicFrame:
    canvas = GeographicCanvas(max(1, width), max(1, height), _WORLD_VIEWPORT)
    canvas.fill_polygons(_projected_world_land(), layer='land')
    return canvas.frame(
        (('land', land_style),),
        solid_braille_layers=('land',),
    )


def _valid_location(location: LocationMetadata) -> bool:
    latitude = location.latitude
    longitude = location.longitude
    return (
        isinstance(latitude, (int, float))
        and not isinstance(latitude, bool)
        and math.isfinite(latitude)
        and -90.0 <= latitude <= 90.0
        and isinstance(longitude, (int, float))
        and not isinstance(longitude, bool)
        and math.isfinite(longitude)
        and -360.0 <= longitude <= 360.0
    )


__all__ = [
    'WorldLocationLabel',
    'WorldLocationPlacement',
    'WorldLocationsMap',
]
