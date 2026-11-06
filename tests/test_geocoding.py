"""Focused checks for place-name and coordinate geocoding."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

from wevva.services import geocoding


class CoordinateQueryTests(unittest.TestCase):
    def test_parses_comma_or_space_separated_decimal_coordinates(self) -> None:
        self.assertEqual(
            geocoding.parse_coordinate_query('55.9533, -3.1883'),
            (55.9533, -3.1883),
        )
        self.assertEqual(
            geocoding.parse_coordinate_query('55.9533 -3.1883'),
            (55.9533, -3.1883),
        )
        self.assertEqual(geocoding.parse_coordinate_query('0,0'), (0.0, 0.0))

    def test_rejects_names_incomplete_pairs_and_out_of_range_values(self) -> None:
        for query in ('Edinburgh', '55.9533,', '91, 0', '0, 181'):
            with self.subTest(query=query):
                self.assertIsNone(geocoding.parse_coordinate_query(query))


class GeocodingServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        geocoding._reverse_cache.clear()

    async def test_coordinate_search_reverse_geocodes_but_retains_exact_point(self) -> None:
        response = Mock()
        response.json.return_value = {
            'name': 'Edinburgh',
            'category': 'place',
            'type': 'city',
            'address': {
                'city': 'Edinburgh',
                'county': 'City of Edinburgh',
                'state': 'Scotland',
                'country': 'United Kingdom',
                'country_code': 'gb',
            },
        }
        client = AsyncMock()
        client.get.return_value = response
        client_context = Mock()
        client_context.__aenter__ = AsyncMock(return_value=client)
        client_context.__aexit__ = AsyncMock(return_value=None)

        with (
            patch('wevva.services.geocoding.httpx.AsyncClient', return_value=client_context) as constructor,
            patch('wevva.services.geocoding._limit_reverse_request_rate', new=AsyncMock()),
        ):
            places = await geocoding.search_places(
                '55.9533, -3.1883',
                language='en',
                timeout=2.5,
            )

        self.assertEqual(
            places,
            [
                {
                    'latitude': 55.9533,
                    'longitude': -3.1883,
                    'elevation': None,
                    'name': 'Edinburgh',
                    'admin': 'City of Edinburgh;Scotland',
                    'country_code': 'GB',
                    'country': 'United Kingdom',
                    'tz_identifier': '',
                    'attribution': '© OpenStreetMap contributors',
                }
            ],
        )
        self.assertIn('wevva/', constructor.call_args.kwargs['headers']['User-Agent'])
        client.get.assert_awaited_once_with(
            'https://nominatim.openstreetmap.org/reverse',
            params={
                'format': 'jsonv2',
                'lat': 55.9533,
                'lon': -3.1883,
                'zoom': 13,
                'addressdetails': 1,
                'layer': 'address',
                'accept-language': 'en',
            },
            timeout=2.5,
        )

    async def test_coordinate_search_remains_usable_when_reverse_lookup_fails(self) -> None:
        client = AsyncMock()
        client.get.side_effect = httpx.ConnectError('offline')
        client_context = Mock()
        client_context.__aenter__ = AsyncMock(return_value=client)
        client_context.__aexit__ = AsyncMock(return_value=None)

        with (
            patch('wevva.services.geocoding.httpx.AsyncClient', return_value=client_context),
            patch('wevva.services.geocoding._limit_reverse_request_rate', new=AsyncMock()),
        ):
            places = await geocoding.search_places('12.5, -45.25')

        self.assertEqual(places[0]['name'], 'No place name found')
        self.assertEqual(places[0]['latitude'], 12.5)
        self.assertEqual(places[0]['longitude'], -45.25)
        self.assertNotIn('attribution', places[0])

    async def test_coordinate_search_tries_broader_address_levels(self) -> None:
        no_result = Mock()
        no_result.json.return_value = {'error': 'Unable to geocode'}
        county_result = Mock()
        county_result.json.return_value = {
            'address': {
                'county': 'Shetland Islands',
                'state': 'Scotland',
                'country': 'United Kingdom',
                'country_code': 'gb',
            },
        }
        client = AsyncMock()
        client.get.side_effect = [no_result, no_result, county_result]
        client_context = Mock()
        client_context.__aenter__ = AsyncMock(return_value=client)
        client_context.__aexit__ = AsyncMock(return_value=None)
        rate_limit = AsyncMock()

        with (
            patch('wevva.services.geocoding.httpx.AsyncClient', return_value=client_context),
            patch('wevva.services.geocoding._limit_reverse_request_rate', new=rate_limit),
        ):
            place = await geocoding.reverse_geocode(67.69, 0.999)

        self.assertEqual(place['name'], 'Shetland Islands')
        self.assertEqual(place['latitude'], 67.69)
        self.assertEqual(place['longitude'], 0.999)
        self.assertEqual(
            [call.kwargs['params']['zoom'] for call in client.get.await_args_list],
            [13, 10, 8],
        )
        self.assertEqual(rate_limit.await_count, 3)

    async def test_coordinate_search_labels_a_point_when_all_levels_are_empty(self) -> None:
        no_result = Mock()
        no_result.json.return_value = {'error': 'Unable to geocode'}
        client = AsyncMock()
        client.get.return_value = no_result
        client_context = Mock()
        client_context.__aenter__ = AsyncMock(return_value=client)
        client_context.__aexit__ = AsyncMock(return_value=None)

        with (
            patch('wevva.services.geocoding.httpx.AsyncClient', return_value=client_context),
            patch('wevva.services.geocoding._limit_reverse_request_rate', new=AsyncMock()),
        ):
            place = await geocoding.reverse_geocode(67.69, 0.999)

        self.assertEqual(place['name'], 'No place name found')
        self.assertEqual(place['latitude'], 67.69)
        self.assertEqual(place['longitude'], 0.999)
        self.assertEqual(
            [call.kwargs['params']['zoom'] for call in client.get.await_args_list],
            [13, 10, 8, 5, 3],
        )

    def test_reverse_result_prefers_named_settlement_over_admin_city(self) -> None:
        place = geocoding._normalize_reverse_place(
            {
                'category': 'place',
                'type': 'village',
                'name': 'Pett Level',
                'address': {
                    'village': 'Pett Level',
                    'city': 'Rother',
                    'county': 'East Sussex',
                    'state': 'England',
                    'country': 'United Kingdom',
                    'country_code': 'gb',
                },
            },
            50.856,
            0.706,
        )

        self.assertIsNotNone(place)
        self.assertEqual(place['name'], 'Pett Level')
        self.assertEqual(place['admin'], 'East Sussex;England')

    async def test_named_search_still_uses_open_meteo(self) -> None:
        response = Mock()
        response.json.return_value = {
            'results': [
                {
                    'name': 'Edinburgh',
                    'country': 'United Kingdom',
                    'country_code': 'GB',
                    'latitude': 55.95,
                    'longitude': -3.19,
                    'timezone': 'Europe/London',
                }
            ]
        }
        client = AsyncMock()
        client.get.return_value = response
        client_context = Mock()
        client_context.__aenter__ = AsyncMock(return_value=client)
        client_context.__aexit__ = AsyncMock(return_value=None)

        with patch('wevva.services.geocoding.httpx.AsyncClient', return_value=client_context):
            places = await geocoding.search_places('Edinburgh', count=3, language='en')

        self.assertEqual(places[0]['name'], 'Edinburgh')
        client.get.assert_awaited_once_with(
            'https://geocoding-api.open-meteo.com/v1/search?name=Edinburgh&count=3&language=en&format=json',
            timeout=5.0,
        )


if __name__ == '__main__':
    unittest.main()
