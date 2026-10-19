"""Country alert discovery workspace (Task 0020)."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any, ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.events import Resize
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    OptionList,
    ProgressBar,
    Select,
    Static,
    Tab,
    Tabs,
)
from textual.widgets.option_list import Option
from wevva_warnings import Alert, WarningQueryProgress

from wevva.alerts_centre_layout import (
    AlertsCentreLayoutBudget,
    AlertsCentrePresentation,
    alerts_centre_layout_for,
)
from wevva.conditions import get_condition
from wevva.geography import PopulatedPlace
from wevva.location_metadata import LocationMetadata
from wevva.messages import PlaceSelected
from wevva.services.alerts import normalize_country_code
from wevva.services.country_alerts import (
    CountryAlertsService,
    SupportedAlertCountry,
    country_alert_default_filter,
    country_alert_identity,
    list_supported_alert_countries,
)
from wevva.widgets.country_alerts_map import (
    CountryAlertCityLabel,
    CountryAlertSettlementPreviewCancelled,
    CountryAlertSettlementPreviewRequested,
    CountryAlertSettlementSelected,
    CountryAlertsMap,
)
from wevva.utils import bearing_to_direction, rain_colour, temp_colour, wind_colour
from wevva.widgets.weather_alerts import (
    WeatherAlertDetailsPanel,
    alert_condition_name,
    alert_renderable,
    alert_severity_color,
)

PlaceWeatherLoader = Callable[
    [float, float, str, str, str],
    Awaitable[dict[str, Any]],
]
_PLACE_WEATHER_CACHE_TTL_SECONDS = 15 * 60
_PLACE_WEATHER_HOVER_DELAY_SECONDS = 0.15
_ALERT_AREA_LABEL_MAX_LENGTH = 24


class AlertFilterDialog(ModalScreen[tuple[str, str, str] | None]):
    """Edit the Alerts Centre's local metadata filter and ordering."""

    BINDINGS = [Binding('escape', 'cancel', 'Cancel', show=False)]

    DEFAULT_CSS = """
    AlertFilterDialog {
        align: center middle;
        background: $background 70%;
    }

    #alerts-centre-filter-dialog {
        width: 60;
        max-width: 90%;
        height: auto;
        padding: 1 2;
        border: round $primary;
        border-title-color: $primary;
        background: $panel;
    }

    #alerts-centre-filter-dialog Input,
    #alerts-centre-filter-dialog Select {
        width: 100%;
        margin-bottom: 1;
    }

    #alerts-centre-filter-actions {
        layout: horizontal;
        width: 100%;
        height: 3;
        align-horizontal: center;
    }

    #alerts-centre-filter-actions Button {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        value: str,
        severity_value: str,
        severity_options: tuple[tuple[str, str], ...],
        sort_value: str,
    ) -> None:
        super().__init__()
        self.value = value
        self.severity_value = severity_value
        self.severity_options = severity_options
        self.sort_value = sort_value

    def compose(self) -> ComposeResult:
        with Container(id='alerts-centre-filter-dialog') as dialog:
            dialog.border_title = 'Filter alerts'
            yield Input(
                value=self.value,
                placeholder='Condition, location, or source',
                id='alerts-centre-filter-dialog-input',
            )
            yield Select(
                options=[('All severities', ''), *self.severity_options],
                value=self.severity_value,
                allow_blank=False,
                id='alerts-centre-filter-dialog-severity',
            )
            yield Select(
                options=[
                    ('Severity', 'severity'),
                    ('New first', 'new'),
                ],
                value=self.sort_value,
                allow_blank=False,
                id='alerts-centre-filter-dialog-sort',
            )
            with Container(id='alerts-centre-filter-actions'):
                yield Button('Clear', id='alerts-centre-filter-clear')
                yield Button(
                    'Apply',
                    variant='primary',
                    id='alerts-centre-filter-apply',
                )
                yield Button('Cancel', id='alerts-centre-filter-cancel')

    def on_mount(self) -> None:
        field = self.query_one('#alerts-centre-filter-dialog-input', Input)
        field.focus()
        field.cursor_position = len(field.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.dismiss(self._result(event.value))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == 'alerts-centre-filter-cancel':
            self.dismiss(None)
        elif event.button.id == 'alerts-centre-filter-clear':
            self.dismiss(self._result('', clear_severity=True))
        else:
            self.dismiss(
                self._result(
                    self.query_one(
                        '#alerts-centre-filter-dialog-input',
                        Input,
                    ).value
                )
            )

    def _result(
        self,
        value: str,
        *,
        clear_severity: bool = False,
    ) -> tuple[str, str, str]:
        severity_value = self.query_one(
            '#alerts-centre-filter-dialog-severity',
            Select,
        ).value
        sort_value = self.query_one(
            '#alerts-centre-filter-dialog-sort',
            Select,
        ).value
        return (
            value,
            (
                severity_value
                if isinstance(severity_value, str) and not clear_severity
                else ''
            ),
            sort_value if isinstance(sort_value, str) else 'severity',
        )

    def action_cancel(self) -> None:
        self.dismiss(None)


class AlertsCentreScreen(Screen[None]):
    """Typeable country browser and full provider-document reader."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding('w', 'back', 'Weather'),
        Binding('escape', 'back', 'Weather', show=False),
        Binding('r', 'refresh_alerts', 'Refresh'),
        Binding('s', 'block_app_binding', '', show=False),
        Binding('a', 'block_app_binding', '', show=False),
        Binding('d', 'block_app_binding', '', show=False),
    ]

    DEFAULT_CSS = """
    AlertsCentreScreen {
        background: $background;
    }

    #alerts-centre-stage {
        width: 100%;
        height: 1fr;
        padding: 1 2;
        align: center middle;
        overflow: hidden hidden;
        background: $background;
        hatch: right $background-lighten-1;
    }

    #alerts-centre-root {
        width: 100%;
        height: 100%;
        layout: vertical;
        background: $background;
        overflow: hidden hidden;
    }

    #alerts-centre-pane-tabs,
    #alerts-centre-workspace-tabs {
        display: none;
        width: 100%;
        height: 2;
    }

    #alerts-centre-body {
        width: 100%;
        height: 1fr;
        layout: horizontal;
        overflow: hidden hidden;
        background: $background;
        hatch: right $background-lighten-1;
    }

    #alerts-centre-navigation {
        width: 36;
        min-width: 28;
        height: 100%;
        layout: vertical;
        margin-right: 2;
        border: round $primary;
        border-title-color: $primary;
        padding: 0 1;
        background: $background;
    }

    #alerts-centre-right {
        width: 1fr;
        height: 100%;
        layout: vertical;
        overflow: hidden hidden;
    }

    #alerts-centre-right-content {
        width: 100%;
        height: 1fr;
        layout: horizontal;
        overflow: hidden hidden;
        background: $background;
        hatch: right $background-lighten-1;
    }

    #alerts-centre-map-pane {
        width: 1fr;
        min-width: 18;
        height: 100%;
        layout: vertical;
        margin-right: 2;
        overflow: hidden hidden;
    }

    #alerts-centre-country-select,
    #alerts-centre-filter-button {
        width: 100%;
        min-width: 0;
        margin: 0;
    }

    #alerts-centre-country-select,
    #alerts-centre-filter-button {
        margin-bottom: 1;
    }

    #alerts-centre-alert-list {
        display: none;
        width: 100%;
        height: 1fr;
        min-height: 3;
        scrollbar-size-vertical: 1;
    }

    #alerts-centre-alert-list > .option-list--separator {
        color: $primary-muted;
    }

    #alerts-centre-list-empty {
        width: 100%;
        height: auto;
        padding: 0 1;
        color: $text-muted;
        text-style: italic;
    }

    #alerts-centre-list-empty {
        height: 1fr;
        content-align: center middle;
        text-align: center;
    }

    #alerts-centre-list-progress {
        display: none;
        width: 100%;
        height: 1fr;
        padding: 0 1;
        align: center middle;
    }

    #alerts-centre-list-progress-bar {
        width: 100%;
        height: 1;
    }

    #alerts-centre-list-progress-bar > Bar {
        width: 1fr;
    }

    #alerts-centre-map {
        width: 100%;
        min-width: 18;
        height: 1fr;
        margin: 0;
    }

    #alerts-centre-document-pane {
        width: 32%;
        min-width: 24;
        height: 100%;
        layout: vertical;
        border: round $primary;
        border-title-color: $primary;
        background: $background;
    }

    #alerts-centre-document-pane WeatherAlertDetailsPanel {
        width: 100%;
        height: 1fr;
        border: none;
    }

    #alerts-centre-document-empty {
        width: 100%;
        height: 1fr;
        padding: 1 2;
        content-align: center middle;
        text-align: center;
        color: $text-muted;
        text-style: italic;
    }

    #alerts-centre-root.stacked #alerts-centre-right-content {
        layout: vertical;
    }

    #alerts-centre-root.stacked #alerts-centre-map-pane {
        width: 100%;
        height: 55%;
        min-height: 8;
        margin: 0 0 1 0;
    }

    #alerts-centre-root.stacked #alerts-centre-document-pane {
        width: 100%;
        height: 1fr;
        min-height: 7;
    }

    #alerts-centre-root.tabbed #alerts-centre-workspace-tabs {
        display: block;
    }

    #alerts-centre-root.tabbed #alerts-centre-country-select,
    #alerts-centre-root.tabbed #alerts-centre-filter-button,
    #alerts-centre-root.single #alerts-centre-country-select {
        margin-bottom: 0;
    }

    #alerts-centre-root.single #alerts-centre-filter-button {
        margin-bottom: 0;
    }

    #alerts-centre-root.tabbed #alerts-centre-filter-button,
    #alerts-centre-root.single #alerts-centre-filter-button {
        height: 1;
        min-height: 1;
        padding: 0;
        border: none;
    }

    #alerts-centre-root.tabbed #alerts-centre-map-pane,
    #alerts-centre-root.tabbed #alerts-centre-document-pane,
    #alerts-centre-root.single #alerts-centre-map-pane,
    #alerts-centre-root.single #alerts-centre-document-pane {
        width: 100%;
        height: 100%;
    }

    #alerts-centre-root.tabbed #alerts-centre-map-pane,
    #alerts-centre-root.single #alerts-centre-map-pane,
    #alerts-centre-root.single #alerts-centre-navigation {
        margin: 0;
    }

    #alerts-centre-root.single #alerts-centre-pane-tabs {
        display: block;
    }

    #alerts-centre-root.single #alerts-centre-body {
        layout: vertical;
    }

    #alerts-centre-root.single #alerts-centre-navigation,
    #alerts-centre-root.single #alerts-centre-right {
        width: 100%;
        height: 100%;
    }
    """

    def __init__(
        self,
        *,
        service: CountryAlertsService | None = None,
        countries: list[SupportedAlertCountry] | None = None,
        initial_country_code: str | None = None,
        warning_language: str = 'auto',
        place_weather_loader: PlaceWeatherLoader | None = None,
        place_weather_cache_ttl_seconds: float = _PLACE_WEATHER_CACHE_TTL_SECONDS,
        place_weather_hover_delay_seconds: float = _PLACE_WEATHER_HOVER_DELAY_SECONDS,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        super().__init__()
        self.service = service or CountryAlertsService()
        self.countries = list(list_supported_alert_countries() if countries is None else countries)
        self.initial_country_code = normalize_country_code(initial_country_code)
        self.warning_language = warning_language
        self._place_weather_loader = place_weather_loader
        self._place_weather_cache_ttl_seconds = max(
            0.0,
            float(place_weather_cache_ttl_seconds),
        )
        self._place_weather_hover_delay_seconds = max(
            0.0,
            float(place_weather_hover_delay_seconds),
        )
        self._clock = clock
        self._place_weather_cache: dict[
            tuple[float, float, str, str, str],
            tuple[float, dict[str, Any]],
        ] = {}
        self.alert_filter_value = ''
        self.alert_severity_filter = ''
        self.alert_sort_value = 'severity'
        self.selected_country_code: str | None = None
        self.alerts: list[Alert] = []
        self.filtered_alerts: list[Alert] = []
        self.new_alert_keys: set[tuple[str, str]] = set()
        self.selected_alert_key: tuple[str, str] | None = None
        self._alert_by_option_id: dict[str, Alert] = {}
        self._load_generation = 0
        self._ui_thread_id: int | None = None
        self._progress_items_total: int | None = None
        self._load_task: asyncio.Task[None] | None = None
        self._place_weather_generation = 0
        self._place_weather_task: asyncio.Task[None] | None = None
        self._place_weather_label: CountryAlertCityLabel | None = None
        self._layout_budget: AlertsCentreLayoutBudget | None = None
        self._presentation: AlertsCentrePresentation | None = None
        self._workspace_tab = 'map'
        self._single_tab = 'navigation'
        self._pending_units_changed = False
        self._pending_appearance_changed = False
        self._pending_language_changed = False
        self._filter_dialog_open = False
        self._preserve_country_on_resume = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id='alerts-centre-stage'), Container(id='alerts-centre-root'):
            yield Tabs(
                Tab('Navigation', id='alerts-centre-pane-navigation'),
                Tab('Map', id='alerts-centre-pane-map'),
                Tab('Details', id='alerts-centre-pane-details'),
                active='alerts-centre-pane-navigation',
                id='alerts-centre-pane-tabs',
            )
            with Container(id='alerts-centre-body'):
                with Container(id='alerts-centre-navigation') as navigation:
                    navigation.border_title = 'Alert navigation'
                    yield Select(
                        options=[(country.name, country.code) for country in self.countries],
                        prompt='Choose country',
                        allow_blank=True,
                        id='alerts-centre-country-select',
                    )
                    yield Button(
                        'Filter alerts',
                        variant='primary',
                        id='alerts-centre-filter-button',
                    )
                    yield Static(
                        'Select a country to view alerts',
                        id='alerts-centre-list-empty',
                    )
                    with Container(id='alerts-centre-list-progress'):
                        yield ProgressBar(
                            total=None,
                            show_percentage=True,
                            show_eta=False,
                            id='alerts-centre-list-progress-bar',
                        )
                    yield OptionList(id='alerts-centre-alert-list')
                with Container(id='alerts-centre-right'):
                    yield Tabs(
                        Tab('Map', id='alerts-centre-workspace-map'),
                        Tab('Details', id='alerts-centre-workspace-details'),
                        active='alerts-centre-workspace-map',
                        id='alerts-centre-workspace-tabs',
                    )
                    with Container(id='alerts-centre-right-content'):
                        with Container(id='alerts-centre-map-pane'):
                            yield CountryAlertsMap(id='alerts-centre-map')
                        with Container(id='alerts-centre-document-pane') as document_pane:
                            document_pane.border_title = 'Alert Detail'
                            yield Static(
                                'Select an alert to view detailed information',
                                id='alerts-centre-document-empty',
                            )
                            details = WeatherAlertDetailsPanel(
                                framed=False,
                                id='alerts-centre-document',
                            )
                            details.display = False
                            yield details
        yield Footer()

    @property
    def country_select(self) -> Select[str]:
        return self.query_one('#alerts-centre-country-select', Select)

    @property
    def alert_filter_button(self) -> Button:
        return self.query_one('#alerts-centre-filter-button', Button)

    @property
    def alert_list(self) -> OptionList:
        return self.query_one('#alerts-centre-alert-list', OptionList)

    @property
    def details(self) -> WeatherAlertDetailsPanel:
        return self.query_one('#alerts-centre-document', WeatherAlertDetailsPanel)

    @property
    def country_map(self) -> CountryAlertsMap:
        return self.query_one('#alerts-centre-map', CountryAlertsMap)

    async def on_mount(self) -> None:
        self._ui_thread_id = threading.get_ident()
        self.title = 'Alerts Centre'
        self.sub_title = 'Country weather warnings'
        self._apply_responsive_layout(self.size.width, self.size.height)
        country_code = self._initial_country()
        if country_code is None:
            self._show_alert_list_state('No supported alert countries are available.')
            return
        self._choose_country(country_code)
        self._apply_pending_preferences()

    def on_screen_resume(self) -> None:
        """Apply changes queued while this installed screen was suspended."""
        if self._filter_dialog_open:
            # Returning from our child modal must retain the country being
            # filtered rather than reapplying the weather location's country.
            self._filter_dialog_open = False
        elif self._preserve_country_on_resume:
            self._preserve_country_on_resume = False
        else:
            country_code = self._initial_country()
            if country_code is not None and country_code != self.selected_country_code:
                self._choose_country(country_code)
        self._apply_pending_preferences()

    def preserve_country_on_next_resume(self, preserve: bool) -> None:
        """Retain alert context after map navigation, unless superseded."""

        self._preserve_country_on_resume = preserve

    def on_unmount(self) -> None:
        # ``asyncio.to_thread`` cancellation cannot stop the provider thread.
        # On final app teardown, invalidate its callback before detaching so
        # late per-alert progress cannot keep entering Textual's message loop.
        self._load_generation += 1
        if self._load_task is not None:
            self._load_task.cancel()
            self._load_task = None
        self._cancel_place_weather_preview()

    def on_resize(self, event: Resize) -> None:
        self._apply_responsive_layout(event.size.width, event.size.height)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        tab_id = event.tab.id
        if tab_id == 'alerts-centre-workspace-map':
            self._workspace_tab = 'map'
        elif tab_id == 'alerts-centre-workspace-details':
            self._workspace_tab = 'details'
        elif tab_id == 'alerts-centre-pane-navigation':
            self._single_tab = 'navigation'
        elif tab_id == 'alerts-centre-pane-map':
            self._single_tab = 'map'
        elif tab_id == 'alerts-centre-pane-details':
            self._single_tab = 'details'
        else:
            return
        self._update_responsive_visibility()

    def _apply_responsive_layout(self, width: int, height: int) -> None:
        self._layout_width = width
        self._layout_height = height
        budget = alerts_centre_layout_for(width, height)
        if budget == self._layout_budget:
            return
        self._layout_budget = budget
        root = self.query_one('#alerts-centre-root', Container)
        root.remove_class('wide', 'stacked', 'tabbed', 'single')
        root.add_class(budget.presentation.value)
        navigation = self.query_one('#alerts-centre-navigation', Container)
        document = self.query_one('#alerts-centre-document-pane', Container)
        if budget.presentation is AlertsCentrePresentation.SINGLE:
            navigation.styles.width = '100%'
        else:
            navigation.styles.width = budget.navigation_width
        if budget.presentation is AlertsCentrePresentation.WIDE:
            document.styles.width = budget.navigation_width
        else:
            document.styles.width = '100%'
        compact_controls = budget.presentation in {
            AlertsCentrePresentation.TABBED,
            AlertsCentrePresentation.SINGLE,
        }
        self.country_select.compact = compact_controls
        self.country_map.set_max_city_labels(budget.settlement_label_limit)
        self._presentation = budget.presentation
        self._update_responsive_visibility()

    def _update_responsive_visibility(self) -> None:
        if self._presentation is None or not self.is_mounted:
            return
        navigation = self.query_one('#alerts-centre-navigation', Container)
        right = self.query_one('#alerts-centre-right', Container)
        map_pane = self.query_one('#alerts-centre-map-pane', Container)
        document = self.query_one('#alerts-centre-document-pane', Container)

        if self._presentation in {
            AlertsCentrePresentation.WIDE,
            AlertsCentrePresentation.STACKED,
        }:
            navigation.display = True
            right.display = True
            map_pane.display = True
            document.display = True
        elif self._presentation is AlertsCentrePresentation.TABBED:
            navigation.display = True
            right.display = True
            map_pane.display = self._workspace_tab == 'map'
            document.display = self._workspace_tab == 'details'
        else:
            navigation.display = self._single_tab == 'navigation'
            right.display = self._single_tab != 'navigation'
            map_pane.display = self._single_tab == 'map'
            document.display = self._single_tab == 'details'

    def _initial_country(self) -> str | None:
        supported = {country.code for country in self.countries}
        active_location = getattr(self.app, 'location', None)
        active_country = normalize_country_code(getattr(active_location, 'country_code', None))
        candidates = (
            active_country,
            self.initial_country_code,
            normalize_country_code(self.service.last_country_code),
        )
        return next(
            (candidate for candidate in candidates if candidate in supported),
            self.countries[0].code if self.countries else None,
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != 'alerts-centre-filter-button':
            return
        event.stop()
        severity_options = _alert_severity_options(self.alerts)
        available_severities = {value for _, value in severity_options}
        if self.alert_severity_filter not in available_severities:
            self.alert_severity_filter = ''
        self._filter_dialog_open = True
        self.app.push_screen(
            AlertFilterDialog(
                self.alert_filter_value,
                self.alert_severity_filter,
                severity_options,
                self.alert_sort_value,
            ),
            callback=self._on_alert_filter_result,
        )

    def _on_alert_filter_result(
        self,
        result: tuple[str, str, str] | None,
    ) -> None:
        if result is None:
            return
        value, severity_value, sort_value = result
        self.alert_filter_value = value
        self.alert_severity_filter = severity_value
        self.alert_sort_value = sort_value
        self._apply_alert_filter(
            value,
            preferred_key=self.selected_alert_key,
        )

    def on_select_changed(self, event: Select.Changed) -> None:
        if (
            event.select.id == 'alerts-centre-country-select'
            and isinstance(event.value, str)
            and event.value != self.selected_country_code
        ):
            self._choose_country(event.value)

    def on_option_list_option_selected(
        self,
        event: OptionList.OptionSelected,
    ) -> None:
        option_id = event.option.id or ''
        if event.option_list.id == 'alerts-centre-alert-list':
            alert = self._alert_by_option_id.get(option_id)
            if alert is not None:
                self._select_alert(alert)

    def on_country_alert_settlement_selected(
        self,
        event: CountryAlertSettlementSelected,
    ) -> None:
        """Open the application's complete weather view for a map settlement."""

        event.stop()
        self._cancel_place_weather_preview()
        country_code = event.place.country_code or self.selected_country_code or ''
        self.post_message(
            PlaceSelected(
                location=LocationMetadata(
                    latitude=event.place.latitude,
                    longitude=event.place.longitude,
                    name=event.place.name,
                    admin=event.place.region_name,
                    country=self._country_name(country_code) if country_code else '',
                    country_code=country_code,
                ),
                preserve_alerts_context=True,
            )
        )

    def on_country_alert_settlement_preview_requested(
        self,
        event: CountryAlertSettlementPreviewRequested,
    ) -> None:
        """Start or reuse the hovered settlement's compact weather preview."""

        event.stop()
        self._start_place_weather_preview(event.label)

    def on_country_alert_settlement_preview_cancelled(
        self,
        event: CountryAlertSettlementPreviewCancelled,
    ) -> None:
        """Cancel a request which is no longer associated with the pointer."""

        event.stop()
        if event.label is self._place_weather_label:
            self._cancel_place_weather_preview()

    def _choose_country(self, country_code: str) -> None:
        country = next(
            (country for country in self.countries if country.code == country_code),
            None,
        )
        if country is None:
            return
        previous_country = self.selected_country_code
        self.selected_country_code = country.code
        self.service.last_country_code = country.code
        if self.country_select.value != country.code:
            self.country_select.value = country.code
        if previous_country != country.code:
            self._cancel_place_weather_preview()
            self.alert_filter_value = country_alert_default_filter(
                country.code,
                country.name,
            )
        self._start_country_load(
            refresh=False,
            preserve_existing=previous_country == country.code,
        )

    def _start_country_load(
        self,
        *,
        refresh: bool,
        preserve_existing: bool,
    ) -> None:
        if self.selected_country_code is None:
            return
        self._load_generation += 1
        generation = self._load_generation
        if self._load_task is not None:
            self._load_task.cancel()
        country = self._country_name(self.selected_country_code)
        if not preserve_existing:
            self.alerts = []
            self.filtered_alerts = []
            self.new_alert_keys.clear()
            self.selected_alert_key = None
            self._render_alert_options()
            self.country_map.update_country(
                self.selected_country_code,
                country,
                (),
            )
            self._clear_document()
        self.alert_filter_button.disabled = True
        self._show_alert_list_progress()
        self._load_task = asyncio.create_task(self._load_country(self.selected_country_code, generation, refresh=refresh))

    async def _load_country(
        self,
        country_code: str,
        generation: int,
        *,
        refresh: bool,
    ) -> None:
        progress = self._progress_callback(generation, country_code)
        try:
            alerts = await self.service.get_alerts(
                country_code,
                warning_language=self.warning_language,
                progress=progress,
                refresh=refresh,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            if not self._request_is_current(generation, country_code):
                return
            self.alert_filter_button.disabled = False
            self._show_alert_list_state('Alerts are temporarily unavailable. Press r to retry.')
            return
        finally:
            if self._load_task is asyncio.current_task():
                self._load_task = None

        if not self._request_is_current(generation, country_code):
            return
        previous_key = self.selected_alert_key
        self.alerts = list(alerts)
        if self.alert_severity_filter not in {
            value for _, value in _alert_severity_options(self.alerts)
        }:
            self.alert_severity_filter = ''
        new_alert_identities = getattr(
            self.service,
            'new_alert_identities',
            None,
        )
        self.new_alert_keys = (
            set(
                new_alert_identities(
                    country_code,
                    warning_language=self.warning_language,
                )
            )
            if callable(new_alert_identities)
            else set()
        )
        filtered_alerts = self._matching_alerts(self.alert_filter_value)
        selected = next(
            (
                alert
                for alert in filtered_alerts
                if country_alert_identity(alert) == previous_key
            ),
            None,
        )
        self.country_map.update_country(
            country_code,
            self._country_name(country_code),
            self.alerts,
            selected_alert_key=(
                country_alert_identity(selected) if selected is not None else None
            ),
        )
        self.alert_filter_button.disabled = False
        self._apply_alert_filter(
            self.alert_filter_value,
            preferred_key=previous_key,
        )

    def _progress_callback(
        self,
        generation: int,
        country_code: str,
    ) -> WarningQueryProgress:
        """Bridge provider worker progress into the active Textual request."""

        def update(event: str, payload: dict[str, object]) -> None:
            # Reject superseded worker events before crossing into Textual's
            # UI thread. The UI-side guard remains necessary for the small
            # race between this check and the scheduled callback.
            if (
                not self.is_attached
                or self.app.screen is not self
                or generation != self._load_generation
                or country_code != self.selected_country_code
            ):
                return
            if threading.get_ident() == self._ui_thread_id:
                self._apply_progress(generation, country_code, event, payload)
            else:
                self.app.call_from_thread(
                    self._apply_progress,
                    generation,
                    country_code,
                    event,
                    payload,
                )

        return update

    def _apply_progress(
        self,
        generation: int,
        country_code: str,
        event: str,
        payload: dict[str, object],
    ) -> None:
        if not self._request_is_current(generation, country_code):
            return
        bar = self.query_one('#alerts-centre-list-progress-bar', ProgressBar)
        if event == 'source_started':
            self._progress_items_total = None
            bar.update(total=None, progress=0)
        elif event == 'alerts_total':
            total = _positive_int(payload.get('total'))
            self._progress_items_total = total
            if total is not None:
                bar.update(total=total, progress=0)
        elif event == 'alerts_checked':
            total = _positive_int(payload.get('total')) or self._progress_items_total
            completed = _non_negative_int(payload.get('completed'))
            if total is None or completed is None:
                return
            completed = min(completed, total)
            bar.update(total=total, progress=completed)
        elif event == 'country_finished' and self._progress_items_total is not None:
            bar.update(
                total=self._progress_items_total,
                progress=self._progress_items_total,
            )

    def _request_is_current(self, generation: int, country_code: str) -> bool:
        return self.is_attached and generation == self._load_generation and country_code == self.selected_country_code

    def _apply_alert_filter(
        self,
        query: str,
        *,
        preferred_key: tuple[str, str] | None = None,
    ) -> None:
        self.filtered_alerts = self._matching_alerts(query)
        current_key = preferred_key or self.selected_alert_key
        selected = next(
            (alert for alert in self.filtered_alerts if country_alert_identity(alert) == current_key),
            None,
        )
        self._render_alert_options()
        if selected is not None:
            self._select_alert(selected)
            selected_key = country_alert_identity(selected)
            selected_index = next(
                index for index, alert in enumerate(self.filtered_alerts) if country_alert_identity(alert) == selected_key
            )
            self.alert_list.highlighted = selected_index
            self._show_alert_list_state('')
        else:
            self.selected_alert_key = None
            self.alert_list.highlighted = None
            self._clear_document()
            if self.filtered_alerts:
                self._show_alert_list_state('')
            else:
                self._show_alert_list_state(
                    'No matching alerts' if self.alerts else 'No active alerts'
                )

    def _matching_alerts(self, query: str) -> list[Alert]:
        """Return locally filtered alerts in their requested stable order."""

        normalized_query = ' '.join(query.casefold().split())
        filtered_alerts = [
            alert
            for alert in self.alerts
            if (
                not self.alert_severity_filter
                or (alert.severity or '').strip().casefold()
                == self.alert_severity_filter
            )
            and (
                not normalized_query
                or normalized_query in _alert_search_text(alert)
            )
        ]
        if self.alert_sort_value == 'new':
            filtered_alerts.sort(
                key=lambda alert: (
                    country_alert_identity(alert) not in self.new_alert_keys
                )
            )
        return filtered_alerts

    def _render_alert_options(self) -> None:
        self._alert_by_option_id.clear()
        self.alert_list.clear_options()
        options: list[Option | None] = []
        for index, alert in enumerate(self.filtered_alerts):
            option_id = f'alert-{index}'
            self._alert_by_option_id[option_id] = alert
            options.append(Option(self._alert_label(alert), id=option_id))
            if index < len(self.filtered_alerts) - 1:
                options.append(None)
        self.alert_list.add_options(options)

    def _alert_label(self, alert: Alert) -> Text:
        severity = (alert.severity or 'Alert').strip().title()
        if severity.casefold() == 'unknown':
            severity = 'Alert'
        color = alert_severity_color(self.app.theme_variables, alert)
        label = Text(no_wrap=True, overflow='ellipsis')
        if country_alert_identity(alert) in self.new_alert_keys:
            primary = self.app.theme_variables.get('primary', '#0178d4')
            background = self.app.theme_variables.get('background', '#000000')
            label.append('NEW', style=f'bold {background} on {primary}')
            label.append(' ')
        label.append(severity, style=f'bold {color}' if color else 'bold')
        label.append(' ')
        label.append(alert_condition_name(alert))
        label.append('\n')
        label.append(_alert_area_label(alert), style='dim')
        return label

    def _select_alert(self, alert: Alert) -> None:
        next_key = country_alert_identity(alert)
        if next_key != self.selected_alert_key:
            self._cancel_place_weather_preview()
        self.selected_alert_key = next_key
        self.country_map.update_selected_alert(self.selected_alert_key)
        self.query_one('#alerts-centre-document-empty', Static).display = False
        self.details.display = True
        self.details.content.update(alert_renderable(alert, include_timing=True))
        self.details.scroll_home(animate=False)
        pane = self.query_one('#alerts-centre-document-pane', Container)
        pane.border_title = 'Alert Detail'
        color = alert_severity_color(self.app.theme_variables, alert)
        frame_color = color or self.app.theme_variables.get('primary', '#0178d4')
        pane.set_styles(f'border: round {frame_color}; border-title-color: {frame_color};')

    def _clear_document(self) -> None:
        if not self.is_mounted:
            return
        self._cancel_place_weather_preview()
        self.details.display = False
        self.country_map.update_selected_alert(None)
        empty = self.query_one('#alerts-centre-document-empty', Static)
        empty.display = True
        empty.update('Select an alert to view detailed information')
        pane = self.query_one('#alerts-centre-document-pane', Container)
        pane.border_title = 'Alert Detail'
        primary = self.app.theme_variables.get('primary', '#0178d4')
        pane.set_styles(f'border: round {primary}; border-title-color: {primary};')

    def _show_alert_list_state(self, message: str) -> None:
        empty = self.query_one('#alerts-centre-list-empty', Static)
        progress = self.query_one('#alerts-centre-list-progress', Container)
        empty.update(message)
        empty.display = bool(message)
        progress.display = False
        self.alert_list.display = not bool(message)

    def _show_alert_list_progress(self) -> None:
        self._progress_items_total = None
        self.query_one('#alerts-centre-list-empty', Static).display = False
        self.query_one('#alerts-centre-list-progress', Container).display = True
        self.query_one('#alerts-centre-list-progress-bar', ProgressBar).update(
            total=None,
            progress=0,
        )
        self.alert_list.display = False

    def _country_name(self, country_code: str) -> str:
        return next(
            (country.name for country in self.countries if country.code == country_code),
            country_code,
        )

    def action_refresh_alerts(self) -> None:
        self._start_country_load(refresh=True, preserve_existing=True)

    def apply_preferences(
        self,
        *,
        warning_language: str,
        units_changed: bool,
        appearance_changed: bool,
    ) -> None:
        """Apply settings changed while this persistent workspace exists."""
        language_changed = warning_language != self.warning_language
        self.warning_language = warning_language
        if not self.is_attached or self.app.screen is not self:
            self._pending_language_changed = self._pending_language_changed or language_changed
            self._pending_units_changed = self._pending_units_changed or units_changed
            self._pending_appearance_changed = self._pending_appearance_changed or appearance_changed
            return

        self._apply_preference_changes(
            language_changed=language_changed,
            units_changed=units_changed,
            appearance_changed=appearance_changed,
        )

    def _apply_pending_preferences(self) -> None:
        language_changed = self._pending_language_changed
        units_changed = self._pending_units_changed
        appearance_changed = self._pending_appearance_changed
        self._pending_language_changed = False
        self._pending_units_changed = False
        self._pending_appearance_changed = False
        if language_changed or units_changed or appearance_changed:
            self._apply_preference_changes(
                language_changed=language_changed,
                units_changed=units_changed,
                appearance_changed=appearance_changed,
            )

    def _apply_preference_changes(
        self,
        *,
        language_changed: bool,
        units_changed: bool,
        appearance_changed: bool,
    ) -> None:
        """Apply already-classified changes while the screen is active."""
        if appearance_changed:
            self._render_alert_options()
            selected = next(
                (alert for alert in self.alerts if country_alert_identity(alert) == self.selected_alert_key),
                None,
            )
            if selected is not None:
                self._select_alert(selected)
            self.country_map.refresh_theme()
            self.country_map.reset_city_tooltips()
            self._cancel_place_weather_preview()

        if units_changed:
            self.country_map.reset_city_tooltips()
            self._cancel_place_weather_preview()

        if language_changed:
            self._start_country_load(refresh=False, preserve_existing=True)

    def action_back(self) -> None:
        self._cancel_place_weather_preview()
        self.app.pop_screen()

    def action_block_app_binding(self) -> None:
        """Prevent hidden weather-screen location actions in this workspace."""

    def _start_place_weather_preview(
        self,
        label: CountryAlertCityLabel,
    ) -> None:
        place = label.place
        temperature_unit = getattr(self.app, 'temperature_unit', 'celsius')
        wind_speed_unit = getattr(self.app, 'wind_speed_unit', 'kmh')
        precipitation_unit = getattr(self.app, 'precipitation_unit', 'mm')
        cache_key = _place_weather_cache_key(
            place,
            temperature_unit=temperature_unit,
            wind_speed_unit=wind_speed_unit,
            precipitation_unit=precipitation_unit,
        )
        cached = self._place_weather_cache.get(cache_key)
        if (
            cached is not None
            and self._clock() - cached[0] < self._place_weather_cache_ttl_seconds
        ):
            self._cancel_place_weather_preview()
            label.tooltip = self._place_weather_tooltip(place, cached[1])
            return

        if (
            label is self._place_weather_label
            and self._place_weather_task is not None
            and not self._place_weather_task.done()
        ):
            return
        self._cancel_place_weather_preview()
        label.reset_tooltip()
        if self._place_weather_loader is None:
            label.tooltip = self._place_weather_unavailable_tooltip(place)
            return
        self._place_weather_generation += 1
        generation = self._place_weather_generation
        self._place_weather_label = label
        self._place_weather_task = asyncio.create_task(
            self._load_place_weather_preview(
                generation,
                label,
                cache_key,
                temperature_unit,
                wind_speed_unit,
                precipitation_unit,
            )
        )

    async def _load_place_weather_preview(
        self,
        generation: int,
        label: CountryAlertCityLabel,
        cache_key: tuple[float, float, str, str, str],
        temperature_unit: str,
        wind_speed_unit: str,
        precipitation_unit: str,
    ) -> None:
        assert self._place_weather_loader is not None
        task = asyncio.current_task()
        try:
            if self._place_weather_hover_delay_seconds:
                await asyncio.sleep(self._place_weather_hover_delay_seconds)
            response = await self._place_weather_loader(
                label.place.latitude,
                label.place.longitude,
                temperature_unit,
                wind_speed_unit,
                precipitation_unit,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            if self._place_weather_request_is_current(generation, label, cache_key):
                label.tooltip = self._place_weather_unavailable_tooltip(label.place)
            return
        finally:
            if self._place_weather_task is task:
                self._place_weather_task = None

        if not self._place_weather_request_is_current(generation, label, cache_key):
            return
        self._place_weather_cache[cache_key] = (self._clock(), response)
        label.tooltip = self._place_weather_tooltip(label.place, response)

    def _place_weather_request_is_current(
        self,
        generation: int,
        label: CountryAlertCityLabel,
        cache_key: tuple[float, float, str, str, str],
    ) -> bool:
        if not self.is_attached or generation != self._place_weather_generation:
            return False
        if label is not self._place_weather_label or not label.is_attached:
            return False
        return cache_key == _place_weather_cache_key(
            label.place,
            temperature_unit=getattr(self.app, 'temperature_unit', 'celsius'),
            wind_speed_unit=getattr(self.app, 'wind_speed_unit', 'kmh'),
            precipitation_unit=getattr(self.app, 'precipitation_unit', 'mm'),
        )

    def _cancel_place_weather_preview(self) -> None:
        self._place_weather_generation += 1
        if self._place_weather_task is not None:
            self._place_weather_task.cancel()
            self._place_weather_task = None
        self._place_weather_label = None

    def _place_weather_tooltip(
        self,
        place: PopulatedPlace,
        response: dict[str, Any],
    ) -> Text:
        """Build a compact, non-interactive current-weather preview."""

        current = response.get('current')
        units = response.get('current_units')
        if not isinstance(current, dict):
            return self._place_weather_unavailable_tooltip(place)
        if not isinstance(units, dict):
            units = {}

        theme = self.app.theme_variables
        tooltip = _place_tooltip_heading(place, theme.get('primary'))
        weather_line = Text()

        code = current.get('weather_code')
        condition = get_condition(int(code)) if isinstance(code, (int, float)) else None
        if condition is not None:
            if getattr(self.app, 'emoji_enabled', True):
                emoji = condition.day_emoji if current.get('is_day') != 0 else condition.night_emoji
                weather_line.append(f'{emoji} ')
            weather_line.append(
                condition.name,
                style=theme.get(condition.color_var or 'text-primary'),
            )

        temperature = _number(current.get('temperature_2m'))
        if temperature is not None:
            if weather_line:
                weather_line.append('  ')
            colour = temp_colour(
                temperature,
                scale='theme_temperature',
                hex=True,
                unit=getattr(self.app, 'temperature_unit', 'celsius'),
                theme_colours=theme,
            )
            weather_line.append(f'{round(temperature):g}', style=f'bold {colour}')
            weather_line.append(
                str(units.get('temperature_2m') or '°C'),
                style=str(colour),
            )

        details = Text()
        probability = _number(current.get('precipitation_probability'))
        amount = _number(current.get('precipitation'))
        if probability is not None or amount is not None:
            details.append('Rain ', style='dim')
            if probability is not None:
                colour = rain_colour(
                    probability,
                    hex=True,
                    min_colour=theme.get('foreground', '#ffffff'),
                    max_colour=theme.get('primary', '#0178d4'),
                )
                details.append(f'{probability:g}%', style=f'bold {colour}')
            if amount is not None:
                if probability is not None:
                    details.append(' · ')
                details.append(
                    f'{amount:g} {units.get("precipitation") or "mm"}',
                    style=theme.get('text-primary'),
                )

        speed = _number(current.get('wind_speed_10m'))
        direction = _number(current.get('wind_direction_10m'))
        if speed is not None:
            if details:
                details.append('  ')
            details.append('Wind ', style='dim')
            colour = wind_colour(
                speed,
                hex=True,
                min_colour=theme.get('foreground', '#ffffff'),
                max_colour=theme.get('secondary', '#00a0a0'),
            )
            details.append(f'{speed:g}', style=f'bold {colour}')
            details.append(
                f' {units.get("wind_speed_10m") or "km/h"}',
                style=str(colour),
            )
            if direction is not None:
                details.append(f' {bearing_to_direction(direction)}')

        if weather_line:
            tooltip.append('\n')
            tooltip.append_text(weather_line)
        if details:
            tooltip.append('\n')
            tooltip.append_text(details)
        if not weather_line and not details:
            tooltip.append('\nNo current observations', style='dim italic')
        tooltip.append('\nClick for full forecast', style='dim')
        return tooltip

    def _place_weather_unavailable_tooltip(self, place: PopulatedPlace) -> Text:
        tooltip = _place_tooltip_heading(
            place,
            self.app.theme_variables.get('primary'),
        )
        tooltip.append('\nCurrent weather unavailable', style='dim italic')
        tooltip.append('\nClick for full forecast', style='dim')
        return tooltip


def _alert_area_label(alert: Alert) -> str:
    """Return a concise provider-supplied geography label."""
    areas: list[str] = []
    seen: set[str] = set()
    for raw_name in alert.area_names:
        name = ' '.join(raw_name.split())
        key = name.casefold()
        if not name or key in seen:
            continue
        seen.add(key)
        areas.append(name)
    if areas:
        return _ellipsize_area_label(', '.join(areas))

    display_geography = getattr(alert.source_info, 'display_geography', None)
    display_name = getattr(display_geography, 'name', None)
    if isinstance(display_name, str) and display_name.strip():
        return _ellipsize_area_label(display_name.strip())
    display_code = getattr(display_geography, 'code', None)
    if isinstance(display_code, str) and display_code.strip():
        return _ellipsize_area_label(display_code.strip())
    source_name = getattr(alert.source_info, 'name', None)
    if isinstance(source_name, str) and source_name.strip():
        return _ellipsize_area_label(source_name.strip())
    return _ellipsize_area_label(alert.source or 'Area not published')


def _ellipsize_area_label(label: str) -> str:
    if len(label) <= _ALERT_AREA_LABEL_MAX_LENGTH:
        return label
    shortened = label[: _ALERT_AREA_LABEL_MAX_LENGTH - 1].rstrip(' ,;:-')
    return f'{shortened}…'


def _place_tooltip_heading(place: PopulatedPlace, colour: str | None) -> Text:
    heading = Text()
    heading.append(place.name, style=f'bold {colour}' if colour else 'bold')
    region = ' '.join(place.region_name.split())
    if region and region.casefold() != place.name.casefold():
        heading.append(f', {region}', style='dim')
    return heading


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _place_weather_cache_key(
    place: PopulatedPlace,
    *,
    temperature_unit: str,
    wind_speed_unit: str,
    precipitation_unit: str,
) -> tuple[float, float, str, str, str]:
    """Bound cache cardinality while retaining neighbourhood-level precision."""

    return (
        round(place.latitude, 4),
        round(place.longitude, 4),
        temperature_unit,
        wind_speed_unit,
        precipitation_unit,
    )


def _alert_severity_options(
    alerts: list[Alert],
) -> tuple[tuple[str, str], ...]:
    options: list[tuple[str, str]] = []
    seen: set[str] = set()
    for alert in alerts:
        label = (alert.severity or '').strip()
        value = label.casefold()
        if not value or value in seen:
            continue
        seen.add(value)
        options.append((label, value))
    return tuple(options)


def _alert_search_text(alert: Alert) -> str:
    source_name = getattr(alert.source_info, 'name', None) or ''
    fields = (
        alert_condition_name(alert),
        alert.event,
        alert.headline,
        *alert.area_names,
        source_name,
        alert.source,
        alert.urgency,
        alert.certainty,
    )
    return ' '.join(' '.join(str(value).casefold().split()) for value in fields if value)


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _non_negative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


__all__ = [
    'AlertsCentreScreen',
]
