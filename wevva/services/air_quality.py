"""Service for fetching hourly air quality data from Open-Meteo Air Quality API."""

import httpx

from wevva.constants import REQUEST_TIMEOUT_S

BASE_URL = 'https://air-quality-api.open-meteo.com/v1/air-quality'


async def fetch_air_quality(lat: float, lon: float, start: str, end: str, country_code: str):
    """Fetch hourly air quality data for the given location and time window."""
    params = {
        'latitude': lat,
        'longitude': lon,
        'hourly': 'us_aqi,european_aqi,pm2_5,pm10,ozone,grass_pollen',
        'start': start,
        'end': end,
    }
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
        resp = await client.get(BASE_URL, params=params)
        resp.raise_for_status()
        return resp.json()
