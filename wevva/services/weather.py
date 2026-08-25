"""Asynchronous weather service that fetches weather data for given coordinates."""

from wevva.openmeteo import OpenMeteoForecast


async def fetch_weather(
    *,
    lat: float,
    lon: float,
    temperature_unit: str = 'celsius',
    wind_speed_unit: str = 'kmh',
    precipitation_unit: str = 'mm',
) -> dict:
    """Use OpenMeteo API to fetch weather data for given latitude and longitude.

    Args:
        lat: Latitude
        lon: Longitude
        temperature_unit: 'celsius' or 'fahrenheit'
        wind_speed_unit: 'kmh', 'ms', 'mph', or 'kn'
        precipitation_unit: 'mm' or 'inch'

    """
    return await OpenMeteoForecast.fetch_all(
        lat=lat,
        lon=lon,
        temperature_unit=temperature_unit,
        wind_speed_unit=wind_speed_unit,
        precipitation_unit=precipitation_unit,
    )


async def fetch_weather_summary(
    *,
    lat: float,
    lon: float,
    temperature_unit: str = 'celsius',
) -> dict:
    """Fetch only the current fields shown beside a saved location."""
    return await OpenMeteoForecast.fetch_current_summary(
        lat=lat,
        lon=lon,
        temperature_unit=temperature_unit,
    )


async def fetch_current_weather(
    *,
    lat: float,
    lon: float,
    temperature_unit: str = 'celsius',
    wind_speed_unit: str = 'kmh',
    precipitation_unit: str = 'mm',
) -> dict:
    """Fetch current-only Open-Meteo conditions for a coordinate."""
    return await OpenMeteoForecast.fetch_current_conditions(
        lat=lat,
        lon=lon,
        temperature_unit=temperature_unit,
        wind_speed_unit=wind_speed_unit,
        precipitation_unit=precipitation_unit,
    )
