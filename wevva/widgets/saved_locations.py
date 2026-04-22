"""Docked saved-location sidebar."""

from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, OptionList, Static
from textual.widgets.option_list import Option

from wevva.conditions import Condition
from wevva.config import location_key, location_label
from wevva.location_metadata import LocationMetadata
from wevva.messages import (
    DeleteSavedLocationRequested,
    SaveCurrentLocationRequested,
    SavedLocationSelected,
)
from wevva.utils import temp_colour


@dataclass
class SavedLocationWeatherSummary:
    """Compact sidebar weather summary for one saved location."""

    temperature: float | None = None
    temperature_unit: str = '°C'
    condition: Condition | None = None
    error: bool = False


class SavedLocationsSidebar(Container):
    """Sidebar for saved locations and compact weather summaries."""

    DEFAULT_CSS = """
    SavedLocationsSidebar {
        dock: left;
        width: 30;
        height: 100%;
        margin-bottom: 1;
        margin-top: 1;
        # border-right: heavy $primary;
        background: $background;
        hatch: right $primary-muted
    }

    SavedLocationsSidebar.hidden {
        display: none;
    }

    #saved-location-header {
        height: 3;
        width: 100%;
    }

    #saved-location-title {
        height: 3;
        width: 100%;
        content-align: center middle;
        color: $primary;
        text-style: bold;
    }

    #saved-location-actions {
        height: 3;
        width: 100%;
        layout: horizontal;
    }

    #save-current-location {
        width: 1fr;
        height: 3;
        min-width: 8;
        min-height: 3;
    }

    #delete-saved-location {
        width: 1fr;
        height: 3;
        min-width: 8;
        min-height: 3;
    }

    #saved-location-list {
        height: 1fr;
        width: 100%;
        border: none;
    }

    #saved-location-list > .option-list--separator {
        color: $primary-muted;
    }
    """

    def __init__(self, *, id: str = 'saved-locations-sidebar') -> None:
        super().__init__(id=id)
        self.border_title = 'Locations'
        self._locations: list[LocationMetadata] = []
        self._location_cache: dict[str, LocationMetadata] = {}
        self._weather_summaries: dict[str, SavedLocationWeatherSummary] = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id='saved-location-header'):
            yield Static('Saved Locations', id='saved-location-title')
        yield OptionList(id='saved-location-list')
        with Horizontal(id='saved-location-actions'):
            yield Button('Save', id='save-current-location', variant='success', tooltip='Save current location')
            yield Button('Delete', id='delete-saved-location', variant='error', tooltip='Delete selected location')

    @property
    def locations(self) -> OptionList:
        return self.query_one('#saved-location-list', OptionList)

    def set_locations(
        self,
        locations: list[LocationMetadata],
    ) -> None:
        """Replace saved locations and re-render rows."""
        self._locations = sorted(locations, key=lambda item: location_label(item).casefold())
        self._render_locations()

    def update_weather_summary(self, location: LocationMetadata, summary: SavedLocationWeatherSummary) -> None:
        """Cache and display compact weather text for one location."""
        self._weather_summaries[location_key(location)] = summary
        self._render_locations()

    def _render_locations(self) -> None:
        if not self.is_mounted:
            return

        highlighted_id = self._current_option_id()
        self.locations.clear_options()
        self._location_cache.clear()

        if not self._locations:
            self.locations.add_option(Option('No saved locations', id='saved-empty', disabled=True))
            return

        for index, location in enumerate(self._locations):
            option_id = f'saved-{index}'
            label = self._format_location(location)
            self.locations.add_option(Option(label, id=option_id))
            self._location_cache[option_id] = location

            if highlighted_id == option_id:
                self.locations.highlighted = index

            if index < len(self._locations) - 1:
                self.locations.add_option(None)

    def _format_location(self, location: LocationMetadata) -> Text:
        key = location_key(location)
        place = ', '.join(part for part in (location.name, location.country) if part)
        if not place:
            place = location_label(location)
        summary = self._weather_summaries.get(key)

        text = Text()
        text.append(f'{place}\n', style='bold')
        text.append(self._format_summary(summary))
        return text

    def _format_summary(self, summary: SavedLocationWeatherSummary | None) -> Text:
        """Build styled weather summary text."""
        text = Text()
        if summary is None:
            text.append('--, --', style='italic dim')
            return text
        if summary.error:
            text.append('--, --', style='italic dim')
            return text

        theme_vars = self.app.theme_variables
        temp = summary.temperature
        if isinstance(temp, (int, float)):
            temp_unit = getattr(self.app, 'temperature_unit', 'celsius')
            colour = temp_colour(
                temp,
                scale='theme_temperature',
                hex=True,
                unit=temp_unit,
                theme_colours=theme_vars,
            )
            unit = summary.temperature_unit[0] if summary.temperature_unit else '°'
            text.append(f'{round(temp):.0f}{unit}', style=f'bold {colour}')
        else:
            text.append('--', style='italic dim')

        text.append(', ', style='dim')
        condition = summary.condition
        if condition is not None:
            colour = theme_vars.get(condition.color_var) if condition.color_var else None
            style = f'italic {colour}' if colour else 'italic'
            text.append(condition.name, style=style)
        else:
            text.append('--', style='italic dim')
        return text

    def _current_option_id(self) -> str | None:
        if not self.is_mounted or self.locations.highlighted is None:
            return None
        try:
            option = self.locations.get_option_at_index(self.locations.highlighted)
        except Exception:
            return None
        option_id = option.id
        return option_id if isinstance(option_id, str) else None

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Switch to a saved location."""
        option_id = event.option.id
        if isinstance(option_id, str) and option_id in self._location_cache:
            self.post_message(SavedLocationSelected(location=self._location_cache[option_id]))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle save/delete buttons."""
        if event.button.id == 'save-current-location':
            self.post_message(SaveCurrentLocationRequested())
            return

        if event.button.id == 'delete-saved-location':
            option_id = self._current_option_id()
            if option_id and option_id in self._location_cache:
                self.post_message(DeleteSavedLocationRequested(location=self._location_cache[option_id]))
