"""Country-view location map geometry, rendering, and widget checks."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock

from textual.app import App, ComposeResult

from wevva.app import Wevva
from wevva.location_metadata import LocationMetadata
from wevva.messages import PlaceSelected
from wevva.screens.weather_screen import WeatherScreen
from wevva.widgets.geographic_scope import GeographicCanvas
from wevva.widgets.location_map import (
    LocationMap,
    LocationMapLabel,
    LocationMapPalette,
    build_location_map_geometry,
    render_location_map,
)


class LocationMapGeometryTests(unittest.TestCase):
    def test_country_view_contains_ranked_cities_and_current_location(self) -> None:
        scope = build_location_map_geometry(
            latitude=48.137,
            longitude=11.575,
            location_name='Munich',
            country_code='DE',
        )

        assert scope is not None
        self.assertTrue(scope.land)
        self.assertEqual(scope.location_name, 'Munich')
        self.assertEqual(
            [place.name for place, _point in scope.places],
            ['Berlin', 'Frankfurt', 'Hamburg', 'Dresden'],
        )
        self.assertTrue(scope.viewport.min_x <= scope.location.x <= scope.viewport.max_x)
        self.assertTrue(scope.viewport.min_y <= scope.location.y <= scope.viewport.max_y)

    def test_hawaii_view_excludes_mainland_us_cities(self) -> None:
        scope = build_location_map_geometry(
            latitude=21.3069,
            longitude=-157.8583,
            location_name='Honolulu',
            country_code='US',
        )

        assert scope is not None
        place_names = {place.name for place, _point in scope.places}
        self.assertEqual(place_names, {'Hilo'})
        self.assertLess(scope.viewport.width, 10.0)

    def test_city_matching_current_location_name_is_removed_even_when_positions_differ(self) -> None:
        scope = build_location_map_geometry(
            latitude=19.7074,
            longitude=-155.0816,
            location_name='  HILO ',
            country_code='US',
        )

        assert scope is not None
        self.assertNotIn('Hilo', {place.name for place, _point in scope.places})

    def test_unknown_country_has_a_clean_hidden_fallback(self) -> None:
        self.assertIsNone(
            build_location_map_geometry(
                latitude=0.0,
                longitude=0.0,
                location_name='Null Island',
                country_code='XX',
            )
        )

    def test_renderer_distinguishes_location_from_city_labels(self) -> None:
        scope = build_location_map_geometry(
            latitude=48.137,
            longitude=11.575,
            location_name='Munich',
            country_code='DE',
        )
        assert scope is not None
        berlin = next(
            (place.latitude, place.longitude)
            for place, _point in scope.places
            if place.name == 'Berlin'
        )

        rendered = render_location_map(
            scope,
            width=96,
            height=24,
            palette=LocationMapPalette(
                land='blue',
                place='yellow',
                location='magenta',
            ),
            temperature_labels={
                berlin: ('16°C', 'bold red'),
            },
        )

        self.assertIn('• Munich', rendered.plain)
        self.assertIn('• Berlin 16°C', rendered.plain)
        self.assertTrue(any(span.style == 'magenta' for span in rendered.spans))
        self.assertTrue(any(span.style == 'bold red' for span in rendered.spans))
        self.assertTrue(any(0x2801 <= ord(character) <= 0x28FF for character in rendered.plain))

    def test_renderer_can_limit_ranked_city_labels(self) -> None:
        scope = build_location_map_geometry(
            latitude=48.137,
            longitude=11.575,
            location_name='Munich',
            country_code='DE',
        )
        assert scope is not None

        rendered = render_location_map(
            scope,
            width=96,
            height=24,
            max_place_labels=2,
        )

        self.assertEqual(rendered.plain.count('•'), 3)
        self.assertIn('Berlin', rendered.plain)
        self.assertIn('Frankfurt', rendered.plain)
        self.assertNotIn('Hamburg', rendered.plain)


class _LocationMapApp(App):
    def __init__(self) -> None:
        super().__init__()
        self.selected: list[LocationMetadata] = []

    def compose(self) -> ComposeResult:
        yield LocationMap()

    def on_place_selected(self, event: PlaceSelected) -> None:
        self.selected.append(event.location)


class LocationMapWidgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_widget_sizes_to_country_and_titles_itself(self) -> None:
        app = _LocationMapApp()
        async with app.run_test(size=(110, 40)) as pilot:
            widget = app.query_one(LocationMap)
            widget.update_location(
                LocationMetadata(
                    latitude=51.5072,
                    longitude=-0.1276,
                    name='London',
                    country='United Kingdom',
                    country_code='GB',
                )
            )
            await pilot.pause()
            await pilot.pause()

            self.assertTrue(widget.display)
            self.assertEqual(widget.border_title, 'Location Map — United Kingdom')
            self.assertGreaterEqual(widget.content_size.height, 12)
            self.assertLessEqual(widget.content_size.height, 26)
            labels = list(widget.query(LocationMapLabel))
            current = next(label for label in labels if label.current)
            self.assertEqual(current.label_text, '• London')
            self.assertIn('reverse', str(current.styles.text_style))
            self.assertTrue(any(0x2801 <= ord(char) <= 0x28FF for char in widget.render().plain))

    async def test_widget_adds_temperature_and_uses_requested_unit(self) -> None:
        app = _LocationMapApp()
        async with app.run_test(size=(110, 40)) as pilot:
            widget = app.query_one(LocationMap)
            widget.update_location(
                LocationMetadata(
                    latitude=48.137,
                    longitude=11.575,
                    name='Munich',
                    country='Germany',
                    country_code='DE',
                )
            )
            scope = build_location_map_geometry(
                latitude=48.137,
                longitude=11.575,
                location_name='Munich',
                country_code='DE',
            )
            assert scope is not None
            berlin = next(
                (place.latitude, place.longitude)
                for place, _point in scope.places
                if place.name == 'Berlin'
            )
            widget.update_temperatures({berlin: 61.2}, temperature_unit='fahrenheit')
            await pilot.pause()
            await pilot.pause()

            berlin_label = next(
                label
                for label in widget.query(LocationMapLabel)
                if label.location.name == 'Berlin'
            )
            self.assertEqual(berlin_label.label_text, '• Berlin 61°F')

    async def test_current_location_label_uses_temperature_as_background(self) -> None:
        app = _LocationMapApp()
        async with app.run_test(size=(110, 40)) as pilot:
            widget = app.query_one(LocationMap)
            widget.update_location(
                LocationMetadata(
                    latitude=48.137,
                    longitude=11.575,
                    name='Munich',
                    country='Germany',
                    country_code='DE',
                ),
                current_temperature=18.0,
                temperature_unit='celsius',
            )
            await pilot.pause()
            await pilot.pause()

            current = next(
                label for label in widget.query(LocationMapLabel) if label.current
            )
            self.assertEqual(current.label_text, '• Munich 18°C')
            self.assertIn('bold', str(current.styles.text_style))
            self.assertIn('reverse', str(current.styles.text_style))
            self.assertIsNotNone(current.styles.color)

    async def test_nearby_city_is_natively_clickable_and_focus_inverts_it(self) -> None:
        app = _LocationMapApp()
        async with app.run_test(size=(110, 40)) as pilot:
            widget = app.query_one(LocationMap)
            widget.update_location(
                LocationMetadata(
                    latitude=48.137,
                    longitude=11.575,
                    name='Munich',
                    country='Germany',
                    country_code='DE',
                )
            )
            for _ in range(3):
                await pilot.pause()

            berlin = next(
                label
                for label in widget.query(LocationMapLabel)
                if label.location.name == 'Berlin'
            )
            berlin.focus()
            await pilot.pause()
            self.assertIn('reverse', str(berlin.styles.text_style))
            self.assertTrue(await pilot.click(berlin))
            await pilot.pause()

            self.assertEqual([location.name for location in app.selected], ['Berlin'])
            self.assertEqual(app.selected[0].country, 'Germany')
            self.assertEqual(app.selected[0].country_code, 'DE')

    async def test_narrow_map_can_place_city_text_left_of_its_marker(self) -> None:
        app = _LocationMapApp()
        async with app.run_test(size=(40, 30)) as pilot:
            widget = app.query_one(LocationMap)
            widget.styles.width = 37
            widget.update_location(
                LocationMetadata(
                    latitude=48.137,
                    longitude=11.575,
                    name='Munich',
                    country='Germany',
                    country_code='DE',
                )
            )
            for _ in range(3):
                await pilot.pause()

            dresden = next(
                label
                for label in widget.query(LocationMapLabel)
                if label.location.name == 'Dresden'
            )
            self.assertEqual(dresden.label_text, 'Dresden •')
            self.assertTrue(
                any(placement.marker_on_right for placement in widget.placements)
            )

    async def test_neighboring_city_labels_preserve_their_projected_rows(self) -> None:
        app = _LocationMapApp()
        async with app.run_test(size=(48, 30)) as pilot:
            widget = app.query_one(LocationMap)
            widget.styles.width = 46
            widget.set_layout_height(24)
            widget.update_location(
                LocationMetadata(
                    latitude=50.86,
                    longitude=-0.71,
                    name='Boxgrove',
                    country='United Kingdom',
                    country_code='GB',
                ),
                current_temperature=14.0,
            )
            widget.update_temperatures(
                {coordinates: 15.0 for coordinates in widget.city_coordinates},
                temperature_unit='celsius',
            )
            for _ in range(3):
                await pilot.pause()

            scope = build_location_map_geometry(
                latitude=50.86,
                longitude=-0.71,
                location_name='Boxgrove',
                country_code='GB',
            )
            assert scope is not None
            canvas = GeographicCanvas(
                widget.content_size.width,
                widget.content_size.height,
                scope.viewport,
            )
            placements = {placement.key: placement for placement in widget.placements}
            labels = {
                label.location.name: label
                for label in widget.query(LocationMapLabel)
            }

            actual_markers = {}
            for name in ('Glasgow', 'Edinburgh'):
                label = labels[name]
                key = f'{label.location.latitude:.6f},{label.location.longitude:.6f}'
                placement = placements[key]
                marker_column = (
                    placement.column + placement.width - 1
                    if placement.marker_on_right
                    else placement.column
                )
                actual_markers[name] = (marker_column, placement.row)
                point = next(
                    point for place, point in scope.places if place.name == name
                )
                self.assertEqual(actual_markers[name], canvas.cell_position(point))

            self.assertEqual(
                actual_markers['Glasgow'][1],
                actual_markers['Edinburgh'][1],
            )
            self.assertEqual(labels['Glasgow'].label_text, 'Glasgow 15°C •')
            self.assertEqual(labels['Edinburgh'].label_text, '• Edinburgh 15°C')

    async def test_map_place_selection_reuses_active_weather_screen(self) -> None:
        munich = LocationMetadata(
            latitude=48.137,
            longitude=11.575,
            name='Munich',
            country='Germany',
            country_code='DE',
        )
        berlin = LocationMetadata(
            latitude=52.52,
            longitude=13.405,
            name='Berlin',
            country='Germany',
            country_code='DE',
        )
        app = Wevva(initial_location=munich)
        app.action_refresh = AsyncMock()

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            weather_screen = app.screen
            await app.on_place_selected(PlaceSelected(location=berlin))
            await pilot.pause()

            self.assertIs(app.screen, weather_screen)
            self.assertEqual(app.location, berlin)
            self.assertEqual(app.action_refresh.await_count, 2)


class _WeatherMapApp(App):
    def __init__(self, loader) -> None:
        super().__init__()
        self.location = LocationMetadata(
            latitude=48.137,
            longitude=11.575,
            name='Munich',
            country='Germany',
            country_code='DE',
        )
        self.saved_locations = []
        self.emoji_enabled = False
        self.temperature_unit = 'celsius'
        self.weather_screen = WeatherScreen(city_temperature_loader=loader)

    def on_mount(self) -> None:
        self.push_screen(self.weather_screen)


class LocationMapLoadingTests(unittest.IsolatedAsyncioTestCase):
    async def test_weather_screen_enriches_map_without_blocking_base_geometry(self) -> None:
        requested = []
        started = asyncio.Event()
        release = asyncio.Event()

        async def loader(coordinates, temperature_unit):
            requested.append(tuple(coordinates))
            self.assertEqual(temperature_unit, 'celsius')
            started.set()
            await release.wait()
            return {coordinates[0]: 15.6}

        app = _WeatherMapApp(loader)
        async with app.run_test(size=(120, 50)) as pilot:
            screen = app.screen
            assert isinstance(screen, WeatherScreen)
            screen.main_panel.display = True
            await pilot.pause()
            screen._refresh_location_map()
            await started.wait()
            await pilot.pause()

            labels = list(screen.location_map.query(LocationMapLabel))
            self.assertIn('• Munich', {label.label_text for label in labels})
            self.assertFalse(any('°C' in label.label_text for label in labels))
            release.set()
            await pilot.pause()
            await pilot.pause()

            self.assertEqual(requested, [screen.location_map.city_coordinates])
            self.assertTrue(
                any(
                    '16°C' in label.label_text
                    for label in screen.location_map.query(LocationMapLabel)
                )
            )


if __name__ == '__main__':
    unittest.main()
