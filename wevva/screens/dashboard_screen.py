"""Persistent unified weather dashboard."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import hashlib
from typing import ClassVar

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.events import Resize
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, OptionList, Static, Tab, Tabs
from textual.widgets.option_list import Option

from wevva.conditions import get_condition
from wevva.config import location_key, location_label
from wevva.dashboard_layout import DashboardLayoutBudget, dashboard_layout_for
from wevva.location_metadata import LocationMetadata
from wevva.services.alert_bulletin import BulletinAlert
from wevva.services.country_alerts import country_alert_identity
from wevva.messages import (
    DashboardPlaceActivated,
    DashboardPlacePressed,
    DashboardPlacePreviewed,
    DashboardPlacePreviewEnded,
    DashboardTropicalActivated,
    HourHighlighted,
    WeatherUpdated,
)
from wevva.utils import emoji_prefix, temp_colour
from wevva.widgets.dashboard_daily_forecast import DashboardDailyForecast
from wevva.widgets.dashboard_hourly_forecast import DashboardHourlyForecast
from wevva.widgets.dashboard_world_map import (
    DashboardAlertMarker,
    DashboardWorldMap,
)
from wevva.widgets.saved_locations import SavedLocationWeatherSummary
from wevva.widgets.weather_alerts import alert_condition_name, alert_severity_color
from wevva.utils.country_codes import get_country_name_by_alpha2


class DashboardForecastPanel(Container):
    """Current, hourly, and daily weather for one Dashboard place."""

    DEFAULT_CSS = """
    DashboardForecastPanel {
        width: 32;
        height: 100%;
        min-width: 20;
        border: round $primary;
        border-title-color: $primary;
        padding: 0 1;
        overflow-y: auto;
        background: $background;
    }

    #dashboard-forecast-role {
        width: 100%;
        height: 1;
        color: $text-muted;
        text-style: italic;
    }

    #dashboard-forecast-place {
        width: 100%;
        height: auto;
        min-height: 1;
        text-style: bold;
    }

    #dashboard-current-summary {
        width: 100%;
        height: 4;
        margin: 1 0;
        content-align: left middle;
    }

    DashboardForecastPanel DashboardHourlyForecast {
        width: 100%;
        max-width: 100%;
        height: 2fr;
        min-height: 8;
    }

    DashboardForecastPanel DashboardDailyForecast {
        width: 100%;
        max-width: 100%;
        height: 6;
    }

    #dashboard-hourly-status {
        width: 100%;
        height: 10;
        border: round $primary-muted;
        color: $text-muted;
        text-style: italic;
        content-align: center middle;
        text-align: center;
    }

    #dashboard-open-weather-hint {
        width: 100%;
        height: auto;
        min-height: 1;
        color: $text-muted;
        text-style: italic;
    }

    """

    def compose(self) -> ComposeResult:
        self.border_title = 'Location Forecast'
        yield Static('', id='dashboard-forecast-role')
        yield Static('No location selected', id='dashboard-forecast-place')
        yield Static('Weather summary unavailable', id='dashboard-current-summary')
        yield DashboardHourlyForecast(id='dashboard-hourly-forecast')
        yield Static(
            'Select a place to load its hourly forecast.',
            id='dashboard-hourly-status',
        )
        yield DashboardDailyForecast(id='dashboard-daily-forecast')
        yield Static(
            'Again opens Weather.',
            id='dashboard-open-weather-hint',
        )

    @property
    def hourly_forecast(self) -> DashboardHourlyForecast:
        return self.query_one(
            '#dashboard-hourly-forecast',
            DashboardHourlyForecast,
        )

    @property
    def daily_forecast(self) -> DashboardDailyForecast:
        return self.query_one(
            '#dashboard-daily-forecast',
            DashboardDailyForecast,
        )

    def on_mount(self) -> None:
        self.hourly_forecast.display = False
        self.daily_forecast.display = False

    def set_layout(self, budget: DashboardLayoutBudget) -> None:
        """Apply the weather-rail reductions selected for this viewport."""

        current = self.query_one('#dashboard-current-summary', Static)
        current.styles.height = budget.current_summary_height
        current.styles.margin = (
            (1, 0) if budget.current_summary_height >= 4 else (0, 0)
        )
        self.hourly_forecast.styles.min_height = budget.hourly_min_height
        self.daily_forecast.set_row_count(budget.daily_rows)
        self.query_one('#dashboard-open-weather-hint', Static).display = (
            budget.show_open_hint
        )

    def show_location(
        self,
        location: LocationMetadata | None,
        summary: SavedLocationWeatherSummary | None,
        *,
        role: str,
        temperature_unit: str,
    ) -> None:
        """Render one active, selected, or transiently previewed place."""

        if not self.is_mounted:
            return
        self.query_one('#dashboard-forecast-role', Static).update(role)
        place = 'No location selected' if location is None else location_label(location)
        self.query_one('#dashboard-forecast-place', Static).update(place)
        self.query_one('#dashboard-current-summary', Static).update(
            self._summary_text(summary, temperature_unit=temperature_unit)
        )
        self._show_hourly_status('Select this place to load its hourly forecast.')

    def show_loading(
        self,
        location: LocationMetadata,
        summary: SavedLocationWeatherSummary | None,
        *,
        role: str,
        temperature_unit: str,
    ) -> None:
        """Keep the known current summary visible while loading a snapshot."""

        self.show_location(
            location,
            summary,
            role=role,
            temperature_unit=temperature_unit,
        )
        self._show_hourly_status('Loading hourly forecast…')

    def show_error(
        self,
        location: LocationMetadata,
        summary: SavedLocationWeatherSummary | None,
        *,
        role: str,
        temperature_unit: str,
    ) -> None:
        """Show a retryable preview failure without discarding known current data."""

        self.show_location(
            location,
            summary,
            role=role,
            temperature_unit=temperature_unit,
        )
        self._show_hourly_status(
            'Hourly forecast unavailable.\nSelect another place and return to retry.'
        )

    def show_forecast(
        self,
        location: LocationMetadata,
        event: WeatherUpdated,
        *,
        role: str,
        temperature_unit: str,
    ) -> None:
        """Render one complete app-owned preview in the narrow rail."""

        if not self.is_mounted:
            return
        self.query_one('#dashboard-forecast-role', Static).update(role)
        self.query_one('#dashboard-forecast-place', Static).update(
            location_label(location)
        )
        self._forecast_event = event
        self._forecast_temperature_unit = temperature_unit
        self.show_hour(0)
        self.hourly_forecast.update_forecast(event)
        self.daily_forecast.update_forecast(event)
        self.hourly_forecast.display = True
        self.daily_forecast.display = True
        self.query_one('#dashboard-hourly-status', Static).display = False

    def show_hour(self, index: int) -> None:
        """Update the fixed conditions summary for one highlighted hour."""

        event = getattr(self, '_forecast_event', None)
        if event is None:
            return
        hourly = event.hourly
        point = hourly.get_point(index)
        if point is None:
            return
        temperature_unit = getattr(
            self,
            '_forecast_temperature_unit',
            'celsius',
        )
        temperature = hourly.get_temperature(index)
        feels = hourly.get_feels_temperature(index)
        rain = hourly.get_precipitation_probability(index)
        wind = hourly.get_wind_speed(index)
        gust = hourly.get_wind_gust(index)
        direction = hourly.get_wind_direction(index) or ''
        temp_unit = hourly.forecast_units.get(
            'temperature_2m',
            '°F' if temperature_unit == 'fahrenheit' else '°C',
        )
        wind_unit = hourly.forecast_units.get('wind_speed_10m', '')
        condition = get_condition(point.get('weather_code'))
        time = point.get('time')

        text = Text()
        if isinstance(temperature, (int, float)) and not isinstance(temperature, bool):
            colour = temp_colour(
                temperature,
                scale='theme_temperature',
                hex=True,
                unit=temperature_unit,
                theme_colours=self.app.theme_variables,
            )
            text.append(f'{round(temperature):.0f}{temp_unit}', style=f'bold {colour}')
        else:
            text.append('--', style='italic dim')
        if condition is not None:
            colour = (
                self.app.theme_variables.get(condition.color_var)
                if condition.color_var
                else None
            )
            text.append(' · ', style='dim')
            text.append(
                condition.name,
                style=f'italic {colour}' if colour else 'italic',
            )
        if time is not None:
            text.append(f'\n{time:%a %H:%M}', style='dim')
        if isinstance(feels, (int, float)):
            text.append(f' · Feels {round(feels):.0f}{temp_unit}')
        if isinstance(rain, (int, float)):
            text.append(f'\nRain {round(rain):.0f}%')
        if isinstance(wind, (int, float)):
            direction_label = f'{direction} ' if direction else ''
            text.append(
                f' · Wind {direction_label}{round(wind):.0f}{wind_unit}'
            )
        if isinstance(gust, (int, float)):
            text.append(f'\nGust {round(gust):.0f}{wind_unit}')
        self.query_one('#dashboard-current-summary', Static).update(text)

    def _show_hourly_status(self, message: str) -> None:
        self._forecast_event = None
        self.hourly_forecast.display = False
        self.daily_forecast.display = False
        status = self.query_one('#dashboard-hourly-status', Static)
        status.update(message)
        status.display = True

    def _summary_text(
        self,
        summary: SavedLocationWeatherSummary | None,
        *,
        temperature_unit: str,
    ) -> Text:
        text = Text()
        if summary is None or summary.error:
            text.append('Current summary unavailable', style='italic dim')
            text.append('\nNo new request is made by Dashboard.', style='dim')
            return text

        temperature = summary.temperature
        if isinstance(temperature, (int, float)) and not isinstance(temperature, bool):
            unit = (summary.temperature_unit or '').strip()
            if not unit:
                unit = '°F' if temperature_unit == 'fahrenheit' else '°C'
            colour = temp_colour(
                temperature,
                scale='theme_temperature',
                hex=True,
                unit=temperature_unit,
                theme_colours=self.app.theme_variables,
            )
            text.append(f'{round(temperature):.0f}{unit}', style=f'bold {colour}')
        else:
            text.append('--', style='italic dim')

        condition = summary.condition
        if condition is not None:
            text.append('\n')
            colour = (
                self.app.theme_variables.get(condition.color_var)
                if condition.color_var
                else None
            )
            style = f'italic {colour}' if colour else 'italic'
            if self.app.emoji_enabled and summary.condition_emoji:
                text.append(emoji_prefix(summary.condition_emoji))
            text.append(condition.name, style=style)
        else:
            text.append('\nCondition unavailable', style='italic dim')
        return text


class DashboardAlertList(OptionList):
    """Keep Enter as an explicit open action while click/Space selects."""

    class OpenRequested(Message):
        def __init__(self, option_id: str | None) -> None:
            super().__init__()
            self.option_id = option_id

    class PreviewChanged(Message):
        def __init__(self, option_id: str | None) -> None:
            super().__init__()
            self.option_id = option_id

    def __init__(self, *args, **kwargs) -> None:
        self._previewed_option_id: str | None = None
        super().__init__(*args, **kwargs)

    def _preview_option_id(self) -> str | None:
        index = self._mouse_hovering_over
        if index is None and self.has_focus:
            index = self.highlighted
        if index is None or not 0 <= index < len(self.options):
            return None
        return self.options[index].id

    def _post_preview_if_changed(self) -> None:
        self._post_preview(self._preview_option_id())

    def _post_preview(self, option_id: str | None) -> None:
        if option_id == self._previewed_option_id:
            return
        self._previewed_option_id = option_id
        if self.is_attached:
            self.post_message(self.PreviewChanged(option_id))

    def clear_preview(self) -> None:
        self._mouse_hovering_over = None
        self._post_preview(None)

    def _on_mouse_move(self, event: events.MouseMove) -> None:
        super()._on_mouse_move(event)
        self._post_preview_if_changed()

    def _on_leave(self, event: events.Leave) -> None:
        super()._on_leave(event)
        self._post_preview_if_changed()

    def on_focus(self, _event: events.Focus) -> None:
        self._post_preview_if_changed()

    def on_blur(self, _event: events.Blur) -> None:
        if self._mouse_hovering_over is None:
            self._post_preview(None)
        else:
            self._post_preview_if_changed()

    def watch_highlighted(self, highlighted: int | None) -> None:
        super().watch_highlighted(highlighted)
        self._post_preview_if_changed()

    def on_key(self, event: events.Key) -> None:
        if event.key != 'enter':
            return
        option_id = None
        if self.highlighted is not None and 0 <= self.highlighted < len(self.options):
            option_id = self.options[self.highlighted].id
        event.stop()
        event.prevent_default()
        self.post_message(self.OpenRequested(option_id))


class DashboardAlertsPanel(Container):
    """Stable alert rows and one fixed bulletin preview."""

    class Selected(Message):
        def __init__(self, row: BulletinAlert | None) -> None:
            super().__init__()
            self.row = row

    class OpenRequested(Message):
        def __init__(self, row: BulletinAlert) -> None:
            super().__init__()
            self.row = row

    class Previewed(Message):
        def __init__(self, row: BulletinAlert | None) -> None:
            super().__init__()
            self.row = row

    DEFAULT_CSS = """
    DashboardAlertsPanel {
        width: 28;
        height: 100%;
        min-width: 20;
        border: round $primary;
        border-title-color: $primary;
        padding: 1;
        background: $background;
    }

    #dashboard-alerts-list {
        width: 100%;
        height: 1fr;
        border: none;
        background: $background;
        scrollbar-size-vertical: 1;
    }

    #dashboard-alerts-empty {
        width: 100%;
        height: 1fr;
        color: $text-muted;
        text-style: italic;
        text-align: center;
        content-align: center middle;
    }

    #dashboard-alert-preview {
        width: 100%;
        height: 8;
        margin-top: 1;
        padding: 0 1;
        border: round $primary-muted;
        overflow: hidden;
    }

    #dashboard-alert-open {
        width: 100%;
        min-width: 0;
        height: 3;
        margin-top: 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._rows: tuple[BulletinAlert, ...] = ()
        self._by_option_id: dict[str, BulletinAlert] = {}
        self._selected_identity: tuple[str, str] | None = None
        self._last_text_width = 0

    def compose(self) -> ComposeResult:
        self.border_title = 'Recent Alerts'
        yield DashboardAlertList(id='dashboard-alerts-list')
        yield Static(
            'No current alerts found yet.\n\nThe session bulletin continues checking countries.',
            id='dashboard-alerts-empty',
        )
        yield Static('Select an alert to preview it.', id='dashboard-alert-preview')
        yield Button('Open alert', id='dashboard-alert-open', disabled=True)

    @property
    def alert_list(self) -> DashboardAlertList:
        return self.query_one('#dashboard-alerts-list', DashboardAlertList)

    @property
    def selected_row(self) -> BulletinAlert | None:
        return next(
            (
                row
                for row in self._rows
                if country_alert_identity(row.alert) == self._selected_identity
            ),
            None,
        )

    def update_alerts(self, rows: tuple[BulletinAlert, ...]) -> None:
        """Replace bulletin data while retaining a still-current selection."""

        selected_identity = self._selected_identity
        self.alert_list.clear_preview()
        self._rows = rows
        self._by_option_id.clear()
        self.alert_list.clear_options()
        self._last_text_width = self._text_width()
        options: list[Option | None] = []
        for index, row in enumerate(rows):
            option_id = _bulletin_option_id(row)
            self._by_option_id[option_id] = row
            options.append(Option(self._row_label(row), id=option_id))
            if index < len(rows) - 1:
                options.append(None)
        self.alert_list.add_options(options)
        empty = self.query_one('#dashboard-alerts-empty', Static)
        empty.display = not rows
        self.alert_list.display = bool(rows)
        if self.selected_row is None:
            self._selected_identity = None
        self._render_preview()
        if selected_identity is not None and self._selected_identity is None:
            self.post_message(self.Selected(None))

    def clear_selection(self) -> None:
        self._selected_identity = None
        self.alert_list.clear_preview()
        self.alert_list.highlighted = None
        self._refresh_option_labels()
        self._render_preview()
        self.post_message(self.Selected(None))

    def on_option_list_option_selected(
        self,
        event: OptionList.OptionSelected,
    ) -> None:
        if event.option_list is not self.alert_list:
            return
        event.stop()
        row = self._by_option_id.get(event.option.id or '')
        if row is None:
            return
        identity = country_alert_identity(row.alert)
        self._selected_identity = (
            None if identity == self._selected_identity else identity
        )
        self._refresh_option_labels()
        self._render_preview()
        self.post_message(self.Selected(self.selected_row))

    def on_dashboard_alert_list_preview_changed(
        self,
        event: DashboardAlertList.PreviewChanged,
    ) -> None:
        event.stop()
        self.post_message(
            self.Previewed(self._by_option_id.get(event.option_id or ''))
        )

    def on_dashboard_alert_list_open_requested(
        self,
        event: DashboardAlertList.OpenRequested,
    ) -> None:
        event.stop()
        row = self._by_option_id.get(event.option_id or '') or self.selected_row
        if row is None:
            return
        self._selected_identity = country_alert_identity(row.alert)
        self._refresh_option_labels()
        self._render_preview()
        self.post_message(self.Selected(row))
        self.post_message(self.OpenRequested(row))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != 'dashboard-alert-open':
            return
        event.stop()
        if row := self.selected_row:
            self.post_message(self.OpenRequested(row))

    def on_resize(self, event: Resize) -> None:
        del event
        width = self._text_width()
        if width == self._last_text_width:
            return
        self._last_text_width = width
        self._refresh_option_labels()
        self._render_preview()

    def focus_selected(self, *, open_button: bool = False) -> bool:
        """Restore focus to the selected row or its explicit open control."""

        row = self.selected_row
        if row is None:
            return False
        if open_button:
            self.query_one('#dashboard-alert-open', Button).focus()
            return True
        option_id = _bulletin_option_id(row)
        self.alert_list.highlighted = self.alert_list.get_option_index(option_id)
        self.alert_list.focus()
        return True

    def _render_preview(self) -> None:
        preview = self.query_one('#dashboard-alert-preview', Static)
        button = self.query_one('#dashboard-alert-open', Button)
        row = self.selected_row
        button.disabled = row is None
        if row is None:
            preview.update('Select an alert to preview it.')
            return
        country = get_country_name_by_alpha2(row.country_code) or row.country_code
        alert = row.alert
        preview_width = max(8, preview.content_size.width)
        text = Text()
        severity = (alert.severity or 'Alert').strip().title()
        colour = alert_severity_color(self.app.theme_variables, alert)
        text.append(severity, style=f'bold {colour}' if colour else 'bold')
        text.append(f' · {alert_condition_name(alert)}')
        text.truncate(preview_width, overflow='ellipsis')
        text.append(f'\n{country}', style='bold')
        area = ' · '.join(value.strip() for value in alert.area_names if value.strip())
        if area:
            area_text = Text(area, style='dim')
            area_text.truncate(preview_width, overflow='ellipsis')
            text.append('\n')
            text.append_text(area_text)
        text.append(
            f'\nFirst found by Wevva {_relative_observation(row.first_observed)}',
            style='italic dim',
        )
        preview.update(text)

    def _row_label(self, row: BulletinAlert) -> Text:
        alert = row.alert
        colour = alert_severity_color(self.app.theme_variables, alert)
        label = Text(no_wrap=True, overflow='ellipsis')
        selected = country_alert_identity(alert) == self._selected_identity
        accent = (
            self.app.theme_variables.get('accent')
            or self.app.theme_variables.get('text-accent')
        )
        indicator_style = f'bold {accent}' if accent else 'bold'
        label.append('▸ ' if selected else '  ', style=indicator_style)
        condition = Text(
            alert_condition_name(alert),
            style=f'bold {colour}' if colour else 'bold',
        )
        condition.truncate(max(1, self._text_width() - 2), overflow='ellipsis')
        label.append_text(condition)
        country = get_country_name_by_alpha2(row.country_code) or row.country_code
        detail = Text(
            f'{country} · {_relative_observation(row.first_observed)}',
            style='dim',
        )
        label.append('\n  ')
        detail.truncate(max(1, self._text_width() - 2), overflow='ellipsis')
        label.append_text(detail)
        return label

    def _refresh_option_labels(self) -> None:
        if not self.is_mounted:
            return
        for row in self._rows:
            option_id = _bulletin_option_id(row)
            if option_id in self._by_option_id:
                self.alert_list.replace_option_prompt(
                    option_id,
                    self._row_label(row),
                )

    def _text_width(self) -> int:
        if not self.is_mounted:
            return 20
        return max(8, self.alert_list.content_size.width - 1)


class DashboardScreen(Screen[None]):
    """Installed dashboard with one stable responsive widget tree."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding('w', 'back', 'Weather'),
        Binding('left', 'previous_feature', 'Previous feature', show=False),
        Binding('right', 'next_feature', 'Next feature', show=False),
        Binding('r', 'refresh_bulletin', 'Refresh alerts'),
        Binding('escape', 'clear_alert_selection', 'Clear alert', show=False),
        Binding('s', 'block_app_binding', '', show=False),
        Binding('a', 'block_app_binding', '', show=False),
        Binding('d', 'block_app_binding', '', show=False),
    ]

    DEFAULT_CSS = """
    DashboardScreen {
        background: $background;
    }

    #dashboard-stage {
        width: 100%;
        height: 1fr;
        padding: 1 2;
        overflow: hidden hidden;
        background: $background;
        hatch: right $background-lighten-1;
    }

    #dashboard-root {
        width: 100%;
        height: 100%;
        layout: vertical;
        overflow: hidden hidden;
        background: $background;
    }

    #dashboard-pane-tabs {
        display: none;
        width: 100%;
        height: 2;
    }

    #dashboard-body {
        width: 100%;
        height: 1fr;
        layout: horizontal;
        overflow: hidden hidden;
    }

    #dashboard-forecast-panel {
        margin-right: 2;
    }

    #dashboard-world-map {
        width: 1fr;
        height: 100%;
        margin-right: 2;
    }

    #dashboard-alerts-panel {
        width: 28;
    }

    #dashboard-root.medium #dashboard-pane-tabs,
    #dashboard-root.compact #dashboard-pane-tabs,
    #dashboard-root.short #dashboard-pane-tabs {
        display: block;
    }

    #dashboard-root.medium #dashboard-body,
    #dashboard-root.compact #dashboard-body,
    #dashboard-root.short #dashboard-body {
        layout: vertical;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._layout_budget: DashboardLayoutBudget | None = None
        self._active_pane = 'map'
        self._selected_location: LocationMetadata | None = None
        self._displayed_location: LocationMetadata | None = None
        self._previewing = False
        self._forecast_request_generation = 0
        self._forecast_request_key: tuple[str, str, str, str] | None = None
        self._forecast_wait_task: asyncio.Task[None] | None = None
        self._tropical_wait_task: asyncio.Task[None] | None = None
        self._bulletin_generation = -1
        self._alert_return_focus: str | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id='dashboard-stage'), Container(id='dashboard-root'):
            yield Tabs(
                Tab('Forecast', id='dashboard-tab-forecast'),
                Tab('Map', id='dashboard-tab-map'),
                Tab('Alerts', id='dashboard-tab-alerts'),
                active='dashboard-tab-map',
                id='dashboard-pane-tabs',
            )
            with Container(id='dashboard-body'):
                yield DashboardForecastPanel(id='dashboard-forecast-panel')
                yield DashboardWorldMap(id='dashboard-world-map')
                yield DashboardAlertsPanel(id='dashboard-alerts-panel')
        yield Footer()

    @property
    def world_map(self) -> DashboardWorldMap:
        return self.query_one('#dashboard-world-map', DashboardWorldMap)

    @property
    def forecast_panel(self) -> DashboardForecastPanel:
        return self.query_one('#dashboard-forecast-panel', DashboardForecastPanel)

    @property
    def alerts_panel(self) -> DashboardAlertsPanel:
        return self.query_one('#dashboard-alerts-panel', DashboardAlertsPanel)

    def selected_country_code(self) -> str | None:
        """Return the persistent map selection used by bulletin priority work."""

        return (
            self._selected_location.country_code
            if self._selected_location is not None
            else None
        )

    def selected_alert_country_code(self) -> str | None:
        row = self.alerts_panel.selected_row if self.is_mounted else None
        return row.country_code if row is not None else None

    def action_refresh_bulletin(self) -> None:
        """Request only the bounded local bulletin refresh set."""

        self.app.refresh_dashboard_bulletin()

    def on_mount(self) -> None:
        self.title = 'Dashboard'
        self.sub_title = 'Weather, locations, storms, and alerts'
        self.sync_from_app()
        self._apply_layout(self.size.width, self.size.height)
        self.call_after_refresh(self.world_map.focus_preferred_location)

    def on_screen_resume(self) -> None:
        self.sync_from_app()
        self.world_map.set_selected_alert(
            self.alerts_panel.selected_row,
            pulse=False,
        )
        self.call_after_refresh(self._restore_focus)

    def on_screen_suspend(self) -> None:
        self.world_map.pause_alert_marker()

    def on_unmount(self) -> None:
        self._cancel_forecast_wait()
        if self._tropical_wait_task is not None:
            self._tropical_wait_task.cancel()
            self._tropical_wait_task = None

    def on_resize(self, event: Resize) -> None:
        self._apply_layout(event.size.width, event.size.height)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        tab_id = event.tab.id
        if tab_id == 'dashboard-tab-forecast':
            self._active_pane = 'forecast'
        elif tab_id == 'dashboard-tab-map':
            self._active_pane = 'map'
        elif tab_id == 'dashboard-tab-alerts':
            self._active_pane = 'alerts'
        else:
            return
        if self._active_pane != 'map' and self._previewing:
            self._previewing = False
            self._show_persistent_location()
        self._update_visibility()
        if self._active_pane == 'map':
            self.call_after_refresh(self.world_map.focus_preferred_location)

    def sync_from_app(self) -> None:
        """Refresh place inputs and reuse or load the persistent preview."""

        if not self.is_mounted:
            return
        locations = self.app.locations_for_dashboard()
        summaries = self.app.saved_location_weather_summaries(locations)
        available = {location_key(location): location for location in locations}
        if self._selected_location is not None:
            self._selected_location = available.get(
                location_key(self._selected_location)
            )
        self.world_map.set_locations(locations, summaries=summaries)
        self.world_map.set_temperature_unit(self.app.temperature_unit)
        self.world_map.set_active_location(self.app.location)
        self.world_map.set_selected_location(self._selected_location)
        self._sync_tropical_systems()
        self.update_bulletin(
            self.app.alert_bulletin.generation,
            self.app.alert_bulletin.recent_alerts_snapshot(),
        )
        self._previewing = False
        self._show_persistent_location()
        self._ensure_persistent_forecast()

    def update_weather_summary(
        self,
        location: LocationMetadata,
        summary: SavedLocationWeatherSummary,
        *,
        temperature_unit: str,
    ) -> None:
        """Apply an app-owned summary result without rebuilding Dashboard."""

        if not self.is_mounted:
            return
        self.world_map.set_temperature_unit(temperature_unit)
        self.world_map.update_weather_summary(location, summary)
        if (
            self._displayed_location is not None
            and location_key(self._displayed_location) == location_key(location)
        ):
            if self._previewing:
                self._show_location(self._displayed_location, role='Preview')
            else:
                self._show_persistent_location()

    def refresh_appearance(self) -> None:
        """Rebuild theme/emoji-sensitive Rich content from cached state only."""

        if not self.is_mounted:
            return
        locations = self.app.locations_for_dashboard()
        self.world_map.set_locations(
            locations,
            summaries=self.app.saved_location_weather_summaries(locations),
        )
        self.world_map.set_temperature_unit(self.app.temperature_unit)
        if (systems := self.app.tropical_systems_snapshot()) is not None:
            self.world_map.set_tropical_systems(systems)
        self.update_bulletin(
            self.app.alert_bulletin.generation,
            self.app.alert_bulletin.recent_alerts_snapshot(),
        )
        self._show_persistent_location()

    def on_dashboard_place_previewed(
        self,
        message: DashboardPlacePreviewed,
    ) -> None:
        message.stop()
        if (
            self._layout_budget is not None
            and not self._layout_budget.simultaneous
            and self._active_pane != 'map'
        ):
            return
        self._previewing = True
        self._show_location(message.location, role='Preview')

    def on_dashboard_place_preview_ended(
        self,
        message: DashboardPlacePreviewEnded,
    ) -> None:
        message.stop()
        self._previewing = False
        self._show_persistent_location()

    def on_dashboard_place_pressed(self, message: DashboardPlacePressed) -> None:
        message.stop()
        key = location_key(message.location)
        selected_key = (
            location_key(self._selected_location)
            if self._selected_location is not None
            else None
        )
        if key == selected_key:
            self._cancel_forecast_wait()
            self.post_message(DashboardPlaceActivated(location=message.location))
            return
        self._selected_location = message.location
        self.app.note_bulletin_country_used(message.location.country_code)
        self._previewing = False
        self.world_map.set_selected_location(message.location)
        self._show_persistent_location()
        self._ensure_persistent_forecast()

    async def on_dashboard_tropical_activated(
        self,
        message: DashboardTropicalActivated,
    ) -> None:
        """Open the owning tropical workspace at the exact source anchor."""

        message.stop()
        self.world_map.set_selected_tropical(message.system)
        await self.app.open_tropical_systems_screen(
            system=message.system,
            observation=message.observation,
        )

    def update_bulletin(
        self,
        generation: int,
        rows: tuple[BulletinAlert, ...],
    ) -> None:
        """Apply only the newest application-owned bulletin snapshot."""

        if not self.is_mounted or generation < self._bulletin_generation:
            return
        self._bulletin_generation = generation
        self.alerts_panel.update_alerts(rows)
        self.world_map.set_selected_alert(
            self.alerts_panel.selected_row,
            pulse=False,
        )

    def on_dashboard_alerts_panel_selected(
        self,
        message: DashboardAlertsPanel.Selected,
    ) -> None:
        message.stop()
        self.world_map.set_selected_alert(message.row)
        if message.row is not None:
            self.app.note_bulletin_country_used(message.row.country_code)

    def on_dashboard_alerts_panel_previewed(
        self,
        message: DashboardAlertsPanel.Previewed,
    ) -> None:
        message.stop()
        self.world_map.set_alert_preview(message.row)

    def on_dashboard_alerts_panel_open_requested(
        self,
        message: DashboardAlertsPanel.OpenRequested,
    ) -> None:
        message.stop()
        row = message.row
        focused = self.app.focused
        self._alert_return_focus = (
            'button'
            if isinstance(focused, Button) and focused.id == 'dashboard-alert-open'
            else 'list'
        )
        self.app.open_alerts_centre_screen(
            country_code=row.country_code,
            alert_identity=country_alert_identity(row.alert),
        )

    def on_dashboard_alert_marker_activated(
        self,
        message: DashboardAlertMarker.Activated,
    ) -> None:
        message.stop()
        row = message.row
        self._alert_return_focus = 'marker'
        self.app.open_alerts_centre_screen(
            country_code=row.country_code,
            alert_identity=country_alert_identity(row.alert),
        )

    def _sync_tropical_systems(self) -> None:
        snapshot = self.app.tropical_systems_snapshot()
        if snapshot is not None:
            self.world_map.set_tropical_systems(snapshot)
            return
        self.world_map.set_tropical_loading()
        if self._tropical_wait_task is None or self._tropical_wait_task.done():
            self._tropical_wait_task = asyncio.create_task(
                self._load_tropical_systems()
            )

    async def _load_tropical_systems(self) -> None:
        try:
            systems = await self.app.load_tropical_systems()
        except asyncio.CancelledError:
            raise
        except Exception:
            if self.is_mounted:
                self.world_map.set_tropical_error()
        else:
            if self.is_mounted:
                self.world_map.set_tropical_systems(systems)
        finally:
            if self._tropical_wait_task is asyncio.current_task():
                self._tropical_wait_task = None

    def _show_persistent_location(self) -> None:
        location = self._selected_location or self.app.location
        self._displayed_location = location
        if location is None:
            self._show_location(None, role='No active place')
            return
        role = self._display_role(location)
        snapshot = self.app.dashboard_forecast_snapshot(location)
        if snapshot is not None:
            self.forecast_panel.show_forecast(
                location,
                snapshot,
                role=role,
                temperature_unit=self.app.temperature_unit,
            )
            return
        summary = self.app.saved_location_weather_summary(location)
        if (
            self._forecast_wait_task is not None
            and not self._forecast_wait_task.done()
            and self._forecast_request_key == self._forecast_selection_key(location)
        ):
            self.forecast_panel.show_loading(
                location,
                summary,
                role=role,
                temperature_unit=self.app.temperature_unit,
            )
            return
        self.forecast_panel.show_location(
            location,
            summary,
            role=role,
            temperature_unit=self.app.temperature_unit,
        )

    def _show_location(self, location: LocationMetadata | None, *, role: str) -> None:
        self._displayed_location = location
        persistent = self._selected_location or self.app.location
        if (
            role == 'Preview'
            and location is not None
            and persistent is not None
            and location_key(location) == location_key(persistent)
        ):
            snapshot = self.app.dashboard_forecast_snapshot(location)
            if snapshot is not None:
                self.forecast_panel.show_forecast(
                    location,
                    snapshot,
                    role=role,
                    temperature_unit=self.app.temperature_unit,
                )
                return
        summary = (
            None
            if location is None
            else self.app.saved_location_weather_summary(location)
        )
        self.forecast_panel.show_location(
            location,
            summary,
            role=role,
            temperature_unit=self.app.temperature_unit,
        )

    def _ensure_persistent_forecast(self) -> None:
        """Start at most one selected-place preview wait for the current state."""

        location = self._selected_location or self.app.location
        if (
            location is None
            or location.latitude is None
            or location.longitude is None
            or self.app.dashboard_forecast_snapshot(location) is not None
        ):
            return
        key = self._forecast_selection_key(location)
        if (
            self._forecast_wait_task is not None
            and not self._forecast_wait_task.done()
            and self._forecast_request_key == key
        ):
            return
        self._cancel_forecast_wait()
        self._forecast_request_generation += 1
        generation = self._forecast_request_generation
        self._forecast_request_key = key
        self._forecast_wait_task = asyncio.create_task(
            self._load_forecast(location, key, generation)
        )
        if not self._previewing:
            self._show_persistent_location()

    async def _load_forecast(
        self,
        location: LocationMetadata,
        key: tuple[str, str, str, str],
        generation: int,
    ) -> None:
        """Apply a preview only while its selected-place generation is current."""

        try:
            await self.app.load_dashboard_forecast(location)
        except asyncio.CancelledError:
            raise
        except Exception:
            if self._forecast_result_is_current(key, generation) and not self._previewing:
                self.forecast_panel.show_error(
                    location,
                    self.app.saved_location_weather_summary(location),
                    role=self._display_role(location),
                    temperature_unit=self.app.temperature_unit,
                )
            return
        finally:
            if (
                generation == self._forecast_request_generation
                and self._forecast_wait_task is asyncio.current_task()
            ):
                self._forecast_request_key = None
                self._forecast_wait_task = None
        if self._forecast_result_is_current(key, generation) and not self._previewing:
            self._show_persistent_location()

    def _forecast_result_is_current(
        self,
        key: tuple[str, str, str, str],
        generation: int,
    ) -> bool:
        location = self._selected_location or self.app.location
        return (
            generation == self._forecast_request_generation
            and location is not None
            and self._forecast_selection_key(location) == key
        )

    def _forecast_selection_key(
        self,
        location: LocationMetadata,
    ) -> tuple[str, str, str, str]:
        """Identify a preview by place and the units visible in its rail."""

        return (
            location_key(location),
            self.app.temperature_unit,
            self.app.wind_speed_unit,
            self.app.precipitation_unit,
        )

    def _cancel_forecast_wait(self) -> None:
        self._forecast_request_generation += 1
        if self._forecast_wait_task is not None and not self._forecast_wait_task.done():
            self._forecast_wait_task.cancel()
        self._forecast_wait_task = None
        self._forecast_request_key = None

    def on_hour_highlighted(self, message: HourHighlighted) -> None:
        """Keep the fixed conditions summary aligned with the hourly cursor."""

        message.stop()
        self.forecast_panel.show_hour(message.index)

    def _display_role(self, location: LocationMetadata | None) -> str:
        if location is None:
            return 'No active place'
        if self._selected_location is not None and (
            location_key(location) == location_key(self._selected_location)
        ):
            return 'Selected place'
        return 'Active weather'

    def _apply_layout(self, width: int, height: int) -> None:
        if not self.is_mounted:
            return
        budget = dashboard_layout_for(width, height)
        if budget == self._layout_budget:
            return
        self._layout_budget = budget
        self.forecast_panel.set_layout(budget)
        root = self.query_one('#dashboard-root', Container)
        root.remove_class('wide', 'medium', 'compact', 'short')
        root.add_class(budget.presentation.value)
        self.query_one('#dashboard-stage', Container).styles.padding = (
            budget.stage_padding
        )
        if budget.simultaneous:
            self.forecast_panel.styles.width = budget.forecast_width
            self.forecast_panel.styles.height = '100%'
            self.forecast_panel.styles.margin = (0, budget.gutter, 0, 0)
            self.world_map.styles.width = '1fr'
            self.world_map.styles.height = (
                '100%' if budget.map_height is None else budget.map_height
            )
            self.world_map.styles.margin = (0, budget.gutter, 0, 0)
            self.alerts_panel.styles.width = budget.alert_width
            self.alerts_panel.styles.height = '100%'
        else:
            for panel in (self.forecast_panel, self.world_map, self.alerts_panel):
                panel.styles.width = '100%'
                panel.styles.height = '100%'
                panel.styles.margin = 0
        self._update_visibility()

    def _update_visibility(self) -> None:
        if self._layout_budget is None:
            return
        tabs = self.query_one('#dashboard-pane-tabs', Tabs)
        tabs.display = not self._layout_budget.simultaneous
        if self._layout_budget.simultaneous:
            self.forecast_panel.display = True
            self.world_map.display = True
            self.alerts_panel.display = True
            return
        self.forecast_panel.display = self._active_pane == 'forecast'
        self.world_map.display = self._active_pane == 'map'
        self.alerts_panel.display = self._active_pane == 'alerts'

    def _restore_focus(self) -> None:
        alert_focus = self._alert_return_focus
        self._alert_return_focus = None
        if alert_focus == 'marker' and self.world_map.alert_marker.display:
            self.world_map.alert_marker.focus()
            return
        if (
            alert_focus in {'list', 'button'}
            and self.alerts_panel.display
            and self.alerts_panel.focus_selected(
                open_button=alert_focus == 'button'
            )
        ):
            return
        if self._layout_budget is None or self._layout_budget.simultaneous:
            self.world_map.focus_preferred_location()
        elif self._active_pane == 'map':
            self.world_map.focus_preferred_location()

    def action_back(self) -> None:
        self._cancel_forecast_wait()
        self.app.pop_screen()

    def action_previous_feature(self) -> None:
        if (
            self._layout_budget is not None
            and (
                self._layout_budget.simultaneous
                or self._active_pane == 'map'
            )
        ):
            self.world_map.focus_relative(-1)

    def action_next_feature(self) -> None:
        if (
            self._layout_budget is not None
            and (
                self._layout_budget.simultaneous
                or self._active_pane == 'map'
            )
        ):
            self.world_map.focus_relative(1)

    def action_clear_alert_selection(self) -> None:
        self.alerts_panel.clear_selection()

    def action_block_app_binding(self) -> None:
        """Prevent deletion based on Weather's hidden saved-list focus."""


def _bulletin_option_id(row: BulletinAlert) -> str:
    source, alert_id = country_alert_identity(row.alert)
    digest = hashlib.sha1(f'{source}\0{alert_id}'.encode()).hexdigest()[:16]
    return f'bulletin-{digest}'


def _relative_observation(value: datetime) -> str:
    observed = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    seconds = max(0, int((datetime.now(UTC) - observed).total_seconds()))
    if seconds < 60:
        return 'just now'
    minutes = seconds // 60
    if minutes < 60:
        return f'{minutes}m ago'
    hours = minutes // 60
    if hours < 24:
        return f'{hours}h ago'
    return observed.strftime('on %d %b')


__all__ = [
    'DashboardAlertsPanel',
    'DashboardForecastPanel',
    'DashboardScreen',
]
