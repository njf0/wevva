"""Dedicated workspace for investigating active tropical systems."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, ClassVar

from rich.console import Group
from rich.style import Style
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.css.query import NoMatches
from textual.events import Resize
from textual.screen import Screen
from textual.widgets import Footer, Header, Markdown, Static, Tab, Tabs
from wevva_warnings import CanonicalTropicalSystem, TropicalProduct, TropicalSystem

from wevva.services.tropical import (
    canonical_tropical_classification,
    get_tropical_products_async,
    sort_canonical_tropical_systems_by_severity,
)
from wevva.tropical_layout import (
    TropicalLayoutBudget,
    TropicalTopology,
    tropical_layout_for,
)
from wevva.widgets.tropical_centre_weather import TropicalCentreWeather
from wevva.widgets.tropical_summary import TropicalStormSummary
from wevva.widgets.tropical_systems import (
    build_tropical_coordinates_text,
    canonical_storm_key,
    source_tab_label,
)
from wevva.widgets.tropical_track import LargeTropicalStormTrackScope

ProductLoader = Callable[[TropicalSystem], Awaitable[list[TropicalProduct]]]
SystemsLoader = Callable[[], Awaitable[list[CanonicalTropicalSystem]]]
CentreWeatherLoader = Callable[[float, float], Awaitable[dict[str, Any]]]


class TropicalSystemsScreen(Screen[None]):
    """Persistent three-level storm, source, and official-product browser."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding('w', 'back', 'Weather'),
        Binding('r', 'refresh_systems', 'Refresh'),
        Binding('s', 'block_app_binding', '', show=False),
        Binding('a', 'block_app_binding', '', show=False),
        Binding('d', 'block_app_binding', '', show=False),
    ]
    DEFAULT_CSS = """
    TropicalSystemsScreen {
        background: $background;
        align: center middle;
        overflow: hidden;
    }

    #tropical-screen-stage {
        width: 100%;
        height: 1fr;
        align: center middle;
        padding: 1 2;
        background: $background;
        hatch: right $background-lighten-1;
    }

    #tropical-screen-root {
        width: 0;
        min-width: 0;
        height: 0;
        min-height: 0;
        padding: 0;
        layout: vertical;
        border: round $primary;
        align: center middle;
        border-title-color: $primary;
        border-title-align: center;
        background: $background;
        hatch: right $background-lighten-1;
    }

    #tropical-screen-content {
        width: 100%;
        height: 1fr;
        layout: vertical;
        align: center middle;
    }

    #tropical-storm-tabs, #tropical-source-tabs, #tropical-product-tabs {
        width: 100%;
        height: 2;
    }

    #tropical-workspace {
        width: 100%;
        height: 1fr;
        layout: horizontal;
        overflow: hidden;
        background: $background;
        hatch: right $background-lighten-1;
    }

    #tropical-left-pane {
        width: 0;
        min-width: 0;
        height: 0;
        layout: vertical;
        margin: 0;
        overflow: hidden;
        hatch: right $background-lighten-1;
    }

    #tropical-right-pane {
        width: 1fr;
        min-width: 0;
        height: 0;
        layout: vertical;
        margin: 0;
        overflow: hidden;
        hatch: right $background-lighten-1;
    }

    #tropical-track-pane {
        width: 100%;
        height: 0;
        min-height: 0;
        layout: vertical;
        border: round $secondary;
        border-title-color: $secondary;
        border-title-align: left;
    }

    #tropical-track-unavailable {
        width: 100%;
        height: auto;
        padding: 1;
        color: $text-muted;
        text-style: italic;
    }

    #tropical-product-pane {
        width: 1fr;
        min-width: 0;
        height: 0;
        layout: vertical;
        border: round $secondary;
        border-title-color: $secondary;
    }

    #tropical-product-content {
        width: 100%;
        height: 1fr;
        layout: vertical;
    }

    #tropical-product-body {
        width: 100%;
        height: 1fr;
        padding: 0 1;
        background: $background;
        scrollbar-size-vertical: 1;
    }

    #tropical-product-body > * {
        width: 100%;
        height: auto;
        margin: 0;
    }

    #tropical-screen-empty {
        width: 100%;
        height: auto;
        padding: 1;
        color: $text-muted;
    }

    """

    def __init__(
        self,
        systems: list[CanonicalTropicalSystem],
        *,
        location_latitude: float | None = None,
        location_longitude: float | None = None,
        location_name: str = '',
        product_loader: ProductLoader | None = None,
        centre_weather_loader: CentreWeatherLoader | None = None,
        systems_loader: SystemsLoader | None = None,
        refresh_loader: SystemsLoader | None = None,
    ) -> None:
        super().__init__()
        self.location_latitude = location_latitude
        self.location_longitude = location_longitude
        self.location_name = location_name
        self.systems = sort_canonical_tropical_systems_by_severity(systems)
        self._product_loader = product_loader or get_tropical_products_async
        self._centre_weather_loader = centre_weather_loader
        self._systems_loader = systems_loader
        self._refresh_loader = refresh_loader
        self._refreshing_systems = False
        self.selected_storm_index = 0
        self._source_by_storm: dict[str, int] = {}
        self._product_by_observation: dict[str, str] = {}
        self._products: dict[str, tuple[TropicalProduct, ...]] = {}
        self._last_update_by_observation: dict[str, datetime] = {}
        self._product_errors: set[str] = set()
        self._loading_keys: set[str] = set()
        self._centre_weather: dict[tuple[float, float], dict[str, Any]] = {}
        self._centre_weather_errors: set[tuple[float, float]] = set()
        self._centre_weather_tasks: dict[tuple[float, float], asyncio.Task[None]] = {}
        self._layout_budget: TropicalLayoutBudget | None = None
        self._selection_generation = 0
        self._tasks: set[asyncio.Task[None]] = set()
        self._updating_tabs = 0
        self._source_tabs_lock = asyncio.Lock()
        self._product_tabs_lock = asyncio.Lock()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id='tropical-screen-stage'), Container(id='tropical-screen-root') as root:
            root.border_title = 'Active Tropical Systems'
            with Container(id='tropical-screen-content'):
                empty = Static('No active tropical systems', id='tropical-screen-empty')
                empty.display = not self.systems
                yield empty
                storm_tabs = Tabs(
                    *(
                        Tab(self._storm_tab_label(system), id=f'tropical-storm-{index}')
                        for index, system in enumerate(self.systems)
                    ),
                    active='tropical-storm-0' if self.systems else None,
                    id='tropical-storm-tabs',
                )
                storm_tabs.display = bool(self.systems)
                yield storm_tabs
                source_tabs = Tabs(id='tropical-source-tabs')
                source_tabs.display = False
                yield source_tabs
                with Container(id='tropical-workspace') as workspace:
                    workspace.display = bool(self.systems)
                    with Container(id='tropical-left-pane'):
                        yield TropicalCentreWeather()
                        with Container(id='tropical-track-pane') as track_pane:
                            track_pane.border_title = 'Storm Track'
                            yield LargeTropicalStormTrackScope(id='tropical-large-track')
                            unavailable = Static(
                                'Storm track unavailable',
                                id='tropical-track-unavailable',
                            )
                            unavailable.display = False
                            yield unavailable
                    with Container(id='tropical-right-pane'):
                        yield TropicalStormSummary()
                        with Container(id='tropical-product-pane') as product_pane:
                            product_pane.border_title = 'Storm Information'
                            with Container(id='tropical-product-content'):
                                product_tabs = Tabs(id='tropical-product-tabs')
                                product_tabs.display = False
                                yield product_tabs
                                yield VerticalScroll(id='tropical-product-body')
        yield Footer()

    async def on_mount(self) -> None:
        self.title = 'Tropical Systems'
        self.sub_title = 'Active systems and official issuing-centre products'
        if self.systems:
            # Populate the first view as part of mounting. Relying on a later
            # tab activation leaves a real app susceptible to showing only the
            # already-composed storm labels while its content shell is empty.
            content = self.query_one('#tropical-screen-content', Container)
            content.loading = True
            try:
                await self._select_storm(0)
            finally:
                content.loading = False
        elif self._systems_loader is not None:
            task = asyncio.create_task(self._load_systems())
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        self.call_after_refresh(self._apply_layout)

    def on_unmount(self) -> None:
        self._selection_generation += 1
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        self._centre_weather_tasks.clear()

    def on_resize(self, event: Resize) -> None:
        del event
        self.call_after_refresh(self._apply_layout)

    def _apply_layout(self) -> None:
        """Apply one pure budget result to the persistent mounted widgets."""
        if not self.is_mounted:
            return
        if not self.systems:
            budget = tropical_layout_for(
                self.size.width,
                self.size.height,
                multiple_sources=False,
                track_available=False,
                centre_weather_available=False,
                information_choice_count=0,
                rich_information=False,
                summary_available_rows=0,
                centre_weather_available_rows=0,
            )
            if budget == self._layout_budget:
                return
            self._layout_budget = budget
            root = self.query_one('#tropical-screen-root', Container)
            root.styles.width = budget.frame_width
            root.styles.height = budget.frame_height
            return
        observation = self.selected_observation
        if observation is None:
            return

        storm = self.systems[self.selected_storm_index]
        track = self.query_one(LargeTropicalStormTrackScope)
        summary = self.query_one(TropicalStormSummary)
        weather = self.query_one(TropicalCentreWeather)
        key = _observation_key(observation)
        product_choices = self._product_tab_specs(observation)
        budget = tropical_layout_for(
            self.size.width,
            self.size.height,
            multiple_sources=len(storm.observations) > 1,
            track_available=track.available,
            centre_weather_available=(
                self._centre_weather_loader is not None
                and _centre_weather_key(observation) is not None
            ),
            information_choice_count=len(product_choices),
            rich_information=(key in self._loading_keys or bool(self._products.get(key))),
            summary_available_rows=summary.available_row_count,
            centre_weather_available_rows=max(6, weather.available_row_count),
        )
        if budget == self._layout_budget:
            return
        self._layout_budget = budget

        root = self.query_one('#tropical-screen-root', Container)
        workspace = self.query_one('#tropical-workspace', Container)
        left = self.query_one('#tropical-left-pane', Container)
        right = self.query_one('#tropical-right-pane', Container)
        track_pane = self.query_one('#tropical-track-pane', Container)
        product_pane = self.query_one('#tropical-product-pane', Container)
        product_tabs = self.query_one('#tropical-product-tabs', Tabs)
        product_body = self.query_one('#tropical-product-body', VerticalScroll)
        source_tabs = self.query_one('#tropical-source-tabs', Tabs)

        root.styles.width = budget.frame_width
        root.styles.height = budget.frame_height
        source_tabs.display = budget.source_tabs_visible
        summary.set_layout(
            row_count=budget.summary_rows,
            height=budget.summary_height,
        )
        weather.set_layout(
            row_count=budget.centre_weather_rows,
            height=budget.centre_weather_height,
        )
        track_pane.display = budget.track_visible
        track_pane.styles.height = budget.track_height
        track.set_layout(
            visible=budget.track_visible,
            height=max(0, budget.track_height - 2),
        )
        self.query_one('#tropical-track-unavailable', Static).display = (
            budget.track_visible and not track.available
        )
        product_tabs.display = budget.information_tabs_visible
        product_pane.styles.height = budget.information_height

        summary.styles.margin = (
            (0, 0, 1, 0) if budget.information_height else 0
        )
        weather.styles.margin = (
            (0, 0, 1, 0) if budget.track_visible else 0
        )
        left.styles.width = budget.left_pane_width
        left.styles.height = budget.left_pane_height

        if budget.topology is TropicalTopology.SPLIT:
            workspace.styles.layout = 'horizontal'
            left.display = True
            left.styles.margin = (0, 2, 0, 0)
            right.styles.width = '1fr'
            right.styles.height = budget.workspace_height
            product_pane.styles.width = '100%'
            product_body.styles.padding = (1, 2)
        else:
            workspace.styles.layout = 'vertical'
            left.display = False
            left.styles.margin = 0
            right.styles.width = '100%'
            right.styles.height = budget.summary_height + (
                1 if budget.summary_height and budget.information_height else 0
            ) + budget.information_height
            product_pane.styles.width = '100%'
            product_body.styles.padding = (0, 1)

    async def _load_systems(self) -> None:
        """Populate the screen from the shared canonical fetch with native loading UI."""
        content = self.query_one('#tropical-screen-content', Container)
        content.loading = True
        try:
            assert self._systems_loader is not None
            systems = await self._systems_loader()
        except asyncio.CancelledError:
            raise
        except Exception:
            self.query_one('#tropical-screen-empty', Static).update('Tropical systems are temporarily unavailable')
        else:
            await self._replace_systems(systems)
        finally:
            if content.is_attached:
                content.loading = False

    async def _replace_systems(self, systems: list[CanonicalTropicalSystem]) -> None:
        """Install a newly loaded canonical set into the persistent screen shell."""
        previous_storm_key = (
            canonical_storm_key(self.systems[self.selected_storm_index])
            if self.systems and self.selected_storm_index < len(self.systems)
            else None
        )
        previous_source = self.selected_observation.source if self.selected_observation is not None else None
        self.systems = sort_canonical_tropical_systems_by_severity(systems)
        selected_index = next(
            (index for index, system in enumerate(self.systems) if canonical_storm_key(system) == previous_storm_key),
            0,
        )
        if self.systems and previous_source is not None:
            selected_storm = self.systems[selected_index]
            selected_source = next(
                (
                    index
                    for index, observation in enumerate(selected_storm.observations)
                    if observation.source == previous_source
                ),
                None,
            )
            if selected_source is not None:
                self._source_by_storm[canonical_storm_key(selected_storm)] = selected_source
        tabs = self.query_one('#tropical-storm-tabs', Tabs)
        self._updating_tabs += 1
        try:
            await tabs.clear()
            for index, system in enumerate(self.systems):
                await tabs.add_tab(Tab(self._storm_tab_label(system), id=f'tropical-storm-{index}'))
            tabs.display = bool(self.systems)
            if self.systems:
                tabs.active = f'tropical-storm-{selected_index}'
        finally:
            self._updating_tabs -= 1
        self.query_one('#tropical-screen-empty', Static).display = not self.systems
        self.query_one('#tropical-workspace', Container).display = bool(self.systems)
        if self.systems:
            await self._select_storm(selected_index)
        self.call_after_refresh(self._apply_layout)

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_refresh_systems(self) -> None:
        """Start a canonical refresh without blocking Textual's message pump."""
        if self._refresh_loader is None or self._refreshing_systems:
            return
        self._refreshing_systems = True
        information = self.query_one('#tropical-product-content', Container)
        information.loading = True
        task = asyncio.create_task(self._refresh_systems(information))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _refresh_systems(self, information: Container) -> None:
        """Refresh canonical systems while leaving summary and track visible."""
        try:
            assert self._refresh_loader is not None
            systems = await self._refresh_loader()
            self._products.clear()
            self._product_errors.clear()
            for task in self._centre_weather_tasks.values():
                task.cancel()
            self._centre_weather_tasks.clear()
            self._centre_weather.clear()
            self._centre_weather_errors.clear()
            await self._replace_systems(systems)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.notify(
                'Tropical systems could not be refreshed.',
                severity='warning',
            )
        finally:
            self._refreshing_systems = False
            if information.is_attached:
                information.loading = False

    def action_block_app_binding(self) -> None:
        """Keep location-mutating app shortcuts inactive in this workspace."""

    async def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:  # type: ignore[override]
        if self._updating_tabs or event.tab.id is None:
            return
        tab_id = event.tab.id
        if tab_id.startswith('tropical-storm-'):
            await self._select_storm(int(tab_id.rsplit('-', 1)[-1]))
        elif tab_id.startswith('tropical-screen-source-'):
            storm = self.systems[self.selected_storm_index]
            self._source_by_storm[canonical_storm_key(storm)] = int(tab_id.rsplit('-', 1)[-1])
            await self._show_observation()
        elif tab_id.startswith('tropical-product-'):
            observation = self.selected_observation
            if observation is None:
                return
            self._product_by_observation[_observation_key(observation)] = tab_id
            await self._render_selected_product()

    @property
    def selected_observation(self) -> TropicalSystem | None:
        if not self.systems:
            return None
        storm = self.systems[self.selected_storm_index]
        if not storm.observations:
            return None
        index = self._source_by_storm.get(canonical_storm_key(storm), 0)
        return storm.observations[min(index, len(storm.observations) - 1)]

    async def _select_storm(self, index: int) -> None:
        if not self.systems:
            return
        self.selected_storm_index = min(max(index, 0), len(self.systems) - 1)
        storm = self.systems[self.selected_storm_index]
        await self._populate_source_tabs(storm)
        await self._show_observation()

    async def _populate_source_tabs(self, storm: CanonicalTropicalSystem) -> None:
        async with self._source_tabs_lock:
            tabs = self.query_one('#tropical-source-tabs', Tabs)
            observations = storm.observations
            tabs.display = len(observations) > 1
            self._updating_tabs += 1
            try:
                await tabs.clear()
                for index, observation in enumerate(observations):
                    await tabs.add_tab(Tab(source_tab_label(observation), id=f'tropical-screen-source-{index}'))
                if len(observations) > 1:
                    selected = min(
                        self._source_by_storm.get(canonical_storm_key(storm), 0),
                        len(observations) - 1,
                    )
                    self._source_by_storm[canonical_storm_key(storm)] = selected
                    tabs.active = f'tropical-screen-source-{selected}'
            finally:
                self._updating_tabs -= 1

    async def _show_observation(self) -> None:
        observation = self.selected_observation
        if observation is None:
            return
        self._selection_generation += 1
        generation = self._selection_generation
        summary = self.query_one(TropicalStormSummary)
        storm = self.systems[self.selected_storm_index]
        summary.update_rows(
            self._summary(
                observation,
                include_source=len(storm.observations) == 1,
            )
        )
        storm_tabs = list(self.query('#tropical-storm-tabs Tab'))
        if self.selected_storm_index < len(storm_tabs):
            storm_tabs[self.selected_storm_index].label = self._storm_tab_label(self.systems[self.selected_storm_index])
        self._show_track(observation)
        self._show_centre_weather(observation)

        key = _observation_key(observation)
        product_body = self.query_one('#tropical-product-body', VerticalScroll)
        needs_load = key not in self._products and key not in self._loading_keys and key not in self._product_errors
        if needs_load:
            self._loading_keys.add(key)
            task = asyncio.create_task(self._load_products(observation, key))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        product_body.loading = key in self._loading_keys
        self._apply_layout()
        await self._populate_product_tabs(observation, generation)
        if generation != self._selection_generation:
            return

    def _show_track(self, observation: TropicalSystem) -> None:
        """Render cached geometry/products without making a provider request."""
        track = self.query_one(LargeTropicalStormTrackScope)
        try:
            track.update_system(
                observation,
                products=self._products.get(_observation_key(observation), ()),
            )
        except Exception as error:
            # Supplementary geography is optional. A bad or newly introduced
            # provider shape must not suppress the source summary and products.
            self.log.error(f'Unable to render tropical track: {error!r}')
            track.clear()

    def _show_centre_weather(self, observation: TropicalSystem) -> None:
        """Show cached centre conditions or start one independent current request."""
        weather = self.query_one(TropicalCentreWeather)
        key = _centre_weather_key(observation)
        if key is None or self._centre_weather_loader is None:
            weather.hide_weather()
            return
        cached = self._centre_weather.get(key)
        if cached is not None:
            weather.update_weather(cached)
            return
        if key in self._centre_weather_errors:
            weather.show_unavailable()
            return
        if key not in self._centre_weather_tasks:
            task = asyncio.create_task(self._load_centre_weather(key))
            self._centre_weather_tasks[key] = task
            self._tasks.add(task)
            task.add_done_callback(
                lambda completed, weather_key=key: self._centre_weather_task_done(
                    weather_key,
                    completed,
                )
            )
        weather.show_loading()

    async def _load_centre_weather(self, key: tuple[float, float]) -> None:
        """Fetch and retain one Open-Meteo current response by source centre."""
        try:
            assert self._centre_weather_loader is not None
            response = await self._centre_weather_loader(*key)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._centre_weather_errors.add(key)
        else:
            self._centre_weather[key] = response

        selected = self.selected_observation
        if (
            not self.is_attached
            or selected is None
            or _centre_weather_key(selected) != key
        ):
            return
        weather = self.query_one(TropicalCentreWeather)
        if key in self._centre_weather:
            weather.update_weather(self._centre_weather[key])
        else:
            weather.show_unavailable()
        self.call_after_refresh(self._apply_layout)

    def _centre_weather_task_done(
        self,
        key: tuple[float, float],
        task: asyncio.Task[None],
    ) -> None:
        if self._centre_weather_tasks.get(key) is task:
            del self._centre_weather_tasks[key]
        self._tasks.discard(task)

    async def _load_products(self, observation: TropicalSystem, key: str) -> None:
        try:
            products = await self._product_loader(observation)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._product_errors.add(key)
        else:
            self._products[key] = tuple(products)
        finally:
            self._loading_keys.discard(key)
        selected = self.selected_observation
        if (
            self.is_attached
            and selected is not None
            and _observation_key(selected) == key
        ):
            self._show_track(selected)
            await self._populate_product_tabs(selected, self._selection_generation)

    async def _populate_product_tabs(self, observation: TropicalSystem, generation: int) -> None:
        async with self._product_tabs_lock:
            selected = self.selected_observation
            if (
                not self.is_attached
                or selected is None
                or _observation_key(selected) != _observation_key(observation)
                or generation != self._selection_generation
            ):
                return
            tabs = self.query_one('#tropical-product-tabs', Tabs)
            key = _observation_key(observation)
            products = self._products.get(key, ())
            tab_specs = self._product_tab_specs(observation)
            valid_ids = {tab_id for tab_id, _label in tab_specs}
            desired = self._product_by_observation.get(key)
            if desired not in valid_ids:
                desired = tab_specs[0][0] if tab_specs else None
            self._updating_tabs += 1
            try:
                await tabs.clear()
                if (
                    not self.is_attached
                    or generation != self._selection_generation
                ):
                    return
                for tab_id, label in tab_specs:
                    if (
                        not self.is_attached
                        or generation != self._selection_generation
                    ):
                        return
                    try:
                        await tabs.add_tab(Tab(label, id=tab_id))
                    except NoMatches:
                        # A popped screen may detach Tabs internals before its
                        # product task observes cancellation.
                        return
                tabs.display = len(tab_specs) > 1
                tabs.active = desired
                if desired is None:
                    self._product_by_observation.pop(key, None)
                else:
                    self._product_by_observation[key] = desired
            finally:
                self._updating_tabs -= 1
            if generation == self._selection_generation:
                storm = self.systems[self.selected_storm_index]
                self.query_one(TropicalStormSummary).update_rows(
                    self._summary(
                        observation,
                        include_source=len(storm.observations) == 1,
                    )
                )
                self.query_one('#tropical-product-body', VerticalScroll).loading = key in self._loading_keys
                await self._render_selected_product()
                self.call_after_refresh(self._apply_layout)

    def _product_tab_specs(
        self,
        observation: TropicalSystem,
    ) -> list[tuple[str, str]]:
        """Return stable choices independently of whether their tab row is useful."""
        tab_specs: list[tuple[str, str]] = []
        if _has_us_forecast_summary(observation):
            tab_specs.append(('tropical-product-forecast', 'Forecast'))
        tab_specs.extend(
            (f'tropical-product-{index}', product.label)
            for index, product in enumerate(
                self._products.get(_observation_key(observation), ())
            )
            if not _is_map_annotation_product(product)
        )
        return tab_specs

    async def _render_selected_product(self) -> None:
        observation = self.selected_observation
        if observation is None:
            return
        body = self.query_one('#tropical-product-body', VerticalScroll)
        await body.remove_children()
        tabs = self.query_one('#tropical-product-tabs', Tabs)
        active = tabs.active
        key = _observation_key(observation)
        if active == 'tropical-product-forecast':
            await body.mount(Static(self._forecast_summary(observation)))
            return
        if active is None:
            if key in self._loading_keys:
                return
            if key in self._product_errors:
                await body.mount(
                    Static(
                        Text(
                            'Supplementary products are temporarily unavailable.',
                            style='dim italic',
                        )
                    )
                )
                if _has_basic_information(observation):
                    await body.mount(Static(self._forecast_summary(observation)))
                return
            if _has_basic_information(observation):
                await body.mount(Static(self._forecast_summary(observation)))
                return
            await body.mount(
                Static(
                    Text(
                        'No supplementary products are available.',
                        style='dim italic',
                    )
                )
            )
            return
        try:
            index = int(active.rsplit('-', 1)[-1])
            product = self._products[key][index]
        except (KeyError, IndexError, ValueError):
            await body.mount(Static('Product unavailable'))
            return
        await body.mount(*_product_widgets(product))

    def _summary(
        self,
        observation: TropicalSystem,
        *,
        include_source: bool = True,
    ) -> list[tuple[str, Any]]:
        rows: list[tuple[str, Any]] = []
        if include_source:
            source = (
                getattr(observation.source_info, 'name', None)
                or source_tab_label(observation)
            )
            if cleaned := _clean(source):
                rows.append(('Source', cleaned))
        if observation.center_lat is not None and observation.center_lon is not None:
            rows.append(
                (
                    'Centre',
                    build_tropical_coordinates_text(observation.center_lat, observation.center_lon),
                )
            )
        for label, value in (
            ('Maximum wind', observation.max_wind),
            ('Minimum pressure', observation.min_pressure),
            ('Movement', observation.movement),
        ):
            if cleaned := _clean(value):
                rows.append((label, cleaned))
        update_time = _latest_update_time(
            observation.issued_at,
            self._products.get(_observation_key(observation), ()),
        )
        update_key = _last_update_key(observation)
        if update_time is not None:
            previous = self._last_update_by_observation.get(update_key)
            if previous is not None:
                update_time = _latest_datetime(previous, update_time)
            self._last_update_by_observation[update_key] = update_time
        else:
            update_time = self._last_update_by_observation.get(update_key)
        if update_time is not None:
            rows.append(('Last update', _format_time(update_time)))
        return rows

    def _forecast_summary(self, observation: TropicalSystem) -> Group:
        """Render a provider's useful discovery headline, summary, and link."""
        parts: list[Any] = []
        heading = _clean(observation.headline) or _clean(observation.name) or 'Forecast'
        parts.append(Text(heading, style='bold'))
        if summary := _clean(observation.summary):
            parts.extend((Text(''), Text(summary)))
        if url := _clean(observation.url):
            link = Text('View official source', style='markdown.link')
            link.stylize(Style(link=url, underline=True))
            parts.extend((Text(''), link))
        return Group(*parts)

    def _storm_tab_label(self, storm: CanonicalTropicalSystem) -> Text:
        name = _clean(storm.name) or 'Tropical System'
        label = Text()
        classification = canonical_tropical_classification(storm)
        if classification:
            theme = getattr(self.app, 'theme_variables', {})
            role = _classification_colour_role(classification)
            colour = theme.get(role) or theme.get(f'text-{role}')
            label.append(
                classification,
                style=f'bold {colour}' if colour else 'bold',
            )
            label.append(' ')
        label.append(name)
        return label


def _product_widgets(product: TropicalProduct) -> list[Static | Markdown]:
    widgets: list[Static | Markdown] = []
    if product.content:
        if product.content_format == 'markdown':
            widgets.append(Markdown(product.content))
        else:
            # A Rich Text object is already parsed content, so provider prose
            # cannot be reinterpreted as Rich markup or Markdown.
            widgets.append(Static(Text(product.content)))
    if product.data and set(product.data) != {'product_code'}:
        widgets.append(Static(_structured_product(product.data)))
    if product.url:
        link = Text('View official product', style='markdown.link')
        link.stylize(Style(link=product.url, underline=True))
        widgets.append(Static(link))
    if not product.content and not product.data:
        widgets.append(Static('No product content is available.'))
    return widgets


def _structured_product(data: dict[str, Any]) -> Table:
    points = data.get('points')
    if isinstance(points, list) and any(isinstance(point, dict) for point in points):
        rows = [point for point in points if isinstance(point, dict)]
        table = Table(box=None, pad_edge=False, expand=False)
        columns = [
            ('Valid', _point_valid, any(_has_valid(point) for point in rows)),
            ('Type', _point_type, any(_has_type(point) for point in rows)),
            ('Centre', _point_centre, any(_has_centre(point) for point in rows)),
            ('Wind', _point_wind, any(_has_wind(point) for point in rows)),
            ('Pressure', _point_pressure, any(_has_pressure(point) for point in rows)),
        ]
        visible = [(label, renderer) for label, renderer, present in columns if present]
        for label, _renderer in visible:
            table.add_column(label, no_wrap=label != 'Type')
        for point in rows:
            table.add_row(*(renderer(point) for _label, renderer in visible))
        return table

    table = Table(box=None, pad_edge=False, expand=False)
    table.add_column('Field', style='bold')
    table.add_column('Value')
    for label, value in _flatten_data(data):
        table.add_row(label, value)
    return table


def _flatten_data(data: dict[str, Any], prefix: str = '') -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for key, value in data.items():
        if key in {'latitude', 'longitude'}:
            continue
        label = f'{prefix} {key}'.strip().replace('_', ' ').title()
        if isinstance(value, dict):
            rows.extend(_flatten_data(value, label))
        elif isinstance(value, (str, int, float)):
            rows.append((label, str(value)))
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
        rows.insert(0, (f'{prefix} Centre'.strip(), _coordinates(float(latitude), float(longitude))))
    return rows


def _point_valid(point: dict[str, Any]) -> str:
    value = point.get('valid_at') or point.get('time') or point.get('forecast_type')
    if value:
        return str(value)
    lead = point.get('lead_hours')
    return f'+{lead:g} h' if isinstance(lead, (int, float)) else '—'


def _point_type(point: dict[str, Any]) -> str:
    value = point.get('classification') or point.get('intensity') or point.get('forecast_type')
    cyclone_data = point.get('cyclone_data')
    if value is None and isinstance(cyclone_data, dict):
        value = cyclone_data.get('development')
    return str(value).replace('_', ' ').title() if value else '—'


def _point_centre(point: dict[str, Any]) -> str:
    lat, lon = point.get('latitude'), point.get('longitude')
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        return _coordinates(float(lat), float(lon))
    return '—'


def _point_wind(point: dict[str, Any]) -> str:
    for key, unit in (('maximum_wind', ''), ('maximum_wind_mps', ' m/s')):
        value = point.get(key)
        if value is not None:
            return f'{value}{unit}'
    cyclone_data = point.get('cyclone_data')
    if isinstance(cyclone_data, dict):
        wind = cyclone_data.get('maximum_wind')
        if isinstance(wind, dict) and wind.get('wind_speed_kt') is not None:
            gust = f' (gust {wind["wind_speed_gust_kt"]} kt)' if wind.get('wind_speed_gust_kt') is not None else ''
            return f'{wind["wind_speed_kt"]} kt{gust}'
    return '—'


def _point_pressure(point: dict[str, Any]) -> str:
    for key, unit in (('minimum_pressure', ''), ('minimum_pressure_hpa', ' hPa')):
        value = point.get(key)
        if value is not None:
            return f'{value}{unit}'
    cyclone_data = point.get('cyclone_data')
    if isinstance(cyclone_data, dict) and cyclone_data.get('minimum_pressure') is not None:
        return f'{cyclone_data["minimum_pressure"]} hPa'
    return '—'


def _has_valid(point: dict[str, Any]) -> bool:
    return any(point.get(key) is not None for key in ('valid_at', 'time', 'forecast_type', 'lead_hours'))


def _has_type(point: dict[str, Any]) -> bool:
    if any(point.get(key) for key in ('classification', 'intensity', 'forecast_type')):
        return True
    cyclone_data = point.get('cyclone_data')
    return isinstance(cyclone_data, dict) and bool(cyclone_data.get('development'))


def _has_centre(point: dict[str, Any]) -> bool:
    return isinstance(point.get('latitude'), (int, float)) and isinstance(point.get('longitude'), (int, float))


def _has_wind(point: dict[str, Any]) -> bool:
    if any(point.get(key) is not None for key in ('maximum_wind', 'maximum_wind_mps')):
        return True
    cyclone_data = point.get('cyclone_data')
    return isinstance(cyclone_data, dict) and isinstance(cyclone_data.get('maximum_wind'), dict)


def _has_pressure(point: dict[str, Any]) -> bool:
    if any(point.get(key) is not None for key in ('minimum_pressure', 'minimum_pressure_hpa')):
        return True
    cyclone_data = point.get('cyclone_data')
    return isinstance(cyclone_data, dict) and cyclone_data.get('minimum_pressure') is not None


def _observation_key(system: TropicalSystem) -> str:
    issued = system.issued_at.isoformat() if system.issued_at else ''
    return f'{system.source}\0{system.id}\0{issued}'


def _has_us_forecast_summary(system: TropicalSystem) -> bool:
    """Return whether an NHC/CPHC discovery summary merits its own tab."""
    source = _clean(system.source).casefold()
    return source.startswith(('nhc_gis_', 'cphc_gis_')) and bool(
        _clean(system.headline) or _clean(system.summary)
    )


def _is_map_annotation_product(product: TropicalProduct) -> bool:
    """Keep coordinate-only forecast metadata out of the information tabs."""
    if (
        product.content
        or not isinstance(product.data, dict)
        or set(product.data) != {'points'}
    ):
        return False
    points = product.data.get('points')
    annotation_fields = {'latitude', 'longitude', 'lead_hours'}
    return bool(points) and isinstance(points, list) and all(
        isinstance(point, dict)
        and {'latitude', 'longitude'} <= set(point)
        and set(point) <= annotation_fields
        for point in points
    )


def _has_basic_information(system: TropicalSystem) -> bool:
    """Return whether useful provider prose can fill the tab-free basic mode."""
    return bool(
        _clean(system.headline)
        or _clean(system.summary)
        or _clean(system.url)
    )


def _last_update_key(system: TropicalSystem) -> str:
    """Return a refresh-stable key for presentation-only freshness state."""
    return f'{system.source}\0{system.id}'


def _centre_weather_key(system: TropicalSystem) -> tuple[float, float] | None:
    latitude = system.center_lat
    longitude = system.center_lon
    if (
        not isinstance(latitude, (int, float))
        or isinstance(latitude, bool)
        or not isinstance(longitude, (int, float))
        or isinstance(longitude, bool)
        or not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not -90.0 <= latitude <= 90.0
        or not -360.0 <= longitude <= 360.0
    ):
        return None
    return round(float(latitude), 4), round(float(longitude), 4)


def _coordinates(latitude: float, longitude: float) -> str:
    return f'{abs(latitude):.1f}°{"N" if latitude >= 0 else "S"} {abs(longitude):.1f}°{"E" if longitude >= 0 else "W"}'


def _format_time(value: datetime) -> str:
    return value.astimezone().strftime('%d %b %Y, %H:%M %Z') if value.tzinfo else value.strftime('%d %b %Y, %H:%M')


def _latest_update_time(
    observation_time: datetime | None,
    products: tuple[TropicalProduct, ...],
) -> datetime | None:
    """Return the newest authoritative observation or product issue time."""
    candidates = [product.issued_at for product in products if product.issued_at is not None]
    if observation_time is not None:
        candidates.append(observation_time)
    if not candidates:
        return None

    return max(candidates, key=_comparable_datetime)


def _latest_datetime(first: datetime, second: datetime) -> datetime:
    return max((first, second), key=_comparable_datetime)


def _comparable_datetime(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _clean(value: object) -> str:
    return value.strip() if isinstance(value, str) else ''


def _classification_colour_role(classification: str) -> str:
    """Map issuing-centre wording to a stable Textual semantic colour role."""
    value = classification.casefold().replace('-', ' ')
    if (
        'hurricane' in value
        or 'typhoon' in value
        or 'category' in value
        or 'intense tropical cyclone' in value
        or 'severe tropical cyclone' in value
    ):
        return 'error'
    if 'severe tropical storm' in value or 'strong tropical storm' in value:
        return 'warning'
    if (
        'tropical storm' in value
        or 'moderate tropical storm' in value
        or 'tropical cyclone' in value
    ):
        return 'accent'
    if 'tropical depression' in value:
        return 'secondary'
    return 'primary'


__all__ = ['TropicalSystemsScreen']
