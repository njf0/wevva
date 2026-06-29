"""Geocoding helper.

Looks up places using Open-Meteo and returns small dicts
with name, country, coordinates, timezone and admin strings.
Keeps network work out of the UI.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

import httpx

from wevva.constants import REQUEST_TIMEOUT_S, SEARCH_MAX_RESULTS
from wevva.utils.country_codes import get_country_name_by_alpha2


async def search_places(
    query: str,
    *,
    count: int = SEARCH_MAX_RESULTS,
    language: str = 'en',
    timeout: float = REQUEST_TIMEOUT_S,
) -> list[dict[str, Any]]:
    """Find places and return simple entries.

    Each entry includes:
    - name, admin, country, country_code
    - latitude, longitude, tz_identifier
    """
    q = query.strip()
    if len(q) < 1:
        return []

    async with httpx.AsyncClient() as client:
        qp = quote_plus(q)
        url = f'https://geocoding-api.open-meteo.com/v1/search?name={qp}&count={count}&language={language}&format=json'
        resp = await client.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        results = data.get('results', [])

    return normalize_places(results)


def normalize_places(results: Any) -> list[dict[str, Any]]:
    """Normalize raw geocoder results into common app shape."""
    if not isinstance(results, list):
        return []

    normalized: list[dict[str, Any]] = []  # build friendly entries
    for place in results:
        if not isinstance(place, dict):
            continue
        name = place.get('name', '')
        country_name = place.get('country', '')
        country_code = place.get('country_code', '')
        if not country_name:
            country_name = get_country_name_by_alpha2(country_code) or '?'
        lat = place.get('latitude')
        lon = place.get('longitude')
        elevation = place.get('elevation')
        tz_identifier = place.get('timezone', '')
        admin1 = place.get('admin1', '')
        admin2 = place.get('admin2', '')
        admin3 = place.get('admin3', '')
        admin4 = place.get('admin4', '')
        admin_parts = [a for a in [admin1, admin2, admin3, admin4] if a][:2][::-1]
        admin_str = ';'.join(admin_parts)

        if lat is None or lon is None:
            continue

        normalized.append(
            {
                'latitude': lat,
                'longitude': lon,
                'elevation': elevation,
                'name': name,
                'admin': admin_str,
                'country_code': country_code,
                'country': country_name,
                'tz_identifier': tz_identifier,
            }
        )

    return normalized
