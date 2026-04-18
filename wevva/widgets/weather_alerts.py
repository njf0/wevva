"""Per-alert widget cards for weather warnings."""

from __future__ import annotations

from datetime import datetime

from rich.markdown import Markdown
from rich.markup import escape
from rich.text import Text
from textual.widgets import Static

from wevva.alerts import Alert

SEVERITY_THEME_KEYS: dict[str, str] = {
    'extreme': 'error',
    'severe': 'error',
    'moderate': 'warning',
    'minor': 'accent',
}
class WeatherAlertCard(Static):
    """One alert card with severity-aware theme coloring."""

    DEFAULT_CSS = """
    WeatherAlertCard {
        # content-align: center middle;
        text-align: left;
        height: auto;
        width: 98;
        border: round $primary;
        border-title-color: $primary;
        border-title-align: left;
        padding: 0 1;
        margin-bottom: 1;
    }
    """

    def __init__(self, alert: Alert, *, id: str | None = None):
        super().__init__('', id=id)
        self.alert = alert

    def on_mount(self) -> None:
        """Render static content and tooltip on mount."""
        self._update_display()

    def _update_display(self) -> None:
        theme = self.app.theme_variables
        severity_key = SEVERITY_THEME_KEYS.get((self.alert.severity or '').lower())
        severity_color = theme.get(severity_key, 'accent')
        severity_color_text = theme.get(f'text-{severity_key}') if severity_key else None

        if severity_color:
            self.styles.border = ('round', severity_color)
            self.styles.border_title_color = severity_color_text

        self.border_title = self.build_border_title()
        self.border_subtitle = self.build_border_subtitle()
        self.styles.border_subtitle_align = 'right'

        content = Text.from_markup(self.build_headline_line())
        if severity_color_text:
            content.stylize(severity_color_text)
        self.update(content)
        self.tooltip = self._tooltip_text()

    def build_border_title(self) -> str:
        severity = (self.alert.severity or '').strip()
        event = (self.alert.event or 'Alert').strip()
        if severity:
            return f'{severity.title()} Weather Alert'
        return event

    def build_headline_line(self) -> str:
        event = self._display_event()
        onset = self._to_local_time(self.alert.onset)
        end = self._to_local_time(self.alert.expires)

        if onset is not None and end is not None:
            return (
                f'[bold][italic]{escape(event)}[/] [dim italic]active from[/] [i]{self._fmt_clock(onset)}[/i] '
                f'[dim italic]until[/] [i]{self._fmt_clock(end)}[/i]'
            )
        if onset is not None:
            return f'[bold][italic]{escape(event)}[/] [dim italic]active from[/] [i]{self._fmt_clock(onset)}[/i]'
        if end is not None:
            return f'[bold][italic]{escape(event)}[/] [dim italic]active until[/] [i]{self._fmt_clock(end)}[/i]'
        return f'[bold][italic]{escape(event)}[/]'

    def build_border_subtitle(self) -> Text | None:
        """Build optional clickable provider link text for the border subtitle."""
        url = (self.alert.url or '').strip()
        if not url:
            return None

        return Text.from_markup(
            f'[link={url}][dim underline]View official warning[/][/]'
        )

    def _display_event(self) -> str:
        event = (self.alert.event or self.alert.headline or 'Weather Alert').strip()
        if event.islower():
            return event.title()
        return event

    def _to_local_time(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value
        return value.astimezone()

    def _fmt_clock(self, value: datetime) -> str:
        # Return day name, date, and 24-hour time
        return value.strftime('%H:%M %A')

    def _tooltip_text(self) -> Markdown:
        description = (self.alert.description or '').strip()
        instruction = (self.alert.instruction or '').strip()
        headline = (self.alert.headline or self.alert.event or 'Weather alert').strip()

        if description and instruction:
            body = f'### {headline}\n\n{description}\n\n*{instruction.replace("\n", " ")}*'
            return Markdown(body)
        if description:
            return Markdown(f'### {headline}\n\n{description}')
        if instruction:
            return Markdown(f'### {headline}\n\n*{instruction.replace("\n", " ")}*')
        return Markdown(f'### {headline}')
