"""Focused regressions for the dedicated tropical-system workspace."""

from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime
from io import StringIO
from unittest.mock import AsyncMock, patch

from rich.console import Console
from textual.app import App
from textual.containers import VerticalScroll
from textual.widgets import Markdown, Static, Tabs
from wevva_warnings import CanonicalTropicalSystem, TropicalProduct, TropicalSystem
from wevva_warnings.registry import get_source

from wevva.app import Wevva
from wevva.screens.tropical_systems_screen import (
    TropicalSystemsScreen,
    _observation_key,
    _product_widgets,
    _structured_product,
)
from wevva.screens.weather_screen import WeatherScreen
from wevva.widgets.tropical_centre_weather import TropicalCentreWeather
from wevva.widgets.tropical_info_table import TropicalInfoTable
from wevva.widgets.tropical_summary import TropicalStormSummary
from wevva.widgets.tropical_track import LargeTropicalStormTrackScope


def _observation(
    system_id: str,
    source: str,
    name: str,
    *,
    classification: str,
    latitude: float | None,
    longitude: float | None,
    pressure: str | None = None,
    track: list[list[float]] | None = None,
    basin: str | None = None,
) -> TropicalSystem:
    return TropicalSystem(
        id=system_id,
        source=source,
        name=name,
        headline=f'{classification} {name}',
        summary=f'{name} provider summary',
        classification=classification,
        basin=basin,
        center_lat=latitude,
        center_lon=longitude,
        min_pressure=pressure,
        movement='NW at 15 kt',
        max_wind='45 kt',
        issued_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
        source_info=get_source(source),
        geometries=({'forecast_track': {'type': 'LineString', 'coordinates': track}} if track is not None else {}),
    )


def _rendered(widget: Static) -> str:
    console = Console(width=100, file=StringIO(), record=True)
    console.print(widget._Static__content)
    return console.export_text()


def _renderable_text(renderable) -> str:
    console = Console(width=120, file=StringIO(), record=True)
    console.print(renderable)
    return console.export_text()


def _data_table_text(table) -> str:
    return '\n'.join(
        getattr(cell, 'plain', str(cell)) for row_index in range(table.row_count) for cell in table.get_row_at(row_index)
    )


class _ScreenApp(App):
    def __init__(self, screen: TropicalSystemsScreen) -> None:
        super().__init__()
        self.test_screen = screen

    async def on_mount(self) -> None:
        await self.push_screen(self.test_screen)


class _BindingApp(_ScreenApp):
    BINDINGS = [
        ('s', 'search', 'Search'),
        ('r', 'refresh', 'Refresh'),
        ('a', 'save', 'Save'),
        ('d', 'delete', 'Delete'),
    ]

    def __init__(self, screen: TropicalSystemsScreen) -> None:
        super().__init__(screen)
        self.app_actions: list[str] = []

    def action_search(self) -> None:
        self.app_actions.append('search')

    def action_refresh(self) -> None:
        self.app_actions.append('refresh')

    def action_save(self) -> None:
        self.app_actions.append('save')

    def action_delete(self) -> None:
        self.app_actions.append('delete')


class _NotificationApp(_ScreenApp):
    def __init__(self, screen: TropicalSystemsScreen) -> None:
        super().__init__(screen)
        self.notified: list[tuple[str, str]] = []

    def notify(
        self,
        message: str,
        *,
        title: str = '',
        severity: str = 'information',
        timeout: float | None = None,
        markup: bool = True,
    ) -> None:
        del title, timeout, markup
        self.notified.append((message, severity))


class TropicalSystemsScreenTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.jma = _observation(
            'nangka-jma',
            'jma_tropical',
            'NANGKA',
            classification='Typhoon',
            latitude=28.0,
            longitude=135.0,
            pressure='970 hPa',
            track=[[135.0, 28.0], [136.0, 29.0], [137.0, 30.0]],
        )
        self.cma = _observation(
            'nangka-cma',
            'cma_tropical',
            'NANGKA',
            classification='Tropical Storm',
            latitude=20.0,
            longitude=120.0,
            pressure='990 hPa',
            track=[[120.0, 20.0], [119.0, 21.0], [118.0, 22.0]],
        )
        self.cphc = _observation(
            'lala-cphc',
            'cphc_gis_central_pacific',
            'LALA',
            classification='Tropical Storm',
            latitude=15.2,
            longitude=-145.5,
            track=[[-145.5, 15.2], [-150.0, 17.0], [-155.0, 19.0]],
        )
        self.nangka = CanonicalTropicalSystem('NANGKA', [self.jma, self.cma])
        self.lala = CanonicalTropicalSystem('LALA', [self.cphc])

    async def test_canonical_storms_are_sorted_and_multi_source_storm_appears_once(self) -> None:
        calls: list[str] = []

        async def loader(system: TropicalSystem) -> list[TropicalProduct]:
            calls.append(system.source)
            return []

        screen = TropicalSystemsScreen(
            [self.lala, self.nangka],
            location_latitude=30.0,
            location_longitude=135.0,
            location_name='Tokyo',
            product_loader=loader,
        )
        app = _ScreenApp(screen)
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            await pilot.pause()

            storm_tabs = list(screen.query('#tropical-storm-tabs Tab'))
            labels = [tab.label.plain for tab in storm_tabs]
            sources = screen.query_one('#tropical-source-tabs', Tabs)
            self.assertEqual(labels, ['Typhoon NANGKA', 'Tropical Storm LALA'])
            self.assertTrue(storm_tabs[0].label.spans[0].style.bold)
            self.assertEqual([tab.label.plain for tab in sources.query('Tab')], ['JMA', 'CMA'])
            self.assertTrue(sources.display)
            self.assertEqual(calls, ['jma_tropical'])
            products = screen.query_one('#tropical-product-tabs', Tabs)
            self.assertEqual(list(products.query('Tab')), [])
            self.assertFalse(products.display)
            summary = screen.query_one(TropicalStormSummary)
            product_body = screen.query_one('#tropical-product-body', VerticalScroll)
            root = screen.query_one('#tropical-screen-root')
            workspace = screen.query_one('#tropical-workspace')
            product = screen.query_one('#tropical-product-pane')
            self.assertTrue(workspace.display)
            self.assertEqual(root.border_title, 'Active Tropical Systems')
            self.assertEqual(root.styles.border_title_align, 'center')
            self.assertEqual(summary.border_title, 'Summary')
            self.assertEqual(product.border_title, 'Storm Information')
            self.assertGreater(summary.region.height, 0)
            self.assertGreater(product_body.region.height, 0)
            self.assertLess(
                summary.region.y,
                root.region.y + root.region.height,
            )
            self.assertGreaterEqual(summary.region.y + summary.region.height, root.region.y)
            self.assertIn('Typhoon', _data_table_text(summary))
            self.assertNotIn('●', _data_table_text(summary))
            self.assertNotIn('Distance', _data_table_text(summary))
            self.assertIn('15 Aug 2026', summary.get_cell('last-update', 'value'))
            screenshot = app.export_screenshot()
            self.assertIn('Classification', screenshot)
            self.assertIn('Typhoon', screenshot)

            await pilot.press('w')
            await pilot.pause()
            self.assertIsNot(app.screen, screen)

    async def test_source_switch_changes_exact_summary_track_land_and_products(self) -> None:
        calls: list[str] = []

        async def loader(system: TropicalSystem) -> list[TropicalProduct]:
            calls.append(system.source)
            return [
                TropicalProduct(
                    kind='forecast',
                    label='Forecast',
                    data={
                        'points': [
                            {
                                'valid_at': '2026-08-16T12:00:00Z',
                                'latitude': system.center_lat,
                                'longitude': system.center_lon,
                                'minimum_pressure_hpa': 970 if system.source.startswith('jma') else 990,
                            }
                        ]
                    },
                )
            ]

        screen = TropicalSystemsScreen(
            [self.nangka],
            location_latitude=55.9533,
            location_longitude=-3.1883,
            location_name='Edinburgh',
            product_loader=loader,
        )
        app = _ScreenApp(screen)
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            await pilot.pause()
            summary = screen.query_one(TropicalStormSummary)
            track = screen.query_one(LargeTropicalStormTrackScope)
            first_scope = track._scope
            self.assertIn('970 hPa', _data_table_text(summary))
            self.assertNotIn('990 hPa', _data_table_text(summary))
            assert first_scope is not None
            self.assertFalse(first_scope.land)

            screen.query_one('#tropical-source-tabs', Tabs).active = 'tropical-screen-source-1'
            await pilot.pause()
            await pilot.pause()
            second_scope = track._scope
            self.assertIn('990 hPa', _data_table_text(summary))
            self.assertNotIn('970 hPa', _data_table_text(summary))
            assert second_scope is not None
            self.assertTrue(second_scope.land)
            self.assertEqual(first_scope.places, second_scope.places)
            self.assertNotEqual(first_scope.storm, second_scope.storm)
            self.assertNotEqual(first_scope.land, second_scope.land)
            self.assertEqual(calls, ['jma_tropical', 'cma_tropical'])

            screen.query_one('#tropical-source-tabs', Tabs).active = 'tropical-screen-source-0'
            await pilot.pause()
            self.assertEqual(calls, ['jma_tropical', 'cma_tropical'])

    async def test_current_weather_loads_by_source_centre_and_reuses_cached_response(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        calls: list[tuple[float, float]] = []

        async def product_loader(_system: TropicalSystem) -> list[TropicalProduct]:
            return []

        async def weather_loader(latitude: float, longitude: float) -> dict:
            calls.append((latitude, longitude))
            started.set()
            if len(calls) == 1:
                await release.wait()
            temperature = 29.4 if latitude == 28.0 else 31.4
            return {
                'latitude': latitude + 0.125,
                'longitude': longitude - 0.125,
                'current': {
                    'temperature_2m': temperature,
                    'apparent_temperature': temperature + 5,
                    'precipitation_probability': 80,
                    'precipitation': 3.2,
                    'weather_code': 95,
                    'surface_pressure': 986.4,
                    'is_day': 1,
                    'wind_speed_10m': 55.4,
                    'wind_gusts_10m': 78.4,
                    'wind_direction_10m': 315,
                },
                'current_units': {
                    'temperature_2m': '°C',
                    'precipitation': 'mm',
                    'surface_pressure': 'hPa',
                    'wind_speed_10m': 'km/h',
                },
            }

        screen = TropicalSystemsScreen(
            [self.nangka],
            product_loader=product_loader,
            centre_weather_loader=weather_loader,
        )
        app = _ScreenApp(screen)
        async with app.run_test(size=(180, 55)) as pilot:
            await started.wait()
            await pilot.pause()
            await pilot.pause()
            weather = screen.query_one(TropicalCentreWeather)
            weather_content = weather.query_one(
                '#tropical-centre-weather-content',
                TropicalInfoTable,
            )
            track = screen.query_one(LargeTropicalStormTrackScope)
            self.assertTrue(weather.display)
            self.assertFalse(weather.loading)
            self.assertTrue(weather_content.loading)
            self.assertFalse(track.loading)
            self.assertEqual(weather.border_title, 'Current weather near centre')
            self.assertEqual(weather.content_size.height, 6)
            self.assertEqual(weather_content.styles.height.value, 6)

            release.set()
            await pilot.pause()
            await pilot.pause()
            self.assertFalse(weather_content.loading)
            self.assertEqual(weather_content.region.height, 6)
            self.assertEqual(weather_content.row_count, 6)
            self.assertEqual(weather_content.get_cell('condition', 'value').plain, '⛈️ Thunderstorm')
            self.assertEqual(weather_content.get_cell('temperature', 'value').plain, '29°C · feels 34°C')
            self.assertEqual(weather_content.get_cell('wind', 'value').plain, '55 km/h NW ↘ · gusts 78 km/h')
            self.assertEqual(weather_content.get_cell('precipitation', 'value').plain, '80% · 3.2 mm/hr')
            self.assertEqual(weather_content.get_cell('surface-pressure', 'value').plain, '986 hPa')
            self.assertEqual(weather_content.get_cell('forecast-coords', 'value').plain, '28.12°N 134.88°E')
            temperature_cell = weather_content.get_cell('temperature', 'value')
            number_span = next(span for span in temperature_cell.spans if temperature_cell.plain[span.start : span.end] == '29')
            unit_span = next(span for span in temperature_cell.spans if temperature_cell.plain[span.start : span.end] == '°C')
            self.assertIn('bold', str(number_span.style))
            self.assertNotIn('bold', str(unit_span.style))
            self.assertEqual(weather.region.width, screen.query_one('#tropical-left-pane').region.width)
            self.assertEqual(weather_content.virtual_size.width, weather_content.content_size.width)

            screen.query_one('#tropical-source-tabs', Tabs).active = 'tropical-screen-source-1'
            await pilot.pause()
            await pilot.pause()
            self.assertEqual(calls, [(28.0, 135.0), (20.0, 120.0)])
            self.assertEqual(weather_content.get_cell('temperature', 'value').plain, '31°C · feels 36°C')

            screen.query_one('#tropical-source-tabs', Tabs).active = 'tropical-screen-source-0'
            await pilot.pause()
            self.assertEqual(calls, [(28.0, 135.0), (20.0, 120.0)])
            self.assertEqual(weather_content.get_cell('temperature', 'value').plain, '29°C · feels 34°C')

    async def test_current_weather_failure_is_compact_and_missing_centre_skips_request(self) -> None:
        calls = 0

        async def weather_loader(_latitude: float, _longitude: float) -> dict:
            nonlocal calls
            calls += 1
            raise RuntimeError('Open-Meteo unavailable')

        async def product_loader(_system: TropicalSystem) -> list[TropicalProduct]:
            return []

        screen = TropicalSystemsScreen(
            [self.lala],
            product_loader=product_loader,
            centre_weather_loader=weather_loader,
        )
        app = _ScreenApp(screen)
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            await pilot.pause()
            weather = screen.query_one(TropicalCentreWeather)
            weather_content = weather.query_one(
                '#tropical-centre-weather-content',
                TropicalInfoTable,
            )
            self.assertEqual(calls, 1)
            self.assertTrue(weather.display)
            self.assertEqual(weather_content.row_count, 1)
            self.assertEqual(
                weather_content.get_cell('weather', 'value').plain,
                'Temporarily unavailable',
            )

        no_centre = _observation(
            'missing-centre',
            'jma_tropical',
            'QUIET',
            classification='Tropical Depression',
            latitude=None,
            longitude=None,
        )
        screen = TropicalSystemsScreen(
            [CanonicalTropicalSystem('QUIET', [no_centre])],
            product_loader=product_loader,
            centre_weather_loader=weather_loader,
        )
        app = _ScreenApp(screen)
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            self.assertFalse(screen.query_one(TropicalCentreWeather).display)
            self.assertEqual(calls, 1)

    async def test_single_source_hides_source_bar_and_global_map_ignores_edinburgh(self) -> None:
        async def loader(_system: TropicalSystem) -> list[TropicalProduct]:
            return []

        screen = TropicalSystemsScreen(
            [self.lala],
            location_latitude=55.9533,
            location_longitude=-3.1883,
            location_name='Edinburgh',
            product_loader=loader,
        )
        app = _ScreenApp(screen)
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            sources = screen.query_one('#tropical-source-tabs', Tabs)
            track = screen.query_one(LargeTropicalStormTrackScope)
            self.assertFalse(sources.display)
            assert track._scope is not None
            self.assertTrue(track._scope.places)
            self.assertTrue(track._scope.land)

    async def test_source_and_product_selection_survive_visiting_another_storm(self) -> None:
        async def loader(_system: TropicalSystem) -> list[TropicalProduct]:
            return [TropicalProduct(kind='forecast', label='Forecast', data={'points': []})]

        screen = TropicalSystemsScreen(
            [self.lala, self.nangka],
            location_latitude=28.0,
            location_longitude=135.0,
            product_loader=loader,
        )
        app = _ScreenApp(screen)
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            await pilot.pause()
            sources = screen.query_one('#tropical-source-tabs', Tabs)
            products = screen.query_one('#tropical-product-tabs', Tabs)
            sources.active = 'tropical-screen-source-1'
            await pilot.pause()
            await pilot.pause()
            products.active = 'tropical-product-0'
            await pilot.pause()

            screen.query_one('#tropical-storm-tabs', Tabs).active = 'tropical-storm-1'
            await pilot.pause()
            self.assertFalse(sources.display)

            screen.query_one('#tropical-storm-tabs', Tabs).active = 'tropical-storm-0'
            await pilot.pause()
            self.assertEqual(sources.active, 'tropical-screen-source-1')
            self.assertEqual(products.active, 'tropical-product-0')

    async def test_products_are_lazy_cached_and_plain_format_stays_literal(self) -> None:
        calls = 0
        self.cphc.issued_at = None

        async def loader(_system: TropicalSystem) -> list[TropicalProduct]:
            nonlocal calls
            calls += 1
            return [
                TropicalProduct(
                    kind='advisory',
                    label='Public Advisory',
                    issued_at=datetime(2026, 8, 15, 14, 32, tzinfo=UTC),
                    content='* literal provider bullet\n[not a link]',
                    content_format='plain',
                ),
            ]

        screen = TropicalSystemsScreen([self.lala], product_loader=loader)
        app = _ScreenApp(screen)
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            await pilot.pause()
            tabs = screen.query_one('#tropical-product-tabs', Tabs)
            self.assertEqual(
                [tab.label.plain for tab in tabs.query('Tab')],
                ['Forecast', 'Public Advisory'],
            )
            self.assertEqual(calls, 1)
            summary = screen.query_one(TropicalStormSummary)
            self.assertIn('15 Aug 2026', summary.get_cell('last-update', 'value'))
            body = screen.query_one('#tropical-product-body', VerticalScroll)
            self.assertIn('Tropical Storm LALA', _rendered(body.query_one(Static)))
            self.assertIn('LALA provider summary', _rendered(body.query_one(Static)))

            tabs.active = 'tropical-product-0'
            await pilot.pause()
            self.assertEqual(len(body.query(Markdown)), 0)
            self.assertIn('* literal provider bullet', _rendered(body.query_one(Static)))

            self.assertEqual(calls, 1)

    def test_last_product_update_survives_refresh_cache_clear(self) -> None:
        self.cphc.issued_at = None
        screen = TropicalSystemsScreen([self.lala])
        product = TropicalProduct(
            kind='advisory',
            label='Public Advisory',
            issued_at=datetime(2026, 8, 15, 14, 32, tzinfo=UTC),
        )
        screen._products[_observation_key(self.cphc)] = (product,)

        before_refresh = dict(screen._summary(self.cphc))['Last update']
        screen._products.clear()
        while_refreshing = dict(screen._summary(self.cphc))['Last update']

        self.assertEqual(while_refreshing, before_refresh)

    def test_explicit_markdown_product_uses_markdown_widget(self) -> None:
        widgets = _product_widgets(
            TropicalProduct(
                kind='discussion',
                label='Discussion',
                title='Provider title already represented by the product',
                issued_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
                content='## Forecast discussion',
                content_format='markdown',
            )
        )

        self.assertEqual(len(widgets), 1)
        self.assertIsInstance(widgets[0], Markdown)

    def test_plain_product_starts_with_retrieved_message_not_ui_preamble(self) -> None:
        widgets = _product_widgets(
            TropicalProduct(
                kind='advisory',
                label='Public Advisory',
                title='Hurricane Lala Public Advisory',
                issued_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
                content='THE OFFICIAL MESSAGE STARTS HERE',
                content_format='plain',
            )
        )

        self.assertEqual(len(widgets), 1)
        self.assertEqual(_rendered(widgets[0]), 'THE OFFICIAL MESSAGE STARTS HERE\n')

    def test_actual_forecast_point_shape_renders_only_available_fields(self) -> None:
        rendered = _renderable_text(
            _structured_product(
                {
                    'agency': 'BABJ',
                    'points': [
                        {
                            'valid_at': '2026-08-11T18:00:00+08:00',
                            'latitude': 20.5,
                            'longitude': 119.5,
                            'classification': 'Typhoon',
                            'minimum_pressure_hpa': 970,
                            'maximum_wind_mps': 38,
                        }
                    ],
                }
            )
        )

        self.assertIn('Valid', rendered)
        self.assertIn('Typhoon', rendered)
        self.assertIn('20.5°N 119.5°E', rendered)
        self.assertIn('38 m/s', rendered)
        self.assertIn('970 hPa', rendered)

        centre_only = _renderable_text(_structured_product({'points': [{'latitude': 17.0, 'longitude': 123.0}]}))
        self.assertIn('Centre', centre_only)
        self.assertNotIn('Wind', centre_only)
        self.assertNotIn('Pressure', centre_only)

    async def test_product_failure_and_missing_track_leave_clear_status(self) -> None:
        no_track = _observation(
            'quiet-jma',
            'jma_tropical',
            'QUIET',
            classification='Tropical Depression',
            latitude=25.0,
            longitude=140.0,
        )

        async def loader(_system: TropicalSystem) -> list[TropicalProduct]:
            raise RuntimeError('provider unavailable')

        screen = TropicalSystemsScreen(
            [CanonicalTropicalSystem('QUIET', [no_track])],
            product_loader=loader,
        )
        app = _NotificationApp(screen)
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            await pilot.pause()
            self.assertFalse(screen.query_one(LargeTropicalStormTrackScope).display)
            self.assertTrue(screen.query_one('#tropical-track-unavailable', Static).display)
            self.assertEqual(
                [tab.label.plain for tab in screen.query('#tropical-product-tabs Tab')],
                [],
            )
            self.assertFalse(screen.query_one('#tropical-product-tabs', Tabs).display)
            body_text = _rendered(screen.query_one('#tropical-product-body', VerticalScroll).query_one(Static))
            self.assertIn('Supplementary products are temporarily unavailable', body_text)
            self.assertEqual(
                app.notified,
                [('Forecast track and cone are not available from JMA.', 'information')],
            )

            await screen._show_observation()
            self.assertEqual(len(app.notified), 1)

    async def test_track_without_cone_notifies_once(self) -> None:
        async def loader(_system: TropicalSystem) -> list[TropicalProduct]:
            return []

        screen = TropicalSystemsScreen([self.lala], product_loader=loader)
        app = _NotificationApp(screen)
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            await pilot.pause()

            self.assertEqual(
                app.notified,
                [('Forecast cone is not available from CPHC.', 'information')],
            )
            await screen._show_observation()
            self.assertEqual(len(app.notified), 1)

    async def test_track_with_cone_does_not_notify(self) -> None:
        self.cphc.geometries['cone'] = {
            'type': 'Polygon',
            'coordinates': [
                [
                    [-145.0, 14.5],
                    [-154.5, 18.5],
                    [-155.5, 19.5],
                    [-144.5, 15.5],
                    [-145.0, 14.5],
                ]
            ],
        }

        async def loader(_system: TropicalSystem) -> list[TropicalProduct]:
            return []

        screen = TropicalSystemsScreen([self.lala], product_loader=loader)
        app = _NotificationApp(screen)
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            await pilot.pause()

            self.assertEqual(app.notified, [])

    async def test_layout_protects_document_width_and_switches_topology(self) -> None:
        async def loader(_system: TropicalSystem) -> list[TropicalProduct]:
            return []

        screen = TropicalSystemsScreen([self.lala], product_loader=loader)
        app = _ScreenApp(screen)
        async with app.run_test(size=(240, 80)) as pilot:
            await pilot.pause()
            stage = screen.query_one('#tropical-screen-stage')
            root = screen.query_one('#tropical-screen-root')
            workspace = screen.query_one('#tropical-workspace')
            product = screen.query_one('#tropical-product-pane')
            left = screen.query_one('#tropical-left-pane')
            track_pane = screen.query_one('#tropical-track-pane')
            track = screen.query_one(LargeTropicalStormTrackScope)
            centre_weather = screen.query_one(TropicalCentreWeather)
            product_body = screen.query_one('#tropical-product-body')
            self.assertFalse(workspace.has_class('compact'))
            self.assertGreaterEqual(product.region.width, 72)
            self.assertGreaterEqual(left.region.width, 54)
            self.assertLess(root.region.width, 240)
            self.assertAlmostEqual(root.region.x, (240 - root.region.width) / 2, delta=2)
            self.assertAlmostEqual(
                root.region.y - stage.region.y,
                (stage.region.height - root.region.height) / 2,
                delta=2,
            )
            self.assertEqual(track_pane.border_title, 'Storm Track')
            self.assertEqual(track_pane.styles.border_title_align, 'left')
            self.assertEqual(track_pane.styles.border_top[0], 'round')
            self.assertEqual(
                product.region.x - (left.region.x + left.region.width),
                2,
            )
            self.assertEqual(stage.styles.hatch[0], '╱')
            self.assertEqual(workspace.styles.hatch[0], '╱')
            self.assertEqual(root.styles.padding.top, 1)
            self.assertEqual(screen.query_one(TropicalStormSummary).styles.padding.top, 0)
            self.assertEqual(screen.query_one(TropicalStormSummary).styles.padding.bottom, 0)
            self.assertEqual(product_body.styles.padding.top, 1)
            self.assertEqual(product_body.styles.padding.right, 2)
            self.assertIsNone(product_body.styles.hatch)
            self.assertEqual(track.styles.padding.left, 1)
            self.assertEqual(track.styles.padding.right, 1)
            self.assertEqual(centre_weather.styles.margin.bottom, 1)

            await pilot.resize_terminal(90, 40)
            await pilot.pause()
            await pilot.pause()
            self.assertTrue(stage.has_class('compact'))
            self.assertTrue(root.has_class('compact'))
            self.assertTrue(workspace.has_class('compact'))
            self.assertEqual(stage.styles.padding.top, 1)
            self.assertEqual(stage.styles.padding.right, 2)
            self.assertEqual(stage.styles.padding.bottom, 1)
            self.assertEqual(stage.styles.padding.left, 2)
            self.assertEqual(root.region.width, stage.content_size.width)
            self.assertEqual(root.region.height, stage.content_size.height)
            self.assertLess(left.region.width, workspace.region.width)
            self.assertGreater(product.region.width, 0)
            self.assertEqual(left.region.y, product.region.y)
            self.assertEqual(
                product.region.x - (left.region.x + left.region.width),
                2,
            )
            self.assertEqual(track_pane.styles.height.unit.name, 'FRACTION')
            self.assertEqual(centre_weather.styles.margin.bottom, 1)

            await pilot.resize_terminal(240, 80)
            await pilot.pause()
            await pilot.pause()
            self.assertFalse(stage.has_class('compact'))
            self.assertFalse(root.has_class('compact'))
            self.assertFalse(workspace.has_class('compact'))

    async def test_native_loading_states_cover_discovery_and_products(self) -> None:
        systems_started = asyncio.Event()
        release_systems = asyncio.Event()
        products_started = asyncio.Event()
        release_products = asyncio.Event()

        async def systems_loader() -> list[CanonicalTropicalSystem]:
            systems_started.set()
            await release_systems.wait()
            return [self.lala]

        async def product_loader(_system: TropicalSystem) -> list[TropicalProduct]:
            products_started.set()
            await release_products.wait()
            return [TropicalProduct(kind='advisory', label='Public Advisory', content='Ready')]

        screen = TropicalSystemsScreen(
            [],
            systems_loader=systems_loader,
            product_loader=product_loader,
        )
        app = _ScreenApp(screen)
        async with app.run_test(size=(140, 45)) as pilot:
            await systems_started.wait()
            root = screen.query_one('#tropical-screen-root')
            content = screen.query_one('#tropical-screen-content')
            self.assertFalse(root.loading)
            self.assertTrue(content.loading)
            self.assertEqual(root.border_title, 'Active Tropical Systems')

            release_systems.set()
            await products_started.wait()
            await pilot.pause()
            body = screen.query_one('#tropical-product-body', VerticalScroll)
            self.assertFalse(content.loading)
            self.assertTrue(body.loading)

            release_products.set()
            await pilot.pause()
            await pilot.pause()
            self.assertFalse(body.loading)
            self.assertEqual(
                [tab.label.plain for tab in screen.query('#tropical-product-tabs Tab')],
                ['Forecast', 'Public Advisory'],
            )

    async def test_weather_binding_replaces_escape_and_location_bindings_are_hidden(self) -> None:
        async def loader(_system: TropicalSystem) -> list[TropicalProduct]:
            return []

        screen = TropicalSystemsScreen([self.lala], product_loader=loader)
        app = _BindingApp(screen)
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            keys = {binding.key for binding in screen.BINDINGS}
            self.assertIn('w', keys)
            self.assertIn('t', keys)
            self.assertIn('c', keys)
            self.assertNotIn('escape', keys)
            self.assertNotIn('left_square_bracket', keys)
            self.assertNotIn('right_square_bracket', keys)
            for key in ('s', 'a', 'd'):
                active = screen.active_bindings[key]
                self.assertIs(active.node, screen)
                self.assertFalse(active.binding.show)

            await pilot.press('s', 'a', 'd', 'escape')
            await pilot.pause()
            self.assertEqual(app.app_actions, [])
            self.assertIs(app.screen, screen)

            track = screen.query_one(LargeTropicalStormTrackScope)
            self.assertTrue(track.track_visible)
            self.assertTrue(track.cone_visible)
            await pilot.press('t', 'c')
            await pilot.pause()
            self.assertFalse(track.track_visible)
            self.assertFalse(track.cone_visible)
            await pilot.press('t', 'c')
            await pilot.pause()
            self.assertTrue(track.track_visible)
            self.assertTrue(track.cone_visible)

            await pilot.press('w')
            await pilot.pause()
            self.assertIsNot(app.screen, screen)

    async def test_refresh_updates_track_in_place_and_loads_only_information_pane(self) -> None:
        refresh_started = asyncio.Event()
        release_refresh = asyncio.Event()
        refreshed = _observation(
            'lala-cphc',
            'cphc_gis_central_pacific',
            'LALA',
            classification='Hurricane',
            latitude=17.0,
            longitude=-147.0,
            pressure='950 hPa',
            track=[[-147.0, 17.0], [-151.0, 19.0], [-156.0, 21.0]],
        )

        async def product_loader(_system: TropicalSystem) -> list[TropicalProduct]:
            return []

        async def refresh_loader() -> list[CanonicalTropicalSystem]:
            refresh_started.set()
            await release_refresh.wait()
            return [CanonicalTropicalSystem('LALA', [refreshed])]

        screen = TropicalSystemsScreen(
            [self.lala],
            product_loader=product_loader,
            refresh_loader=refresh_loader,
        )
        app = _BindingApp(screen)
        async with app.run_test(size=(180, 55)) as pilot:
            await pilot.pause()
            track = screen.query_one(LargeTropicalStormTrackScope)
            old_scope = track._scope
            information = screen.query_one('#tropical-product-pane')
            information_content = screen.query_one('#tropical-product-content')
            content = screen.query_one('#tropical-screen-content')
            left = screen.query_one('#tropical-left-pane')

            await pilot.press('r')
            await refresh_started.wait()
            loading_state = (
                information.loading,
                information_content.loading,
                content.loading,
                left.loading,
                track.loading,
            )
            scope_while_loading = track._scope
            app_actions_while_loading = list(app.app_actions)
            release_refresh.set()
            await pilot.pause()
            await pilot.pause()
            self.assertEqual(loading_state, (False, True, False, False, False))
            self.assertEqual(information.border_title, 'Storm Information')
            self.assertIs(scope_while_loading, old_scope)
            self.assertEqual(app_actions_while_loading, [])
            self.assertFalse(information.loading)
            self.assertFalse(information_content.loading)
            self.assertIs(screen.query_one(LargeTropicalStormTrackScope), track)
            self.assertIsNot(track._scope, old_scope)
            self.assertIn(
                '950 hPa',
                _data_table_text(screen.query_one(TropicalStormSummary)),
            )
            self.assertEqual(
                [tab.label.plain for tab in screen.query('#tropical-storm-tabs Tab')],
                ['Hurricane LALA'],
            )

    def test_weather_screen_exposes_tropical_workspace_binding(self) -> None:
        self.assertIn(
            ('t', 'tropical_systems', 'Tropical Systems'),
            WeatherScreen.BINDINGS,
        )


class TropicalProductApplicationCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_application_forced_system_refresh_replaces_cache(self) -> None:
        refreshed = _observation(
            'lala-cphc',
            'cphc_gis_central_pacific',
            'LALA',
            classification='Hurricane',
            latitude=17.0,
            longitude=-147.0,
        )
        canonical = CanonicalTropicalSystem('LALA', [refreshed])
        loader = AsyncMock(return_value=([canonical], True))
        app = Wevva()
        app._tropical_system_cache = (0.0, ())
        app._tropical_product_cache[('source', 'id', 'issued')] = ()

        with patch('wevva.app.get_tropical_system_candidates_async', loader):
            systems = await app.refresh_tropical_systems()

        self.assertEqual(systems, [canonical])
        self.assertEqual(app._tropical_system_cache[1], (canonical,))
        self.assertEqual(app._tropical_product_cache, {})
        loader.assert_awaited_once_with()

    async def test_application_cache_reuses_products_for_same_issued_observation(self) -> None:
        observation = _observation(
            'lala-cphc',
            'cphc_gis_central_pacific',
            'LALA',
            classification='Tropical Storm',
            latitude=15.2,
            longitude=-145.5,
        )
        product = TropicalProduct(kind='advisory', label='Public Advisory', content='Advisory')
        loader = AsyncMock(return_value=[product])
        app = Wevva()

        with patch('wevva.app.get_tropical_products_async', loader):
            first = await app.load_tropical_products(observation)
            second = await app.load_tropical_products(observation)

        self.assertEqual(first, [product])
        self.assertEqual(second, [product])
        loader.assert_awaited_once_with(observation)


if __name__ == '__main__':
    unittest.main()
