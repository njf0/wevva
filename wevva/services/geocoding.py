"""Forward and reverse geocoding helpers.

Looks up named places using Open-Meteo. Decimal coordinate queries use
OpenStreetMap's Nominatim service for a best-effort place name. Both paths
return small dictionaries with the common app location shape and keep network
work out of the UI.
"""

from __future__ import annotations

import asyncio
from importlib.metadata import PackageNotFoundError, version
import os
import re
from threading import Lock
from time import monotonic
from typing import Any
from urllib.parse import quote_plus

import httpx

from wevva.constants import REQUEST_TIMEOUT_S, SEARCH_MAX_RESULTS
from wevva.utils.country_codes import get_country_name_by_alpha2


_COORDINATE_QUERY = re.compile(
    r'^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?:,\s*|\s+)([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*$'
)
_DEFAULT_REVERSE_GEOCODING_URL = 'https://nominatim.openstreetmap.org/reverse'
_REVERSE_ATTRIBUTION = '© OpenStreetMap contributors'
_REVERSE_CACHE_MAX_SIZE = 64
_REVERSE_MIN_INTERVAL_S = 1.0
_REVERSE_ZOOM_LEVELS = (13, 10, 8, 5, 3)
_SETTLEMENT_TYPES = {
    'borough',
    'city',
    'city_district',
    'hamlet',
    'isolated_dwelling',
    'municipality',
    'neighbourhood',
    'quarter',
    'suburb',
    'town',
    'village',
}
_reverse_cache: dict[tuple[float, float, str], dict[str, Any]] = {}
_reverse_rate_lock = Lock()
_next_reverse_request_at = 0.0


def parse_coordinate_query(query: str) -> tuple[float, float] | None:
    """Return a valid ``(latitude, longitude)`` decimal pair from ``query``."""
    match = _COORDINATE_QUERY.fullmatch(query)
    if match is None:
        return None

    latitude, longitude = (float(value) for value in match.groups())
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return latitude, longitude


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

    coordinates = parse_coordinate_query(q)
    if coordinates is not None:
        latitude, longitude = coordinates
        return [
            await reverse_geocode(
                latitude,
                longitude,
                language=language,
                timeout=timeout,
            )
        ]

    async with httpx.AsyncClient() as client:
        qp = quote_plus(q)
        url = f'https://geocoding-api.open-meteo.com/v1/search?name={qp}&count={count}&language={language}&format=json'
        resp = await client.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        results = data.get('results', [])

    return normalize_places(results)


async def reverse_geocode(
    latitude: float,
    longitude: float,
    *,
    language: str = 'en',
    timeout: float = REQUEST_TIMEOUT_S,
) -> dict[str, Any]:
    """Build one location entry from coordinates and a best-effort place lookup.

    The exact requested coordinates are retained while progressively broader
    address levels are tried. If reverse geocoding is unavailable or has no
    nearby place, an explicit unnamed-place result remains selectable.
    """
    fallback = _coordinate_place(latitude, longitude)
    cache_key = (latitude, longitude, language.casefold())
    cached = _reverse_cache.get(cache_key)
    if cached is not None:
        return dict(cached)

    url = os.environ.get(
        'WEVVA_REVERSE_GEOCODING_URL',
        _DEFAULT_REVERSE_GEOCODING_URL,
    )
    try:
        async with httpx.AsyncClient(headers={'User-Agent': _reverse_user_agent()}) as client:
            for zoom in _REVERSE_ZOOM_LEVELS:
                await _limit_reverse_request_rate()
                response = await client.get(
                    url,
                    params={
                        'format': 'jsonv2',
                        'lat': latitude,
                        'lon': longitude,
                        'zoom': zoom,
                        'addressdetails': 1,
                        'layer': 'address',
                        'accept-language': language,
                    },
                    timeout=timeout,
                )
                response.raise_for_status()
                place = _normalize_reverse_place(response.json(), latitude, longitude)
                if place is not None:
                    _cache_reverse_place(cache_key, place)
                    return dict(place)
    except (httpx.HTTPError, ValueError, TypeError):
        return fallback

    _cache_reverse_place(cache_key, fallback)
    return dict(fallback)


def _normalize_reverse_place(
    payload: Any,
    latitude: float,
    longitude: float,
) -> dict[str, Any] | None:
    """Normalize one Nominatim reverse result into the app location shape."""
    if not isinstance(payload, dict) or payload.get('error'):
        return None
    address = payload.get('address')
    if not isinstance(address, dict):
        address = {}

    payload_name = payload.get('name')
    payload_type = payload.get('type')
    name = ''
    if (
        payload.get('category') == 'place'
        and isinstance(payload_type, str)
        and payload_type in _SETTLEMENT_TYPES
        and isinstance(payload_name, str)
    ):
        name = payload_name.strip()
    if not name:
        name = _first_text(
            address,
            'hamlet',
            'village',
            'town',
            'suburb',
            'neighbourhood',
            'city_district',
            'borough',
            'city',
            'municipality',
            'isolated_dwelling',
            'county',
            'state',
            'country',
        )
    if not name and isinstance(payload_name, str):
        name = payload_name.strip()
    if not name:
        return None

    admin_parts: list[str] = []
    for key in ('county', 'state_district', 'state', 'region'):
        value = address.get(key)
        if not isinstance(value, str):
            continue
        value = value.strip()
        if value and value != name and value not in admin_parts:
            admin_parts.append(value)
        if len(admin_parts) == 2:
            break

    raw_country_code = address.get('country_code')
    country_code = raw_country_code.upper() if isinstance(raw_country_code, str) else ''
    raw_country = address.get('country')
    country = raw_country.strip() if isinstance(raw_country, str) else ''
    if not country:
        country = get_country_name_by_alpha2(country_code) or ''

    return {
        'latitude': latitude,
        'longitude': longitude,
        'elevation': None,
        'name': name,
        'admin': ';'.join(admin_parts),
        'country_code': country_code,
        'country': country,
        'tz_identifier': '',
        'attribution': _REVERSE_ATTRIBUTION,
    }


def _first_text(values: dict[str, Any], *keys: str) -> str:
    """Return the first non-empty string for ``keys``."""
    for key in keys:
        value = values.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ''


def _coordinate_place(latitude: float, longitude: float) -> dict[str, Any]:
    """Return a usable location entry when reverse geocoding has no result."""
    return {
        'latitude': latitude,
        'longitude': longitude,
        'elevation': None,
        'name': 'No place name found',
        'admin': '',
        'country_code': '',
        'country': '',
        'tz_identifier': '',
    }


def _reverse_user_agent() -> str:
    """Return the identifying User-Agent required by the reverse provider."""
    try:
        package_version = version('wevva')
    except PackageNotFoundError:
        package_version = 'development'
    return f'wevva/{package_version} (+https://github.com/njf0/wevva)'


async def _limit_reverse_request_rate() -> None:
    """Space reverse requests at the public provider's required interval."""
    global _next_reverse_request_at
    now = monotonic()
    with _reverse_rate_lock:
        request_at = max(now, _next_reverse_request_at)
        _next_reverse_request_at = request_at + _REVERSE_MIN_INTERVAL_S
    delay = request_at - now
    if delay > 0:
        await asyncio.sleep(delay)


def _cache_reverse_place(
    key: tuple[float, float, str],
    place: dict[str, Any],
) -> None:
    """Keep a small session cache for repeated coordinate searches."""
    if key in _reverse_cache:
        _reverse_cache.pop(key)
    _reverse_cache[key] = dict(place)
    while len(_reverse_cache) > _REVERSE_CACHE_MAX_SIZE:
        oldest_key = next(iter(_reverse_cache))
        _reverse_cache.pop(oldest_key)


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
