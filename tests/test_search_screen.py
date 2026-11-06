"""Mounted lifecycle checks for startup and place search."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from tests.weather_fixtures import weather_update
from wevva.app import Wevva
from wevva.location_metadata import LocationMetadata
from wevva.messages import SearchQueryReady
from wevva.screens.dashboard_screen import DashboardScreen
from wevva.screens.search_screen import SearchScreen
from wevva.widgets.search_results import SearchResultsList


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
    async def test_search_dialog_stays_contained_with_many_results(self) -> None:
        app = Wevva()
        async with app.run_test(size=(80, 24)) as pilot:
            screen = app.screen
            self.assertIsInstance(screen, SearchScreen)
            places = [_place(f'Place {index}') for index in range(20)]
            places[-1]['country'] = 'France'
            places[-1]['country_code'] = 'FR'
            screen.dialog.show_results(places)
            screen.dialog.results.remove_class('hidden')
            await pilot.pause(0)

            self.assertEqual(screen.dialog.results.option_count, 20)
            self.assertTrue(screen.dialog.results.has_focus)
            filter_row = screen.dialog.query_one('#filter-row')
            self.assertFalse(filter_row.has_class('hidden'))
            self.assertEqual(screen.dialog.results.region.y - filter_row.region.bottom, 1)
            self.assertLessEqual(screen.dialog.region.bottom, 23)
            self.assertLessEqual(
                screen.dialog.results.region.bottom,
                screen.dialog.content_region.bottom,
            )

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

    async def test_cli_location_starts_in_dashboard_and_refreshes_once(self) -> None:
        app = Wevva(initial_location=replace(BERLIN))
        app.controller.fetch = AsyncMock(return_value=weather_update())
        app._schedule_saved_weather_refresh = Mock()
        app._schedule_alert_refresh = Mock()
        app._tropical_system_cache = (app._tropical_system_cache_clock(), ())

        async with app.run_test() as pilot:
            await pilot.pause(0)
            self.assertIsInstance(app.screen, DashboardScreen)
            self.assertIs(app.screen, app._dashboard_screen)
            self.assertIn(app.weather_screen, app.screen_stack)
            app.controller.fetch.assert_awaited_once_with(
                lat=BERLIN.latitude,
                lon=BERLIN.longitude,
                country_code=BERLIN.country_code,
            )

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

    async def test_coordinate_search_waits_for_enter_then_can_be_selected(self) -> None:
        query_returned = asyncio.Event()
        queries: list[str] = []

        async def search_fixture(query: str, **_kwargs) -> list[dict[str, object]]:
            queries.append(query)
            query_returned.set()
            return [_place('Edinburgh')]

        with (
            patch('wevva.screens.search_screen.search_places', new=search_fixture),
            patch('wevva.widgets.search_dialog.SEARCH_DEBOUNCE_S', new=0.01),
        ):
            app = Wevva()
            app.action_refresh = AsyncMock()
            async with app.run_test() as pilot:
                screen = app.screen
                self.assertIsInstance(screen, SearchScreen)

                screen.dialog.latitude_input.value = '55.9533'
                screen.dialog.longitude_input.value = '-3.1883'
                screen.dialog.longitude_input.focus()
                await pilot.pause(0.05)
                self.assertEqual(queries, [])

                await pilot.press('enter')
                await asyncio.wait_for(query_returned.wait(), timeout=1)
                await pilot.pause(0)
                self.assertEqual(queries, ['55.9533, -3.1883'])

                await pilot.press('enter')
                await pilot.pause(0)
                self.assertIs(app.screen, app.weather_screen)
                app.action_refresh.assert_awaited_once_with()

    async def test_coordinate_fields_validate_ranges_and_require_a_pair(self) -> None:
        app = Wevva()
        async with app.run_test() as pilot:
            screen = app.screen
            self.assertIsInstance(screen, SearchScreen)
            self.assertEqual(
                screen.dialog.latitude_input.region.y,
                screen.dialog.longitude_input.region.y,
            )
            self.assertLessEqual(
                screen.dialog.latitude_input.region.right,
                screen.dialog.longitude_input.region.x,
            )
            self.assertLess(
                screen.dialog.longitude_input.region.bottom,
                screen.dialog.query_one('#coordinate-preview').region.y + 1,
            )
            self.assertEqual(screen.dialog.border_title, 'Search location')
            self.assertEqual(str(screen.dialog.styles.border_title_align), 'center')
            self.assertTrue(screen.dialog.styles.border_title_style.bold)
            self.assertTrue(screen.dialog.styles.border_title_style.reverse)
            self.assertEqual(
                screen.dialog.query_one('#coordinate-hint').render().plain,
                'Decimal degrees',
            )
            coordinate_heading = screen.dialog.query_one('#coordinate-heading')
            self.assertEqual(str(coordinate_heading.styles.text_align), 'center')
            self.assertTrue(coordinate_heading.styles.text_style.dim)
            self.assertTrue(coordinate_heading.styles.text_style.italic)

            titled_controls = (
                (screen.dialog.search_input, 'Place name', 'Enter place name'),
                (screen.dialog.latitude_input, 'Latitude', '50.856'),
                (screen.dialog.longitude_input, 'Longitude', '−0.706'),
            )
            for control, title, placeholder in titled_controls:
                self.assertEqual(control.border_title, title)
                self.assertEqual(control.placeholder, placeholder)
                self.assertEqual(str(control.styles.border_title_align), 'left')
                self.assertTrue(control.styles.border_title_style.bold)
                self.assertTrue(control.styles.border_title_style.reverse)
                self.assertEqual(
                    control.styles.border.top[1],
                    control.styles.border_title_color,
                )

            self.assertEqual(screen.dialog.country_filter.border_title, 'Filter by country')
            self.assertEqual(str(screen.dialog.country_filter.styles.border_title_align), 'left')
            self.assertTrue(screen.dialog.country_filter.styles.border_title_style.bold)
            self.assertTrue(screen.dialog.country_filter.styles.border_title_style.reverse)
            self.assertEqual(screen.dialog.results.border_title, 'Results')
            self.assertEqual(str(screen.dialog.results.styles.border_title_align), 'left')
            self.assertTrue(screen.dialog.results.styles.border_title_style.bold)
            self.assertTrue(screen.dialog.results.styles.border_title_style.reverse)

            screen.dialog.latitude_input.value = '91'
            await pilot.pause(0)
            self.assertFalse(screen.dialog.latitude_input.is_valid)
            self.assertEqual(
                screen.dialog.query_one('#coordinate-preview').render().plain,
                '',
            )
            self.assertTrue(screen.dialog.results_section.has_class('hidden'))

            screen.dialog.longitude_input.value = 'not-a-number'
            await pilot.pause(0)
            self.assertFalse(screen.dialog.longitude_input.is_valid)
            validation_message = screen.dialog.query_one('#coordinate-preview').render().plain
            self.assertIn('Latitude must be between −90 and 90', validation_message)
            self.assertIn('Longitude must be between −180 and 180', validation_message)
            self.assertTrue(screen.dialog.results_section.has_class('hidden'))

            screen.dialog.latitude_input.value = '-90'
            screen.dialog.longitude_input.value = '180'
            await pilot.pause(0)
            self.assertTrue(screen.dialog.latitude_input.is_valid)
            self.assertTrue(screen.dialog.longitude_input.is_valid)
            self.assertEqual(
                screen.dialog.query_one('#coordinate-preview').render().plain,
                '90°S, 180°E',
            )
            self.assertTrue(screen.dialog.results_section.has_class('hidden'))

            screen.dialog.latitude_input.value = '50.856'
            screen.dialog.longitude_input.value = '0.706'
            await pilot.pause(0)
            self.assertEqual(
                screen.dialog.query_one('#coordinate-preview').render().plain,
                '50.856°N, 0.706°E',
            )

            screen.dialog.longitude_input.value = '-0.706'
            await pilot.pause(0)
            self.assertEqual(
                screen.dialog.query_one('#coordinate-preview').render().plain,
                '50.856°N, 0.706°W',
            )

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


class SearchResultsFormattingTests(unittest.TestCase):
    def test_unnamed_coordinate_result_has_no_empty_country_line(self) -> None:
        results = SearchResultsList()

        self.assertEqual(
            results._format_place_label(
                {
                    'name': 'No place name found',
                    'admin': '',
                    'country': '',
                    'latitude': 67.69,
                    'longitude': 0.999,
                }
            ),
            '[bold]No place name found[/]\n[dim italic]67.690°N, 0.999°E[/]',
        )


if __name__ == '__main__':
    unittest.main()
