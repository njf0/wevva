"""Search results widget.

Manages the option list for place search results with status messages.
"""

from __future__ import annotations

from textual.widgets import OptionList
from textual.widgets.option_list import Option

from wevva.location_metadata import LocationMetadata

# Status message option IDs
_STATUS_SEARCHING = 'status-searching'
_STATUS_ERROR = 'status-error'
_STATUS_NO_RESULTS = 'status-no-results'


class SearchResultsList(OptionList):
    """OptionList specialized for place search results."""

    DEFAULT_CSS = """
    SearchResultsList {
        height: auto;
        max-height: 14;
        width: 100%;
        scrollbar-size-vertical: 1;
    }
    """

    def __init__(self):
        super().__init__(id='place-search-results')
        self._place_cache: dict[str, dict] = {}  # Maps option ID to place metadata

    def show_searching(self) -> None:
        """Display 'Searching...' status message."""
        self._update_status(_STATUS_SEARCHING, 'Searching…')

    def show_error(self, error: Exception) -> None:
        """Display error message."""
        self._update_status(_STATUS_ERROR, f'Error: {error}')

    def show_no_results(self) -> None:
        """Display 'No results found' message."""
        self._update_status(_STATUS_NO_RESULTS, 'No results found')

    def update_results(self, places: list[dict]) -> None:
        """Update list with search results.

        Args:
            places: List of place dicts from geocoding service

        """
        self.clear_options()
        self._place_cache.clear()

        for place in places:
            option_id = self._build_place_id(place)
            label = self._format_place_label(place)
            self.add_option(Option(label, id=option_id))
            self._place_cache[option_id] = place

        # Highlight first result
        if self.option_count > 0:
            self.highlighted = 0

    def get_selected_place(self, option_id: str) -> LocationMetadata | None:
        """Get LocationMetadata for selected option ID."""
        if option_id not in self._place_cache:
            return None

        place = self._place_cache[option_id]
        return LocationMetadata(
            latitude=place.get('latitude'),
            longitude=place.get('longitude'),
            name=place.get('name') or '',
            admin=place.get('admin') or '',
            country=place.get('country') or '',
            country_code=place.get('country_code') or '',
            timezone=place.get('tz_identifier') or '',
        )

    def get_single_result(self) -> LocationMetadata | None:
        """Get metadata if exactly one result exists."""
        if len(self._place_cache) == 1:
            option_id = next(iter(self._place_cache.keys()))
            return self.get_selected_place(option_id)
        return None

    def clear_all(self) -> None:
        """Clear all options and cache."""
        self.clear_options()
        self._place_cache.clear()

    # Helper methods --------------------------------------------------
    def _update_status(self, status_id: str, message: str) -> None:
        """Show a status message (disabled option)."""
        self.clear_options()
        self._place_cache.clear()
        self.add_option(Option(message, id=status_id, disabled=True))

    def _build_place_id(self, place: dict) -> str:
        """Build stable unique ID for a place."""
        name = place.get('name', '')
        country_code = place.get('country_code', '')
        lat = place.get('latitude', 0)
        lon = place.get('longitude', 0)
        tz = place.get('tz_identifier', '')
        return f'geo:{name}|{country_code}|{lat:.3f},{lon:.3f}|{tz}'

    def _format_place_label(self, place: dict) -> str:
        """Format place as rich text label."""
        name = place.get('name', '')
        country = place.get('country', '')
        admin = place.get('admin', '').split(';')

        label = f'[bold]{name}[/]\n[dim italic]'
        if admin:
            label += f'{", ".join([a for a in admin if a != name])}[/]\n'
        label += f'{country}\n'

        return label
