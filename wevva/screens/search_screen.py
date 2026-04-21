"""Search screen.

Lets you search for a place and pick one.
Sends a `PlaceSelected` message back to the app.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Footer, Header

from wevva.constants import REQUEST_TIMEOUT_S, SEARCH_MAX_RESULTS
from wevva.messages import PlaceSelected, SearchQueryReady
from wevva.services.geocoding import search_places
from wevva.widgets.search_dialog import SearchDialog


class SearchScreen(ModalScreen[None]):
    """Modal screen for place search - coordinates API calls with SearchDialog widget."""

    BINDINGS = [('escape', 'dismiss', 'Close')]

    def compose(self) -> ComposeResult:  # type: ignore[override]
        yield Header(show_clock=True, id='place-search-header')
        yield SearchDialog()
        yield Footer()

    @property
    def dialog(self) -> SearchDialog:
        return self.query_one(SearchDialog)

    # Message handlers -------------------------------------------------
    async def on_search_query_ready(self, event: SearchQueryReady) -> None:
        """Handle search query from dialog (after debounce)."""
        try:
            places = await search_places(
                event.query,
                count=SEARCH_MAX_RESULTS,
                language='en',
                timeout=REQUEST_TIMEOUT_S,
            )
        except Exception as e:
            self.dialog.show_error(e)
            return

        if not places:
            self.dialog.show_no_results()
        else:
            self.dialog.show_results(places)

    def on_place_selected(self, event: PlaceSelected) -> None:
        """Handle place selection from dialog - dismiss to let message bubble to app."""
        self.dismiss()
