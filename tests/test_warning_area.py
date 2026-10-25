"""Focused selected-warning geographic-scope checks."""

from __future__ import annotations

from dataclasses import replace
from io import StringIO
import unittest

from rich.console import Console
from textual.app import App, ComposeResult
from textual.color import Color
from textual.containers import Container

from wevva.alerts import Alert
from wevva.location_metadata import LocationMetadata
from wevva.screens.weather_screen import WeatherScreen
from wevva.widgets.warning_area import (
    WarningAreaPalette,
    WarningAreaScope,
    build_warning_area_geometry,
    render_warning_area,
)
from wevva.widgets.weather_alerts import (
    WeatherAlertDetailsPanel,
    WeatherAlertDetailsSidebar,
    WeatherAlertSummary,
    WeatherAlertsModal,
    WeatherAlertsReader,
    alert_severity_color,
)
from wevva_warnings import TropicalSystem
from wevva_warnings.registry import get_source


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

        self.assertIn('•', rendered.plain)
        self.assertIn('Accra', rendered.plain)
        self.assertIn('• Accra', rendered.plain)
        label_offset = rendered.plain.index('Accra')
        self.assertTrue(
            any(
                span.start <= label_offset < span.end and 'bold' in str(span.style)
                for span in rendered.spans
            )
        )
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


class _WarningModalApp(App):
    def __init__(self, alerts: list[Alert], *, initial_index: int = 0) -> None:
        super().__init__()
        self.alerts = alerts
        self.initial_index = initial_index
        self.location = LocationMetadata(
            latitude=5.6037,
            longitude=-0.1870,
            name='Accra',
            country='Ghana',
            country_code='GH',
        )
        self.forecast_metadata = LocationMetadata(latitude=5.6037, longitude=-0.1870)

    def on_mount(self) -> None:
        self.push_screen(
            WeatherAlertsModal(self.alerts, initial_index=self.initial_index)
        )


class WarningAreaSidebarTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _details_text(sidebar: WeatherAlertDetailsSidebar) -> str:
        return sidebar.content._markdown

    async def test_cap_details_and_warning_scope_share_the_sidebar(self) -> None:
        app = _WarningSidebarApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            sidebar = app.query_one(WeatherAlertDetailsSidebar)
            details = app.query_one(WeatherAlertDetailsPanel)
            warning = app.query_one(WarningAreaScope)

            self.assertIs(details.parent, sidebar)
            self.assertIs(warning.parent, sidebar)
            self.assertEqual(list(sidebar.children), [details, warning])
            self.assertEqual(details.border_title, 'Alert Details')
            self.assertEqual(details.styles.border_top[0], 'round')

            sidebar.update_alert(_ghana_alert())
            await pilot.pause()
            self.assertTrue(warning.display)
            self.assertEqual(warning.region.y, details.region.y + details.region.height + 1)
            self.assertEqual(warning.styles.margin.top, 1)
            self.assertEqual(sidebar.styles.hatch[0], '╱')
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
            self.assertIn('• Accra', rendered.plain)

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

    async def test_switching_modal_alert_tabs_updates_scrolling_details(self) -> None:
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
            summary = screen.query_one(WeatherAlertSummary)
            summary.focus()
            await pilot.press('enter')
            await pilot.pause()
            self.assertIsInstance(app.screen, WeatherAlertsModal)
            reader = app.screen.query_one(WeatherAlertsReader)

            reader.tabs.active = 'alert-item-1'
            await pilot.pause()

            details = reader.details
            self.assertIn(
                'second-tab heavy rain warning',
                details.content._markdown,
            )


class WarningAreaModalTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _details_text(reader: WeatherAlertsReader) -> str:
        return reader.details.content._markdown

    async def test_modal_is_geometrically_centred_at_supported_sizes(self) -> None:
        for size in ((80, 24), (200, 60)):
            with self.subTest(size=size):
                app = _WarningModalApp([_ghana_alert()])
                async with app.run_test(size=size) as pilot:
                    for _ in range(3):
                        await pilot.pause()

                    dialog = app.screen.query_one('#weather-alert-modal', Container)
                    viewport = app.screen.region
                    left = dialog.region.x - viewport.x
                    right = viewport.width - left - dialog.region.width
                    top = dialog.region.y - viewport.y
                    bottom = viewport.height - top - dialog.region.height

                    self.assertLessEqual(abs(left - right), 1)
                    self.assertLessEqual(abs(top - bottom), 1)
                    self.assertEqual(dialog.border_title, '1 Severe Weather Alert')

    async def test_tabs_synchronize_document_map_frame_and_scroll(self) -> None:
        first = replace(
            _ghana_alert('first-modal'),
            severity='severe',
            description='\n\n'.join(
                f'Paragraph {index}: detailed warning guidance.'
                for index in range(30)
            ),
        )
        second = replace(
            _ghana_alert(
                'second-modal',
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
            ),
            severity='extreme',
        )
        without_geometry = replace(
            _ghana_alert('plain-modal'),
            severity='minor',
            geometry=None,
        )
        app = _WarningModalApp([first, second, without_geometry])

        async with app.run_test(size=(80, 24)) as pilot:
            for _ in range(3):
                await pilot.pause()

            dialog = app.screen.query_one('#weather-alert-modal', Container)
            reader = app.screen.query_one(WeatherAlertsReader)
            warning = reader.warning_area
            first_geometry = warning._scope.warning if warning._scope else None

            self.assertEqual(dialog.border_title, '3 Severe Weather Alerts')
            self.assertEqual(dialog.styles.border_title_align, 'center')
            self.assertTrue(dialog.styles.border_title_style.bold)
            self.assertTrue(warning.display)
            self.assertEqual(reader.details.region.height, warning.region.height)
            self.assertLessEqual(
                warning.region.x + warning.region.width,
                reader.presentation.region.x + reader.presentation.region.width,
            )
            first_color = alert_severity_color(app.theme_variables, first)
            assert first_color is not None
            self.assertEqual(dialog.styles.border_top[1], Color.parse(first_color))
            self.assertEqual(dialog.styles.border_title_color, Color.parse(first_color))

            reader.details.scroll_end(animate=False)
            await pilot.pause()
            self.assertGreater(reader.details.scroll_y, 0)

            reader.tabs.active = 'alert-item-1'
            await pilot.pause()

            self.assertEqual(reader.selected_index, 1)
            self.assertEqual(reader.details.scroll_y, 0)
            self.assertIn('second-modal heavy rain warning', self._details_text(reader))
            self.assertTrue(warning.display)
            self.assertNotEqual(
                warning._scope.warning if warning._scope else None,
                first_geometry,
            )
            second_color = alert_severity_color(app.theme_variables, second)
            assert second_color is not None
            self.assertEqual(dialog.styles.border_top[1], Color.parse(second_color))
            self.assertEqual(dialog.styles.border_title_color, Color.parse(second_color))

            reader.tabs.active = 'alert-item-2'
            await pilot.pause()

            self.assertEqual(reader.selected_index, 2)
            self.assertIn('plain-modal heavy rain warning', self._details_text(reader))
            self.assertFalse(warning.display)
            self.assertEqual(
                reader.details.region.width,
                reader.presentation.content_region.width,
            )


if __name__ == '__main__':
    unittest.main()
