"""Search dialog widget.

Composite widget containing search input and results list.
Handles debouncing and emits custom messages for search and selection.
"""

from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.validation import Number
from textual.widgets import Input, Label, Select

from wevva.constants import SEARCH_DEBOUNCE_S, SEARCH_MIN_CHARS
from wevva.location_metadata import LocationMetadata
from wevva.messages import PlaceSelected, SearchQueryReady
from wevva.services.geocoding import parse_coordinate_query
from wevva.widgets.search_results import SearchResultsList


class SearchDialog(Container):
    """Composite search widget with input and results list."""

    DEFAULT_CSS = """
    SearchDialog {
        layout: vertical;
        width: 60;
        max-width: 80%;
        height: auto;
        max-height: 100%;
        padding: 1 2;
        overflow-y: auto;
        border: tall $accent;
        border-title-align: center;
        border-title-color: $accent;
        border-title-style: bold reverse;
        background: $panel;
        align-horizontal: center;
        align-vertical: top;
        margin: 2 0 0 0;
    }
    SearchDialog Input {
        width: 100%;
        border: tall $primary;
        border-title-align: left;
        border-title-color: $primary;
        border-title-style: bold reverse;
    }
    SearchDialog .form-hint {
        width: 100%;
        height: 1;
        color: $text-muted;
    }
    SearchDialog Input:focus {
        border: tall $primary;
    }
    SearchDialog Input.-invalid,
    SearchDialog Input.-invalid:focus {
        border: tall $error;
        border-title-color: $error;
    }
    SearchDialog #coordinate-heading {
        width: 100%;
        height: 1;
        margin-top: 1;
        color: $text-muted;
        text-align: center;
        text-style: dim italic;
    }
    SearchDialog #coordinate-hint {
        text-align: center;
    }
    SearchDialog #coordinate-row {
        width: 100%;
        height: 3;
    }
    SearchDialog #coordinate-preview {
        width: 100%;
        height: 1;
        color: $text-muted;
    }
    SearchDialog #coordinate-preview.-ready {
        color: $text;
    }
    SearchDialog #coordinate-preview.-error {
        color: $error;
    }
    SearchDialog #latitude-input {
        width: 1fr;
        margin-right: 1;
    }
    SearchDialog #longitude-input {
        width: 1fr;
    }
    SearchDialog #results-section {
        width: 100%;
        height: auto;
    }
    SearchDialog #filter-row {
        height: auto;
        width: 100%;
        margin-bottom: 1;
    }
    SearchDialog Select {
        width: 1fr;
        height: auto;
        border: tall $primary;
        border-title-align: left;
        border-title-color: $primary;
        border-title-style: bold reverse;
    }
    SearchDialog Select > SelectCurrent,
    SearchDialog Select:focus > SelectCurrent {
        border: none;
    }
    """

    def __init__(self):
        super().__init__(id='place-search-dialog')
        self.border_title = 'Search location'
        self._lookup_timer = None  # Debounce timer
        self._min_query = SEARCH_MIN_CHARS
        self._all_places: list[dict] = []  # Cache unfiltered results
        self._submitted_coordinate_query: str | None = None

    def compose(self) -> ComposeResult:  # type: ignore[override]
        place_input = Input(
            placeholder='Enter place name',
            id='place-search-input',
        )
        place_input.border_title = 'Place name'
        yield place_input
        yield Label(
            'Or use coordinates',
            id='coordinate-heading',
        )
        yield Label(
            'Decimal degrees',
            id='coordinate-hint',
            classes='form-hint',
        )
        with Horizontal(id='coordinate-row'):
            latitude_input = Input(
                placeholder='50.856',
                validators=Number(minimum=-90, maximum=90),
                validate_on=['changed', 'submitted'],
                valid_empty=True,
                id='latitude-input',
            )
            latitude_input.border_title = 'Latitude'
            yield latitude_input
            longitude_input = Input(
                placeholder='−0.706',
                validators=Number(minimum=-180, maximum=180),
                validate_on=['changed', 'submitted'],
                valid_empty=True,
                id='longitude-input',
            )
            longitude_input.border_title = 'Longitude'
            yield longitude_input
        yield Label('', id='coordinate-preview')
        with Vertical(id='results-section'):
            with Vertical(id='filter-row'):
                country_filter = Select(
                    options=[('All Countries', None)],
                    prompt='Filter by country',
                    value=None,
                    id='country-filter',
                )
                country_filter.border_title = 'Filter by country'
                yield country_filter
            yield SearchResultsList()

    @property
    def results(self) -> SearchResultsList:
        return self.query_one(SearchResultsList)

    @property
    def search_input(self) -> Input:
        return self.query_one('#place-search-input', Input)

    @property
    def latitude_input(self) -> Input:
        return self.query_one('#latitude-input', Input)

    @property
    def longitude_input(self) -> Input:
        return self.query_one('#longitude-input', Input)

    @property
    def country_filter(self) -> Select:
        return self.query_one('#country-filter', Select)

    @property
    def results_section(self) -> Vertical:
        return self.query_one('#results-section', Vertical)

    def on_mount(self) -> None:
        """Focus input and hide filter/results initially."""
        self._size_results_for_terminal()
        self.search_input.focus()
        self.results_section.add_class('hidden')
        self.query_one('#filter-row').add_class('hidden')

    def on_unmount(self) -> None:
        """Cancel pending timer on unmount."""
        if self._lookup_timer:
            self._lookup_timer.stop()

    def on_resize(self, _event: events.Resize) -> None:
        """Keep results useful without allowing the modal to leave the viewport."""
        self._size_results_for_terminal()

    # Event handlers ---------------------------------------------------
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle typing with debounce."""
        if event.input.id in {'latitude-input', 'longitude-input'}:
            if self._lookup_timer:
                self._lookup_timer.stop()
            self._submitted_coordinate_query = None
            self.query_one('#filter-row').add_class('hidden')
            self._show_coordinate_status()
            return

        if event.input.id != 'place-search-input':
            return

        query = event.value.strip()
        if self._lookup_timer:
            self._lookup_timer.stop()
        self._submitted_coordinate_query = None

        if len(query) < self._min_query:
            self._hide_results()
            return

        if parse_coordinate_query(query) is not None:
            self._show_results()
            self.results.show_coordinate_error('Use the latitude and longitude fields below')
            return

        # Show searching status and schedule query emission
        self._show_results()
        self.results.show_searching()
        self._lookup_timer = self.set_timer(
            SEARCH_DEBOUNCE_S,
            lambda: self._emit_place_query_if_current(query),
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """If exactly one result, select it on enter."""
        if event.input.id in {'latitude-input', 'longitude-input'}:
            query = self._coordinate_query()
            if query is None:
                self._show_coordinate_status()
                return

            location = self.results.get_single_result()
            if query == self._submitted_coordinate_query and location is not None:
                self.post_message(PlaceSelected(location=location))
                return
            self._submitted_coordinate_query = query
            self._show_results()
            self.results.show_searching()
            self._emit_query(query)
            return

        if event.input.id != 'place-search-input':
            return

        if parse_coordinate_query(event.value.strip()) is not None:
            self._show_results()
            self.results.show_coordinate_error('Use the latitude and longitude fields below')
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
        self._show_results()
        self.results.show_error(error)

    def show_no_results(self) -> None:
        """Display 'no results' message."""
        self._show_results()
        self.results.show_no_results()

    def show_results(self, places: list[dict]) -> None:
        """Update results list with places and populate country filter."""
        self._show_results()
        self._all_places = places
        self.results.update_results(places, preferred_location=self._preferred_location())
        self.results.focus()

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

    def _emit_place_query_if_current(self, query: str) -> None:
        """Emit only if the debounced place query is still the active input."""
        if self.search_input.value.strip() != query:
            return
        if self.latitude_input.value.strip() or self.longitude_input.value.strip():
            return
        self._emit_query(query)

    def _size_results_for_terminal(self) -> None:
        """Allocate spare terminal rows to results after the fixed form controls."""
        self.results.styles.max_height = max(6, min(16, self.app.size.height - 18))

        if self.app.size.height <= 24:
            self.styles.padding = (0, 2)
            self.styles.margin = (0, 0, 0, 0)
            self.query_one('#coordinate-heading').styles.margin = (0, 0, 0, 0)
        else:
            self.styles.padding = (1, 2)
            self.styles.margin = (2, 0, 0, 0)
            self.query_one('#coordinate-heading').styles.margin = (1, 0, 0, 0)

    def _hide_results(self) -> None:
        """Hide stale output and its controls while the form is being edited."""
        self.results_section.add_class('hidden')
        self.query_one('#filter-row').add_class('hidden')

    def _show_results(self) -> None:
        """Reveal the output region for a search status or result set."""
        self.results_section.remove_class('hidden')
        self.query_one('#filter-row').add_class('hidden')

    def _coordinate_query(self) -> str | None:
        """Return the normalized coordinate query when both fields are valid."""
        latitude = self.latitude_input.value.strip()
        longitude = self.longitude_input.value.strip()
        if not latitude or not longitude:
            return None
        query = f'{latitude}, {longitude}'
        if not self.latitude_input.is_valid or not self.longitude_input.is_valid:
            return None
        return query if parse_coordinate_query(query) is not None else None

    def _show_coordinate_status(self) -> None:
        """Render validation or submission guidance for the coordinate fields."""
        latitude = self.latitude_input.value.strip()
        longitude = self.longitude_input.value.strip()
        self._hide_results()
        self._update_coordinate_preview(latitude, longitude)
        if not latitude and not longitude:
            place_query = self.search_input.value.strip()
            if len(place_query) < self._min_query:
                self._hide_results()
            else:
                self._show_results()
                self.results.show_searching()
                self._lookup_timer = self.set_timer(
                    SEARCH_DEBOUNCE_S,
                    lambda: self._emit_place_query_if_current(place_query),
                )
            return

    def _update_coordinate_preview(self, latitude: str, longitude: str) -> None:
        """Show how a valid signed pair will be interpreted geographically."""
        preview = self.query_one('#coordinate-preview', Label)
        coordinates = parse_coordinate_query(f'{latitude}, {longitude}')
        if coordinates is None:
            preview.remove_class('-ready')
            if not latitude or not longitude:
                preview.remove_class('-error')
                preview.update('')
            else:
                errors = []
                if not self.latitude_input.is_valid:
                    errors.append('Latitude must be between −90 and 90')
                if not self.longitude_input.is_valid:
                    errors.append('Longitude must be between −180 and 180')
                preview.add_class('-error')
                preview.update('  •  '.join(errors) or 'Check both coordinates')
            return

        latitude_value, longitude_value = coordinates
        latitude_suffix = 'N' if latitude_value >= 0 else 'S'
        longitude_suffix = 'E' if longitude_value >= 0 else 'W'
        preview.remove_class('-error')
        preview.add_class('-ready')
        preview.update(
            f'{self._format_coordinate_value(latitude_value)}°{latitude_suffix}, '
            f'{self._format_coordinate_value(longitude_value)}°{longitude_suffix}'
        )

    @staticmethod
    def _format_coordinate_value(value: float) -> str:
        """Format an absolute coordinate without unnecessary trailing zeroes."""
        return f'{abs(value):.8f}'.rstrip('0').rstrip('.')

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
