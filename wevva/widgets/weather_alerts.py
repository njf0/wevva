"""Compact weather warning display."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from rich.console import Group
from rich.markup import escape
from rich.rule import Rule
from rich.style import Style
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.events import Click, Key, Resize
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Static, Tab, Tabs
from wevva.alerts import Alert
from wevva.geography import short_location_name
from wevva.messages import WeatherAlertSelected
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


def alert_condition_name(alert: Alert) -> str:
    """Return a concise provider-neutral event name."""

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


def alert_severity_surface_color(
    theme: dict[str, str],
    alert: Alert,
) -> str | None:
    """Return a darker semantic shade for warning pixels over land."""

    severity = (alert.severity or '').strip().lower()
    if severity in ORANGE_SEVERITIES:
        return (
            interpolated_hex(
                theme.get('warning-darken-2') or theme.get('warning'),
                theme.get('error-darken-2') or theme.get('error'),
            )
            or theme.get('error')
        )

    severity_key = SEVERITY_THEME_KEYS.get(severity)
    if severity_key is None:
        return theme.get('accent-darken-2') or theme.get('accent')
    return theme.get(f'{severity_key}-darken-2') or theme.get(severity_key)


def alert_tab_label(theme: dict[str, str], alert: Alert) -> Text:
    """Build the shared compact label used by warning tab selectors."""

    severity = (alert.severity or '').strip()
    condition = alert_condition_name(alert)
    if severity.lower() == 'unknown':
        return Text.from_markup(escape(condition))

    severity_color = alert_severity_color(theme, alert)
    # Keep the separating space inside the styled span: Textual's tab-label
    # conversion trims whitespace which begins a new Rich style segment.
    if severity_color:
        severity_text = escape(severity.title() or 'Alert')
        return Text.from_markup(
            f'[bold {severity_color}]{severity_text} [/]{escape(condition)}'
        )
    return Text.from_markup(
        f'[bold]{escape(severity.title() or "Alert")} [/]{escape(condition)}'
    )


def alert_collection_title(alert_count: int) -> str:
    """Describe a collection of applicable severe-weather alerts."""

    return f'{alert_count} Severe Weather Alert{"s" if alert_count != 1 else ""}'


def _alert_location_context(
    app: Any,
) -> tuple[float | None, float | None, str, str | None]:
    """Resolve the forecast point and selected-location map context."""

    selected_location = getattr(app, 'location', None)
    forecast_location = getattr(app, 'forecast_metadata', None)
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


class WeatherAlertPreviewBody(Static):
    """Focusable preview body which requests the full warning reader."""

    can_focus = True

    class OpenRequested(Message):
        """Request the modal reader for the currently selected warning."""

    def on_mount(self) -> None:
        self.tooltip = 'Open full weather warning'

    def on_click(self, event: Click) -> None:
        event.stop()
        self.post_message(self.OpenRequested())

    def on_key(self, event: Key) -> None:
        if event.key in {'enter', 'space'}:
            event.stop()
            self.post_message(self.OpenRequested())


class WeatherAlertsPanel(Container):
    """Compact tabbed alert preview for a roomy primary forecast."""

    DEFAULT_CSS = """
    WeatherAlertsPanel {
        layout: vertical;
        height: 6;
        width: 100%;
        max-width: 98;
        min-width: 0;
        border: round $primary;
        border-title-color: $primary;
        border-title-style: bold;
        border-title-align: center;
        margin: 0;
        hatch: right $background-lighten-1;
    }

    #weather-alert-tabs {
        width: 100%;
    }

    #weather-alert-body {
        width: 100%;
        height: 2;
        padding: 0 1;
        text-align: left;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }

    WeatherAlertsPanel.-wrap-headline #weather-alert-body {
        text-wrap: wrap;
    }

    #weather-alert-body:focus {
        background: $boost;
        text-style: underline;
    }
    """

    def __init__(
        self,
        alerts: list[Alert],
        *,
        id: str | None = None,
    ):
        super().__init__(id=id)
        self.alerts = alerts
        self.selected_index = 0

    def compose(self) -> ComposeResult:
        tabs = [
            Tab(
                label=self.build_tab_label(alert),
                id=f'alert-item-{index}',
            )
            for index, alert in enumerate(self.alerts)
        ]
        yield Tabs(
            *tabs,
            active='alert-item-0' if tabs else None,
            id='weather-alert-tabs',
        )
        yield WeatherAlertPreviewBody('', id='weather-alert-body')

    @property
    def tabs(self) -> Tabs:
        return self.query_one(Tabs)

    @property
    def body(self) -> WeatherAlertPreviewBody:
        return self.query_one('#weather-alert-body', WeatherAlertPreviewBody)

    def on_mount(self) -> None:
        if self.alerts:
            self.update_selected_alert()

    def set_headline_wrapping(self, enabled: bool) -> None:
        """Allow the full headline to occupy the body's available rows."""

        self.set_class(enabled, '-wrap-headline')

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:  # type: ignore[override]
        if event.tab.id is None:
            return
        self.selected_index = int(event.tab.id.removeprefix('alert-item-'))
        self.update_selected_alert()

    def update_selected_alert(self) -> None:
        alert = self.alerts[self.selected_index]
        severity_color = alert_severity_color(self.app.theme_variables, alert)
        self.border_title = self.panel_title()
        self.border_subtitle = None
        self.apply_frame_color(severity_color)

        self.body.update(Text.from_markup(self.build_body(alert, severity_color)))
        self.post_message(WeatherAlertSelected(alert=alert))

    def panel_title(self) -> str:
        """Describe the weather-alert collection."""
        return alert_collection_title(len(self.alerts))

    def build_tab_label(self, alert: Alert) -> Text:
        return alert_tab_label(self.app.theme_variables, alert)

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
        return alert_condition_name(alert)

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

    def on_weather_alert_preview_body_open_requested(
        self,
        event: WeatherAlertPreviewBody.OpenRequested,
    ) -> None:
        event.stop()
        self.app.push_screen(
            WeatherAlertsModal(self.alerts, initial_index=self.selected_index)
        )


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

    WeatherAlertDetailsPanel.-unframed {
        border: none;
    }

    #weather-alert-details {
        width: 100%;
        height: auto;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        *,
        framed: bool = True,
        id: str = 'weather-alert-details-panel',
    ) -> None:
        super().__init__(id=id)
        self.framed = framed
        if framed:
            self.border_title = 'Alert Details'
            self.styles.border_title_align = 'left'
        else:
            self.add_class('-unframed')

    def compose(self) -> ComposeResult:
        yield Static('', id='weather-alert-details')

    @property
    def content(self) -> Static:
        return self.query_one('#weather-alert-details', Static)


class WeatherAlertPresentation(Container):
    """Synchronized provider document and optional selected-warning map."""

    DEFAULT_CSS = """
    WeatherAlertPresentation {
        layout: horizontal;
        width: 100%;
        height: 1fr;
        min-height: 0;
    }

    WeatherAlertPresentation WeatherAlertDetailsPanel {
        width: 1fr;
        height: 100%;
        min-width: 0;
    }

    WeatherAlertPresentation WarningAreaScope {
        width: 40%;
        min-width: 24;
        max-width: 42;
        height: 100%;
        margin: 0 0 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield WeatherAlertDetailsPanel(
            framed=False,
            id='weather-alert-reader-details',
        )
        yield WarningAreaScope(
            fill_height=True,
            id='weather-alert-reader-warning-area',
        )

    @property
    def details(self) -> WeatherAlertDetailsPanel:
        return self.query_one('#weather-alert-reader-details', WeatherAlertDetailsPanel)

    @property
    def warning_area(self) -> WarningAreaScope:
        return self.query_one('#weather-alert-reader-warning-area', WarningAreaScope)

    def update_alert(self, alert: Alert, *, warning_color: str | None) -> None:
        """Update every selected-alert surface as one presentation change."""

        self.details.content.update(alert_renderable(alert, include_timing=True))
        self.details.scroll_home(animate=False)
        latitude, longitude, location_name, country_code = _alert_location_context(
            self.app
        )
        self.warning_area.update_alert(
            alert,
            location_latitude=latitude,
            location_longitude=longitude,
            location_name=location_name,
            country_code=country_code,
            warning_color=warning_color,
        )
        self._sync_warning_area_visibility()

    def on_resize(self, event: Resize) -> None:
        self._sync_warning_area_visibility()

    def _sync_warning_area_visibility(self) -> None:
        """Give compact, unsupported widths entirely to the document."""

        self.warning_area.display = (
            self.app.size.width >= 80 and self.warning_area.has_geometry
        )


class WeatherAlertReaderSelected(Message):
    """Report the alert now shown by a complete warning reader."""

    def __init__(self, alert: Alert) -> None:
        super().__init__()
        self.alert = alert


class WeatherAlertsReader(Container):
    """Tabbed selector whose body is the complete provider warning document."""

    DEFAULT_CSS = """
    WeatherAlertsReader {
        layout: vertical;
        width: 100%;
        height: 100%;
        min-height: 0;
    }

    #weather-alert-reader-tabs {
        width: 100%;
        height: 2;
    }

    """

    def __init__(
        self,
        alerts: list[Alert],
        *,
        initial_index: int = 0,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self.alerts = list(alerts)
        self.selected_index = min(
            max(0, int(initial_index)),
            max(0, len(self.alerts) - 1),
        )

    def compose(self) -> ComposeResult:
        tabs = [
            Tab(
                label=alert_tab_label(self.app.theme_variables, alert),
                id=f'alert-item-{index}',
            )
            for index, alert in enumerate(self.alerts)
        ]
        yield Tabs(
            *tabs,
            active=(f'alert-item-{self.selected_index}' if tabs else None),
            id='weather-alert-reader-tabs',
        )
        yield WeatherAlertPresentation(id='weather-alert-reader-presentation')

    @property
    def tabs(self) -> Tabs:
        return self.query_one('#weather-alert-reader-tabs', Tabs)

    @property
    def details(self) -> WeatherAlertDetailsPanel:
        return self.presentation.details

    @property
    def presentation(self) -> WeatherAlertPresentation:
        return self.query_one(
            '#weather-alert-reader-presentation', WeatherAlertPresentation
        )

    @property
    def warning_area(self) -> WarningAreaScope:
        return self.presentation.warning_area

    def on_mount(self) -> None:
        if self.alerts:
            self._show_alert(self.selected_index)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:  # type: ignore[override]
        if event.tab.id is None:
            return
        self._show_alert(int(event.tab.id.removeprefix('alert-item-')))

    def _show_alert(self, index: int) -> None:
        if not self.alerts:
            return
        self.selected_index = min(max(0, index), len(self.alerts) - 1)
        alert = self.alerts[self.selected_index]
        severity_color = alert_severity_color(self.app.theme_variables, alert)
        self.presentation.update_alert(alert, warning_color=severity_color)
        self.post_message(WeatherAlertReaderSelected(alert))


class WeatherAlertsModal(ModalScreen[None]):
    """Tabbed alert reader whose provider document scrolls independently."""

    BINDINGS = [('escape', 'dismiss', 'Close')]

    DEFAULT_CSS = """
    WeatherAlertsModal {
        width: 100%;
        height: 100%;
        align: center middle;
        background: $background 65%;
    }

    #weather-alert-modal {
        layout: vertical;
        width: 92%;
        max-width: 112;
        height: 88%;
        max-height: 48;
        min-height: 12;
        padding: 1 2;
        border: round $primary;
        border-title-color: $primary;
        border-title-style: bold;
        border-title-align: center;
        background: $background;
    }

    #weather-alert-modal WeatherAlertsReader {
        width: 100%;
        height: 100%;
    }
    """

    def __init__(self, alerts: list[Alert], *, initial_index: int = 0) -> None:
        super().__init__()
        self.alerts = list(alerts)
        self.initial_index = initial_index

    def compose(self) -> ComposeResult:
        with Container(id='weather-alert-modal') as dialog:
            dialog.border_title = alert_collection_title(len(self.alerts))
            yield WeatherAlertsReader(
                self.alerts,
                initial_index=self.initial_index,
                id='weather-alert-modal-reader',
            )

    def on_mount(self) -> None:
        if self.alerts:
            selected_index = min(
                max(0, int(self.initial_index)),
                len(self.alerts) - 1,
            )
            self._apply_selected_alert_frame(self.alerts[selected_index])

    def on_weather_alert_reader_selected(
        self,
        event: WeatherAlertReaderSelected,
    ) -> None:
        event.stop()
        self._apply_selected_alert_frame(event.alert)

    def _apply_selected_alert_frame(self, alert: Alert) -> None:
        color = alert_severity_color(self.app.theme_variables, alert)
        if color:
            self.query_one('#weather-alert-modal', Container).set_styles(
                f'border: round {color}; border-title-color: {color};'
            )


class WeatherAlertSummary(Static):
    """Bordered warning presence control for the primary weather layout."""

    can_focus = True

    DEFAULT_CSS = """
    WeatherAlertSummary {
        width: 100%;
        height: 3;
        min-width: 0;
        padding: 0 1;
        border: round $warning;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }

    WeatherAlertSummary:focus {
        background: $boost;
        text-style: underline;
    }
    """

    def __init__(self, alerts: list[Alert]) -> None:
        super().__init__('')
        self.alerts = list(alerts)

    def on_mount(self) -> None:
        colour = alert_severity_color(self.app.theme_variables, self.alerts[0])
        if colour:
            self.set_styles(
                f'border: round {colour}; border-title-color: {colour};'
            )
        self.update(self._label())
        self.tooltip = 'Open weather warning details'

    def _label(self) -> Text:
        alert = self.alerts[0]
        severity = (alert.severity or '').strip().title()
        condition = alert_condition_name(alert)
        event = (alert.event or '').strip().lower()
        warning_suffix = ' Warning' if event.endswith(' warning') else ''
        colour = alert_severity_color(self.app.theme_variables, alert)
        label = Text()
        if severity and severity.lower() != 'unknown':
            label.append(severity, style=f'bold {colour}' if colour else 'bold')
            label.append(' ')
        label.append(f'{condition}{warning_suffix}', style='bold')
        remaining = len(self.alerts) - 1
        if remaining:
            label.append(f' · +{remaining} more', style='dim')
        return label

    def on_click(self, event: Click) -> None:
        event.stop()
        self._open()

    def on_key(self, event: Key) -> None:
        if event.key in {'enter', 'space'}:
            event.stop()
            self._open()

    def _open(self) -> None:
        self.app.push_screen(WeatherAlertsModal(self.alerts))


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
        return _alert_location_context(self.app)

    def update_alert(self, alert: Alert) -> None:
        self.details.display = True
        self.details.border_title = 'Alert Details'
        self.content.display = True
        color = alert_severity_color(self.app.theme_variables, alert)
        if color:
            self.details.set_styles(f'border: round {color}; border-title-color: {color};')
        self.content.update(alert_renderable(alert, include_timing=True))
        latitude, longitude, location_name, country_code = self._location_context()
        self.query_one(WarningAreaScope).update_alert(
            alert,
            location_latitude=latitude,
            location_longitude=longitude,
            location_name=location_name,
            country_code=country_code,
            warning_color=color,
        )

def alert_markdown(alert: Alert) -> str:
    """Return a conservatively de-wrapped text representation for compatibility."""
    description = _normalise_alert_text(alert.description or '')
    instruction = _normalise_alert_text(alert.instruction or '')
    headline = (alert.headline or alert.event or 'Weather alert').strip()
    sections = [f'### {headline}']
    if area := alert_area_text(alert):
        sections.append(f'Affects: {area}')
    if description:
        sections.append(description)
    if instruction:
        sections.append(instruction)
    content = '\n\n'.join(sections)

    if url := (alert.url or '').strip():
        return f'{content}\n\n[View official warning]({url})'
    return content


def alert_renderable(alert: Alert, *, include_timing: bool = False):
    """Render authoritative provider prose without interpreting it as Markdown."""
    headline = (alert.headline or alert.event or 'Weather alert').strip()
    heading = Text(headline)
    heading.stylize('markdown.h3')
    renderables: list[object] = [heading]
    if area := alert_area_text(alert):
        area_line = Text()
        area_line.append('Affects: ', style='dim italic')
        area_line.append(area, style='italic')
        renderables.append(area_line)
    if include_timing:
        renderables.extend((Text(''), alert_timing_renderable(alert)))
    if alert.description and alert.description.strip():
        renderables.extend((Text(''), *alert_text_renderables(alert.description)))
    if alert.instruction and alert.instruction.strip():
        renderables.extend((Text(''), *alert_text_renderables(alert.instruction, base_style='italic')))
    official_link = _official_warning_link(alert)
    if official_link is not None:
        renderables.extend((Text(''), official_link))
    return Group(*renderables)


def alert_area_text(alert: Alert) -> str:
    """Return complete, de-duplicated provider area names for alert prose."""

    areas: list[str] = []
    seen: set[str] = set()
    for raw_name in alert.area_names:
        name = ' '.join(raw_name.split())
        key = name.casefold()
        if not name or key in seen:
            continue
        seen.add(key)
        areas.append(name)
    return ', '.join(areas)


def alert_timing_renderable(alert: Alert) -> object:
    """Render concise local timing as a centred single-line timeline."""

    def local_time(value: datetime | None) -> datetime | None:
        if value is None or value.tzinfo is None:
            return value
        return value.astimezone()

    def clock(value: datetime) -> str:
        return value.strftime('%H:%M %A')

    onset = local_time(alert.onset)
    end = local_time(alert.expires)
    if onset is not None and end is not None:
        timeline = Table.grid(expand=True, padding=(0, 1))
        timeline.add_column(no_wrap=True)
        timeline.add_column(ratio=1)
        timeline.add_column(no_wrap=True)
        timeline.add_row(
            Text(clock(onset), style='italic'),
            Rule(style='dim', characters='─'),
            Text(clock(end), style='italic'),
        )
        return timeline

    line = Text(justify='center')
    if onset is not None:
        line.append('From ', style='dim italic')
        line.append(clock(onset), style='italic')
    elif end is not None:
        line.append('Until ', style='dim italic')
        line.append(clock(end), style='italic')
    else:
        line.append(
            f'{alert_condition_name(alert)} timing not published',
            style='dim italic',
        )
    return line


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


def alert_text_renderables(value: str, *, base_style: str = '') -> list[object]:
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
