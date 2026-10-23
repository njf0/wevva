"""Dedicated interactive world map for saved weather locations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Footer, Header

from wevva.location_metadata import LocationMetadata
from wevva.widgets.saved_locations import SavedLocationWeatherSummary
from wevva.widgets.world_locations_map import WorldLocationsMap


class WorldLocationsScreen(Screen[None]):
    """Full-content world overview of the locations shown by the sidebar."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding('b', 'app.dashboard', 'Dashboard'),
        Binding('escape', 'app.dashboard', 'Dashboard', show=False),
        Binding('left', 'previous_location', 'Previous location', show=False),
        Binding('right', 'next_location', 'Next location', show=False),
    ]

    DEFAULT_CSS = """
    WorldLocationsScreen {
        background: $background;
    }

    #world-locations-stage {
        width: 100%;
        height: 1fr;
        padding: 1 2;
        background: $background;
        hatch: right $background-lighten-1;
        overflow: hidden hidden;
    }

    #world-locations-map {
        width: 100%;
        height: 100%;
    }
    """

    def __init__(
        self,
        locations: Sequence[LocationMetadata],
        *,
        summaries: Mapping[str, SavedLocationWeatherSummary] | None = None,
        current_location: LocationMetadata | None = None,
        temperature_unit: str = 'celsius',
    ) -> None:
        super().__init__()
        self._locations = list(locations)
        self._summaries = dict(summaries or {})
        self._current_location = current_location
        self._temperature_unit = temperature_unit

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id='world-locations-stage'):
            yield WorldLocationsMap(
                self._locations,
                summaries=self._summaries,
                temperature_unit=self._temperature_unit,
                id='world-locations-map',
            )
        yield Footer()

    @property
    def world_map(self) -> WorldLocationsMap:
        return self.query_one('#world-locations-map', WorldLocationsMap)

    def on_mount(self) -> None:
        self.call_after_refresh(self._focus_initial_location)

    def _focus_initial_location(self) -> None:
        if not self.world_map.focus_location(self._current_location):
            self.world_map.focus_relative(1)

    def update_weather_summary(
        self,
        location: LocationMetadata,
        summary: SavedLocationWeatherSummary,
        *,
        temperature_unit: str,
    ) -> None:
        """Apply a saved-summary result which completed while this screen was open."""

        self.world_map.set_temperature_unit(temperature_unit)
        self.world_map.update_weather_summary(location, summary)

    def action_previous_location(self) -> None:
        self.world_map.focus_relative(-1)

    def action_next_location(self) -> None:
        self.world_map.focus_relative(1)

__all__ = ['WorldLocationsScreen']
