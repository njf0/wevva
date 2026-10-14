"""Public library API for fetching weather without the TUI."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from copy import deepcopy
from typing import Any, ParamSpec, TypeVar

from wevva.alerts import Alert, get_alerts, get_alerts_async
from wevva.location_metadata import LocationMetadata, location_metadata_from_place
from wevva.models import ForecastBundle
from wevva.openmeteo import (
    CurrentOpenMeteoForecast,
    DailyOpenMeteoForecast,
    HourlyOpenMeteoForecast,
    OpenMeteoForecast,
)
from wevva.services.air_quality import fetch_air_quality, merge_air_quality_fields
from wevva.services.geocoding import search_places
from wevva.services.weather import fetch_weather

T = TypeVar('T')
P = ParamSpec('P')


class WevvaAPIError(RuntimeError):
    """Base exception for public API helpers."""


class LocationNotFoundError(WevvaAPIError):
    """Raised when a place query returns no geocoding matches."""


def _run_sync(
    async_callable: Callable[P, Coroutine[Any, Any, T]],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """Call an async function from synchronous code."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(async_callable(*args, **kwargs))
    raise WevvaAPIError('Sync API cannot run inside an active event loop. Use async API functions instead.')


def _apply_place_metadata(metadata: LocationMetadata, place: dict[str, Any] | None) -> None:
    """Overlay geocoding place fields onto API metadata."""
    if not place:
        return
    metadata.name = place.get('name') or metadata.name
    metadata.admin = place.get('admin') or metadata.admin
    metadata.country = place.get('country') or metadata.country
    metadata.country_code = place.get('country_code') or metadata.country_code
    if not metadata.timezone:
        metadata.timezone = place.get('tz_identifier') or metadata.timezone


async def _build_forecast_bundle(
    weather_data: dict[str, Any],
    *,
    country_code: str = '',
    place: dict[str, Any] | None = None,
) -> ForecastBundle:
    """Build typed forecast models from raw API weather data."""
    data = deepcopy(weather_data)
    metadata = OpenMeteoForecast.extract_metadata(data)
    _apply_place_metadata(metadata, place)

    units_current = OpenMeteoForecast.extract_units(data, key='current')
    units_hourly = OpenMeteoForecast.extract_units(data, key='hourly')
    units_daily = OpenMeteoForecast.extract_units(data, key='daily')

    hourly_data = data.get('hourly') if isinstance(data.get('hourly'), dict) else {}
    times = hourly_data.get('time', []) if isinstance(hourly_data, dict) else []
    start = times[0] if times else None
    end = times[-1] if times else None

    air_quality = None
    if start and end and metadata.latitude is not None and metadata.longitude is not None:
        air_quality = await fetch_air_quality(
            metadata.latitude,
            metadata.longitude,
            start,
            end,
            country_code or metadata.country_code,
        )

    merged_hourly = merge_air_quality_fields(hourly_data, air_quality)
    data['hourly'] = merged_hourly

    current = CurrentOpenMeteoForecast(metadata, units_current, data.get('current', {}))
    hourly = HourlyOpenMeteoForecast(metadata, units_hourly, merged_hourly)
    daily = DailyOpenMeteoForecast(metadata, units_daily, data.get('daily', {}))

    return ForecastBundle(
        metadata=metadata,
        current=current,
        hourly=hourly,
        daily=daily,
        raw=data,
    )


async def geocode(
    query: str,
    *,
    count: int = 5,
    language: str = 'en',
) -> list[LocationMetadata]:
    """Search for places and return normalized location metadata entries."""
    places = await search_places(query, count=count, language=language)
    return [location_metadata_from_place(place) for place in places]


def geocode_sync(
    query: str,
    *,
    count: int = 5,
    language: str = 'en',
) -> list[LocationMetadata]:
    """Synchronous wrapper for :func:`geocode`."""
    return _run_sync(geocode, query, count=count, language=language)


async def alerts_by_coordinates(
    *,
    lat: float,
    lon: float,
    country_code: str | None = None,
) -> list[Alert]:
    """Fetch active weather alerts for explicit coordinates."""
    return await get_alerts_async(lat, lon, country_code)


def alerts_by_coordinates_sync(
    *,
    lat: float,
    lon: float,
    country_code: str | None = None,
) -> list[Alert]:
    """Synchronous alert lookup for explicit coordinates."""
    return get_alerts(lat, lon, country_code)


async def forecast_by_coordinates(
    *,
    lat: float,
    lon: float,
    temperature_unit: str = 'celsius',
    wind_speed_unit: str = 'kmh',
    precipitation_unit: str = 'mm',
    country_code: str = '',
) -> ForecastBundle:
    """Fetch forecasts for explicit coordinates."""
    weather_data = await fetch_weather(
        lat=lat,
        lon=lon,
        temperature_unit=temperature_unit,
        wind_speed_unit=wind_speed_unit,
        precipitation_unit=precipitation_unit,
    )
    return await _build_forecast_bundle(weather_data, country_code=country_code)


def forecast_by_coordinates_sync(
    *,
    lat: float,
    lon: float,
    temperature_unit: str = 'celsius',
    wind_speed_unit: str = 'kmh',
    precipitation_unit: str = 'mm',
    country_code: str = '',
) -> ForecastBundle:
    """Synchronous wrapper for :func:`forecast_by_coordinates`."""
    return _run_sync(
        forecast_by_coordinates,
        lat=lat,
        lon=lon,
        temperature_unit=temperature_unit,
        wind_speed_unit=wind_speed_unit,
        precipitation_unit=precipitation_unit,
        country_code=country_code,
    )


async def forecast_by_place(
    query: str,
    *,
    language: str = 'en',
    temperature_unit: str = 'celsius',
    wind_speed_unit: str = 'kmh',
    precipitation_unit: str = 'mm',
) -> ForecastBundle:
    """Geocode a place query and fetch forecasts for the best match."""
    matches = await search_places(query, count=1, language=language)
    if not matches:
        raise LocationNotFoundError(f'No location found for query: {query!r}')

    place = matches[0]
    lat = place.get('latitude')
    lon = place.get('longitude')
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        raise WevvaAPIError(f'Geocoding result for {query!r} is missing coordinates.')

    weather_data = await fetch_weather(
        lat=float(lat),
        lon=float(lon),
        temperature_unit=temperature_unit,
        wind_speed_unit=wind_speed_unit,
        precipitation_unit=precipitation_unit,
    )
    return await _build_forecast_bundle(
        weather_data,
        country_code=place.get('country_code') or '',
        place=place,
    )


def forecast_by_place_sync(
    query: str,
    *,
    language: str = 'en',
    temperature_unit: str = 'celsius',
    wind_speed_unit: str = 'kmh',
    precipitation_unit: str = 'mm',
) -> ForecastBundle:
    """Synchronous wrapper for :func:`forecast_by_place`."""
    return _run_sync(
        forecast_by_place,
        query,
        language=language,
        temperature_unit=temperature_unit,
        wind_speed_unit=wind_speed_unit,
        precipitation_unit=precipitation_unit,
    )


__all__ = [
    'Alert',
    'LocationNotFoundError',
    'WevvaAPIError',
    'alerts_by_coordinates',
    'alerts_by_coordinates_sync',
    'forecast_by_coordinates',
    'forecast_by_coordinates_sync',
    'forecast_by_place',
    'forecast_by_place_sync',
    'geocode',
    'geocode_sync',
]
