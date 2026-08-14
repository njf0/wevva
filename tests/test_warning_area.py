"""Focused selected-warning geographic-scope checks."""

from __future__ import annotations

from dataclasses import replace
from io import StringIO
import unittest

from rich.console import Console
from textual.app import App, ComposeResult

from wevva.alerts import Alert
from wevva.location_metadata import LocationMetadata
from wevva.screens.weather_screen import WeatherScreen
from wevva.services.tropical import NearbyTropicalSystem
from wevva.widgets.tropical_track import TropicalStormTrackScope
from wevva.widgets.saved_locations import SavedLocationsSidebar
from wevva.widgets.warning_area import (
    WarningAreaPalette,
    WarningAreaScope,
    build_warning_area_geometry,
    render_warning_area,
)
from wevva.widgets.weather_alerts import (
    WeatherAlertDetailsPanel,
    WeatherAlertDetailsSidebar,
    WeatherAlertsPanel,
)
from wevva_warnings import TropicalSystem


def _ghana_alert(identifier: str = 'ghana-rain', *, geometry=None) -> Alert:
    return Alert(
        id=identifier,
        source='test-cap',
        event='Heavy Rain',
        headline=f'{identifier} heavy rain warning',
        severity='moderate',
        geometry=geometry
        or {
            'type': 'Polygon',
            'coordinates': [[
                [-1.2, 5.0],
                [0.8, 5.0],
                [0.8, 7.2],
                [-1.2, 7.2],
                [-1.2, 5.0],
            ]],
        },
    )


class WarningAreaGeometryTests(unittest.TestCase):
    def test_warning_scope_uses_stable_whole_context_viewport(self) -> None:
        small = _ghana_alert()
        large = _ghana_alert(
            'ghana-wide',
            geometry={
                'type': 'Polygon',
                'coordinates': [[
                    [-3.0, 4.8],
                    [1.0, 4.8],
                    [1.0, 10.8],
                    [-3.0, 10.8],
                    [-3.0, 4.8],
                ]],
            },
        )

        small_scope = build_warning_area_geometry(
            small,
            location_latitude=5.6037,
            location_longitude=-0.1870,
            location_name='Accra',
            country_code='GH',
        )
        large_scope = build_warning_area_geometry(
            large,
            location_latitude=5.6037,
            location_longitude=-0.1870,
            location_name='Accra',
            country_code='GH',
        )

        assert small_scope is not None and large_scope is not None
        self.assertEqual(small_scope.viewport, large_scope.viewport)
        self.assertTrue(small_scope.land)
        self.assertEqual(small_scope.location_name, 'Accra')

    def test_multipolygon_preserves_every_warning_component(self) -> None:
        alert = _ghana_alert(
            geometry={
                'type': 'MultiPolygon',
                'coordinates': [
                    [[[-1.2, 5.0], [-0.5, 5.0], [-0.5, 5.8], [-1.2, 5.8], [-1.2, 5.0]]],
                    [[[0.1, 6.0], [0.8, 6.0], [0.8, 6.8], [0.1, 6.8], [0.1, 6.0]]],
                ],
            },
        )

        scope = build_warning_area_geometry(
            alert,
            location_latitude=5.6037,
            location_longitude=-0.1870,
            location_name='Accra',
            country_code='GH',
        )

        assert scope is not None
        self.assertEqual(len(scope.warning), 2)

    def test_missing_or_non_polygon_geometry_has_no_scope(self) -> None:
        for geometry in (None, {'type': 'Point', 'coordinates': [-0.187, 5.604]}):
            alert = replace(_ghana_alert(), geometry=geometry)
            self.assertIsNone(
                build_warning_area_geometry(
                    alert,
                    location_latitude=5.6037,
                    location_longitude=-0.1870,
                    location_name='Accra',
                    country_code='GH',
                )
            )

    def test_warning_fill_and_location_render_over_subdued_land(self) -> None:
        scope = build_warning_area_geometry(
            _ghana_alert(),
            location_latitude=5.6037,
            location_longitude=-0.1870,
            location_name='Accra',
            country_code='GH',
        )
        assert scope is not None

        rendered = render_warning_area(
            scope,
            width=34,
            height=11,
            palette=WarningAreaPalette(land='#5684a5', warning='yellow', location='green'),
        )

        self.assertIn('✦', rendered.plain)
        self.assertIn('Accra', rendered.plain)
        self.assertIn('✦ Accra', rendered.plain)
        self.assertTrue(any(span.style == 'yellow' for span in rendered.spans))
        self.assertTrue(any(span.style == '#5684a5' for span in rendered.spans))
        self.assertTrue(any(0x2801 <= ord(character) <= 0x28FF for character in rendered.plain))
        self.assertIn('⣿', rendered.plain)


class _WarningSidebarApp(App):
    def __init__(self) -> None:
        super().__init__()
        self.location = LocationMetadata(
            latitude=5.6037,
            longitude=-0.1870,
            name='Accra',
            country='Ghana',
            country_code='GH',
        )
        self.forecast_metadata = LocationMetadata(latitude=5.6037, longitude=-0.1870)

    def compose(self) -> ComposeResult:
        yield WeatherAlertDetailsSidebar()


class _WarningWeatherApp(App):
    def __init__(self) -> None:
        super().__init__()
        self.location = LocationMetadata(
            latitude=5.6037,
            longitude=-0.1870,
            name='Accra',
            country='Ghana',
            country_code='GH',
        )
        self.forecast_metadata = LocationMetadata(latitude=5.6037, longitude=-0.1870)
        self.saved_locations = []

    def on_mount(self) -> None:
        self.push_screen(WeatherScreen())


class WarningAreaSidebarTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _details_text(sidebar: WeatherAlertDetailsSidebar) -> str:
        console = Console(width=80, file=StringIO(), record=True)
        console.print(getattr(sidebar.content, '_Static__content'))
        return console.export_text()

    async def test_details_and_scopes_are_adjacent_siblings(self) -> None:
        app = _WarningSidebarApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            sidebar = app.query_one(WeatherAlertDetailsSidebar)
            details = app.query_one(WeatherAlertDetailsPanel)
            storm = app.query_one(TropicalStormTrackScope)
            warning = app.query_one(WarningAreaScope)

            self.assertIs(details.parent, sidebar)
            self.assertIs(storm.parent, sidebar)
            self.assertIs(warning.parent, sidebar)
            self.assertEqual(list(sidebar.children), [details, storm, warning])

            system = TropicalSystem(
                id='test-storm',
                source='test-source',
                classification='Tropical Storm',
                name='TEST',
                headline='Tropical Storm TEST',
                center_lat=4.5,
                center_lon=1.0,
                geometries={
                    'forecast_track': {
                        'type': 'LineString',
                        'coordinates': [[1.0, 4.5], [0.5, 5.0], [0.0, 5.5]],
                    },
                },
            )
            sidebar.update_tropical_system(NearbyTropicalSystem(system, 150.0))
            await pilot.pause()
            self.assertTrue(storm.display)
            self.assertFalse(warning.display)
            self.assertEqual(storm.region.y, details.region.y + details.region.height + 1)
            self.assertEqual(storm.styles.margin.top, 1)

            sidebar.update_alert(_ghana_alert())
            await pilot.pause()
            self.assertFalse(storm.display)
            self.assertTrue(warning.display)
            self.assertEqual(warning.region.y, details.region.y + details.region.height + 1)
            self.assertEqual(warning.styles.margin.top, 1)
            self.assertEqual(sidebar.styles.hatch[0], '╱')
            self.assertEqual(storm.styles.background, sidebar.styles.background)
            self.assertEqual(warning.styles.background, sidebar.styles.background)

    async def test_widget_renders_warning_map_in_braille(self) -> None:
        app = _WarningSidebarApp()
        async with app.run_test(size=(80, 40)) as pilot:
            sidebar = app.query_one(WeatherAlertDetailsSidebar)
            warning = app.query_one(WarningAreaScope)

            sidebar.update_alert(_ghana_alert())
            await pilot.pause()
            rendered = warning.render()

            self.assertTrue(any(0x2801 <= ord(character) <= 0x28FF for character in rendered.plain))
            self.assertIn('⣿', rendered.plain)
            self.assertIn('✦ Accra', rendered.plain)

    async def test_selected_alert_updates_prose_and_warning_geometry_together(self) -> None:
        app = _WarningSidebarApp()
        first = _ghana_alert('first')
        second = _ghana_alert(
            'second',
            geometry={
                'type': 'Polygon',
                'coordinates': [[
                    [-0.4, 5.3],
                    [0.4, 5.3],
                    [0.4, 6.1],
                    [-0.4, 6.1],
                    [-0.4, 5.3],
                ]],
            },
        )
        without_geometry = replace(_ghana_alert('plain'), geometry=None)

        async with app.run_test(size=(80, 40)) as pilot:
            sidebar = app.query_one(WeatherAlertDetailsSidebar)
            warning = app.query_one(WarningAreaScope)

            sidebar.update_alert(first)
            await pilot.pause()
            first_geometry = warning._scope.warning if warning._scope else None
            self.assertTrue(warning.display)
            self.assertFalse(app.query_one(TropicalStormTrackScope).display)
            self.assertIn('first heavy rain warning', self._details_text(sidebar))

            sidebar.update_alert(second)
            await pilot.pause()
            self.assertTrue(warning.display)
            self.assertNotEqual(warning._scope.warning if warning._scope else None, first_geometry)
            self.assertIn('second heavy rain warning', self._details_text(sidebar))

            sidebar.update_alert(without_geometry)
            await pilot.pause()
            self.assertFalse(warning.display)
            self.assertIn('plain heavy rain warning', self._details_text(sidebar))

    async def test_long_details_scroll_without_pushing_warning_scope_offscreen(self) -> None:
        app = _WarningSidebarApp()
        alert = replace(
            _ghana_alert('long'),
            description='\n\n'.join(f'Paragraph {index}: detailed guidance.' for index in range(30)),
        )

        async with app.run_test(size=(80, 30)) as pilot:
            sidebar = app.query_one(WeatherAlertDetailsSidebar)
            details = app.query_one(WeatherAlertDetailsPanel)
            warning = app.query_one(WarningAreaScope)

            sidebar.update_alert(alert)
            await pilot.pause()

            self.assertGreater(details.max_scroll_y, 0)
            self.assertEqual(sidebar.scroll_y, 0)
            self.assertEqual(warning.region.y, details.region.y + details.region.height + 1)
            self.assertLessEqual(
                warning.region.y + warning.region.height,
                sidebar.region.y + sidebar.region.height,
            )

    async def test_tall_britain_warning_uses_the_warning_height_maximum(self) -> None:
        app = _WarningSidebarApp()
        app.location = LocationMetadata(
            latitude=51.5072,
            longitude=-0.1276,
            name='London',
            country='United Kingdom',
            country_code='GB',
        )
        app.forecast_metadata = LocationMetadata(latitude=51.5072, longitude=-0.1276)
        alert = replace(
            _ghana_alert('britain'),
            geometry={
                'type': 'Polygon',
                'coordinates': [[
                    [-1.0, 50.5],
                    [1.0, 50.5],
                    [1.0, 52.0],
                    [-1.0, 52.0],
                    [-1.0, 50.5],
                ]],
            },
        )

        async with app.run_test(size=(80, 50)) as pilot:
            sidebar = app.query_one(WeatherAlertDetailsSidebar)
            warning = app.query_one(WarningAreaScope)
            sidebar.update_alert(alert)
            await pilot.pause()

            self.assertEqual(warning._preferred_content_height, 20)
            self.assertEqual(warning.content_size.height, 20)
            self.assertEqual(warning.region.height, 22)

    async def test_storm_height_recomputes_when_sidebar_width_changes(self) -> None:
        app = _WarningSidebarApp()
        app.location = LocationMetadata(
            latitude=19.7297,
            longitude=-155.09,
            name='Hilo',
            country='United States',
            country_code='US',
        )
        app.forecast_metadata = LocationMetadata(latitude=19.7297, longitude=-155.09)
        system = TropicalSystem(
            id='wide-storm',
            source='cphc_gis_central_pacific',
            classification='Tropical Storm',
            name='TEST',
            headline='Tropical Storm TEST',
            center_lat=15.2,
            center_lon=-145.5,
            geometries={
                'forecast_track': {
                    'type': 'LineString',
                    'coordinates': [
                        [-145.5, 15.2],
                        [-146.9, 15.9],
                        [-149.2, 16.6],
                        [-151.7, 17.4],
                        [-154.1, 18.0],
                        [-156.3, 18.7],
                        [-159.0, 19.6],
                    ],
                },
            },
        )

        async with app.run_test(size=(100, 50)) as pilot:
            sidebar = app.query_one(WeatherAlertDetailsSidebar)
            storm = app.query_one(TropicalStormTrackScope)
            sidebar.update_tropical_system(NearbyTropicalSystem(system, 150.0))
            await pilot.pause()
            initial_height = storm._preferred_content_height

            sidebar.styles.width = 60
            await pilot.pause()

            assert initial_height is not None
            self.assertGreater(storm._preferred_content_height or 0, initial_height)
            self.assertEqual(storm.content_size.height, storm._preferred_content_height)

    async def test_switching_alert_tabs_updates_the_same_warning_scope(self) -> None:
        app = _WarningWeatherApp()
        first = _ghana_alert('first-tab')
        second = _ghana_alert(
            'second-tab',
            geometry={
                'type': 'Polygon',
                'coordinates': [[
                    [-0.4, 5.3],
                    [0.4, 5.3],
                    [0.4, 6.1],
                    [-0.4, 6.1],
                    [-0.4, 5.3],
                ]],
            },
        )

        async with app.run_test(size=(200, 60)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, WeatherScreen)
            await screen.render_alert_panel([first, second])
            await pilot.pause()
            warning = screen.query_one(WarningAreaScope)
            progress = screen.query_one(SavedLocationsSidebar).warning_progress
            panel = screen.query_one(WeatherAlertsPanel)
            first_geometry = warning._scope.warning if warning._scope else None

            panel.tabs.active = 'alert-item-1'
            await pilot.pause()

            self.assertTrue(warning.display)
            self.assertEqual(warning.styles.margin, progress.styles.margin)
            self.assertNotEqual(warning._scope.warning if warning._scope else None, first_geometry)
            self.assertIn('second-tab heavy rain warning', self._details_text(screen.alert_details_sidebar))


if __name__ == '__main__':
    unittest.main()
