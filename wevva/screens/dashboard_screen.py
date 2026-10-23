"""Persistent unified weather dashboard."""

from __future__ import annotations

import asyncio
from dataclasses import replace
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
from textual.widgets import Footer, Header, OptionList, Static, Tab, Tabs
from textual.widgets.option_list import Option
from wevva_warnings import (
    CanonicalTropicalSystem,
    TropicalProduct,
    TropicalSystem,
)

from wevva.alerts import Alert
from wevva.config import location_key
from wevva.dashboard_layout import DashboardLayoutBudget, dashboard_layout_for
from wevva.layout import CurrentDensity
from wevva.location_metadata import LocationMetadata
from wevva.messages import (
    DashboardPlacePressed,
    DashboardTropicalActivated,
    HourHighlighted,
    PlaceSelected,
    WeatherUpdated,
)
from wevva.services.alert_bulletin import BulletinAlert
from wevva.services.country_alerts import country_alert_identity
from wevva.widgets.country_alerts_map import (
    CountryAlertCityLabel,
    CountryAlertSettlementPreviewCancelled,
    CountryAlertSettlementPreviewRequested,
    CountryAlertSettlementSelected,
    CountryAlertsMap,
    country_alert_place_weather_tooltip,
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
from wevva.widgets.tropical_systems import canonical_storm_key
from wevva.widgets.tropical_track import LargeTropicalStormTrackScope
from wevva.widgets.weather_alerts import (
    WeatherAlertPreviewBody,
    WeatherAlertsPanel,
    alert_condition_name,
    alert_renderable,
    alert_severity_color,
)
from wevva.utils.country_codes import get_country_name_by_alpha2


class DashboardWeatherAlertsPanel(WeatherAlertsPanel):
    """Weather's tabbed warning preview with a separator instead of a frame."""

    DEFAULT_CSS = """
    DashboardWeatherAlertsPanel {
        height: 5;
        max-width: 100%;
        border: none;
        border-top: solid $primary-muted;
        hatch: none;
    }

    DashboardWeatherAlertsPanel #weather-alert-body {
        padding: 0;
    }
    """

    def panel_title(self) -> str:
        return ''

    def __init__(
        self,
        alerts: list[Alert],
        location: LocationMetadata,
    ) -> None:
        super().__init__(alerts)
        self.location = location

    def apply_frame_color(self, color: str | None) -> None:
        if color:
            self.set_styles(f'border: none; border-top: solid {color};')

    def on_weather_alert_preview_body_open_requested(
        self,
        event: WeatherAlertPreviewBody.OpenRequested,
    ) -> None:
        """Open the selected warning through Dashboard's accurate detail route."""

        event.stop()
        event.prevent_default()
        alert = self.alerts[self.selected_index]
        self.app.open_alerts_centre_screen(
            country_code=self.location.country_code,
            alert_identity=country_alert_identity(alert),
        )

    def refresh_appearance(self) -> None:
        """Rebuild theme-sensitive tab labels and selected-alert content."""

        for index, tab in enumerate(self.tabs.query(Tab)):
            tab.label = self.build_tab_label(self.alerts[index])
        self.update_selected_alert()


class DashboardForecastPanel(Container):
    """Current, hourly, daily, and warning context for one Dashboard place."""

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
        height: 1fr;
        max-height: 24;
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

    #dashboard-location-alerts {
        display: none;
        width: 100%;
        height: 5;
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
        yield Container(id='dashboard-location-alerts')
        yield Static(
            '──────────────────────────────────────────────────────────',
            classes='dashboard-forecast-separator',
        )
        yield CurrentConditions(id='dashboard-current-conditions')
        yield Static(
            '──────────────────────────────────────────────────────────',
            classes='dashboard-forecast-separator',
        )
        yield DashboardHourlyForecast(id='dashboard-hourly-forecast')
        yield Static(
            '──────────────────────────────────────────────────────────',
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

    @property
    def location_alerts(self) -> Container:
        return self.query_one('#dashboard-location-alerts', Container)

    def on_mount(self) -> None:
        self._layout_context_rows = 1
        self._current_conditions_height = 5
        self._hourly_min_height = 5
        self._daily_rows = 3
        self._context_height = 6
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
        self._current_conditions_height = budget.current_conditions_height
        self._hourly_min_height = budget.hourly_min_height
        self._daily_rows = budget.daily_rows
        self._context_height = context_height
        self.context_bar.set_layout(
            row_count=budget.context_rows,
            height=context_height,
            narrow=True,
            show_air_quality=True,
            separated=True,
        )
        self._sync_context_visibility()
        self.call_after_refresh(self._sync_context_visibility)

    def show_location(
        self,
        location: LocationMetadata | None,
    ) -> None:
        """Show one place while its complete forecast is unavailable."""

        if not self.is_mounted:
            return
        self.loading = False
        self.query_one('#dashboard-forecast-status', Static).loading = False
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
        self.query_one('#dashboard-forecast-status', Static).loading = True

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
        *,
        force: bool = False,
    ) -> None:
        """Render one complete app-owned forecast in the narrow rail."""

        if not self.is_mounted:
            return
        identity = (
            location.latitude,
            location.longitude,
            location.elevation,
            location.name,
            location.admin,
            location.country,
            location.country_code,
            location.timezone,
            location.timezone_abbreviation,
            id(event.current),
            id(event.hourly),
            id(event.daily),
        )
        if not force and identity == getattr(self, '_forecast_identity', None):
            return
        self.loading = False
        self.query_one('#dashboard-forecast-status', Static).loading = False
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
        self.location_alerts.display = bool(
            self.location_alerts.children
        )
        self._sync_context_visibility()
        for separator in self.query('.dashboard-forecast-separator'):
            separator.display = True
        self.query_one('#dashboard-forecast-status', Static).display = False
        self._forecast_identity = identity

    def show_hour(self, index: int) -> None:
        """Update standard current instruments and AQI for one hourly row."""

        event = getattr(self, '_forecast_event', None)
        if event is None:
            return
        if event.hourly.get_point(index) is None:
            return
        self.current_conditions.hour_index = index
        self.context_bar.on_hour_highlighted(index)

    async def show_alerts(
        self,
        location: LocationMetadata,
        alerts: list[Alert],
    ) -> None:
        """Replace the selected location's compact warning preview."""

        await self.location_alerts.remove_children()
        if not alerts:
            self.location_alerts.display = False
            self._sync_context_visibility()
            return
        await self.location_alerts.mount(
            DashboardWeatherAlertsPanel(alerts, location)
        )
        self.location_alerts.display = getattr(self, '_forecast_event', None) is not None
        self._sync_context_visibility()

    def hide_alerts(self) -> None:
        """Hide stale warning content while another location is selected."""

        self.location_alerts.display = False
        for child in tuple(self.location_alerts.children):
            child.remove()
        self._sync_context_visibility()

    def _sync_context_visibility(self) -> None:
        """Keep the bottom context block inside the available forecast rail."""

        has_forecast = getattr(self, '_forecast_event', None) is not None
        required_height = (
            2
            + 3
            + self._current_conditions_height
            + self._hourly_min_height
            + self._daily_rows
            + self._context_height
            + (5 if self.location_alerts.display else 0)
        )
        self.context_bar.display = (
            has_forecast
            and self._layout_context_rows > 0
            and self.content_size.height >= required_height
        )

    def _show_status(self, message: str) -> None:
        self._forecast_identity = None
        self._forecast_event = None
        self.current_conditions.display = False
        self.hourly_forecast.display = False
        self.daily_forecast.display = False
        self.context_bar.display = False
        self.location_alerts.display = False
        for separator in self.query('.dashboard-forecast-separator'):
            separator.display = False
        status = self.query_one('#dashboard-forecast-status', Static)
        status.update(message)
        status.display = True

class DashboardAlertList(OptionList):
    """Alert list which reports transient map previews."""

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

class DashboardAlertsPanel(Container):
    """Stable bulletin rows with one committed selection."""

    class Selected(Message):
        def __init__(self, row: BulletinAlert | None) -> None:
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

    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._rows: tuple[BulletinAlert, ...] = ()
        self._by_option_id: dict[str, BulletinAlert] = {}
        self._selected_identity: tuple[str, str] | None = None
        self._last_text_width = 0
        self._presentation_key: tuple[tuple[BulletinAlert, str], ...] = ()

    def compose(self) -> ComposeResult:
        self.border_title = 'Severe Weather Alert Bulletin'
        yield DashboardAlertList(id='dashboard-alerts-list')
        yield Static(
            'New weather alerts will display here.',
            id='dashboard-alerts-empty',
        )

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

        presentation_key = self.presentation_key(rows)
        if presentation_key == self._presentation_key:
            return
        self._presentation_key = presentation_key
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

    def needs_update(self, rows: tuple[BulletinAlert, ...]) -> bool:
        """Return whether row content or its relative-time label changed."""

        return self.presentation_key(rows) != self._presentation_key

    @staticmethod
    def presentation_key(
        rows: tuple[BulletinAlert, ...],
    ) -> tuple[tuple[BulletinAlert, str], ...]:
        return tuple(
            (row, _relative_observation(row.first_observed))
            for row in rows
        )

    def refresh_appearance(self) -> None:
        """Rebuild only the theme-derived option labels."""

        self._refresh_option_labels()

    def clear_selection(self) -> None:
        self._selected_identity = None
        self.alert_list.clear_preview()
        self.alert_list.highlighted = None
        self._refresh_option_labels()
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
        self.post_message(self.Selected(self.selected_row))

    def on_dashboard_alert_list_preview_changed(
        self,
        event: DashboardAlertList.PreviewChanged,
    ) -> None:
        event.stop()
        self.post_message(
            self.Previewed(self._by_option_id.get(event.option_id or ''))
        )

    def on_resize(self, event: Resize) -> None:
        del event
        width = self._text_width()
        if width == self._last_text_width:
            return
        self._last_text_width = width
        self._refresh_option_labels()

    def _row_label(self, row: BulletinAlert) -> Text:
        alert = row.alert
        colour = alert_severity_color(self.app.theme_variables, alert)
        label = Text(no_wrap=True, overflow='ellipsis')
        prefix_width = 0
        if row.is_new:
            primary = self.app.theme_variables.get('primary', '#0178d4')
            background = self.app.theme_variables.get('background', '#000000')
            label.append('NEW', style=f'bold {background} on {primary}')
            label.append(' ')
            prefix_width = 4
        condition = Text(
            alert_condition_name(alert),
            style=f'bold {colour}' if colour else 'bold',
        )
        condition.truncate(
            max(1, self._text_width() - prefix_width),
            overflow='ellipsis',
        )
        label.append_text(condition)
        country = get_country_name_by_alpha2(row.country_code) or row.country_code
        detail = Text(
            f'{country} · {_relative_observation(row.first_observed)}',
            style='dim',
        )
        label.append('\n')
        detail.truncate(self._text_width(), overflow='ellipsis')
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

    _SELECTION_PROMPT = (
        'Select a tropical system on the map to view its track and official products.'
    )

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
                self._SELECTION_PROMPT,
                id='dashboard-tropical-detail-state',
            )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._observation: TropicalSystem | None = None
        self._products: tuple[TropicalProduct, ...] = ()
        self._product_indices: dict[str, int] = {}
        self._updating_tabs = False
        self._overview_state: tuple[str, bool] | None = None

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
            message = self._SELECTION_PROMPT
        else:
            message = 'No active tropical systems.'
        state = message, systems is None
        if state == self._overview_state:
            return
        self._overview_state = state
        self._show_state(message)
        self.set_loading(systems is None)

    def show_error(self) -> None:
        message = 'Tropical systems are temporarily unavailable.'
        state = message, False
        if state == self._overview_state:
            return
        self._overview_state = state
        self._show_state(message)
        self.set_loading(False)

    def set_loading(self, loading: bool) -> None:
        """Load inside the pane while retaining its titled outer frame."""

        self.loading = False
        self.query_one('#dashboard-tropical-content', Container).loading = loading

    def show_system(
        self,
        system: CanonicalTropicalSystem | None,
        observation: TropicalSystem | None,
    ) -> None:
        """Show the source track immediately, before product loading settles."""

        if system is None or observation is None:
            self.show_overview(())
            return
        self._overview_state = None
        self.set_loading(False)
        classification = (observation.classification or '').strip()
        name = (system.name or observation.name or '').strip()
        self._set_frame(
            ' '.join(part for part in (classification, name) if part)
            or 'Tropical System',
            self.app.theme_variables.get('accent')
            or self.app.theme_variables.get('text-accent'),
        )
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
        self.set_loading(False)

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
        self._set_frame(
            'Tropical System',
            self.app.theme_variables.get('primary'),
        )
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

    def _set_frame(self, title: str, colour: str | None) -> None:
        self.border_title = title or 'Tropical System'
        if colour:
            self.styles.border = ('round', colour)
            self.styles.border_title_color = colour


class DashboardAlertDetailPanel(Container):
    """Provider-neutral map and document reader for one bulletin alert."""

    _SELECTION_PROMPT = (
        'Select an alert from the bulletin to view its map and full details.'
    )

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

    #dashboard-alert-detail-tabs {
        width: 100%;
        height: 2;
    }

    #dashboard-alert-detail-content {
        width: 100%;
        height: 1fr;
        overflow: hidden hidden;
    }

    #dashboard-alert-map {
        width: 100%;
        height: 100%;
        min-height: 1;
        border: none;
    }

    #dashboard-alert-document {
        width: 100%;
        height: 100%;
        padding: 0 1;
        scrollbar-size-vertical: 1;
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

    _DOCUMENT_TAB_ID = 'dashboard-alert-document-tab'

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._row: BulletinAlert | None = None

    def compose(self) -> ComposeResult:
        self.border_title = 'Selected Alert'
        tabs = Tabs(
            Tab('Map', id='dashboard-alert-map-tab'),
            Tab('Alert', id=self._DOCUMENT_TAB_ID),
            active='dashboard-alert-map-tab',
            id='dashboard-alert-detail-tabs',
        )
        tabs.display = False
        yield tabs
        with Container(id='dashboard-alert-detail-content'):
            alert_map = CountryAlertsMap(id='dashboard-alert-map')
            alert_map.display = False
            yield alert_map
            document = VerticalScroll(id='dashboard-alert-document')
            document.display = False
            with document:
                yield Static(id='dashboard-alert-document-body')
            yield Static(
                self._SELECTION_PROMPT,
                id='dashboard-alert-detail-state',
            )

    @property
    def tabs(self) -> Tabs:
        return self.query_one('#dashboard-alert-detail-tabs', Tabs)

    @property
    def alert_map(self) -> CountryAlertsMap:
        return self.query_one('#dashboard-alert-map', CountryAlertsMap)

    def show_alert(self, row: BulletinAlert | None) -> None:
        """Present only tabs backed by the committed bulletin alert."""

        if row == self._row:
            return
        previous_identity = (
            country_alert_identity(self._row.alert)
            if self._row is not None
            else None
        )
        next_identity = (
            country_alert_identity(row.alert) if row is not None else None
        )
        same_selection = previous_identity == next_identity
        previous_tab = self.tabs.active if self.is_mounted else None
        self._row = row
        state = self.query_one('#dashboard-alert-detail-state', Static)
        if row is None:
            self._set_frame(
                'Selected Alert',
                self.app.theme_variables.get('primary'),
            )
            state.update(self._SELECTION_PROMPT)
            state.display = True
            self.tabs.display = False
            self.alert_map.display = False
            self.query_one('#dashboard-alert-document').display = False
            self.alert_map.clear()
            return
        alert = row.alert
        self._set_frame(
            alert_condition_name(alert),
            alert_severity_color(self.app.theme_variables, alert),
        )
        country = get_country_name_by_alpha2(row.country_code) or row.country_code
        self.alert_map.update_country(
            row.country_code,
            country,
            [alert],
            selected_alert_key=country_alert_identity(alert),
        )
        if not same_selection:
            self.alert_map.reset_city_tooltips()
        state.display = False
        self.tabs.display = True
        active_tab = (
            previous_tab
            if same_selection
            and previous_tab is not None
            else 'dashboard-alert-map-tab'
        )
        self.tabs.active = active_tab
        self._show_tab(active_tab)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if event.tabs is not self.tabs or event.tab.id is None:
            return
        event.stop()
        self._show_tab(event.tab.id)

    def _show_tab(self, tab_id: str) -> None:
        row = self._row
        if row is None:
            return
        is_map = tab_id == 'dashboard-alert-map-tab'
        self.alert_map.display = is_map
        document = self.query_one('#dashboard-alert-document', VerticalScroll)
        document.display = not is_map
        if is_map:
            return
        body = self.query_one('#dashboard-alert-document-body', Static)
        if tab_id == self._DOCUMENT_TAB_ID:
            body.update(alert_renderable(row.alert, include_timing=True))

    def refresh_appearance(self) -> None:
        """Refresh theme-derived detail styling without rebuilding geometry."""

        row = self._row
        if row is None:
            self._set_frame(
                'Selected Alert',
                self.app.theme_variables.get('primary'),
            )
        else:
            self._set_frame(
                alert_condition_name(row.alert),
                alert_severity_color(self.app.theme_variables, row.alert),
            )
            if self.tabs.active == self._DOCUMENT_TAB_ID:
                self._show_tab(self._DOCUMENT_TAB_ID)
        self.alert_map.refresh_theme()
        self.alert_map.reset_city_tooltips()

    def _set_frame(self, title: str, colour: str | None) -> None:
        self.border_title = title or 'Selected Alert'
        if colour:
            self.styles.border = ('round', colour)
            self.styles.border_title_color = colour


class DashboardScreen(Screen[None]):
    """Installed dashboard with one stable responsive widget tree."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding('w', 'back', 'Weather'),
        Binding('m', 'world_map', 'World Map'),
        Binding('t', 'tropical_systems', 'Tropical Systems'),
        Binding('g', 'alerts_centre', 'Alerts Centre'),
        Binding('r', 'refresh_bulletin', 'Refresh alerts'),
        Binding('left', 'previous_feature', 'Previous feature', show=False),
        Binding('right', 'next_feature', 'Next feature', show=False),
        Binding('escape', 'clear_alert_selection', 'Clear alert', show=False),
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
        background: $background;
        hatch: right $background-lighten-1;
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
        self._selected_tropical_system: CanonicalTropicalSystem | None = None
        self._selected_tropical_observation: TropicalSystem | None = None
        self._forecast_request_generation = 0
        self._forecast_request_key: tuple[str, str, str, str] | None = None
        self._forecast_wait_task: asyncio.Task[None] | None = None
        self._location_alert_generation = 0
        self._location_alert_key: tuple[str, str] | None = None
        self._location_alert_loaded_at: float | None = None
        self._location_alert_task: asyncio.Task[None] | None = None
        self._tropical_wait_task: asyncio.Task[None] | None = None
        self._tropical_product_task: asyncio.Task[None] | None = None
        self._tropical_detail_generation = 0
        self._tropical_detail_key: tuple[str, str, str] | None = None
        self._tropical_selection_refresh_task: asyncio.Task[None] | None = None
        self._tropical_selection_refresh_target: tuple[str, str, str] | None = None
        self._alert_place_weather_generation = 0
        self._alert_place_weather_task: asyncio.Task[None] | None = None
        self._alert_place_weather_label: CountryAlertCityLabel | None = None
        self._bulletin_generation = -1
        self._present_new_alert_identities: frozenset[tuple[str, str]] = frozenset()
        self._alert_return_focus: str | None = None
        self._time_refresh_timer = None

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
        panels = tuple(self.query(DashboardAlertsPanel)) if self.is_attached else ()
        row = panels[0].selected_row if panels and panels[0].is_attached else None
        return row.country_code if row is not None else None

    def action_refresh_bulletin(self) -> None:
        """Request only the bounded local bulletin refresh set."""

        self.app.refresh_dashboard_bulletin()

    def on_mount(self) -> None:
        self.title = 'Dashboard'
        self.sub_title = 'Weather, locations, storms, and alerts'
        self.sync_from_app()
        self._apply_layout(self.size.width, self.size.height)
        self._time_refresh_timer = self.set_interval(
            1,
            self.forecast_panel.context_bar.refresh_time_display,
        )
        self.call_after_refresh(self.world_map.focus_preferred_location)

    def on_screen_resume(self) -> None:
        if self._time_refresh_timer is not None:
            self._time_refresh_timer.resume()
        self.sync_from_app()
        self.world_map.set_selected_alert(
            self.alerts_panel.selected_row,
        )
        self.call_after_refresh(self._restore_focus)

    def on_screen_suspend(self) -> None:
        if self._time_refresh_timer is not None:
            self._time_refresh_timer.pause()
        self.world_map.pause_alert_marker()
        self._cancel_alert_place_weather()

    def on_unmount(self) -> None:
        if self._time_refresh_timer is not None:
            self._time_refresh_timer.stop()
            self._time_refresh_timer = None
        self._cancel_forecast_wait()
        self._cancel_location_alert_wait()
        if self._tropical_wait_task is not None:
            self._tropical_wait_task.cancel()
            self._tropical_wait_task = None
        self._cancel_tropical_selection_refresh()
        self._cancel_tropical_product_wait()
        self._cancel_alert_place_weather()

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
                location_key(self._selected_location),
                self._selected_location,
            )
        self.world_map.set_locations(locations, summaries=summaries)
        self.world_map.set_temperature_unit(self.app.temperature_unit)
        self.world_map.set_active_location(self.app.location)
        self.world_map.set_selected_location(
            self._selected_location or self.app.location
        )
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
        self._ensure_persistent_alerts()

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

    def refresh_appearance(self) -> None:
        """Rebuild theme/emoji-sensitive Rich content from cached state only."""

        if not self.is_mounted:
            return
        locations = self.app.locations_for_dashboard()
        self.world_map.set_locations(
            locations,
            summaries=self.app.saved_location_weather_summaries(locations),
            force=True,
        )
        self.world_map.set_temperature_unit(self.app.temperature_unit)
        if (systems := self.app.tropical_systems_snapshot()) is not None:
            self.world_map.set_tropical_systems(systems)
        self.update_bulletin(
            self.app.alert_bulletin.generation,
            self.app.alert_bulletin.recent_alerts_snapshot(),
        )
        self.alerts_panel.refresh_appearance()
        self.world_map.refresh_alert_appearance()
        self.alert_detail_panel.refresh_appearance()
        self._cancel_alert_place_weather()
        self._show_persistent_location(force=True)
        for panel in self.query(DashboardWeatherAlertsPanel):
            panel.refresh_appearance()
        self._ensure_persistent_alerts()

    def on_dashboard_place_pressed(self, message: DashboardPlacePressed) -> None:
        message.stop()
        self._select_forecast_location(message.location)

    def on_place_selected(self, message: PlaceSelected) -> None:
        """Keep mini-map place selection inside the Dashboard forecast rail."""

        message.stop()
        location = message.location
        if not location.country and location.country_code:
            country = get_country_name_by_alpha2(location.country_code)
            if country:
                location = replace(location, country=country)
        self._select_forecast_location(location)

    def on_dashboard_tropical_activated(
        self,
        message: DashboardTropicalActivated,
    ) -> None:
        """Commit the exact storm/source anchor to the Dashboard detail pane."""

        message.stop()
        refresh_target = (
            canonical_storm_key(message.system),
            message.observation.source,
            message.observation.id,
        )
        if (
            self._tropical_selection_refresh_task is not None
            and not self._tropical_selection_refresh_task.done()
        ):
            if refresh_target == self._tropical_selection_refresh_target:
                return
            refresh_required = True
        else:
            refresh_required = self.app.tropical_systems_snapshot() is None
        if refresh_required:
            self.world_map.set_selected_tropical(message.system)
            self._refresh_tropical_selection(
                message.system,
                message.observation,
            )
            return
        self._cancel_tropical_selection_refresh()
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

        if not self.is_attached or generation < self._bulletin_generation:
            return
        alerts_panels = tuple(self.query(DashboardAlertsPanel))
        world_maps = tuple(self.query(DashboardWorldMap))
        detail_panels = tuple(self.query(DashboardAlertDetailPanel))
        forecast_panels = tuple(self.query(DashboardForecastPanel))
        widgets = (
            *alerts_panels[:1],
            *world_maps[:1],
            *detail_panels[:1],
            *forecast_panels[:1],
        )
        if (
            len(widgets) != 4
            or not all(widget.is_attached for widget in widgets)
        ):
            return
        alerts_panel = alerts_panels[0]
        world_map = world_maps[0]
        detail_panel = detail_panels[0]
        arrived_while_open = (
            self._bulletin_generation >= 0
            and generation > self._bulletin_generation
            and self.app.screen is self
        )
        new_alert_identities = frozenset(
            country_alert_identity(row.alert) for row in rows if row.is_new
        )
        unflashed_rows = tuple(
            row
            for row in rows
            if row.is_new
            and country_alert_identity(row.alert)
            not in self._present_new_alert_identities
        )
        self._present_new_alert_identities = new_alert_identities
        self._bulletin_generation = generation
        previous_selection = alerts_panel.selected_row
        if alerts_panel.needs_update(rows):
            alerts_panel.update_alerts(rows)
        selected_row = alerts_panel.selected_row
        if _bulletin_detail_key(previous_selection) != _bulletin_detail_key(
            selected_row
        ):
            world_map.set_selected_alert(selected_row)
            detail_panel.show_alert(selected_row)
        if arrived_while_open and unflashed_rows:
            world_map.flash_new_alerts(unflashed_rows)
        self._ensure_persistent_alerts()

    def on_dashboard_alerts_panel_selected(
        self,
        message: DashboardAlertsPanel.Selected,
    ) -> None:
        message.stop()
        self._cancel_alert_place_weather()
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

    def on_country_alert_settlement_selected(
        self,
        event: CountryAlertSettlementSelected,
    ) -> None:
        """Show the focused-alert map's city in the Dashboard forecast rail."""

        event.stop()
        self._cancel_alert_place_weather()
        row = self.alerts_panel.selected_row
        country_code = event.place.country_code or (row.country_code if row else '')
        self._select_forecast_location(
            LocationMetadata(
                latitude=event.place.latitude,
                longitude=event.place.longitude,
                name=event.place.name,
                admin=event.place.region_name,
                country=get_country_name_by_alpha2(country_code) or country_code,
                country_code=country_code,
            )
        )

    def on_country_alert_settlement_preview_requested(
        self,
        event: CountryAlertSettlementPreviewRequested,
    ) -> None:
        """Load compact city weather only after a map label is inspected."""

        event.stop()
        self._cancel_alert_place_weather()
        self._alert_place_weather_generation += 1
        generation = self._alert_place_weather_generation
        self._alert_place_weather_label = event.label
        event.label.reset_tooltip()
        self._alert_place_weather_task = asyncio.create_task(
            self._load_alert_place_weather(generation, event.label)
        )

    def on_country_alert_settlement_preview_cancelled(
        self,
        event: CountryAlertSettlementPreviewCancelled,
    ) -> None:
        event.stop()
        if event.label is self._alert_place_weather_label:
            self._cancel_alert_place_weather()

    async def _load_alert_place_weather(
        self,
        generation: int,
        label: CountryAlertCityLabel,
    ) -> None:
        task = asyncio.current_task()
        try:
            await asyncio.sleep(0.15)
            response = await self.app.load_alert_place_weather(
                label.place.latitude,
                label.place.longitude,
                self.app.temperature_unit,
                self.app.wind_speed_unit,
                self.app.precipitation_unit,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            if self._alert_place_weather_request_is_current(generation, label):
                label.tooltip = country_alert_place_weather_tooltip(
                    label.place,
                    None,
                    theme=self.app.theme_variables,
                    temperature_unit=self.app.temperature_unit,
                    emoji_enabled=self.app.emoji_enabled,
                )
            return
        finally:
            if self._alert_place_weather_task is task:
                self._alert_place_weather_task = None
        if self._alert_place_weather_request_is_current(generation, label):
            label.tooltip = country_alert_place_weather_tooltip(
                label.place,
                response,
                theme=self.app.theme_variables,
                temperature_unit=self.app.temperature_unit,
                emoji_enabled=self.app.emoji_enabled,
            )

    def _alert_place_weather_request_is_current(
        self,
        generation: int,
        label: CountryAlertCityLabel,
    ) -> bool:
        return (
            self.is_attached
            and generation == self._alert_place_weather_generation
            and label is self._alert_place_weather_label
            and label.is_attached
        )

    def _cancel_alert_place_weather(self) -> None:
        self._alert_place_weather_generation += 1
        if self._alert_place_weather_task is not None:
            self._alert_place_weather_task.cancel()
            self._alert_place_weather_task = None
        self._alert_place_weather_label = None

    def _sync_tropical_systems(self) -> None:
        snapshot = self.app.tropical_systems_snapshot()
        if snapshot is not None:
            self.world_map.set_tropical_systems(snapshot)
            if self._selected_tropical_observation is None:
                self.tropical_panel.show_overview(snapshot)
            return
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
        self.tropical_panel.set_loading(True)
        generation = self._tropical_detail_generation
        self._tropical_product_task = asyncio.create_task(
            self._load_tropical_detail_products(
                observation,
                key,
                generation,
            )
        )

    def _refresh_tropical_selection(
        self,
        system: CanonicalTropicalSystem,
        observation: TropicalSystem,
    ) -> None:
        """Refresh one stale selection without disturbing its visible pane."""

        self._cancel_tropical_selection_refresh()
        self._cancel_tropical_product_wait()
        generation = self._tropical_detail_generation
        self._tropical_selection_refresh_target = (
            canonical_storm_key(system),
            observation.source,
            observation.id,
        )
        self.tropical_panel.set_loading(True)
        self._tropical_selection_refresh_task = asyncio.create_task(
            self._load_refreshed_tropical_selection(
                *self._tropical_selection_refresh_target,
                generation,
            )
        )

    async def _load_refreshed_tropical_selection(
        self,
        system_key: str,
        source: str,
        observation_id: str,
        generation: int,
    ) -> None:
        """Replace a stale pane only after its fresh products are available."""

        task = asyncio.current_task()
        try:
            systems = await self.app.load_tropical_systems()
            refreshed = _matching_tropical_selection(
                systems,
                system_key,
                source,
                observation_id,
            )
            if refreshed is None:
                products = None
            else:
                _system, observation = refreshed
                products = await self.app.load_tropical_products(observation)
        except asyncio.CancelledError:
            raise
        except Exception:
            if (
                self.is_mounted
                and generation == self._tropical_detail_generation
            ):
                self.tropical_panel.set_loading(False)
            return
        finally:
            if self._tropical_selection_refresh_task is task:
                self._tropical_selection_refresh_task = None
                self._tropical_selection_refresh_target = None

        if (
            not self.is_mounted
            or generation != self._tropical_detail_generation
        ):
            return
        self.world_map.set_tropical_systems(systems)
        if refreshed is None or products is None:
            self._selected_tropical_system = None
            self._selected_tropical_observation = None
            self.world_map.set_selected_tropical(None)
            self.tropical_panel.show_overview(tuple(systems))
            return

        system, observation = refreshed
        self._selected_tropical_system = system
        self._selected_tropical_observation = observation
        self.world_map.set_selected_tropical(system)
        self._tropical_detail_key = _tropical_observation_key(observation)
        self.tropical_panel.show_system(system, observation)
        await self.tropical_panel.show_products(observation, products)

    def _cancel_tropical_selection_refresh(self) -> None:
        was_loading = (
            self._tropical_selection_refresh_task is not None
            and not self._tropical_selection_refresh_task.done()
        )
        if (
            self._tropical_selection_refresh_task is not None
            and not self._tropical_selection_refresh_task.done()
        ):
            self._tropical_selection_refresh_task.cancel()
        self._tropical_selection_refresh_task = None
        self._tropical_selection_refresh_target = None
        if was_loading and self.is_mounted:
            self.tropical_panel.set_loading(False)

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
                self.tropical_panel.set_loading(False)
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
        was_loading = (
            self._tropical_product_task is not None
            and not self._tropical_product_task.done()
        )
        if (
            self._tropical_product_task is not None
            and not self._tropical_product_task.done()
        ):
            self._tropical_product_task.cancel()
        self._tropical_product_task = None
        self._tropical_detail_key = None
        if was_loading and self.is_mounted:
            self.tropical_panel.set_loading(False)

    def _show_persistent_location(self, *, force: bool = False) -> None:
        location = self._selected_location or self.app.location
        if location is None:
            self.forecast_panel.show_location(None)
            return
        snapshot = self.app.dashboard_forecast_snapshot(location)
        if snapshot is not None:
            self.forecast_panel.show_forecast(location, snapshot, force=force)
            return
        if (
            self._forecast_wait_task is not None
            and not self._forecast_wait_task.done()
            and self._forecast_request_key == self._forecast_selection_key(location)
        ):
            self.forecast_panel.show_loading(location)
            return
        self.forecast_panel.show_location(location)

    def _select_forecast_location(self, location: LocationMetadata) -> None:
        """Commit one place to the rail without adopting it as Weather state."""

        self._selected_location = location
        self.app.note_bulletin_country_used(location.country_code)
        self.world_map.set_selected_location(location)
        self._show_persistent_location()
        self._ensure_persistent_forecast()
        self._ensure_persistent_alerts()

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

    def _ensure_persistent_alerts(self) -> None:
        """Load warnings once for the current Dashboard location selection."""

        location = self._selected_location or self.app.location
        if location is None:
            self._cancel_location_alert_wait()
            self.forecast_panel.hide_alerts()
            return
        key = (location_key(location), self.app.warning_language)
        loaded_is_fresh = (
            self._location_alert_loaded_at is not None
            and asyncio.get_running_loop().time() - self._location_alert_loaded_at
            < self.app.country_alerts_service.ttl_seconds
        )
        if key == self._location_alert_key and (
            loaded_is_fresh
            or (
                self._location_alert_task is not None
                and not self._location_alert_task.done()
            )
        ):
            return
        replacing_same_location = key == self._location_alert_key
        self._cancel_location_alert_wait()
        if not replacing_same_location:
            self.forecast_panel.hide_alerts()
        self._location_alert_generation += 1
        generation = self._location_alert_generation
        self._location_alert_key = key
        self._location_alert_task = asyncio.create_task(
            self._load_location_alerts(location, key, generation)
        )

    async def _load_location_alerts(
        self,
        location: LocationMetadata,
        key: tuple[str, str],
        generation: int,
    ) -> None:
        """Apply point warnings only to the selection that requested them."""

        try:
            alerts = await self.app.load_dashboard_alerts(location)
        except asyncio.CancelledError:
            raise
        except Exception:
            alerts = []
        if not self._location_alert_result_is_current(key, generation):
            return
        try:
            await self.forecast_panel.show_alerts(location, alerts)
            self._location_alert_loaded_at = asyncio.get_running_loop().time()
        finally:
            if (
                generation == self._location_alert_generation
                and self._location_alert_task is asyncio.current_task()
            ):
                self._location_alert_task = None

    def _location_alert_result_is_current(
        self,
        key: tuple[str, str],
        generation: int,
    ) -> bool:
        location = self._selected_location or self.app.location
        return (
            generation == self._location_alert_generation
            and location is not None
            and key == (location_key(location), self.app.warning_language)
        )

    def _cancel_location_alert_wait(self) -> None:
        self._location_alert_generation += 1
        if (
            self._location_alert_task is not None
            and not self._location_alert_task.done()
        ):
            self._location_alert_task.cancel()
        self._location_alert_task = None
        self._location_alert_key = None
        self._location_alert_loaded_at = None

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
        if self._layout_budget is None or self._layout_budget.simultaneous:
            self.world_map.focus_preferred_location()
        elif self._active_pane == 'map':
            self.world_map.focus_preferred_location()

    def action_back(self) -> None:
        self._cancel_forecast_wait()
        self._cancel_alert_place_weather()
        self.app.pop_screen()

    def action_world_map(self) -> None:
        self.app.open_world_locations_screen()

    async def action_tropical_systems(self) -> None:
        await self.app.open_tropical_systems_screen()

    def action_alerts_centre(self) -> None:
        self.app.open_alerts_centre_screen()

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

def _bulletin_option_id(row: BulletinAlert) -> str:
    source, alert_id = country_alert_identity(row.alert)
    digest = hashlib.sha1(f'{source}\0{alert_id}'.encode()).hexdigest()[:16]
    return f'bulletin-{digest}'


def _bulletin_detail_key(
    row: BulletinAlert | None,
) -> tuple[str, Alert] | None:
    """Identify map/document content independently of badge and row age."""

    return None if row is None else (row.country_code, row.alert)


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


def _dashboard_place_heading(location: LocationMetadata | None) -> Text:
    """Return the compact place heading without administrative regions."""

    if location is None:
        return Text('No location selected', style='bold', justify='center')
    name = (location.name or '').strip()
    if not name and location.latitude is not None and location.longitude is not None:
        name = f'{location.latitude:.3f}, {location.longitude:.3f}'
    name = name or 'Selected location'
    heading = Text(name, style='bold', justify='center')
    country = (location.country or '').strip()
    if country and country != name:
        heading.append('\n')
        heading.append(country, style='dim not bold')
    return heading


def _tropical_observation_key(
    observation: TropicalSystem,
) -> tuple[str, str, str]:
    issued = observation.issued_at.isoformat() if observation.issued_at else ''
    return observation.source, observation.id, issued


def _matching_tropical_selection(
    systems: list[CanonicalTropicalSystem],
    system_key: str,
    source: str,
    observation_id: str,
) -> tuple[CanonicalTropicalSystem, TropicalSystem] | None:
    """Find the refreshed form of one exact Dashboard source selection."""

    for system in systems:
        if canonical_storm_key(system) != system_key:
            continue
        source_match = None
        for observation in system.observations:
            if observation.source != source:
                continue
            source_match = source_match or observation
            if observation.id == observation_id:
                return system, observation
        return None if source_match is None else (system, source_match)
    return None


__all__ = [
    'DashboardAlertDetailPanel',
    'DashboardAlertsPanel',
    'DashboardForecastPanel',
    'DashboardScreen',
    'DashboardTropicalPanel',
]
