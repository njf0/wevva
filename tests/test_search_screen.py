"""Mounted lifecycle checks for startup and place search."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from wevva.app import Wevva
from wevva.location_metadata import LocationMetadata
from wevva.messages import SearchQueryReady
from wevva.screens.search_screen import SearchScreen


BERLIN = LocationMetadata(
    name='Berlin',
    admin='Berlin',
    country='Germany',
    country_code='DE',
    latitude=52.52,
    longitude=13.405,
    timezone='Europe/Berlin',
)


def _place(name: str) -> dict[str, object]:
    return {
        'name': name,
        'country': 'Germany',
        'country_code': 'DE',
        'admin': name,
        'latitude': 52.52,
        'longitude': 13.405,
        'tz_identifier': 'Europe/Berlin',
    }


class SearchScreenLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_location_keyboard_selection_hands_off_once(self) -> None:
        app = Wevva()
        app.action_refresh = AsyncMock()

        async with app.run_test() as pilot:
            screen = app.screen
            self.assertIsInstance(screen, SearchScreen)

            screen.dialog.show_results([_place('Berlin')])
            screen.dialog.search_input.focus()
            await pilot.press('enter')
            await pilot.pause(0)

            self.assertIs(app.screen, app.weather_screen)
            self.assertEqual(app.location, BERLIN)
            app.action_refresh.assert_awaited_once_with()

    async def test_mouse_selection_hands_off_once(self) -> None:
        app = Wevva()
        app.action_refresh = AsyncMock()

        async with app.run_test() as pilot:
            screen = app.screen
            self.assertIsInstance(screen, SearchScreen)
            screen.dialog.show_results([_place('Berlin')])
            screen.dialog.results.remove_class('hidden')
            await pilot.pause(0)

            clicked = await pilot.click('#place-search-results', offset=(2, 1))
            self.assertTrue(clicked)
            await pilot.pause(0)

            self.assertIs(app.screen, app.weather_screen)
            self.assertEqual(app.location, BERLIN)
            app.action_refresh.assert_awaited_once_with()

    async def test_cli_location_starts_in_weather_and_refreshes_once(self) -> None:
        app = Wevva(initial_location=BERLIN)
        app.action_refresh = AsyncMock()

        async with app.run_test() as pilot:
            await pilot.pause(0)
            self.assertIs(app.screen, app.weather_screen)
            app.action_refresh.assert_awaited_once_with()

    async def test_new_query_cancels_obsolete_request_and_owns_results(self) -> None:
        first_started = asyncio.Event()
        first_cancelled = asyncio.Event()
        second_returned = asyncio.Event()
        queries: list[str] = []

        async def search_fixture(query: str, **_kwargs) -> list[dict[str, object]]:
            queries.append(query)
            if query == 'first':
                first_started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    first_cancelled.set()
                    return [_place('First')]
            second_returned.set()
            return [_place('Second')]

        with patch('wevva.screens.search_screen.search_places', new=search_fixture):
            app = Wevva()
            async with app.run_test() as pilot:
                screen = app.screen
                self.assertIsInstance(screen, SearchScreen)
                screen.post_message(SearchQueryReady('first'))
                await asyncio.wait_for(first_started.wait(), timeout=1)

                screen.post_message(SearchQueryReady('second'))
                await asyncio.wait_for(first_cancelled.wait(), timeout=1)
                await asyncio.wait_for(second_returned.wait(), timeout=1)
                await pilot.pause(0)

                self.assertEqual(queries, ['first', 'second'])
                self.assertEqual(
                    [place['name'] for place in screen.dialog.results._place_cache.values()],
                    ['Second'],
                )

    async def test_typing_replaces_the_pending_debounce_query(self) -> None:
        queries: list[str] = []

        async def search_fixture(query: str, **_kwargs) -> list[dict[str, object]]:
            queries.append(query)
            return [_place(query)]

        with (
            patch('wevva.screens.search_screen.search_places', new=search_fixture),
            patch('wevva.widgets.search_dialog.SEARCH_DEBOUNCE_S', new=0.01),
        ):
            app = Wevva()
            async with app.run_test() as pilot:
                screen = app.screen
                self.assertIsInstance(screen, SearchScreen)

                screen.dialog.search_input.value = 'Ber'
                await pilot.pause(0)
                screen.dialog.search_input.value = 'Berlin'
                await pilot.pause(0.05)

                self.assertEqual(queries, ['Berlin'])

    async def test_dismissing_search_cancels_active_request(self) -> None:
        request_started = asyncio.Event()
        request_cancelled = asyncio.Event()

        async def search_fixture(*_args, **_kwargs) -> list[dict[str, object]]:
            request_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                request_cancelled.set()
                raise

        with patch('wevva.screens.search_screen.search_places', new=search_fixture):
            app = Wevva()
            async with app.run_test() as pilot:
                screen = app.screen
                self.assertIsInstance(screen, SearchScreen)
                screen.post_message(SearchQueryReady('Berlin'))
                await asyncio.wait_for(request_started.wait(), timeout=1)

                screen.dismiss()
                await pilot.pause(0)

                await asyncio.wait_for(request_cancelled.wait(), timeout=1)


if __name__ == '__main__':
    unittest.main()
