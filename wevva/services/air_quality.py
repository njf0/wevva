"""Service for fetching hourly air quality data from Open-Meteo Air Quality API."""

from typing import Any

import httpx

from wevva.constants import REQUEST_TIMEOUT_S

BASE_URL = 'https://air-quality-api.open-meteo.com/v1/air-quality'
AIR_QUALITY_FIELDS: tuple[str, ...] = (
    'us_aqi',
    'european_aqi',
    'pm2_5',
    'pm10',
    'ozone',
    'grass_pollen',
)


def merge_air_quality_fields(
    hourly_data: dict[str, Any],
    air_quality: Any,
) -> dict[str, Any]:
    """Return hourly weather with valid air-quality series aligned by time."""
    merged = dict(hourly_data)
    if not isinstance(air_quality, dict):
        return merged
    aq_hourly = air_quality.get('hourly')
    if not isinstance(aq_hourly, dict):
        return merged

    weather_times = merged.get('time', [])
    weather_count = len(weather_times) if isinstance(weather_times, list) else 0
    for field in AIR_QUALITY_FIELDS:
        values = aq_hourly.get(field)
        if not isinstance(values, list):
            continue
        merged[field] = (values + [None] * weather_count)[:weather_count]
    return merged


async def fetch_air_quality(lat: float, lon: float, start: str, end: str, country_code: str):
    """Fetch hourly air quality data for the given location and time window."""
    params = {
        'latitude': lat,
        'longitude': lon,
        'hourly': ','.join(AIR_QUALITY_FIELDS),
        'start': start,
        'end': end,
    }
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
        resp = await client.get(BASE_URL, params=params)
        resp.raise_for_status()
        return resp.json()
