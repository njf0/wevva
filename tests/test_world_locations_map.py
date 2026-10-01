"""Focused checks for the interactive full-world saved-location map."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from textual.app import App, ComposeResult

from wevva.app import Wevva
from wevva.config import location_key
from wevva.location_metadata import LocationMetadata
from wevva.messages import SavedLocationSelected
from wevva.screens.weather_screen import WeatherScreen
from wevva.screens.world_locations_screen import WorldLocationsScreen
from wevva.widgets.saved_locations import SavedLocationWeatherSummary
from wevva.widgets.world_locations_map import WorldLocationLabel, WorldLocationsMap


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
            for placement in world_map.placements:
                cells = {
                    (placement.column + offset, placement.row)
                    for offset in range(placement.width)
                }
                self.assertFalse(cells & occupied)
                occupied.update(cells)

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
                weather_screen.update_saved_location_weather(
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
