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
from textual.containers import Container, VerticalScroll
from textual.events import Resize
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, OptionList, Static, Tab, Tabs
from textual.widgets.option_list import Option
from wevva_warnings import (
    CanonicalTropicalSystem,
    TropicalProduct,
    TropicalSystem,
)

from wevva.config import location_key
from wevva.dashboard_layout import DashboardLayoutBudget, dashboard_layout_for
from wevva.layout import CurrentDensity
from wevva.location_metadata import LocationMetadata
from wevva.services.alert_bulletin import BulletinAlert
from wevva.services.country_alerts import country_alert_identity
from wevva.messages import (
    DashboardPlacePressed,
    DashboardTropicalActivated,
    HourHighlighted,
    WeatherUpdated,
)
from wevva.widgets.context_bar import ContextBar
from wevva.widgets.current_conditions import CurrentConditions
from wevva.widgets.dashboard_daily_forecast import DashboardDailyForecast
from wevva.widgets.dashboard_hourly_forecast import DashboardHourlyForecast
from wevva.widgets.dashboard_world_map import (
    DashboardAlertMarker,
    DashboardWorldMap,
)
from wevva.widgets.saved_locations import SavedLocationWeatherSummary
from wevva.widgets.tropical_products import (
    tropical_forecast_summary,
    tropical_product_tab_specs,
    tropical_product_widgets,
)
from wevva.widgets.tropical_track import LargeTropicalStormTrackScope
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
        overflow: hidden hidden;
        background: $background;
    }

    #dashboard-forecast-place {
        width: 100%;
        height: 2;
        text-style: bold;
        text-align: center;
        content-align: center middle;
    }

    #dashboard-current-conditions {
        grid-size: 3 1;
        grid-columns: 1fr 1fr 1fr;
        grid-gutter: 0 1;
        width: 100%;
        max-width: 100%;
        height: 5;
        hatch: none;
    }

    #dashboard-current-conditions CurrentDetailTable {
        display: none;
    }

    #dashboard-current-conditions WeatherWidget,
    #dashboard-current-conditions PrecipWidget {
        border: none;
        padding: 0;
        align-horizontal: center;
    }

    #dashboard-current-conditions WeatherWidget > Static {
        text-align: center;
        align-horizontal: center;
    }

    #dashboard-current-conditions WeatherWidget #digits-row {
        width: 100%;
        align-horizontal: center;
    }

    .dashboard-forecast-separator {
        width: 100%;
        height: 1;
        color: $primary-muted;
        text-style: bold;
        text-wrap: nowrap;
        text-overflow: clip;
    }

    DashboardForecastPanel DashboardHourlyForecast {
        width: 100%;
        max-width: 100%;
        height: 2fr;
        min-height: 5;
    }

    DashboardForecastPanel DashboardDailyForecast {
        width: 100%;
        max-width: 100%;
        height: 3;
    }

    #dashboard-forecast-context {
        width: 100%;
        height: 6;
    }

    #dashboard-forecast-status {
        width: 100%;
        height: 1fr;
        color: $text-muted;
        text-style: italic;
        content-align: center middle;
        text-align: center;
    }
    """

    def compose(self) -> ComposeResult:
        self.border_title = 'Location Forecast'
        yield Static('No location selected', id='dashboard-forecast-place')
        yield Static(
            '─ Current ────────────────────────────────────────────────',
            classes='dashboard-forecast-separator',
        )
        yield CurrentConditions(id='dashboard-current-conditions')
        yield Static(
            '─ Hourly Forecast ─────────────────────────────────────────',
            classes='dashboard-forecast-separator',
        )
        yield DashboardHourlyForecast(id='dashboard-hourly-forecast')
        yield Static(
            '─ Daily Forecast ──────────────────────────────────────────',
            classes='dashboard-forecast-separator',
        )
        yield DashboardDailyForecast(id='dashboard-daily-forecast')
        yield ContextBar(id='dashboard-forecast-context')
        yield Static(
            'Select a place to load its forecast.',
            id='dashboard-forecast-status',
        )

    @property
    def current_conditions(self) -> CurrentConditions:
        return self.query_one('#dashboard-current-conditions', CurrentConditions)

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

    @property
    def context_bar(self) -> ContextBar:
        return self.query_one('#dashboard-forecast-context', ContextBar)

    def on_mount(self) -> None:
        self._layout_context_rows = 1
        self._show_status('Select a place to load its forecast.')

    def set_layout(self, budget: DashboardLayoutBudget) -> None:
        """Apply the weather-rail reductions selected for this viewport."""

        density = (
            CurrentDensity.STANDARD
            if budget.current_conditions_height >= 5
            else CurrentDensity.SMALL
        )
        self.current_conditions.set_layout(
            density,
            budget.current_conditions_height,
            (),
            False,
        )
        self.current_conditions.detail.display = False
        self.hourly_forecast.styles.min_height = budget.hourly_min_height
        self.daily_forecast.set_row_count(budget.daily_rows)
        self._layout_context_rows = budget.context_rows
        context_height = (
            (budget.context_rows + 1) * 3 if budget.context_rows else 0
        )
        self.context_bar.set_layout(
            row_count=budget.context_rows,
            height=context_height,
            narrow=True,
            show_air_quality=True,
            separated=True,
        )

    def show_location(
        self,
        location: LocationMetadata | None,
    ) -> None:
        """Show one place while its complete forecast is unavailable."""

        if not self.is_mounted:
            return
        self.query_one('#dashboard-forecast-place', Static).update(
            _dashboard_place_heading(location)
        )
        self._show_status('Select this place to load its forecast.')

    def show_loading(
        self,
        location: LocationMetadata,
    ) -> None:
        """Show a stable loading state for one committed place."""

        self.show_location(location)
        self._show_status('Loading forecast…')

    def show_error(
        self,
        location: LocationMetadata,
    ) -> None:
        """Show a retryable selected-place failure."""

        self.show_location(location)
        self._show_status(
            'Forecast unavailable.\nSelect another place and return to retry.'
        )

    def show_forecast(
        self,
        location: LocationMetadata,
        event: WeatherUpdated,
    ) -> None:
        """Render one complete app-owned forecast in the narrow rail."""

        if not self.is_mounted:
            return
        self.query_one('#dashboard-forecast-place', Static).update(
            _dashboard_place_heading(location)
        )
        self._forecast_event = event
        self.current_conditions.hourly_model = event.hourly
        self.show_hour(0)
        self.hourly_forecast.update_forecast(event)
        self.daily_forecast.update_forecast(event)
        self.context_bar.update_forecast(event, location=location)
        self.current_conditions.display = True
        self.hourly_forecast.display = True
        self.daily_forecast.display = True
        self.context_bar.display = self._layout_context_rows > 0
        for separator in self.query('.dashboard-forecast-separator'):
            separator.display = True
        self.query_one('#dashboard-forecast-status', Static).display = False

    def show_hour(self, index: int) -> None:
        """Update standard current instruments and AQI for one hourly row."""

        event = getattr(self, '_forecast_event', None)
        if event is None:
            return
        if event.hourly.get_point(index) is None:
            return
        self.current_conditions.hour_index = index
        self.context_bar.on_hour_highlighted(index)

    def _show_status(self, message: str) -> None:
        self._forecast_event = None
        self.current_conditions.display = False
        self.hourly_forecast.display = False
        self.daily_forecast.display = False
        self.context_bar.display = False
        for separator in self.query('.dashboard-forecast-separator'):
            separator.display = False
        status = self.query_one('#dashboard-forecast-status', Static)
        status.update(message)
        status.display = True

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


class DashboardTropicalPanel(Container):
    """Track and official products for one committed source observation."""

    DEFAULT_CSS = """
    DashboardTropicalPanel {
        width: 1fr;
        height: 100%;
        min-width: 18;
        min-height: 8;
        border: round $primary;
        border-title-color: $primary;
        background: $background;
    }

    #dashboard-tropical-tabs {
        width: 100%;
        height: 2;
    }

    #dashboard-tropical-content {
        width: 100%;
        height: 1fr;
        overflow: hidden hidden;
    }

    #dashboard-tropical-track {
        width: 100%;
        height: 1fr;
    }

    #dashboard-tropical-product-body {
        width: 100%;
        height: 1fr;
        padding: 0 1;
        scrollbar-size-vertical: 1;
    }

    #dashboard-tropical-track-unavailable,
    #dashboard-tropical-detail-state {
        width: 100%;
        height: 100%;
        padding: 0 1;
        color: $text-muted;
        text-style: italic;
        text-align: center;
        content-align: center middle;
    }
    """

    def compose(self) -> ComposeResult:
        self.border_title = 'Tropical System'
        tabs = Tabs(
            Tab('Track and Cone', id='dashboard-tropical-track-tab'),
            active='dashboard-tropical-track-tab',
            id='dashboard-tropical-tabs',
        )
        tabs.display = False
        yield tabs
        with Container(id='dashboard-tropical-content'):
            yield LargeTropicalStormTrackScope(id='dashboard-tropical-track')
            unavailable = Static(
                'Track and cone unavailable for this source.',
                id='dashboard-tropical-track-unavailable',
            )
            unavailable.display = False
            yield unavailable
            body = VerticalScroll(id='dashboard-tropical-product-body')
            body.display = False
            yield body
            yield Static(
                'Select a tropical system on the map.',
                id='dashboard-tropical-detail-state',
            )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._observation: TropicalSystem | None = None
        self._products: tuple[TropicalProduct, ...] = ()
        self._product_indices: dict[str, int] = {}
        self._updating_tabs = False

    @property
    def track(self) -> LargeTropicalStormTrackScope:
        return self.query_one(
            '#dashboard-tropical-track',
            LargeTropicalStormTrackScope,
        )

    @property
    def tabs(self) -> Tabs:
        return self.query_one('#dashboard-tropical-tabs', Tabs)

    def show_overview(
        self,
        systems: tuple[CanonicalTropicalSystem, ...] | None,
    ) -> None:
        """Show loading, empty, or selection guidance below the world map."""

        if systems is None:
            message = 'Loading tropical systems…'
        elif systems:
            message = 'Select a tropical system on the map.'
        else:
            message = 'No active tropical systems.'
        self._show_state(message)

    def show_error(self) -> None:
        self._show_state('Tropical systems are temporarily unavailable.')

    def show_system(
        self,
        system: CanonicalTropicalSystem | None,
        observation: TropicalSystem | None,
    ) -> None:
        """Show the source track immediately, before product loading settles."""

        if system is None or observation is None:
            self.show_overview(())
            return
        self._observation = observation
        self._products = ()
        self._product_indices.clear()
        self.query_one('#dashboard-tropical-detail-state', Static).display = False
        self.tabs.display = True
        self.tabs.active = 'dashboard-tropical-track-tab'
        self.query_one('#dashboard-tropical-product-body').display = False
        try:
            self.track.update_system(observation)
        except Exception as error:
            self.log.error(f'Unable to render Dashboard tropical track: {error!r}')
            self.track.clear()
        self._show_track()

    async def reset_products(self) -> None:
        """Discard prior selection tabs while keeping the new track visible."""

        await self._replace_tabs(())

    async def show_products(
        self,
        observation: TropicalSystem,
        products: list[TropicalProduct],
    ) -> None:
        """Add only provider-backed tabs for the still-selected observation."""

        if observation is not self._observation:
            return
        self._products = tuple(products)
        try:
            self.track.update_system(observation, products=self._products)
        except Exception as error:
            self.log.error(f'Unable to render Dashboard tropical products: {error!r}')
            self.track.clear()
        specs = tropical_product_tab_specs(
            observation,
            self._products,
            id_prefix='dashboard-tropical-product',
        )
        await self._replace_tabs(specs)
        self._show_track()

    async def _replace_tabs(self, specs: list[tuple[str, str]] | tuple) -> None:
        self._updating_tabs = True
        try:
            await self.tabs.clear()
            await self.tabs.add_tab(
                Tab('Track and Cone', id='dashboard-tropical-track-tab')
            )
            self._product_indices.clear()
            for tab_id, label in specs:
                await self.tabs.add_tab(Tab(label, id=tab_id))
                suffix = tab_id.rsplit('-', 1)[-1]
                if suffix.isdigit():
                    self._product_indices[tab_id] = int(suffix)
            self.tabs.active = 'dashboard-tropical-track-tab'
        finally:
            self._updating_tabs = False

    async def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if event.tabs is not self.tabs:
            return
        event.stop()
        if self._updating_tabs or event.tab.id is None:
            return
        if event.tab.id == 'dashboard-tropical-track-tab':
            self._show_track()
            return
        await self._show_product(event.tab.id)

    def _show_track(self) -> None:
        body = self.query_one(
            '#dashboard-tropical-product-body',
            VerticalScroll,
        )
        body.display = False
        unavailable = self.query_one(
            '#dashboard-tropical-track-unavailable',
            Static,
        )
        unavailable.display = not self.track.available
        self.track.set_layout(
            visible=True,
            height=max(1, self.content_size.height - 2),
        )

    async def _show_product(self, tab_id: str) -> None:
        observation = self._observation
        if observation is None:
            return
        self.track.set_layout(visible=False, height=0)
        self.query_one(
            '#dashboard-tropical-track-unavailable',
            Static,
        ).display = False
        body = self.query_one(
            '#dashboard-tropical-product-body',
            VerticalScroll,
        )
        body.display = True
        await body.remove_children()
        if tab_id == 'dashboard-tropical-product-forecast':
            await body.mount(Static(tropical_forecast_summary(observation)))
            return
        index = self._product_indices.get(tab_id)
        if index is None or not 0 <= index < len(self._products):
            await body.mount(Static('Product unavailable'))
            return
        await body.mount(*tropical_product_widgets(self._products[index]))

    def _show_state(self, message: str) -> None:
        self._observation = None
        self._products = ()
        if not self.is_mounted:
            return
        self.tabs.display = False
        self.track.clear()
        self.query_one(
            '#dashboard-tropical-track-unavailable',
            Static,
        ).display = False
        self.query_one('#dashboard-tropical-product-body').display = False
        state = self.query_one('#dashboard-tropical-detail-state', Static)
        state.update(message)
        state.display = True


class DashboardAlertDetailPanel(Container):
    """Persistent lower-centre home for one committed bulletin selection."""

    DEFAULT_CSS = """
    DashboardAlertDetailPanel {
        width: 1fr;
        height: 100%;
        min-width: 18;
        min-height: 8;
        border: round $primary;
        border-title-color: $primary;
        background: $background;
    }

    #dashboard-alert-detail-state {
        width: 100%;
        height: 100%;
        padding: 0 1;
        color: $text-muted;
        text-style: italic;
        text-align: center;
        content-align: center middle;
    }
    """

    def compose(self) -> ComposeResult:
        self.border_title = 'Selected Alert'
        yield Static(
            'Select an alert from the bulletin.',
            id='dashboard-alert-detail-state',
        )

    def show_alert(self, row: BulletinAlert | None) -> None:
        """Show honest Slice A state for the committed alert identity."""

        state = self.query_one('#dashboard-alert-detail-state', Static)
        if row is None:
            state.update('Select an alert from the bulletin.')
            return
        country = get_country_name_by_alpha2(row.country_code) or row.country_code
        state.update(
            f'{alert_condition_name(row.alert)}\n{country}\n\n'
            'Map and warning details are not available here yet.'
        )


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

    #dashboard-center-column {
        width: 1fr;
        height: 100%;
        layout: vertical;
        margin-right: 2;
        overflow: hidden hidden;
        background: $background;
        hatch: right $background-lighten-1;
    }

    #dashboard-world-map {
        width: 100%;
        height: 14;
    }

    #dashboard-detail-row {
        width: 100%;
        height: 1fr;
        layout: horizontal;
        margin-top: 1;
        overflow: hidden hidden;
        background: $background;
        hatch: right $background-lighten-1;
    }

    #dashboard-tropical-panel {
        margin-right: 1;
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
        self._selected_tropical_system: CanonicalTropicalSystem | None = None
        self._selected_tropical_observation: TropicalSystem | None = None
        self._forecast_request_generation = 0
        self._forecast_request_key: tuple[str, str, str, str] | None = None
        self._forecast_wait_task: asyncio.Task[None] | None = None
        self._tropical_wait_task: asyncio.Task[None] | None = None
        self._tropical_product_task: asyncio.Task[None] | None = None
        self._tropical_detail_generation = 0
        self._tropical_detail_key: tuple[str, str, str] | None = None
        self._bulletin_generation = -1
        self._alert_return_focus: str | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id='dashboard-stage'), Container(id='dashboard-root'):
            yield Tabs(
                Tab('Forecast', id='dashboard-tab-forecast'),
                Tab('Map', id='dashboard-tab-map'),
                Tab('Tropical', id='dashboard-tab-tropical'),
                Tab('Selected Alert', id='dashboard-tab-alert-detail'),
                Tab('Recent Alerts', id='dashboard-tab-alerts'),
                active='dashboard-tab-map',
                id='dashboard-pane-tabs',
            )
            with Container(id='dashboard-body'):
                yield DashboardForecastPanel(id='dashboard-forecast-panel')
                with Container(id='dashboard-center-column'):
                    yield DashboardWorldMap(id='dashboard-world-map')
                    with Container(id='dashboard-detail-row'):
                        yield DashboardTropicalPanel(
                            id='dashboard-tropical-panel'
                        )
                        yield DashboardAlertDetailPanel(
                            id='dashboard-alert-detail-panel'
                        )
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

    @property
    def tropical_panel(self) -> DashboardTropicalPanel:
        return self.query_one('#dashboard-tropical-panel', DashboardTropicalPanel)

    @property
    def alert_detail_panel(self) -> DashboardAlertDetailPanel:
        return self.query_one(
            '#dashboard-alert-detail-panel',
            DashboardAlertDetailPanel,
        )

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
        self._cancel_tropical_product_wait()

    def on_resize(self, event: Resize) -> None:
        self._apply_layout(event.size.width, event.size.height)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        tab_id = event.tab.id
        if tab_id == 'dashboard-tab-forecast':
            self._active_pane = 'forecast'
        elif tab_id == 'dashboard-tab-map':
            self._active_pane = 'map'
        elif tab_id == 'dashboard-tab-tropical':
            self._active_pane = 'tropical'
        elif tab_id == 'dashboard-tab-alert-detail':
            self._active_pane = 'alert-detail'
        elif tab_id == 'dashboard-tab-alerts':
            self._active_pane = 'alerts'
        else:
            return
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
        if (
            self._selected_tropical_system is not None
            and self._selected_tropical_observation is not None
        ):
            self._select_tropical_detail(
                self._selected_tropical_system,
                self._selected_tropical_observation,
            )
        self.update_bulletin(
            self.app.alert_bulletin.generation,
            self.app.alert_bulletin.recent_alerts_snapshot(),
        )
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

    def on_dashboard_place_pressed(self, message: DashboardPlacePressed) -> None:
        message.stop()
        self._selected_location = message.location
        self.app.note_bulletin_country_used(message.location.country_code)
        self.world_map.set_selected_location(message.location)
        self._show_persistent_location()
        self._ensure_persistent_forecast()

    def on_dashboard_tropical_activated(
        self,
        message: DashboardTropicalActivated,
    ) -> None:
        """Commit the exact storm/source anchor to the Dashboard detail pane."""

        message.stop()
        self._selected_tropical_system = message.system
        self._selected_tropical_observation = message.observation
        self.world_map.set_selected_tropical(message.system)
        self._select_tropical_detail(
            message.system,
            message.observation,
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
        self.alert_detail_panel.show_alert(self.alerts_panel.selected_row)

    def on_dashboard_alerts_panel_selected(
        self,
        message: DashboardAlertsPanel.Selected,
    ) -> None:
        message.stop()
        self.world_map.set_selected_alert(message.row)
        self.alert_detail_panel.show_alert(message.row)
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
            if self._selected_tropical_observation is None:
                self.tropical_panel.show_overview(snapshot)
            return
        self.world_map.set_tropical_loading()
        if self._selected_tropical_observation is None:
            self.tropical_panel.show_overview(None)
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
                if self._selected_tropical_observation is None:
                    self.tropical_panel.show_error()
        else:
            if self.is_mounted:
                self.world_map.set_tropical_systems(systems)
                if self._selected_tropical_observation is None:
                    self.tropical_panel.show_overview(tuple(systems))
        finally:
            if self._tropical_wait_task is asyncio.current_task():
                self._tropical_wait_task = None

    def _select_tropical_detail(
        self,
        system: CanonicalTropicalSystem,
        observation: TropicalSystem,
    ) -> None:
        """Show one exact source and lazily join its app-owned product load."""

        key = _tropical_observation_key(observation)
        if self._tropical_detail_key == key and (
            self._tropical_product_task is None
            or not self._tropical_product_task.done()
        ):
            return
        self._cancel_tropical_product_wait()
        self._tropical_detail_key = key
        self.tropical_panel.show_system(system, observation)
        generation = self._tropical_detail_generation
        self._tropical_product_task = asyncio.create_task(
            self._load_tropical_detail_products(
                observation,
                key,
                generation,
            )
        )

    async def _load_tropical_detail_products(
        self,
        observation: TropicalSystem,
        key: tuple[str, str, str],
        generation: int,
    ) -> None:
        try:
            await self.tropical_panel.reset_products()
            products = await self.app.load_tropical_products(observation)
        except asyncio.CancelledError:
            raise
        except Exception:
            if generation == self._tropical_detail_generation:
                self._tropical_detail_key = None
            return
        finally:
            if (
                generation == self._tropical_detail_generation
                and self._tropical_product_task is asyncio.current_task()
            ):
                self._tropical_product_task = None
        if self._tropical_detail_result_is_current(key, generation):
            await self.tropical_panel.show_products(observation, products)

    def _tropical_detail_result_is_current(
        self,
        key: tuple[str, str, str],
        generation: int,
    ) -> bool:
        selected = self._selected_tropical_observation
        return (
            self.is_mounted
            and generation == self._tropical_detail_generation
            and selected is not None
            and _tropical_observation_key(selected) == key
        )

    def _cancel_tropical_product_wait(self) -> None:
        self._tropical_detail_generation += 1
        if (
            self._tropical_product_task is not None
            and not self._tropical_product_task.done()
        ):
            self._tropical_product_task.cancel()
        self._tropical_product_task = None
        self._tropical_detail_key = None

    def _show_persistent_location(self) -> None:
        location = self._selected_location or self.app.location
        self._displayed_location = location
        if location is None:
            self.forecast_panel.show_location(None)
            return
        snapshot = self.app.dashboard_forecast_snapshot(location)
        if snapshot is not None:
            self.forecast_panel.show_forecast(location, snapshot)
            return
        if (
            self._forecast_wait_task is not None
            and not self._forecast_wait_task.done()
            and self._forecast_request_key == self._forecast_selection_key(location)
        ):
            self.forecast_panel.show_loading(location)
            return
        self.forecast_panel.show_location(location)

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
            if self._forecast_result_is_current(key, generation):
                self.forecast_panel.show_error(location)
            return
        finally:
            if (
                generation == self._forecast_request_generation
                and self._forecast_wait_task is asyncio.current_task()
            ):
                self._forecast_request_key = None
                self._forecast_wait_task = None
        if self._forecast_result_is_current(key, generation):
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
            centre = self.query_one('#dashboard-center-column', Container)
            centre.styles.width = '1fr'
            centre.styles.height = '100%'
            centre.styles.margin = (0, budget.gutter, 0, 0)
            self.world_map.styles.width = '100%'
            self.world_map.styles.height = budget.map_height or '1fr'
            self.world_map.styles.margin = 0
            detail_row = self.query_one('#dashboard-detail-row', Container)
            detail_row.styles.width = '100%'
            detail_row.styles.height = budget.detail_height
            detail_row.styles.margin = (budget.detail_gutter, 0, 0, 0)
            self.tropical_panel.styles.width = '1fr'
            self.tropical_panel.styles.height = '100%'
            self.tropical_panel.styles.margin = (
                0,
                budget.detail_gutter,
                0,
                0,
            )
            self.alert_detail_panel.styles.width = '1fr'
            self.alert_detail_panel.styles.height = '100%'
            self.alert_detail_panel.styles.margin = 0
            self.alerts_panel.styles.width = budget.alert_width
            self.alerts_panel.styles.height = '100%'
            self.alerts_panel.styles.margin = 0
        else:
            centre = self.query_one('#dashboard-center-column', Container)
            for panel in (self.forecast_panel, centre, self.alerts_panel):
                panel.styles.width = '100%'
                panel.styles.height = '100%'
                panel.styles.margin = 0
            self.world_map.styles.width = '100%'
            self.world_map.styles.height = '100%'
            self.world_map.styles.margin = 0
        self._update_visibility()

    def _update_visibility(self) -> None:
        if self._layout_budget is None:
            return
        tabs = self.query_one('#dashboard-pane-tabs', Tabs)
        centre = self.query_one('#dashboard-center-column', Container)
        detail_row = self.query_one('#dashboard-detail-row', Container)
        tabs.display = not self._layout_budget.simultaneous
        if self._layout_budget.simultaneous:
            self.forecast_panel.display = True
            centre.display = True
            self.world_map.display = True
            detail_row.display = True
            self.tropical_panel.display = True
            self.alert_detail_panel.display = True
            self.alerts_panel.display = True
            return
        self.forecast_panel.display = self._active_pane == 'forecast'
        centre.display = self._active_pane in {
            'map',
            'tropical',
            'alert-detail',
        }
        self.world_map.display = self._active_pane == 'map'
        detail_row.display = self._active_pane in {'tropical', 'alert-detail'}
        self.tropical_panel.display = self._active_pane == 'tropical'
        self.alert_detail_panel.display = self._active_pane == 'alert-detail'
        if detail_row.display:
            detail_row.styles.height = '100%'
            detail_row.styles.margin = 0
            selected_detail = (
                self.tropical_panel
                if self._active_pane == 'tropical'
                else self.alert_detail_panel
            )
            selected_detail.styles.width = '100%'
            selected_detail.styles.height = '100%'
            selected_detail.styles.margin = 0
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


def _dashboard_place_heading(location: LocationMetadata | None) -> str:
    """Return the compact place heading without administrative regions."""

    if location is None:
        return 'No location selected'
    name = (location.name or '').strip()
    if not name and location.latitude is not None and location.longitude is not None:
        name = f'{location.latitude:.3f}, {location.longitude:.3f}'
    name = name or 'Selected location'
    country = (location.country or '').strip()
    return f'{name}\n{country}' if country and country != name else name


def _tropical_observation_key(
    observation: TropicalSystem,
) -> tuple[str, str, str]:
    issued = observation.issued_at.isoformat() if observation.issued_at else ''
    return observation.source, observation.id, issued


__all__ = [
    'DashboardAlertDetailPanel',
    'DashboardAlertsPanel',
    'DashboardForecastPanel',
    'DashboardScreen',
    'DashboardTropicalPanel',
]
