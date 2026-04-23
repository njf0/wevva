"""Search dialog widget.

Composite widget containing search input and results list.
Handles debouncing and emits custom messages for search and selection.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Input, Select

from wevva.constants import SEARCH_DEBOUNCE_S, SEARCH_MIN_CHARS
from wevva.location_metadata import LocationMetadata
from wevva.messages import PlaceSelected, SearchQueryReady
from wevva.widgets.search_results import SearchResultsList


class SearchDialog(Container):
    """Composite search widget with input and results list."""

    DEFAULT_CSS = """
    SearchDialog {
        layout: vertical;
        width: 60;
        max-width: 80%;
        height: auto;
        padding: 1 2;
        border: tall $accent;
        border-title-color: $accent;
        border-title-align: left;
        background: $panel;
        align-horizontal: center;
        align-vertical: top;
        margin: 2 0 0 0;
    }
    SearchDialog Input { width: 100%; }
    SearchDialog #filter-row {
        height: auto;
        width: 100%;
        margin-bottom: 1;
    }
    SearchDialog Select {
        width: 1fr;
    }
    """

    def __init__(self):
        super().__init__(id='place-search-dialog')
        self._lookup_timer = None  # Debounce timer
        self._min_query = SEARCH_MIN_CHARS
        self._all_places: list[dict] = []  # Cache unfiltered results

    def compose(self) -> ComposeResult:  # type: ignore[override]
        yield Input(placeholder='Search for a place...', id='place-search-input')
        with Horizontal(id='filter-row'):
            yield Select(
                options=[('All Countries', None)],
                prompt='Filter by country',
                value=None,
                id='country-filter',
            )
        yield SearchResultsList()

    @property
    def results(self) -> SearchResultsList:
        return self.query_one(SearchResultsList)

    @property
    def search_input(self) -> Input:
        return self.query_one('#place-search-input', Input)

    @property
    def country_filter(self) -> Select:
        return self.query_one('#country-filter', Select)

    def on_mount(self) -> None:
        """Focus input and hide filter/results initially."""
        self.search_input.focus()
        self.results.add_class('hidden')
        self.query_one('#filter-row').add_class('hidden')

    def on_unmount(self) -> None:
        """Cancel pending timer on unmount."""
        if self._lookup_timer:
            self._lookup_timer.stop()

    # Event handlers ---------------------------------------------------
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle typing with debounce."""
        if event.input.id != 'place-search-input':
            return

        query = event.value.strip()
        if self._lookup_timer:
            self._lookup_timer.stop()

        if len(query) < self._min_query:
            self.results.add_class('hidden')
            self.query_one('#filter-row').add_class('hidden')
            return

        # Show searching status and schedule query emission
        self.results.remove_class('hidden')
        self.results.show_searching()
        self._lookup_timer = self.set_timer(SEARCH_DEBOUNCE_S, lambda: self._emit_query(query))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """If exactly one result, select it on enter."""
        if event.input.id != 'place-search-input':
            return

        location = self.results.get_single_result()
        if location:
            self.post_message(PlaceSelected(location=location))

    async def on_option_list_option_selected(self, event) -> None:  # type: ignore[override]
        """Handle place selection from list."""
        option_id = event.option.id or ''
        location = self.results.get_selected_place(option_id)
        if location:
            self.post_message(PlaceSelected(location=location))

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle country filter selection."""
        if event.select.id != 'country-filter':
            return

        selected_country = event.value
        if selected_country is None:
            # Show all results
            self.results.update_results(self._all_places, preferred_location=self._preferred_location())
        else:
            # Filter by selected country
            filtered = [p for p in self._all_places if p.get('country') == selected_country]
            self.results.update_results(filtered, preferred_location=self._preferred_location())

    # Public API -------------------------------------------------------
    def show_error(self, error: Exception) -> None:
        """Display error in results list."""
        self.results.show_error(error)

    def show_no_results(self) -> None:
        """Display 'no results' message."""
        self.results.show_no_results()

    def show_results(self, places: list[dict]) -> None:
        """Update results list with places and populate country filter."""
        self._all_places = places
        self.results.update_results(places, preferred_location=self._preferred_location())

        # Extract unique countries and populate filter
        countries = sorted(set(p.get('country', '') for p in places if p.get('country')))
        if len(countries) > 1:
            # Show filter only if multiple countries present
            options = [('All Countries', None)] + [(country, country) for country in countries]
            self.country_filter.set_options(options)
            self.country_filter.value = None  # Reset to "All"
            self.query_one('#filter-row').remove_class('hidden')
        else:
            # Hide filter if only one country
            self.query_one('#filter-row').add_class('hidden')

    def _emit_query(self, query: str) -> None:
        """Emit SearchQueryReady message after debounce."""
        self.post_message(SearchQueryReady(query))

    def _preferred_location(self) -> LocationMetadata | None:
        """Return the location that should be highlighted in search results."""
        current_location = getattr(self.app, 'location', None)
        if (
            isinstance(current_location, LocationMetadata)
            and current_location.latitude is not None
            and current_location.longitude is not None
        ):
            return current_location

        saved_locations = getattr(self.app, 'saved_locations', [])
        if saved_locations:
            return saved_locations[0]
        return None
