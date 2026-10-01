"""Country-view location map geometry, rendering, and widget checks."""

from __future__ import annotations

import asyncio
import unittest

from rich.style import Style
from textual.app import App, ComposeResult

from wevva.location_metadata import LocationMetadata
from wevva.screens.weather_screen import WeatherScreen
from wevva.widgets.location_map import (
    LocationMap,
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

        self.assertIn('✦ Munich', rendered.plain)
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

        self.assertEqual(rendered.plain.count('•'), 2)
        self.assertIn('Berlin', rendered.plain)
        self.assertIn('Frankfurt', rendered.plain)
        self.assertNotIn('Hamburg', rendered.plain)


class _LocationMapApp(App):
    def compose(self) -> ComposeResult:
        yield LocationMap()


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

            self.assertTrue(widget.display)
            self.assertEqual(widget.border_title, 'Location Map — United Kingdom')
            self.assertGreaterEqual(widget.content_size.height, 12)
            self.assertLessEqual(widget.content_size.height, 26)
            self.assertIn('✦ London', widget.render().plain)
            self.assertEqual(widget.render().plain.count('London'), 1)

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

            self.assertIn('Berlin 61°F', widget.render().plain)

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

            rendered = widget.render()
            location_offset = rendered.plain.index('Munich')
            marker_offset = rendered.plain.index('✦')
            gap_offset = marker_offset + 1
            temperature_offset = rendered.plain.index('18°C')
            location_span = next(
                span
                for span in rendered.spans
                if span.start <= location_offset < span.end
            )
            marker_span = next(
                span
                for span in rendered.spans
                if span.start <= marker_offset < span.end
            )
            gap_span = next(
                span
                for span in rendered.spans
                if span.start <= gap_offset < span.end
            )
            temperature_span = next(
                span
                for span in rendered.spans
                if span.start <= temperature_offset < span.end
            )
            resolved = Style.parse(str(location_span.style))
            self.assertTrue(resolved.bold)
            self.assertIsNotNone(resolved.color)
            self.assertIsNotNone(resolved.bgcolor)
            self.assertIn('✦ Munich 18°C', rendered.plain)
            self.assertEqual(marker_span.style, location_span.style)
            self.assertEqual(gap_span.style, location_span.style)
            self.assertEqual(temperature_span.style, location_span.style)


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

            self.assertIn('✦ Munich', screen.location_map.render().plain)
            self.assertNotIn('°C', screen.location_map.render().plain)
            release.set()
            await pilot.pause()
            await pilot.pause()

            self.assertEqual(requested, [screen.location_map.city_coordinates])
            self.assertIn('16°C', screen.location_map.render().plain)


if __name__ == '__main__':
    unittest.main()
