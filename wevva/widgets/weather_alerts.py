"""Compact weather warning display."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from rich.console import Group
from rich.markup import escape
from rich.style import Style
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Static, Tab, Tabs
from wevva.alerts import Alert
from wevva.geography import short_location_name
from wevva.messages import NearbyTropicalSystemSelected, WeatherAlertSelected
from wevva.services.tropical import NearbyTropicalSystem
from wevva.widgets.tropical_systems import (
    build_tropical_system_text,
    build_tropical_tab_label,
)
from wevva.widgets.warning_area import WarningAreaScope

SEVERITY_THEME_KEYS: dict[str, str] = {
    'extreme': 'error',
    'moderate': 'warning',
    'minor': 'accent',
    'red': 'error',
    'yellow': 'accent',
    'green': 'accent',
}

ORANGE_SEVERITIES = {'severe', 'orange', 'amber'}

_ALERT_LIST_ITEM = re.compile(
    r'^(?P<indent>[ \t]*)(?P<marker>[-+*]|\d+[.)]|●)\s+(?P<body>.*?)\s*$',
)
_ALERT_SUBSECTION = re.compile(r'^[ \t]*\*[ \t]+(?P<body>[A-Z][A-Z /&-]*:)[ \t]*$')
_ALERT_HEADING_UNDERLINE = re.compile(r'^[ \t]*-{3,}[ \t]*$')

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


class WeatherAlertDetailsPanel(VerticalScroll):
    """Independently scrolling prose panel for the selected alert."""

    DEFAULT_CSS = """
    WeatherAlertDetailsPanel {
        width: 100%;
        height: 1fr;
        min-height: 3;
        margin: 0;
        background: $background;
        border: round $primary;
        scrollbar-size-vertical: 1;
    }

    #weather-alert-details {
        width: 100%;
        height: auto;
        padding: 0 1;
    }
    """

    def __init__(self, *, id: str = 'weather-alert-details-panel') -> None:
        super().__init__(id=id)
        self.border_title = 'Alert Details'
        self.styles.border_title_align = 'left'

    def compose(self) -> ComposeResult:
        yield Static('', id='weather-alert-details')

    @property
    def content(self) -> Static:
        return self.query_one('#weather-alert-details', Static)


class WeatherAlertDetailsSidebar(Container):
    """Optional scrolling CAP reader with its geographic warning scope."""

    DEFAULT_CSS = """
    WeatherAlertDetailsSidebar {
        dock: right;
        width: 40;
        height: 100%;
        margin: 2 2 2 0;
        layout: vertical;
        background: $background;
        hatch: right $background-lighten-1;
    }

    """

    def __init__(self, *, id: str = 'weather-alert-details-sidebar') -> None:
        super().__init__(id=id)

    def compose(self) -> ComposeResult:
        details = WeatherAlertDetailsPanel()
        details.display = False
        yield details
        yield WarningAreaScope()

    @property
    def details(self) -> WeatherAlertDetailsPanel:
        return self.query_one(WeatherAlertDetailsPanel)

    @property
    def content(self) -> Static:
        return self.details.content

    def _location_context(self) -> tuple[float | None, float | None, str, str | None]:
        selected_location = getattr(self.app, 'location', None)
        forecast_location = getattr(self.app, 'forecast_metadata', None)
        latitude = getattr(forecast_location, 'latitude', None)
        longitude = getattr(forecast_location, 'longitude', None)
        if latitude is None:
            latitude = getattr(selected_location, 'latitude', None)
        if longitude is None:
            longitude = getattr(selected_location, 'longitude', None)
        return (
            latitude,
            longitude,
            short_location_name(selected_location),
            getattr(selected_location, 'country_code', None),
        )

    def update_alert(self, alert: Alert) -> None:
        self.details.display = True
        self.details.border_title = 'Alert Details'
        self.content.display = True
        color = alert_severity_color(self.app.theme_variables, alert)
        if color:
            self.details.set_styles(f'border: round {color}; border-title-color: {color};')
        self.content.update(alert_renderable(alert))
        latitude, longitude, location_name, country_code = self._location_context()
        self.query_one(WarningAreaScope).update_alert(
            alert,
            location_latitude=latitude,
            location_longitude=longitude,
            location_name=location_name,
            country_code=country_code,
            warning_color=color,
        )

    def update_tropical_system(self, _nearby: NearbyTropicalSystem) -> None:
        """Hide CAP-only details while a local tropical tab is selected."""
        self.details.display = False
        self.query_one(WarningAreaScope).clear()


def alert_markdown(alert: Alert) -> str:
    """Return a conservatively de-wrapped text representation for compatibility."""
    description = _normalise_alert_text(alert.description or '')
    instruction = _normalise_alert_text(alert.instruction or '')
    headline = (alert.headline or alert.event or 'Weather alert').strip()

    if description and instruction:
        content = f'### {headline}\n\n{description}\n\n{instruction}'
    elif description:
        content = f'### {headline}\n\n{description}'
    elif instruction:
        content = f'### {headline}\n\n{instruction}'
    else:
        content = f'### {headline}'

    if url := (alert.url or '').strip():
        return f'{content}\n\n[View official warning]({url})'
    return content


def alert_renderable(alert: Alert):
    """Render authoritative provider prose without interpreting it as Markdown."""
    headline = (alert.headline or alert.event or 'Weather alert').strip()
    heading = Text(headline)
    heading.stylize('markdown.h3')
    renderables: list[object] = [heading]
    if alert.description and alert.description.strip():
        renderables.extend((Text(''), *_alert_text_renderables(alert.description)))
    if alert.instruction and alert.instruction.strip():
        renderables.extend((Text(''), *_alert_text_renderables(alert.instruction, base_style='italic')))
    official_link = _official_warning_link(alert)
    if official_link is not None:
        renderables.extend((Text(''), official_link))
    return Group(*renderables)


def _official_warning_link(alert: Alert) -> Text | None:
    """Build the detail-reader footer link, when an official warning URL exists."""
    url = (alert.url or '').strip()
    if not url:
        return None
    link = Text('View official warning', style='markdown.link')
    link.stylize(Style(link=url, underline=True))
    return link


@dataclass(frozen=True, slots=True)
class _AlertTextBlock:
    kind: str
    text: str = ''
    marker: str = ''


def _alert_text_blocks(value: str) -> list[_AlertTextBlock]:
    """Join source hard wraps while retaining obvious bulletin structure."""
    lines = value.replace('\r\n', '\n').replace('\r', '\n').strip().split('\n')
    blocks: list[_AlertTextBlock] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            blocks.append(_AlertTextBlock('blank'))
            index += 1
            continue

        if index + 1 < len(lines) and _ALERT_HEADING_UNDERLINE.fullmatch(lines[index + 1]):
            blocks.append(_AlertTextBlock('heading', stripped))
            index += 2
            continue

        if subsection := _ALERT_SUBSECTION.fullmatch(line):
            blocks.append(_AlertTextBlock('subsection', subsection.group('body'), '●'))
            index += 1
            continue

        list_item = _ALERT_LIST_ITEM.fullmatch(line)
        if list_item is not None:
            marker = list_item.group('marker')
            display_marker = marker if marker[0].isdigit() else '●'
            parts = [list_item.group('body')]
            item_indent = len(list_item.group('indent').expandtabs(4))
            index += 1
            while index < len(lines) and not _starts_alert_block(lines, index):
                continuation = lines[index]
                if item_indent and continuation == continuation.lstrip():
                    break
                parts.append(continuation.strip())
                index += 1
            blocks.append(_AlertTextBlock('list', ' '.join(parts), display_marker))
            continue

        parts = [stripped]
        index += 1
        while index < len(lines) and not _starts_alert_block(lines, index):
            parts.append(lines[index].strip())
            index += 1
        blocks.append(_AlertTextBlock('text', ' '.join(parts)))

    while blocks and blocks[-1].kind == 'blank':
        blocks.pop()
    return blocks


def _starts_alert_block(lines: list[str], index: int) -> bool:
    line = lines[index]
    if not line.strip() or _ALERT_LIST_ITEM.fullmatch(line):
        return True
    if index + 1 < len(lines) and _ALERT_HEADING_UNDERLINE.fullmatch(lines[index + 1]):
        return True
    return False


def _normalise_alert_text(value: str) -> str:
    """Serialize the minimally normalised bulletin without Markdown inference."""
    lines: list[str] = []
    for block in _alert_text_blocks(value):
        if block.kind == 'blank':
            lines.append('')
        elif block.kind == 'heading':
            lines.extend((block.text, '-' * len(block.text)))
        elif block.kind == 'subsection':
            lines.append(f'* {block.text}')
        elif block.kind == 'list':
            marker = block.marker if block.marker[0].isdigit() else '-'
            lines.append(f'{marker} {block.text}')
        else:
            lines.append(block.text)
    return '\n'.join(lines)


def _alert_text_renderables(value: str, *, base_style: str = '') -> list[object]:
    """Turn bulletin blocks into literal Rich text with native wrapping."""
    renderables: list[object] = []
    for block in _alert_text_blocks(value):
        if block.kind == 'blank':
            renderables.append(Text(''))
            continue
        if block.kind == 'heading':
            heading = Text(block.text, style=base_style)
            heading.stylize('markdown.h2')
            renderables.append(heading)
            continue
        if block.kind in {'list', 'subsection'}:
            table = Table.grid(expand=True, padding=0)
            table.add_column(width=2, no_wrap=True)
            table.add_column(ratio=1)
            marker = Text(block.marker, style=base_style)
            body = Text(block.text, style=base_style)
            if block.kind == 'subsection':
                body.stylize('bold')
            table.add_row(marker, body)
            renderables.append(table)
            continue
        renderables.append(Text(block.text, style=base_style))
    return renderables
