"""Open-Meteo models and helpers.

Wraps the Open-Meteo API response into small classes for
current, hourly, and daily views.
"""

from datetime import datetime
from collections.abc import Sequence
from typing import Any

import httpx
from zoneinfo import ZoneInfo

from wevva.conditions import get_condition
from wevva.constants import (
    DEFAULT_PRECIPITATION_UNIT,
    DEFAULT_TEMPERATURE_UNIT,
    DEFAULT_WIND_SPEED_UNIT,
    REQUEST_TIMEOUT_S,
    VALID_PRECIPITATION_UNITS,
    VALID_TEMPERATURE_UNITS,
    VALID_WIND_SPEED_UNITS,
)
from wevva.location_metadata import LocationMetadata
from wevva.utils import bearing_to_direction

# WMO weather codes

# WEATHER_CODES superseded by wevva.conditions; keep API compatibility via methods.


class OpenMeteoForecast:
    """Base class for Open-Meteo forecast objects.

    Holds metadata, units, and the timeseries.
    """

    BASE_URL = 'https://api.open-meteo.com/v1/forecast'

    def __init__(self, metadata: LocationMetadata, units: dict, timeseries: list):
        self.forecast_metadata = metadata
        self.forecast_units = units
        self.forecast_timeseries = timeseries

    @staticmethod
    def normalize_units(
        temperature_unit: str,
        wind_speed_unit: str,
        precipitation_unit: str,
    ) -> tuple[str, str, str]:
        """Validate requested units and return safe API-ready values.

        Parameters
        ----------
        temperature_unit: str
            Requested temperature unit.
        wind_speed_unit: str
            Requested wind-speed unit.
        precipitation_unit: str
            Requested precipitation unit.

        Returns
        -------
        tuple[str, str, str]
            Normalized tuple of ``(temperature_unit, wind_speed_unit, precipitation_unit)``.

        """
        normalized_temp = temperature_unit if temperature_unit in VALID_TEMPERATURE_UNITS else DEFAULT_TEMPERATURE_UNIT
        normalized_wind = wind_speed_unit if wind_speed_unit in VALID_WIND_SPEED_UNITS else DEFAULT_WIND_SPEED_UNIT
        normalized_precip = (
            precipitation_unit if precipitation_unit in VALID_PRECIPITATION_UNITS else DEFAULT_PRECIPITATION_UNIT
        )
        return normalized_temp, normalized_wind, normalized_precip

    @staticmethod
    def build_params(
        lat: float,
        lon: float,
        temperature_unit: str = 'celsius',
        wind_speed_unit: str = 'kmh',
        precipitation_unit: str = 'mm',
    ) -> dict:
        """Build params for a single API call covering all forecast types.

        Parameters
        ----------
        lat: float
            Latitude
        lon: float
            Longitude
        temperature_unit: str
            'celsius' or 'fahrenheit'
        wind_speed_unit: str
            'kmh', 'ms', 'mph', or 'kn'
        precipitation_unit: str
            'mm' or 'inch'

        """
        params = {
            'latitude': lat,
            'longitude': lon,
            'timezone': 'auto',
            'current': [
                'temperature_2m',
                'relative_humidity_2m',
                'apparent_temperature',
                'precipitation_probability',
                'precipitation',
                'weather_code',
                'surface_pressure',
                'is_day',
                'cloud_cover',
                'visibility',
                'wind_speed_10m',
                'wind_gusts_10m',
                'wind_direction_10m',
                'uv_index',
            ],
            'hourly': [
                'temperature_2m',
                'relative_humidity_2m',
                'apparent_temperature',
                'precipitation_probability',
                'precipitation',
                'rain',
                'showers',
                'snowfall',
                'is_day',
                'weather_code',
                'surface_pressure',
                'cloud_cover',
                'visibility',
                'wind_speed_10m',
                'wind_gusts_10m',
                'wind_direction_10m',
                'uv_index',
            ],
            'daily': [
                'weather_code',
                'temperature_2m_max',
                'temperature_2m_min',
                'sunrise',
                'sunset',
                'daylight_duration',
                'precipitation_sum',
                'precipitation_probability_max',
                'wind_speed_10m_max',
                'wind_gusts_10m_max',
                'wind_direction_10m_dominant',
            ],
        }

        # Normalize unit choices and only send params when they differ from API defaults.
        temperature_unit, wind_speed_unit, precipitation_unit = OpenMeteoForecast.normalize_units(
            temperature_unit,
            wind_speed_unit,
            precipitation_unit,
        )
        if temperature_unit != DEFAULT_TEMPERATURE_UNIT:
            params['temperature_unit'] = temperature_unit
        if wind_speed_unit != DEFAULT_WIND_SPEED_UNIT:
            params['wind_speed_unit'] = wind_speed_unit
        if precipitation_unit != DEFAULT_PRECIPITATION_UNIT:
            params['precipitation_unit'] = precipitation_unit

        return params

    @classmethod
    async def fetch_all(
        cls,
        lat: float,
        lon: float,
        temperature_unit: str = 'celsius',
        wind_speed_unit: str = 'kmh',
        precipitation_unit: str = 'mm',
    ) -> dict:
        """Fetch the full Open-Meteo API response for all forecast types."""
        params = cls.build_params(lat, lon, temperature_unit, wind_speed_unit, precipitation_unit)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(cls.BASE_URL, params=params)
            response.raise_for_status()
            return response.json()

    @classmethod
    async def fetch_current_summary(
        cls,
        lat: float,
        lon: float,
        temperature_unit: str = 'celsius',
    ) -> dict:
        """Fetch only the fields needed for a saved-location summary."""
        temperature_unit = (
            temperature_unit if temperature_unit in VALID_TEMPERATURE_UNITS else DEFAULT_TEMPERATURE_UNIT
        )
        params: dict[str, Any] = {
            'latitude': lat,
            'longitude': lon,
            'current': ['temperature_2m', 'weather_code', 'is_day'],
        }
        if temperature_unit != DEFAULT_TEMPERATURE_UNIT:
            params['temperature_unit'] = temperature_unit
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(cls.BASE_URL, params=params)
            response.raise_for_status()
            return response.json()

    @classmethod
    async def fetch_current_temperatures(
        cls,
        coordinates: Sequence[tuple[float, float]],
        temperature_unit: str = 'celsius',
    ) -> dict[tuple[float, float], float]:
        """Fetch only current temperatures for several coordinate pairs."""
        points = tuple(coordinates)
        if not points:
            return {}
        temperature_unit = (
            temperature_unit if temperature_unit in VALID_TEMPERATURE_UNITS else DEFAULT_TEMPERATURE_UNIT
        )
        params: dict[str, Any] = {
            'latitude': ','.join(str(latitude) for latitude, _longitude in points),
            'longitude': ','.join(str(longitude) for _latitude, longitude in points),
            'current': 'temperature_2m',
        }
        if temperature_unit != DEFAULT_TEMPERATURE_UNIT:
            params['temperature_unit'] = temperature_unit
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
            response = await client.get(cls.BASE_URL, params=params)
            response.raise_for_status()
            payload = response.json()

        forecasts = payload if isinstance(payload, list) else [payload]
        temperatures = {}
        for point, forecast in zip(points, forecasts):
            if not isinstance(forecast, dict):
                continue
            current = forecast.get('current')
            if not isinstance(current, dict):
                continue
            temperature = current.get('temperature_2m')
            if isinstance(temperature, (int, float)) and not isinstance(temperature, bool):
                temperatures[point] = float(temperature)
        return temperatures

    @classmethod
    async def fetch_hourly_summary(
        cls,
        lat: float,
        lon: float,
        temperature_unit: str = 'celsius',
        wind_speed_unit: str = 'kmh',
    ) -> dict:
        """Fetch only the hourly fields used by an alert-place forecast."""

        temperature_unit, wind_speed_unit, _precipitation_unit = cls.normalize_units(
            temperature_unit,
            wind_speed_unit,
            DEFAULT_PRECIPITATION_UNIT,
        )
        params: dict[str, Any] = {
            'latitude': lat,
            'longitude': lon,
            'timezone': 'auto',
            'hourly': [
                'temperature_2m',
                'precipitation_probability',
                'wind_speed_10m',
                'wind_direction_10m',
            ],
        }
        if temperature_unit != DEFAULT_TEMPERATURE_UNIT:
            params['temperature_unit'] = temperature_unit
        if wind_speed_unit != DEFAULT_WIND_SPEED_UNIT:
            params['wind_speed_unit'] = wind_speed_unit
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
            response = await client.get(cls.BASE_URL, params=params)
            response.raise_for_status()
            return response.json()

    @classmethod
    async def fetch_current_conditions(
        cls,
        lat: float,
        lon: float,
        temperature_unit: str = 'celsius',
        wind_speed_unit: str = 'kmh',
        precipitation_unit: str = 'mm',
    ) -> dict:
        """Fetch the compact current conditions used at a storm centre."""
        temperature_unit, wind_speed_unit, precipitation_unit = cls.normalize_units(
            temperature_unit,
            wind_speed_unit,
            precipitation_unit,
        )
        params: dict[str, Any] = {
            'latitude': lat,
            'longitude': lon,
            'timezone': 'auto',
            'current': [
                'temperature_2m',
                'apparent_temperature',
                'precipitation_probability',
                'precipitation',
                'weather_code',
                'surface_pressure',
                'is_day',
                'wind_speed_10m',
                'wind_gusts_10m',
                'wind_direction_10m',
            ],
        }
        if temperature_unit != DEFAULT_TEMPERATURE_UNIT:
            params['temperature_unit'] = temperature_unit
        if wind_speed_unit != DEFAULT_WIND_SPEED_UNIT:
            params['wind_speed_unit'] = wind_speed_unit
        if precipitation_unit != DEFAULT_PRECIPITATION_UNIT:
            params['precipitation_unit'] = precipitation_unit
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(cls.BASE_URL, params=params)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def extract_metadata(response: dict) -> LocationMetadata:
        # Return LocationMetadata with API-provided fields
        return LocationMetadata(
            latitude=response.get('latitude'),
            longitude=response.get('longitude'),
            elevation=int(response.get('elevation', 0)) if response.get('elevation') is not None else None,
            timezone=response.get('timezone') or '',
            timezone_abbreviation=response.get('timezone_abbreviation') or '',
        )

    @staticmethod
    def extract_units(response: dict, key: str) -> dict:
        """Extract units dict from API response, returning as-is."""
        return response.get(f'{key}_units', {})

    def get_point(self, offset: int = 0) -> dict[str, Any] | None:
        """Return a timeseries point, or ``None`` when the offset is invalid."""
        if 0 <= offset < len(self.forecast_timeseries):
            return self.forecast_timeseries[offset]
        return None

    def _get_value(self, key: str, offset: int = 0) -> Any | None:
        """Return a point value, or ``None`` for a missing point or value."""
        point = self.get_point(offset)
        return point.get(key) if point is not None else None

    def _get_rounded_value(self, key: str, offset: int = 0) -> float | None:
        """Return a rounded point value while preserving missing-value semantics."""
        value = self._get_value(key, offset)
        return round(value) if value is not None else None


class CurrentOpenMeteoForecast(OpenMeteoForecast):
    """Current weather view."""

    def __init__(self, metadata: LocationMetadata, units: dict, timeseries: dict):
        # Timeseries: the 'current' section from API response
        super().__init__(metadata, units, [])
        self._get_timeseries(timeseries)

    def _get_timeseries(self, ts: dict):
        if not ts:
            self.forecast_timeseries = []
            return
        tz_name = self.forecast_metadata.timezone
        tzinfo = ZoneInfo(tz_name)
        result = [{}]
        for key, value in ts.items():
            processed_value = value
            if key == 'time':
                entry_time = datetime.fromisoformat(value)
                if entry_time.tzinfo is None:
                    entry_time = entry_time.replace(tzinfo=tzinfo)
                processed_value = entry_time
            result[0][key] = processed_value
        self.forecast_timeseries = result

    def get_time(self) -> str:
        """Get the time of the current weather observation."""
        t = self._get_value('time')
        if isinstance(t, str):
            t = datetime.fromisoformat(t)
        return t.isoformat() if t else ''

    def get_temperature(self) -> float | None:
        """Get air temperature at 2m."""
        return self._get_rounded_value('temperature_2m')

    def get_feels_like(self) -> float | None:
        """Get apparent temperature (feels like)."""
        return self._get_rounded_value('apparent_temperature')

    def get_humidity(self) -> float | None:
        """Get relative humidity at 2m."""
        return self._get_rounded_value('relative_humidity_2m')

    def get_wind_speed(self) -> float | None:
        """Get wind speed at 10m in the configured API unit."""
        return self._get_rounded_value('wind_speed_10m')

    def get_wind_gust(self) -> float | None:
        """Get wind gusts at 10m in the configured API unit."""
        return self._get_rounded_value('wind_gusts_10m')

    def get_wind_direction(self) -> float | None:
        """Get wind direction at 10m (degrees, may not be present)."""
        return self._get_value('wind_direction_10m')

    def get_pressure(self) -> float | None:
        """Get surface pressure (may not be present)."""
        return self._get_rounded_value('surface_pressure')

    def get_precipitation(self) -> float | None:
        """Get precipitation (mm or %, may not be present)."""
        return self._get_value('precipitation')

    def get_condition(self) -> str:
        """Get weather code or description (not always present in current endpoint)."""
        code = self._get_value('weather_code')
        return str(code) if code is not None else ''

    def get_is_day(self) -> int | None:
        """Get is_day flag (1 for day, 0 for night, may not be present)."""
        return self._get_value('is_day')


class HourlyOpenMeteoForecast(OpenMeteoForecast):
    """Open-Meteo hourly forecast (temperature, precipitation, etc. each hour)."""

    def __init__(self, metadata: LocationMetadata, units: dict, timeseries: dict):
        # timeseries: the 'hourly' section from API response
        super().__init__(metadata, units, [])
        self._get_timeseries(timeseries)

    def _get_timeseries(self, ts: dict):
        if not ts:
            self.forecast_timeseries = []
            return
        times = ts['time']
        variables = list(ts.keys())
        tz_name = self.forecast_metadata.timezone
        tzinfo = ZoneInfo(tz_name)
        now_local = datetime.now(tzinfo).replace(minute=0, second=0, microsecond=0)
        result = []
        start_idx = None
        for idx, tstr in enumerate(times):
            entry_time = datetime.fromisoformat(tstr)
            if entry_time.tzinfo is None:
                entry_time = entry_time.replace(tzinfo=tzinfo)
            if entry_time >= now_local:
                start_idx = idx
                break
        if start_idx is None:
            self.forecast_timeseries = []
            return
        # Keep all future hours provided by the API (allows tabbing across days)
        for idx in range(start_idx, len(times)):
            entry = {var: ts[var][idx] for var in variables}
            entry_time = datetime.fromisoformat(entry['time'])
            if entry_time.tzinfo is None:
                entry_time = entry_time.replace(tzinfo=tzinfo)
            entry['time'] = entry_time
            # Compute a display emoji now so widgets can rely on it (handles clear-night crescent)
            code = entry.get('weather_code')
            cond = get_condition(code) if code is not None else None
            if cond:
                is_day_flag = entry.get('is_day')
                entry['weather_emoji'] = cond.night_emoji if is_day_flag == 0 else cond.day_emoji

            result.append(entry)
        self.forecast_timeseries = result

    def get_temperature(self, offset: int = 0) -> float | None:
        return self._get_value('temperature_2m', offset)

    def get_humidity(self, offset: int = 0) -> float | None:
        """Get relative humidity at 2m for a given hour."""
        return self._get_rounded_value('relative_humidity_2m', offset)

    def get_feels_temperature(self, offset: int = 0) -> float | None:
        """Get apparent temperature at 2m for a given hour."""
        return self._get_rounded_value('apparent_temperature', offset)

    def get_precipitation_probability(self, offset: int = 0) -> float | None:
        """Get precipitation probability for a given hour."""
        return self._get_rounded_value('precipitation_probability', offset)

    def get_precipitation(self, offset: int = 0) -> float | None:
        """Get precipitation for a given hour."""
        return self._get_value('precipitation', offset)

    def get_rain(self, offset: int = 0) -> float | None:
        """Get rain amount for a given hour."""
        return self._get_value('rain', offset)

    def get_showers(self, offset: int = 0) -> float | None:
        """Get showers amount for a given hour."""
        return self._get_value('showers', offset)

    def get_snowfall(self, offset: int = 0) -> float | None:
        """Get snowfall amount for a given hour."""
        return self._get_value('snowfall', offset)

    def get_weather_code(self, offset: int = 0, return_emoji: bool = False) -> str:
        """Get weather code for a given hour."""
        code = self._get_value('weather_code', offset)
        if code is None:
            return ''
        cond = get_condition(code) if code is not None else None
        if not cond:
            return str(code)
        if return_emoji:
            # Prefer precomputed emoji (set during parsing), fall back to cond + is_day
            return self._get_value('weather_emoji', offset) or (
                cond.night_emoji if self._get_value('is_day', offset) == 0 else cond.day_emoji
            )
        return cond.name

    # New helpers for abbreviation/emoji
    def get_condition_abbreviation(self, offset: int = 0) -> str:
        code = self._get_value('weather_code', offset)
        if code is None:
            return ''
        cond = get_condition(code) if code is not None else None
        return cond.abbr if cond else str(code)

    def get_condition_emoji(self, offset: int = 0) -> str:
        code = self._get_value('weather_code', offset)
        cond = get_condition(code) if code is not None else None
        if not cond:
            return ''
        # Prefer precomputed emoji (set during parsing)
        return self._get_value('weather_emoji', offset) or (
            cond.night_emoji if self._get_value('is_day', offset) == 0 else cond.day_emoji
        )

    def get_surface_pressure(self, offset: int = 0) -> float | None:
        """Get surface pressure for a given hour."""
        return self._get_rounded_value('surface_pressure', offset)

    def get_cloud_cover(self, offset: int = 0) -> float | None:
        """Get cloud cover for a given hour."""
        return self._get_rounded_value('cloud_cover', offset)

    def get_visibility(self, offset: int = 0) -> float | None:
        """Get visibility for a given hour."""
        vis = self._get_value('visibility', offset)
        if vis is None:
            return None
        # Open-Meteo returns visibility in meters; we display rounded kilometers.
        vis = vis / 1000.0
        return round(vis)

    def get_wind_speed(self, offset: int = 0) -> float | None:
        """Get wind speed at 10m for a given hour in the configured API unit."""
        return self._get_value('wind_speed_10m', offset)

    def get_wind_gust(self, offset: int = 0) -> float | None:
        """Get wind gusts at 10m for a given hour in the configured API unit."""
        return self._get_rounded_value('wind_gusts_10m', offset)

    def get_wind_direction(self, offset: int = 0) -> str | None:
        """Get wind direction at 10m for a given hour."""
        bearing = self._get_value('wind_direction_10m', offset)
        return bearing_to_direction(bearing) if bearing is not None else None

    def get_uv_index(self, offset: int = 0) -> float | None:
        """Get UV index for a given hour."""
        return self._get_rounded_value('uv_index', offset)

    def get_us_aqi(self, offset: int = 0) -> float | None:
        return self._get_value('us_aqi', offset)

    def get_european_aqi(self, offset: int = 0) -> float | None:
        return self._get_value('european_aqi', offset)

    def get_pm2_5(self, offset: int = 0) -> float | None:
        return self._get_value('pm2_5', offset)

    def get_pm10(self, offset: int = 0) -> float | None:
        return self._get_value('pm10', offset)

    def get_ozone(self, offset: int = 0) -> float | None:
        return self._get_value('ozone', offset)

    def get_grass_pollen(self, offset: int = 0) -> float | None:
        return self._get_value('grass_pollen', offset)


class DailyOpenMeteoForecast(OpenMeteoForecast):
    """Open-Meteo daily forecast (min/max temperature, precipitation, etc. each day)."""

    def __init__(self, metadata: LocationMetadata, units: dict, timeseries: dict):
        # timeseries: the 'daily' section from API response
        super().__init__(metadata, units, [])
        self._get_timeseries(timeseries)

    def _get_timeseries(self, ts: dict):
        if not ts:
            self.forecast_timeseries = []
            return
        times = ts['time']
        variables = list(ts.keys())

        result = []
        for idx, _ in enumerate(times):
            entry = {var: ts[var][idx] for var in variables}
            if 'time' in entry:
                entry['time'] = datetime.fromisoformat(entry['time']).date()
            for field in ('sunrise', 'sunset'):
                if field in entry:
                    entry[field] = datetime.fromisoformat(entry[field])
            result.append(entry)
        self.forecast_timeseries = result

    def get_temperature_min(self, offset: int = 0) -> float | None:
        """Get minimum 2m temperature for a given day."""
        return self._get_value('temperature_2m_min', offset)

    def get_temperature_max(self, offset: int = 0) -> float | None:
        """Get maximum 2m temperature for a given day."""
        return self._get_value('temperature_2m_max', offset)

    def get_precipitation(self, offset: int = 0) -> float | None:
        """Get precipitation sum for a given day."""
        return self._get_value('precipitation_sum', offset)

    def get_precipitation_probability(self, offset: int = 0) -> float | None:
        """Get precipitation probability for a given day (not always present)."""
        return self._get_rounded_value('precipitation_probability_max', offset)

    def get_weather_code(self, offset: int = 0, return_emoji: bool = False) -> str:
        """Get weather code for a given day."""
        code = self._get_value('weather_code', offset)
        if code is None:
            return ''
        cond = get_condition(code) if code is not None else None
        if not cond:
            return str(code)
        if return_emoji:
            return cond.day_emoji
        return cond.name

    def get_condition_abbreviation(self, offset: int = 0) -> str:
        code = self._get_value('weather_code', offset)
        if code is None:
            return ''
        cond = get_condition(code) if code is not None else None
        return cond.abbr if cond else str(code)

    def get_wind_speed(self, offset: int = 0) -> float | None:
        """Get max wind speed at 10m for a given day in the configured API unit."""
        return self._get_value('wind_speed_10m_max', offset)

    def get_wind_gust(self, offset: int = 0) -> float | None:
        """Get max wind gusts at 10m for a given day in the configured API unit."""
        return self._get_value('wind_gusts_10m_max', offset)

    def get_wind_direction(self, offset: int = 0) -> str | None:
        """Get dominant wind direction at 10m for a given day."""
        bearing = self._get_value('wind_direction_10m_dominant', offset)
        return bearing_to_direction(bearing) if bearing is not None else None

    def get_sunrise(self, offset: int = 0) -> datetime | None:
        """Get sunrise time for a given day."""
        return self._get_value('sunrise', offset)

    def get_sunset(self, offset: int = 0) -> datetime | None:
        """Get sunset time for a given day."""
        return self._get_value('sunset', offset)

    def get_daylight_duration(self, offset: int = 0) -> int | None:
        """Get daylight duration (in seconds) for a given day."""
        return self._get_value('daylight_duration', offset)
