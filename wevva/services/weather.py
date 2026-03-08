"""Asynchronous weather service that fetches weather data for given coordinates."""

from wevva.openmeteo import OpenMeteoForecast


async def fetch_weather(
    *,
    lat: float,
    lon: float,
    temperature_unit: str = "celsius",
    wind_speed_unit: str = "kmh",
    precipitation_unit: str = "mm",
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


if __name__ == "__main__":
    import asyncio

    async def main():
        lat = 52.52
        lon = 13.405
        data = await fetch_weather(lat=lat, lon=lon)
        print(data)

    asyncio.run(main())
