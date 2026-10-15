"""Structural regression checks for the Weather screen's hot paths."""

from __future__ import annotations

import unittest
from contextlib import ExitStack
from unittest.mock import AsyncMock, Mock, patch

from textual.app import App

from tests.weather_fixtures import chicago_location, weather_update
from wevva.messages import DaySelected, HourHighlighted
from wevva.screens.weather_screen import WeatherScreen
from wevva.widgets.daily_forecast import DailyForecast


class _WeatherApp(App):
    def __init__(self, loader: AsyncMock) -> None:
        super().__init__()
        self.location = chicago_location()
        self.forecast_metadata = None
        self.saved_locations = []
        self.emoji_enabled = False
        self.temperature_unit = 'celsius'
        self.weather_update_count = 0
        self.weather_screen = WeatherScreen(city_temperature_loader=loader)

    def on_mount(self) -> None:
        self.push_screen(self.weather_screen)

    async def on_weather_updated(self, _event) -> None:
        self.weather_update_count += 1


async def _settle(pilot, cycles: int = 5) -> None:
    for _ in range(cycles):
        await pilot.pause(0)


class WeatherScreenPerformanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_weather_message_reaches_each_child_and_map_loader_once(self) -> None:
        loader = AsyncMock(return_value={})
        app = _WeatherApp(loader)

        async with app.run_test(size=(140, 45)) as pilot:
            await _settle(pilot)
            screen = app.weather_screen
            children = (
                screen.context_bar,
                screen.current_weather,
                screen.hourly_forecast,
                screen.weather_summary,
                screen.query_one(DailyForecast),
            )
            with ExitStack() as stack:
                handlers = [
                    stack.enter_context(
                        patch.object(
                            child,
                            'on_weather_updated',
                            new=AsyncMock(wraps=child.on_weather_updated),
                        )
                    )
                    for child in children
                ]
                screen.post_message(weather_update(with_warnings=True))
                await _settle(pilot, 8)
                if screen._location_map_task is not None:
                    await screen._location_map_task

            for handler in handlers:
                handler.assert_awaited_once()
            loader.assert_awaited_once()
            self.assertEqual(screen._location_map_generation, 1)
            self.assertEqual(app.weather_update_count, 1)

    async def test_unchanged_layout_budget_does_not_reapply_child_layouts(self) -> None:
        loader = AsyncMock(return_value={})
        app = _WeatherApp(loader)

        async with app.run_test(size=(140, 45)) as pilot:
            screen = app.weather_screen
            await screen.on_weather_updated(weather_update(with_warnings=True))
            await _settle(pilot, 8)
            self.assertIsNotNone(screen._layout_budget)

            targets = (
                (screen.current_weather, 'set_layout'),
                (screen.hourly_forecast, 'set_layout'),
                (screen.query_one(DailyForecast), 'set_layout'),
                (screen.context_bar, 'set_layout'),
                (screen.location_map, 'set_layout_height'),
            )
            with ExitStack() as stack:
                setters = [
                    stack.enter_context(
                        patch.object(owner, name, new=Mock(wraps=getattr(owner, name)))
                    )
                    for owner, name in targets
                ]
                screen._apply_layout()
                screen._apply_layout()
                for setter in setters:
                    setter.assert_not_called()

                screen._layout_budget = None
                screen._apply_layout()
                for setter in setters:
                    setter.assert_called_once()

    async def test_identical_alert_completion_keeps_mounted_widgets(self) -> None:
        app = _WeatherApp(AsyncMock(return_value={}))
        update = weather_update(with_warnings=True)

        async with app.run_test(size=(140, 45)) as pilot:
            screen = app.weather_screen
            await screen.on_weather_updated(update)
            await _settle(pilot, 8)
            summary = screen.weather_alert_summary
            panel = screen.weather_alert_panel

            await screen.render_alert_panel(list(update.alerts))
            await _settle(pilot)

            self.assertIs(screen.weather_alert_summary, summary)
            self.assertIs(screen.weather_alert_panel, panel)

    async def test_selection_time_and_resize_do_not_reload_map_temperatures(self) -> None:
        loader = AsyncMock(return_value={})
        app = _WeatherApp(loader)

        async with app.run_test(size=(140, 45)) as pilot:
            screen = app.weather_screen
            await screen.on_weather_updated(weather_update(with_warnings=True))
            await _settle(pilot, 8)
            if screen._location_map_task is not None:
                await screen._location_map_task
            loader.assert_awaited_once()

            with patch(
                'wevva.widgets.location_map.build_location_map_geometry'
            ) as geometry_builder:
                await screen.on_hour_highlighted(HourHighlighted(4))
                screen.on_day_selected(DaySelected(1))
                screen._refresh_time_display()
                await pilot.resize_terminal(80, 24)
                await pilot.resize_terminal(180, 55)
                await _settle(pilot, 5)

            loader.assert_awaited_once()
            geometry_builder.assert_not_called()


if __name__ == '__main__':
    unittest.main()
