"""Small widget for a weather metric.

Shows an optional top line, big digits, and a lower line.
"""

from rich.text import Text
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Digits, Static


class WeatherWidget(Widget):
    """Show a compact metric: top text (optional), digits, lower text.

    If `show_spacer` is False, the spacer row is omitted.
    """

    DEFAULT_CSS = """
    WeatherWidget {
        layout: vertical;
        height: 7;
        width: 22;
        border: round $primary;
        border-title-color: $primary;
        border-title-align: left;
        padding: 0 1;
        margin: 0 3 0 0;
        align-horizontal: left;
    }
    WeatherWidget > Static {
        width: 100%;
        align-horizontal: left;
    }
    WeatherWidget #digits-row {
        height: auto;
        width: auto;
        align-horizontal: left;
        align-vertical: middle;
    }
    WeatherWidget #digits {
        width: auto;
    }
    WeatherWidget #units {
        width: auto;
        height: auto;
        padding-left: 1;
        align-vertical: middle;
    }
    """

    def __init__(self, title: str | None = None, **kwargs):
        """Create with options like `value`, `lower_text`, `colour`, `top_text`, `units`.

        Remaining kwargs go to the base widget (e.g., id, classes).
        """
        # Extract our options (with defaults) from kwargs
        value = kwargs.pop('value', '—')
        lower_text = kwargs.pop('lower_text', '')
        colour = kwargs.pop('colour', None)
        top_text = kwargs.pop('top_text', '')
        units = kwargs.pop('units', '')
        show_spacer = kwargs.pop('show_spacer', True)
        super().__init__(**kwargs)
        self._value = str(value)
        self._lower_text = lower_text
        self._colour = colour
        self._top_text = top_text
        self._units = units
        self.border_title = title
        self._show_spacer = bool(show_spacer)

    def compose(self):  # type: ignore[override]
        """Build child widgets; include a top line only if set."""
        if self._top_text:
            self._top = Static(Text.from_markup(self._top_text), id='top')
            yield self._top

        # Horizontal row for digits and units
        with Horizontal(id='digits-row'):
            self._digits = Digits(str(self._value), id='digits')
            yield self._digits
            self._units_widget = Static(Text.from_markup(self._units), id='units')
            yield self._units_widget

        if self._show_spacer:
            self._spacer = Static('', id='spacer')
            yield self._spacer

        self._lower = Static(Text.from_markup(self._lower_text), id='lower')
        yield self._lower

        if self._colour:
            self._digits.styles.color = self._colour

    # Public API -------------------------------------------------
    def set(
        self,
        value: str | float | int,
        lower_text: str | Text = '',
        colour: str | None = None,
        top_text: str | Text | None = None,
        units: str | Text | None = None,
    ):
        """Update value and texts (colour/top text/units are optional)."""
        self._value = str(value)
        self._lower_text = lower_text if isinstance(lower_text, str) else lower_text.plain
        if top_text is not None:
            self._top_text = top_text if isinstance(top_text, str) else top_text.plain
        if units is not None:
            self._units = units if isinstance(units, str) else units.plain
        if colour:
            self._colour = colour

        if not hasattr(self, '_digits') or not isinstance(self._digits, Digits):
            return  # compose not yet run

        # Update digits value and colour
        self._digits.update(str(value))
        if colour:
            self._digits.styles.color = colour

        # Update text widgets
        if top_text is not None and hasattr(self, '_top'):
            self._update_text_widget(self._top, top_text)
        if units is not None and hasattr(self, '_units_widget'):
            self._update_text_widget(self._units_widget, units)
        self._update_text_widget(self._lower, lower_text)
        self.refresh()

    def _update_text_widget(self, widget: Static, content: str | Text) -> None:
        """Update a Static text widget with string or rich Text content."""
        if isinstance(content, Text):
            widget.update(content)
        else:
            widget.update(Text.from_markup(str(content)))

    def set_colour(self, colour: str):
        """Update only the colour of the digits."""
        self._digits.styles.color = colour
        self.refresh()
