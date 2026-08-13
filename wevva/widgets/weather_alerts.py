"""Compact weather warning display."""

from __future__ import annotations

from datetime import datetime
import re

from rich.markdown import Markdown
from rich.markup import escape
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Static, Tab, Tabs

from wevva.alerts import Alert
from wevva.messages import NearbyTropicalSystemSelected, WeatherAlertSelected
from wevva.services.tropical import NearbyTropicalSystem
from wevva.widgets.tropical_systems import (
    TropicalSystemDetailsTable,
    build_tropical_system_text,
    build_tropical_tab_label,
)

SEVERITY_THEME_KEYS: dict[str, str] = {
    'extreme': 'error',
    'moderate': 'warning',
    'minor': 'accent',
    'red': 'error',
    'yellow': 'accent',
    'green': 'accent',
}

ORANGE_SEVERITIES = {'severe', 'orange', 'amber'}

_MARKDOWN_LIST_ITEM = re.compile(
    r'^(?P<indent>[ \t]*)(?P<marker>[-+*]|\d+[.)]|•)\s+(?P<body>.*?)\s*$',
)
_NWS_SECTION_LABEL = re.compile(r'^[A-Z][A-Z /&-]*\.\.\.')
_NWS_ADDITIONAL_DETAILS = re.compile(r'^ADDITIONAL DETAILS\.\.\.')

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
        border-title-style: bold;
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

    def __init__(
        self,
        alerts: list[Alert],
        *,
        tropical_systems: list[NearbyTropicalSystem] | None = None,
        id: str | None = None,
    ):
        super().__init__(id=id)
        self.alerts = alerts
        self.tropical_systems = tropical_systems or []
        self.items: list[NearbyTropicalSystem | Alert] = [*self.tropical_systems, *self.alerts]
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
        for index, item in enumerate(self.items):
            self.tabs.add_tab(Tab(label=self.build_tab_label(item), id=f'alert-item-{index}'))
        self.tabs.active = 'alert-item-0'

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:  # type: ignore[override]
        if event.tab.id is None:
            return
        self.selected_index = int(event.tab.id.removeprefix('alert-item-'))
        self.update_selected_alert()

    def update_selected_alert(self) -> None:
        item = self.items[self.selected_index]
        if isinstance(item, NearbyTropicalSystem):
            accent = self.app.theme_variables.get('text-accent')
            self.border_title = self.panel_title()
            self.border_subtitle = None
            self.apply_frame_color(accent)
            self.body.update(build_tropical_system_text(item, accent=accent))
            self.post_message(NearbyTropicalSystemSelected(system=item))
            return

        alert = item
        severity_color = alert_severity_color(self.app.theme_variables, alert)
        self.border_title = self.panel_title()
        self.border_subtitle = None
        self.apply_frame_color(severity_color)

        self.body.update(Text.from_markup(self.build_body(alert, severity_color)))
        self.post_message(WeatherAlertSelected(alert=alert))

    def panel_title(self) -> str:
        """Describe the combined panel without treating storms as warnings."""
        titles = []
        tropical_count = len(self.tropical_systems)
        alert_count = len(self.alerts)
        if tropical_count:
            titles.append(f'{tropical_count} Tropical System Alert{"s" if tropical_count != 1 else ""}')
        if alert_count:
            titles.append(f'{alert_count} Severe Weather Alert{"s" if alert_count != 1 else ""}')
        return ' · '.join(titles)

    def build_tab_label(self, item: NearbyTropicalSystem | Alert) -> Text:
        if isinstance(item, NearbyTropicalSystem):
            return build_tropical_tab_label(item, accent=self.app.theme_variables.get('text-accent'))

        alert = item
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
                f'[dim italic]Active from[/] [i]{self.fmt_clock(onset)}[/i] [dim italic]until[/] [i]{self.fmt_clock(end)}[/i]'
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
    """Docked reader for selected warning or tropical-system details."""

    DEFAULT_CSS = """
    WeatherAlertDetailsSidebar {
        dock: right;
        width: 40;
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
        tropical_details = TropicalSystemDetailsTable()
        tropical_details.display = False
        yield tropical_details

    @property
    def content(self) -> Static:
        return self.query_one('#weather-alert-details', Static)

    @property
    def tropical_details(self) -> TropicalSystemDetailsTable:
        return self.query_one(TropicalSystemDetailsTable)

    def update_alert(self, alert: Alert) -> None:
        self.border_title = 'Alert Details'
        self.content.display = True
        self.tropical_details.display = False
        color = alert_severity_color(self.app.theme_variables, alert)
        if color:
            self.set_styles(f'border: round {color}; border-title-color: {color};')
        self.content.update(Markdown(alert_markdown(alert)))

    def update_tropical_system(self, nearby: NearbyTropicalSystem) -> None:
        """Show supplementary facts for the selected nearby tropical report."""
        self.border_title = 'Tropical System Details'
        accent = self.app.theme_variables.get('text-accent')
        if accent:
            self.set_styles(f'border: round {accent}; border-title-color: {accent};')
        self.content.display = False
        self.tropical_details.update_system(nearby)
        self.tropical_details.display = True


def alert_markdown(alert: Alert) -> str:
    description = _normalise_alert_markdown(alert.description or '')
    instruction = _normalise_alert_markdown(alert.instruction or '')
    headline = (alert.headline or alert.event or 'Weather alert').strip()

    if description and instruction:
        return f'### {headline}\n\n{description}\n\n{instruction}'
    if description:
        return f'### {headline}\n\n{description}'
    if instruction:
        return f'### {headline}\n\n{instruction}'
    return f'### {headline}'


def _normalise_alert_markdown(value: str) -> str:
    """Preserve provider Markdown while making indented CAP lists render as lists."""
    lines = value.replace('\r\n', '\n').replace('\r', '\n').strip().split('\n')
    normalised: list[str] = []
    previous_kind: str | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            normalised.append('')
            continue

        list_item = _MARKDOWN_LIST_ITEM.match(line)
        if list_item is not None:
            if previous_kind not in {'list', 'nws-list', 'nws-additional-details', 'nws-sublist'} and normalised and normalised[-1]:
                normalised.append('')
            marker = list_item.group('marker')
            bullet = marker if marker[0].isdigit() else '-'
            body = list_item.group('body')
            is_nws_sublist = (
                previous_kind in {'nws-additional-details', 'nws-sublist'}
                and marker in {'-', '+', '•'}
            )
            if is_nws_sublist:
                normalised.append(f'  {bullet} {body}')
                previous_kind = 'nws-sublist'
                continue
            normalised.append(f'{bullet} {body}')
            if _NWS_ADDITIONAL_DETAILS.match(body):
                previous_kind = 'nws-additional-details'
            elif _NWS_SECTION_LABEL.match(body):
                previous_kind = 'nws-list'
            else:
                previous_kind = 'list'
            continue

        if previous_kind == 'nws-list':
            normalised.append(f'  {stripped}')
            continue

        if previous_kind == 'nws-additional-details':
            normalised.append(f'  {stripped}')
            continue

        if previous_kind == 'nws-sublist':
            normalised.append(f'    {stripped}')
            continue

        if previous_kind == 'list' and normalised and normalised[-1]:
            normalised.append('')
        normalised.append(line.rstrip())
        previous_kind = 'text'

    return '\n'.join(normalised).strip()
