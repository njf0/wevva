"""WeatherController: async orchestrator for fetching and normalizing weather data.

Emits `WeatherUpdated` or `WeatherFetchFailed` to decouple App/Widgets from I/O.
This file adds small comments for clarity in a public release.
"""

from __future__ import annotations

from typing import Any

from wevva.messages import WeatherUpdated  # message payload pushed to App and widgets
from wevva.openmeteo import (
    CurrentOpenMeteoForecast,
    DailyOpenMeteoForecast,
    HourlyOpenMeteoForecast,
    OpenMeteoForecast,
)
from wevva.services.air_quality import fetch_air_quality
from wevva.services.weather import fetch_weather  # fetches raw Open-Meteo response


class WeatherController:
    """Async data orchestrator (no UI logic).

    - Fetches raw API data.
    - Normalizes units and builds forecast models.
    - Returns a single `WeatherUpdated` message for the App to post.
    """

    def __init__(
        self,
        temperature_unit: str = "celsius",
        wind_speed_unit: str = "kmh",
        precipitation_unit: str = "mm",
    ):
        """Initialize controller with unit preferences.

        Args:
            temperature_unit: 'celsius' or 'fahrenheit'
            wind_speed_unit: 'kmh', 'ms', 'mph', or 'kn'
            precipitation_unit: 'mm' or 'inch'

        """
        self.temperature_unit = temperature_unit
        self.wind_speed_unit = wind_speed_unit
        self.precipitation_unit = precipitation_unit

    async def fetch(
        self, *, lat: float, lon: float, country_code: str = ""
    ) -> WeatherUpdated:
        """Fetch weather and air quality by coordinates and return a `WeatherUpdated` message."""
        # 1) Get raw API response (single call covering current/hourly/daily)
        data: dict[str, Any] = await fetch_weather(
            lat=lat,
            lon=lon,
            temperature_unit=self.temperature_unit,
            wind_speed_unit=self.wind_speed_unit,
            precipitation_unit=self.precipitation_unit,
        )

        # 2) Extract canonical metadata (lat/lon/elevation/timezone)
        meta = OpenMeteoForecast.extract_metadata(data)

        # 3) Extract API-provided units for each forecast section
        units_current = OpenMeteoForecast.extract_units(data, key="current")
        units_hourly = OpenMeteoForecast.extract_units(data, key="hourly")
        units_daily = OpenMeteoForecast.extract_units(data, key="daily")

        # 4) Fetch air quality data (hourly)

        # Use the same time window as the weather hourly timeseries
        times = data.get("hourly", {}).get("time", [])
        start = times[0] if times else None
        end = times[-1] if times else None
        air_quality = None
        if start and end:
            air_quality = await fetch_air_quality(lat, lon, start, end, country_code)

        # 5) Merge air quality fields into hourly timeseries
        hourly_data = data.get("hourly", {})
        if air_quality and "hourly" in air_quality:
            aq_hourly = air_quality["hourly"]
            weather_times = hourly_data.get("time", [])
            n = len(weather_times)
            for field in [
                "us_aqi",
                "european_aqi",
                "pm2_5",
                "pm10",
                "ozone",
                "grass_pollen",
            ]:
                if field in aq_hourly:
                    aq_values = aq_hourly[field]
                    # Pad or truncate to match weather timeseries length
                    if len(aq_values) < n:
                        aq_values = aq_values + [None] * (n - len(aq_values))
                    elif len(aq_values) > n:
                        aq_values = aq_values[:n]
                    hourly_data[field] = aq_values

        # 6) Build models for each forecast view
        current = CurrentOpenMeteoForecast(meta, units_current, data.get("current", {}))
        hourly = HourlyOpenMeteoForecast(meta, units_hourly, hourly_data)
        daily = DailyOpenMeteoForecast(meta, units_daily, data.get("daily", {}))

        # 7) Return unified message consumed by the App and widgets
        return WeatherUpdated(
            metadata=meta,
            current=current,
            hourly=hourly,
            daily=daily,
        )
