"""Focused checks for the interactive full-world saved-location map."""

from __future__ import annotations

import unittest
from contextlib import ExitStack
from unittest.mock import AsyncMock, Mock, patch

from textual.app import App, ComposeResult

from wevva.app import Wevva
from wevva.config import location_key
from wevva.location_metadata import LocationMetadata
from wevva.messages import SavedLocationSelected
from wevva.screens.weather_screen import WeatherScreen
from wevva.screens.world_locations_screen import WorldLocationsScreen
from wevva.widgets.saved_locations import SavedLocationWeatherSummary
from wevva.widgets.world_locations_map import (
    WorldLocationLabel,
    WorldLocationsMap,
    _world_frame,
)


LONDON = LocationMetadata(
    name='London',
    country='United Kingdom',
    country_code='GB',
    latitude=51.5072,
    longitude=-0.1276,
)
NEW_YORK = LocationMetadata(
    name='New York',
    country='United States',
    country_code='US',
    latitude=40.7128,
    longitude=-74.0060,
)
TOKYO = LocationMetadata(
    name='Tokyo',
    country='Japan',
    country_code='JP',
    latitude=35.6762,
    longitude=139.6503,
)


class _WorldMapApp(App):
    def __init__(self) -> None:
        super().__init__()
        summaries = {
            location_key(LONDON): SavedLocationWeatherSummary(
                temperature=16,
                temperature_unit='°C',
            ),
            location_key(NEW_YORK): SavedLocationWeatherSummary(
                temperature=23,
                temperature_unit='°C',
            ),
            location_key(TOKYO): SavedLocationWeatherSummary(
                temperature=28,
                temperature_unit='°C',
            ),
        }
        self.world_map = WorldLocationsMap(
            [LONDON, NEW_YORK, TOKYO],
            summaries=summaries,
        )
        self.selected: list[LocationMetadata] = []

    def compose(self) -> ComposeResult:
        yield self.world_map

    def on_saved_location_selected(self, event: SavedLocationSelected) -> None:
        self.selected.append(event.location)


class WorldLocationsMapTests(unittest.IsolatedAsyncioTestCase):
    def test_world_frame_cache_is_bounded_by_size_and_style(self) -> None:
        _world_frame.cache_clear()
        try:
            first = _world_frame(80, 24, land_style='dim red')
            self.assertIs(first, _world_frame(80, 24, land_style='dim red'))
            self.assertIsNot(first, _world_frame(80, 24, land_style='dim blue'))
            for width in (90, 100, 110, 120):
                _world_frame(width, 24, land_style='dim red')
            for width in (90, 100, 110, 120):
                _world_frame(width, 24, land_style='dim red')

            cache = _world_frame.cache_info()
            self.assertEqual(cache.maxsize, 4)
            self.assertEqual(cache.currsize, 4)
            self.assertEqual(cache.hits, 5)
        finally:
            _world_frame.cache_clear()

    async def test_world_map_uses_native_location_widgets(self) -> None:
        app = _WorldMapApp()
        async with app.run_test(size=(80, 24)) as pilot:
            for _ in range(3):
                await pilot.pause()

            world_map = app.world_map
            labels = list(world_map.query(WorldLocationLabel))
            self.assertEqual(world_map.styles.border_top[0], 'round')
            self.assertEqual(len(labels), 3)
            self.assertTrue(
                all(
                    label.label_text.startswith('• ')
                    or label.label_text.endswith(' •')
                    for label in labels
                )
            )
            self.assertIn('London 16°C', labels[0].label_text)
            tokyo = next(label for label in labels if label.location.name == 'Tokyo')
            self.assertEqual(tokyo.label_text, 'Tokyo 28°C •')
            self.assertTrue(all(label.styles.position == 'absolute' for label in labels))
            self.assertEqual(len(world_map.placements), 3)
            self.assertTrue(
                any(placement.marker_on_right for placement in world_map.placements)
            )

            occupied = set()
            frame = _world_frame(
                world_map.content_size.width,
                world_map.content_size.height,
                land_style=None,
            )
            locations = {
                location_key(location): location
                for location in (LONDON, NEW_YORK, TOKYO)
            }
            for placement in world_map.placements:
                cells = {
                    (placement.column + offset, placement.row)
                    for offset in range(placement.width)
                }
                self.assertFalse(cells & occupied)
                occupied.update(cells)
                location = locations[placement.key]
                anchor = frame.canvas.cell_position(
                    frame.canvas.viewport.project(location.longitude, location.latitude)
                )
                marker_column = (
                    placement.column + placement.width - 1
                    if placement.marker_on_right
                    else placement.column
                )
                self.assertEqual((marker_column, placement.row), anchor)

            backdrop = world_map.query_one('#world-locations-backdrop')
            rendered = backdrop.render()
            self.assertTrue(
                any(
                    0x2801 <= ord(character) <= 0x28FF
                    for character in rendered.plain
                )
            )

    async def test_focus_inverts_label_and_enter_selects_location(self) -> None:
        app = _WorldMapApp()
        async with app.run_test(size=(100, 30)) as pilot:
            for _ in range(3):
                await pilot.pause()

            label = list(app.world_map.query(WorldLocationLabel))[0]
            label.focus()
            await pilot.pause()

            self.assertIn('reverse', str(label.styles.text_style))
            await pilot.press('enter')
            await pilot.pause()
            self.assertEqual(app.selected, [label.location])

    async def test_summary_burst_reuses_backdrop_and_label_widgets(self) -> None:
        _world_frame.cache_clear()
        app = _WorldMapApp()
        async with app.run_test(size=(100, 30)) as pilot:
            for _ in range(3):
                await pilot.pause()

            world_map = app.world_map
            labels = list(world_map.query(WorldLocationLabel))
            labels[0].focus()
            cache_before = _world_frame.cache_info()
            backdrop = world_map.query_one('#world-locations-backdrop')

            with ExitStack() as stack:
                backdrop_update = stack.enter_context(
                    patch.object(
                        backdrop,
                        'update',
                        new=Mock(wraps=backdrop.update),
                    )
                )
                label_updates = [
                    stack.enter_context(
                        patch.object(
                            label,
                            'update',
                            new=Mock(wraps=label.update),
                        )
                    )
                    for label in labels
                ]
                world_resource = stack.enter_context(
                    patch('wevva.widgets.world_locations_map.world_map_unit_polygons')
                )
                reflow = stack.enter_context(
                    patch.object(
                        world_map,
                        '_reflow',
                        new=Mock(wraps=world_map._reflow),
                    )
                )
                for index, location in enumerate((LONDON, NEW_YORK, TOKYO)):
                    world_map.update_weather_summary(
                        location,
                        SavedLocationWeatherSummary(
                            temperature=10 + index,
                            temperature_unit='°C',
                        ),
                    )
                for _ in range(3):
                    await pilot.pause()

            cache_after = _world_frame.cache_info()
            self.assertEqual(cache_after.misses, cache_before.misses)
            self.assertEqual(cache_after.hits, cache_before.hits)
            backdrop_update.assert_not_called()
            world_resource.assert_not_called()
            reflow.assert_not_called()
            for update in label_updates:
                update.assert_called_once()
            self.assertEqual(list(world_map.query(WorldLocationLabel)), labels)
            self.assertIs(app.focused, labels[0])

            with patch.object(
                world_map,
                '_reflow',
                wraps=world_map._reflow,
            ) as reflow:
                world_map.update_weather_summary(
                    LONDON,
                    SavedLocationWeatherSummary(
                        temperature=100,
                        temperature_unit='°C',
                    ),
                )
                for _ in range(3):
                    await pilot.pause()
                reflow.assert_called_once_with()

    async def test_summary_for_location_outside_map_is_ignored(self) -> None:
        app = _WorldMapApp()
        outside = LocationMetadata(
            name='Berlin',
            country='Germany',
            country_code='DE',
            latitude=52.52,
            longitude=13.405,
        )
        async with app.run_test(size=(100, 30)) as pilot:
            for _ in range(3):
                await pilot.pause()

            world_map = app.world_map
            with patch.object(
                world_map,
                '_reflow',
                wraps=world_map._reflow,
            ) as reflow:
                world_map.update_weather_summary(
                    outside,
                    SavedLocationWeatherSummary(
                        temperature=14,
                        temperature_unit='°C',
                    ),
                )
                for _ in range(2):
                    await pilot.pause()

            self.assertNotIn(location_key(outside), world_map._summaries)
            reflow.assert_not_called()

    async def test_resize_repositions_existing_native_widgets(self) -> None:
        app = _WorldMapApp()
        async with app.run_test(size=(80, 24)) as pilot:
            for _ in range(3):
                await pilot.pause()

            labels = list(app.world_map.query(WorldLocationLabel))
            labels[0].focus()
            initial = {
                placement.key: (placement.column, placement.row)
                for placement in app.world_map.placements
            }

            with patch(
                'wevva.widgets.world_locations_map.world_map_unit_polygons'
            ) as world_resource:
                await pilot.resize_terminal(140, 40)
                for _ in range(3):
                    await pilot.pause()

            resized_labels = list(app.world_map.query(WorldLocationLabel))
            resized = {
                placement.key: (placement.column, placement.row)
                for placement in app.world_map.placements
            }
            self.assertEqual(resized_labels, labels)
            self.assertIs(app.focused, labels[0])
            self.assertEqual(len(resized), 3)
            self.assertNotEqual(resized, initial)
            world_resource.assert_not_called()

    async def test_click_uses_the_same_saved_location_message(self) -> None:
        app = _WorldMapApp()
        async with app.run_test(size=(100, 30)) as pilot:
            for _ in range(3):
                await pilot.pause()

            label = list(app.world_map.query(WorldLocationLabel))[1]
            self.assertTrue(await pilot.click(label))
            await pilot.pause()
            self.assertEqual(app.selected, [label.location])


class WorldLocationsScreenTests(unittest.IsolatedAsyncioTestCase):
    async def test_weather_binding_opens_padded_world_screen_and_selection_returns(self) -> None:
        app = Wevva(
            initial_location=LONDON,
            saved_locations=[LONDON, NEW_YORK, TOKYO],
            start_on_dashboard=False,
        )
        app.action_refresh = AsyncMock()

        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            weather_screen = app.screen
            self.assertIsInstance(weather_screen, WeatherScreen)
            for location, temperature in (
                (LONDON, 16),
                (NEW_YORK, 23),
                (TOKYO, 28),
            ):
                app._update_saved_location_weather(
                    location,
                    SavedLocationWeatherSummary(
                        temperature=temperature,
                        temperature_unit='°C',
                    ),
                )

            await pilot.press('m')
            for _ in range(3):
                await pilot.pause()

            self.assertIsInstance(app.screen, WorldLocationsScreen)
            world_screen = app.screen
            stage = world_screen.query_one('#world-locations-stage')
            self.assertEqual(stage.styles.padding.top, 1)
            self.assertEqual(stage.styles.padding.right, 2)
            self.assertEqual(stage.styles.padding.bottom, 1)
            self.assertEqual(stage.styles.padding.left, 2)
            self.assertEqual(world_screen.world_map.styles.border_top[0], 'round')
            self.assertEqual(world_screen.world_map.region.x, 2)
            self.assertEqual(world_screen.world_map.region.width, 116)

            labels = list(world_screen.world_map.query(WorldLocationLabel))
            self.assertEqual(len(labels), 3)
            self.assertEqual(app.focused.location, LONDON)
            first_focused = app.focused
            await pilot.press('right')
            await pilot.pause()
            self.assertIsNot(app.focused, first_focused)

            tokyo_label = next(
                label
                for label in labels
                if location_key(label.location) == location_key(TOKYO)
            )
            self.assertTrue(await pilot.click(tokyo_label))
            for _ in range(2):
                await pilot.pause()

            self.assertIs(app.screen, weather_screen)
            self.assertEqual(app.location, TOKYO)
            self.assertEqual(app.action_refresh.await_count, 2)

    async def test_world_screen_weather_binding_returns_without_selecting(self) -> None:
        app = Wevva(
            initial_location=LONDON,
            saved_locations=[LONDON, NEW_YORK],
            start_on_dashboard=False,
        )
        app.action_refresh = AsyncMock()

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            weather_screen = app.screen
            await pilot.press('m')
            await pilot.pause()
            self.assertIsInstance(app.screen, WorldLocationsScreen)

            await pilot.press('w')
            await pilot.pause()
            self.assertIs(app.screen, weather_screen)
            self.assertEqual(app.action_refresh.await_count, 1)


if __name__ == '__main__':
    unittest.main()
