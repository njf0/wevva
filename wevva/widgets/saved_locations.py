"""Docked saved-location sidebar."""

from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import OptionList, ProgressBar
from textual.widgets.option_list import Option

from wevva.conditions import Condition
from wevva.config import location_key, location_label
from wevva.location_metadata import LocationMetadata
from wevva.messages import SavedLocationSelected
from wevva.utils import emoji_prefix, temp_colour


@dataclass
class SavedLocationWeatherSummary:
    """Compact sidebar weather summary for one saved location."""

    temperature: float | None = None
    temperature_unit: str = '°C'
    condition: Condition | None = None
    condition_emoji: str = ''
    error: bool = False


class SavedLocationsSidebar(Container):
    """Sidebar for saved locations and compact weather summaries."""

    DEFAULT_CSS = """
    SavedLocationsSidebar {
        dock: left;
        width: 40;
        height: 100%;
        # margin-bottom: 1;
        # margin-top: 1;
        margin: 2 0 2 2;
        layout: vertical;
        background: $background;
        hatch: right $background-lighten-1;
    }

    SavedLocationsSidebar.hidden {
        display: none;
    }

    #saved-locations-panel {
        height: 1fr;
        width: 100%;
        margin: 0;
        border: round $primary;
        background: $background;
    }

    #saved-location-list {
        height: 100%;
        width: 100%;
        scrollbar-size-vertical: 1;
        # border: round $primary-muted;
        border: none;
        background: $background;
    }

    #saved-location-list > .option-list--separator {
        color: $primary-muted;
    }

    #saved-location-warning-progress {
        layout: vertical;
        width: 100%;
        height: auto;
        padding: 0 1;
        margin: 1 0 0 0;
        border: round $primary;
        background: $background;
        color: $text-muted;
    }

    #saved-location-warning-progress-bar {
        width: 100%;
        height: 1;
    }

    #saved-location-warning-progress-bar > Bar {
        width: 1fr;
    }

    #saved-location-tropical-progress {
        layout: vertical;
        width: 100%;
        height: auto;
        padding: 0 1;
        margin: 1 0 0 0;
        border: round $primary;
        background: $background;
        color: $text-muted;
    }

    #saved-location-tropical-progress-bar {
        width: 100%;
        height: 1;
    }

    #saved-location-tropical-progress-bar > Bar {
        width: 1fr;
    }
    """

    def __init__(self, *, id: str = 'saved-locations-sidebar') -> None:
        super().__init__(id=id)
        self._locations: list[LocationMetadata] = []
        self._location_cache: dict[str, LocationMetadata] = {}
        self._weather_summaries: dict[str, SavedLocationWeatherSummary] = {}
        self._warning_progress_has_measured_work = False

    def compose(self) -> ComposeResult:
        self.locations_panel = Container(id='saved-locations-panel')
        self.locations_panel.border_title = 'Saved Locations'
        self.locations_panel.styles.border_title_align = 'left'
        with self.locations_panel:
            yield OptionList(id='saved-location-list')

        self.warning_progress = Container(id='saved-location-warning-progress')
        self.warning_progress.border_title = 'Checking alerts'
        self.warning_progress.styles.border_title_align = 'left'
        self.warning_progress.display = False
        with self.warning_progress:
            self.warning_progress_bar = ProgressBar(
                total=None,
                show_percentage=True,
                show_eta=False,
                id='saved-location-warning-progress-bar',
            )
            yield self.warning_progress_bar

        self.tropical_progress = Container(id='saved-location-tropical-progress')
        self.tropical_progress.border_title = 'Checking tropical systems'
        self.tropical_progress.styles.border_title_align = 'left'
        self.tropical_progress.display = False
        with self.tropical_progress:
            self.tropical_progress_bar = ProgressBar(
                total=None,
                show_percentage=True,
                show_eta=False,
                id='saved-location-tropical-progress-bar',
            )
            yield self.tropical_progress_bar

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

    def weather_summary(self, location: LocationMetadata) -> SavedLocationWeatherSummary | None:
        """Return the cached summary for one saved location, if any."""
        return self._weather_summaries.get(location_key(location))

    def update_warning_progress(self, event: str, payload: dict[str, object]) -> None:
        """Show progress for the active ordinary-warning query."""
        details = self._warning_progress_details(
            event,
            payload,
            has_measured_progress=self._warning_progress_has_measured_work,
        )
        if details is None:
            return
        completed, total = details
        if total is not None:
            self._warning_progress_has_measured_work = True
        self.warning_progress.border_title = self._warning_progress_title(total)
        self.warning_progress_bar.update(total=total, progress=completed)
        self.warning_progress.display = True

    def clear_warning_progress(self) -> None:
        """Hide the transient warning-query progress panel."""
        self.warning_progress.border_title = 'Checking alerts'
        self.warning_progress_bar.update(total=None, progress=0)
        self.warning_progress.display = False
        self._warning_progress_has_measured_work = False

    def update_tropical_progress(self, event: str, payload: dict[str, object]) -> None:
        """Show progress for the active nearby tropical-system refresh."""
        details = self._tropical_progress_details(event, payload)
        if details is None:
            return
        completed, total = details
        self.tropical_progress.border_title = self._tropical_progress_title(total)
        self.tropical_progress_bar.update(total=total, progress=completed)
        self.tropical_progress.display = True

    def clear_tropical_progress(self) -> None:
        """Hide the transient tropical-system progress panel."""
        self.tropical_progress.border_title = 'Checking tropical systems'
        self.tropical_progress_bar.update(total=None, progress=0)
        self.tropical_progress.display = False

    @staticmethod
    def _warning_progress_details(
        event: str,
        payload: dict[str, object],
        *,
        has_measured_progress: bool = False,
    ) -> tuple[int, int | None] | None:
        """Return sidebar data for pending or measured individual warning work."""
        if event == 'source_started':
            # Providers and the nearby tropical lookup run as one refresh.  Once
            # matching has begun, do not send the sidebar back through a second
            # indeterminate "Fetching alerts" phase for the next source.
            if has_measured_progress:
                return None
            return 0, None

        total = payload.get('total')
        completed = payload.get('completed')
        phase = payload.get('phase')
        if event not in {'alerts_total', 'alerts_checked'} or not isinstance(total, int) or total <= 0:
            return None
        if phase not in {'documents', 'geometry', 'matching'}:
            return None

        progress = 0 if event == 'alerts_total' else completed
        if not isinstance(progress, int):
            return None
        return progress, total

    @staticmethod
    def _warning_progress_title(total: int | None) -> str:
        """Return the title that matches an indeterminate or measured bar."""
        return 'Fetching alerts' if total is None else 'Checking alerts'

    @staticmethod
    def _tropical_progress_details(event: str, payload: dict[str, object]) -> tuple[int, int | None] | None:
        """Return sidebar data for tropical fetching or local matching work."""
        if event == 'tropical_fetch_started':
            return 0, None

        total = payload.get('total')
        completed = payload.get('completed')
        if event not in {'tropical_check_total', 'tropical_checked'} or not isinstance(total, int) or total <= 0:
            return None

        progress = 0 if event == 'tropical_check_total' else completed
        if not isinstance(progress, int):
            return None
        return progress, total

    @staticmethod
    def _tropical_progress_title(total: int | None) -> str:
        """Return the title that matches tropical fetching or matching work."""
        return 'Fetching tropical systems' if total is None else 'Checking tropical systems'

    def _render_locations(self) -> None:
        if not self.is_mounted:
            return

        highlighted_key = self._highlighted_location_key()
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

            if highlighted_key == location_key(location):
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
        text.append(f'{place}\n')
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
            if self.app.emoji_enabled and summary.condition_emoji:
                text.append(emoji_prefix(summary.condition_emoji))
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

    def _highlighted_location_key(self) -> str | None:
        """Return the preferred location key to highlight."""
        current_location = getattr(self.app, 'location', None)
        if current_location is not None:
            return location_key(current_location)
        selected = self.selected_location()
        if selected is not None:
            return location_key(selected)
        return None

    def selected_location(self) -> LocationMetadata | None:
        """Return the currently highlighted saved location, if any."""
        option_id = self._current_option_id()
        if option_id is None:
            return None
        return self._location_cache.get(option_id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Switch to a saved location."""
        option_id = event.option.id
        if isinstance(option_id, str) and option_id in self._location_cache:
            self.post_message(SavedLocationSelected(location=self._location_cache[option_id]))
