"""Compact weather warning display."""

from __future__ import annotations

from datetime import datetime

from rich.markdown import Markdown
from rich.markup import escape
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Static, Tab, Tabs

from wevva.alerts import Alert
from wevva.messages import WeatherAlertSelected

SEVERITY_THEME_KEYS: dict[str, str] = {
    'extreme': 'error',
    'moderate': 'warning',
    'minor': 'accent',
    'red': 'error',
    'yellow': 'accent',
    'green': 'accent',
}

ORANGE_SEVERITIES = {'severe', 'orange', 'amber'}

ALERT_PREFIX_WORDS = {
    'extreme',
    'severe',
    'moderate',
    'minor',
    'red',
    'orange',
    'amber',
    'yellow',
    'green',
}


def interpolated_hex(first: str | None, second: str | None) -> str | None:
    """Return the midpoint between two theme hex colours."""
    if not first or not second:
        return None

    first = first.removeprefix('#')
    second = second.removeprefix('#')
    if len(first) != 6 or len(second) != 6:
        return None
    if not all(character in '0123456789abcdefABCDEF' for character in first + second):
        return None

    channels = []
    for index in range(0, 6, 2):
        channel = round(
            (int(first[index : index + 2], 16) + int(second[index : index + 2], 16)) / 2,
        )
        channels.append(f'{channel:02x}')
    return f'#{"".join(channels)}'


def alert_severity_color(theme: dict[str, str], alert: Alert) -> str | None:
    severity = (alert.severity or '').strip().lower()
    if severity in ORANGE_SEVERITIES:
        return interpolated_hex(theme.get('text-warning'), theme.get('text-error')) or theme.get('text-error')

    severity_key = SEVERITY_THEME_KEYS.get(severity)
    return theme.get(f'text-{severity_key}', theme.get('text-accent'))


class WeatherAlertsPanel(Container):
    """Tabbed alert panel showing one selected warning at a time."""

    DEFAULT_CSS = """
    WeatherAlertsPanel {
        layout: vertical;
        height: auto;
        width: 98;
        border: round $primary;
        border-title-color: $primary;
        border-title-align: center;
        margin-bottom: 1;
        hatch: right $background-lighten-1;
    }

    #weather-alert-tabs {
        width: 100%;
    }

    #weather-alert-body {
        width: 100%;
        padding: 0 1;
        text-align: left;
    }
    """

    def __init__(self, alerts: list[Alert], *, id: str | None = None):
        super().__init__(id=id)
        self.alerts = alerts
        self.selected_index = 0

    def compose(self) -> ComposeResult:
        yield Tabs(id='weather-alert-tabs')
        yield Static('', id='weather-alert-body')

    @property
    def tabs(self) -> Tabs:
        return self.query_one(Tabs)

    @property
    def body(self) -> Static:
        return self.query_one('#weather-alert-body', Static)

    def on_mount(self) -> None:
        self.populate_tabs()
        self.update_selected_alert()

    def populate_tabs(self) -> None:
        for index, alert in enumerate(self.alerts):
            self.tabs.add_tab(Tab(label=self.build_tab_label(alert), id=f'alert-{index}'))
        self.tabs.active = 'alert-0'

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:  # type: ignore[override]
        if event.tab.id is None:
            return
        self.selected_index = int(event.tab.id.removeprefix('alert-'))
        self.update_selected_alert()

    def update_selected_alert(self) -> None:
        alert = self.alerts[self.selected_index]
        severity_color = alert_severity_color(self.app.theme_variables, alert)

        alert_count = len(self.alerts)
        self.border_title = f'{alert_count} Weather Alert{"s" if alert_count != 1 else ""}'
        self.border_subtitle = None
        self.apply_frame_color(severity_color)

        self.body.update(Text.from_markup(self.build_body(alert, severity_color)))
        self.post_message(WeatherAlertSelected(alert=alert))

    def build_tab_label(self, alert: Alert) -> Text:
        severity = (alert.severity or '').strip()
        condition = self.condition_name(alert)
        if severity.lower() == 'unknown':
            return Text.from_markup(escape(condition))

        severity_color = alert_severity_color(self.app.theme_variables, alert)
        if severity_color:
            severity_text = escape(severity.title() or 'Alert')
            return Text.from_markup(f'[bold {severity_color}]{severity_text}[/] {escape(condition)}')
        return Text.from_markup(f'[bold]{escape(severity.title() or "Alert")}[/] {escape(condition)}')

    def build_body(self, alert: Alert, severity_color: str | None) -> str:
        headline = (alert.headline or self.condition_name(alert)).strip()
        if severity_color:
            headline_markup = f'[bold italic {severity_color}]{escape(headline)}[/]'
        else:
            headline_markup = f'[bold italic]{escape(headline)}[/]'
        return f'{headline_markup}\n{self.build_timing_line(alert)}'

    def build_timing_line(self, alert: Alert) -> str:
        condition = self.condition_name(alert)
        onset = self.to_local_time(alert.onset)
        end = self.to_local_time(alert.expires)

        if onset is not None and end is not None:
            line = (
                f'[dim italic]Active from[/] [i]{self.fmt_clock(onset)}[/i] '
                f'[dim italic]until[/] [i]{self.fmt_clock(end)}[/i]'
            )
        elif onset is not None:
            line = f'[dim italic]Active from[/] [i]{self.fmt_clock(onset)}[/i]'
        elif end is not None:
            line = f'[dim italic]Active until[/] [i]{self.fmt_clock(end)}[/i]'
        else:
            line = f'[dim italic]{escape(condition)} timing not published[/]'

        url = (alert.url or '').strip()
        if url:
            line = f'{line}  [link={url}][dim underline]View official warning[/][/]'
        return line

    def condition_name(self, alert: Alert) -> str:
        words = (alert.event or alert.headline or 'Weather Alert').replace('_', ' ').split()
        while words and words[0].lower().rstrip(':') in ALERT_PREFIX_WORDS:
            words.pop(0)

        condition = ' '.join(words).strip()
        if condition.lower().endswith(' warning'):
            condition = condition[:-8].strip()
        if not condition:
            return 'Weather Alert'
        if condition.islower():
            return condition.title()
        return condition

    def to_local_time(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value
        return value.astimezone()

    def fmt_clock(self, value: datetime) -> str:
        # Return day name, date, and 24-hour time
        return value.strftime('%H:%M %A')

    def apply_frame_color(self, color: str | None) -> None:
        if color:
            self.set_styles(f'border: round {color}; border-title-color: {color};')


class WeatherAlertDetailsSidebar(VerticalScroll):
    """Docked reader for the selected alert's full published text."""

    DEFAULT_CSS = """
    WeatherAlertDetailsSidebar {
        dock: right;
        width: 56;
        height: 100%;
        margin: 2 2 2 0;
        background: $background;
        border: round $primary;
    }

    #weather-alert-details {
        width: 100%;
        padding: 0 1;
    }
    """

    def __init__(self, *, id: str = 'weather-alert-details-sidebar') -> None:
        super().__init__(id=id)
        self.border_title = 'Alert Details'
        self.styles.border_title_align = 'left'

    def compose(self) -> ComposeResult:
        yield Static('', id='weather-alert-details')

    @property
    def content(self) -> Static:
        return self.query_one('#weather-alert-details', Static)

    def update_alert(self, alert: Alert) -> None:
        color = alert_severity_color(self.app.theme_variables, alert)
        if color:
            self.set_styles(f'border: round {color}; border-title-color: {color};')
        self.content.update(Markdown(alert_markdown(alert)))


def alert_markdown(alert: Alert) -> str:
    description = (alert.description or '').strip()
    instruction = (alert.instruction or '').strip()
    headline = (alert.headline or alert.event or 'Weather alert').strip()

    if description and instruction:
        return f'### {headline}\n\n{description}\n\n*{instruction.replace("\n", " ")}*'
    if description:
        return f'### {headline}\n\n{description}'
    if instruction:
        return f'### {headline}\n\n*{instruction.replace("\n", " ")}*'
    return f'### {headline}'
