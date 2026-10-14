"""Checks for canonical geocoding-result conversion."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from wevva.api import geocode
from wevva.cli import _resolve_first_location
from wevva.location_metadata import LocationMetadata, location_metadata_from_place
from wevva.widgets.search_results import SearchResultsList


COMPLETE_PLACE = {
    'latitude': 52,
    'longitude': 13.405,
    'elevation': 34.8,
    'name': 'Berlin',
    'admin': 'Berlin',
    'country': 'Germany',
    'country_code': 'DE',
    'tz_identifier': 'Europe/Berlin',
}


class LocationMetadataConversionTests(unittest.TestCase):
    def test_complete_normalized_place_retains_all_location_fields(self) -> None:
        self.assertEqual(
            location_metadata_from_place(COMPLETE_PLACE),
            LocationMetadata(
                latitude=52.0,
                longitude=13.405,
                elevation=34,
                name='Berlin',
                admin='Berlin',
                country='Germany',
                country_code='DE',
                timezone='Europe/Berlin',
            ),
        )

    def test_incomplete_place_uses_empty_optional_metadata(self) -> None:
        self.assertEqual(
            location_metadata_from_place(
                {
                    'latitude': 'invalid',
                    'longitude': None,
                    'elevation': False,
                    'name': None,
                }
            ),
            LocationMetadata(),
        )

    def test_cli_and_search_widget_use_the_canonical_conversion(self) -> None:
        expected = location_metadata_from_place(COMPLETE_PLACE)
        with patch('wevva.cli._lookup_places', return_value=[COMPLETE_PLACE]):
            cli_location, raw_place = _resolve_first_location('Berlin')

        results = SearchResultsList()
        results._place_cache['berlin'] = COMPLETE_PLACE

        self.assertEqual(cli_location, expected)
        self.assertIs(raw_place, COMPLETE_PLACE)
        self.assertEqual(results.get_selected_place('berlin'), expected)


class PublicGeocodeConversionTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_geocode_uses_the_canonical_conversion(self) -> None:
        with patch(
            'wevva.api.search_places',
            new=AsyncMock(return_value=[COMPLETE_PLACE]),
        ):
            locations = await geocode('Berlin')

        self.assertEqual(locations, [location_metadata_from_place(COMPLETE_PLACE)])


if __name__ == '__main__':
    unittest.main()
