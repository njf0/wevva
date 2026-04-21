"""Open-Meteo models and helpers.

Wraps the Open-Meteo API response into small classes for
current, hourly, and daily views.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from zoneinfo import ZoneInfo

from wevva.conditions import get_condition
from wevva.constants import (
    DEFAULT_PRECIPITATION_UNIT,
    DEFAULT_TEMPERATURE_UNIT,
    DEFAULT_WIND_SPEED_UNIT,
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

    def _get_metadata(
        self,
        response: dict,
    ) -> LocationMetadata:
        """Store metadata (latitude, longitude, elevation, timezone)."""
        self.forecast_metadata = LocationMetadata(
            latitude=response.get('latitude'),
            longitude=response.get('longitude'),
            elevation=int(response.get('elevation', 0)) if response.get('elevation') is not None else None,
            timezone=response.get('timezone') or '',
            timezone_abbreviation=response.get('timezone_abbreviation') or '',
        )
        return self.forecast_metadata

    def _get_units(
        self,
        response: dict,
        key: str,
    ) -> Dict[str, str]:
        """Store units for the forecast variables (hourly/daily/etc)."""
        units = response.get(f'{key}_units', {})
        self.forecast_units.update(units)

    def get_point(self, offset: int = 0) -> Optional[Dict[str, Any]]:
        """Get a point from the timeseries (0 = first)."""
        if 0 <= offset < len(self.forecast_timeseries):
            return self.forecast_timeseries[offset]
        return None


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

    def fetch_and_parse_forecast(
        self,
    ) -> tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, str]]:
        """Fetch and return (metadata, timeseries, units dict) as a tuple."""
        # Fetch the full API response
        full_api_response = self.fetch()

        # Set metadata by supplying the full response
        self._get_metadata(full_api_response)

        # Parse and store units by supplying the 'daily' section
        self._get_units(full_api_response, 'current')

        # Parse timeseries by supplying the full response
        self._get_timeseries(full_api_response)

    def get_time(self) -> str:
        """Get the time of the current weather observation."""
        t = self.forecast_timeseries[0].get('time')
        if isinstance(t, str):
            t = datetime.fromisoformat(t)
        return t.isoformat() if t else ''

    def get_temperature(self) -> float | None:
        """Get air temperature at 2m."""
        return round(self.forecast_timeseries[0].get('temperature_2m'))

    def get_feels_like(self) -> float | None:
        """Get apparent temperature (feels like)."""
        return round(self.forecast_timeseries[0].get('apparent_temperature'))

    def get_humidity(self) -> float | None:
        """Get relative humidity at 2m."""
        return round(self.forecast_timeseries[0].get('relative_humidity_2m'))

    def get_wind_speed(self) -> float | None:
        """Get wind speed at 10m in the configured API unit."""
        ws = self.forecast_timeseries[0].get('wind_speed_10m')
        return round(ws) if ws is not None else None

    def get_wind_gust(self) -> float | None:
        """Get wind gusts at 10m in the configured API unit."""
        gust = self.forecast_timeseries[0].get('wind_gusts_10m')
        return round(gust) if gust is not None else None

    def get_wind_direction(self) -> float | None:
        """Get wind direction at 10m (degrees, may not be present)."""
        return self.forecast_timeseries[0].get('wind_direction_10m')

    def get_pressure(self) -> float | None:
        """Get surface pressure (may not be present)."""
        return round(self.forecast_timeseries[0].get('surface_pressure'))

    def get_precipitation(self) -> float | None:
        """Get precipitation (mm or %, may not be present)."""
        return self.forecast_timeseries[0].get('precipitation')

    def get_condition(self) -> str:
        """Get weather code or description (not always present in current endpoint)."""
        code = self.forecast_timeseries[0].get('weather_code')
        return str(code) if code is not None else ''

    def get_is_day(self) -> int | None:
        """Get is_day flag (1 for day, 0 for night, may not be present)."""
        return self.forecast_timeseries[0].get('is_day')


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
        times = ts.get('time', [])
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

    def fetch_and_parse_forecast(
        self,
    ) -> tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, str]]:
        """Fetch and return (metadata, timeseries, units dict) as a tuple."""
        # Fetch the full API response
        full_api_response = self.fetch()

        # Set metadata by supplying the full response
        self._get_metadata(full_api_response)

        # Parse and store units by supplying the 'hourly' section
        self._get_units(full_api_response, 'hourly')

        # Parse timeseries by supplying the full response
        self._get_timeseries(full_api_response)

    def get_temperature(self, offset: int = 0) -> float | None:
        point = self.get_point(offset)
        return point.get('temperature_2m')

    def get_humidity(self, offset: int = 0) -> float | None:
        """Get relative humidity at 2m for a given hour."""
        point = self.get_point(offset)
        return round(point.get('relative_humidity_2m'))

    def get_feels_temperature(self, offset: int = 0) -> float | None:
        """Get apparent temperature at 2m for a given hour."""
        point = self.get_point(offset)
        return round(point.get('apparent_temperature'))

    def get_precipitation_probability(self, offset: int = 0) -> float | None:
        """Get precipitation probability for a given hour."""
        point = self.get_point(offset)
        return round(point.get('precipitation_probability'))

    def get_precipitation(self, offset: int = 0) -> float | None:
        """Get precipitation for a given hour."""
        point = self.get_point(offset)
        return point.get('precipitation')

    def get_rain(self, offset: int = 0) -> float | None:
        """Get rain amount for a given hour."""
        point = self.get_point(offset)
        return point.get('rain')

    def get_showers(self, offset: int = 0) -> float | None:
        """Get showers amount for a given hour."""
        point = self.get_point(offset)
        return point.get('showers')

    def get_snowfall(self, offset: int = 0) -> float | None:
        """Get snowfall amount for a given hour."""
        point = self.get_point(offset)
        return point.get('snowfall')

    def get_weather_code(self, offset: int = 0, return_emoji: bool = False) -> str:
        """Get weather code for a given hour."""
        point = self.get_point(offset)
        code = point.get('weather_code')
        cond = get_condition(code) if code is not None else None
        if not cond:
            return str(code)
        if return_emoji:
            # Prefer precomputed emoji (set during parsing), fall back to cond + is_day
            return point.get('weather_emoji') or (cond.night_emoji if point.get('is_day') == 0 else cond.day_emoji)
        return cond.name

    # New helpers for abbreviation/emoji
    def get_condition_abbreviation(self, offset: int = 0) -> str:
        point = self.get_point(offset)
        code = point.get('weather_code')
        cond = get_condition(code) if code is not None else None
        return cond.abbr if cond else str(code)

    def get_condition_emoji(self, offset: int = 0) -> str:
        point = self.get_point(offset)
        code = point.get('weather_code')
        cond = get_condition(code) if code is not None else None
        if not cond:
            return ''
        # Prefer precomputed emoji (set during parsing)
        return point.get('weather_emoji') or (cond.night_emoji if point.get('is_day') == 0 else cond.day_emoji)

    def get_surface_pressure(self, offset: int = 0) -> float | None:
        """Get surface pressure for a given hour."""
        point = self.get_point(offset)
        return round(point.get('surface_pressure'))

    def get_cloud_cover(self, offset: int = 0) -> float | None:
        """Get cloud cover for a given hour."""
        point = self.get_point(offset)
        return round(point.get('cloud_cover'))

    def get_visibility(self, offset: int = 0) -> float | None:
        """Get visibility for a given hour."""
        point = self.get_point(offset)
        if not point:
            return None
        vis = point.get('visibility')
        if vis is None:
            return None
        # Open-Meteo returns visibility in meters; we display rounded kilometers.
        vis = vis / 1000.0
        return round(vis)

    def get_wind_speed(self, offset: int = 0) -> float | None:
        """Get wind speed at 10m for a given hour in the configured API unit."""
        point = self.get_point(offset)
        return point.get('wind_speed_10m')

    def get_wind_gust(self, offset: int = 0) -> float | None:
        """Get wind gusts at 10m for a given hour in the configured API unit."""
        point = self.get_point(offset)
        return round(point.get('wind_gusts_10m'))

    def get_wind_direction(self, offset: int = 0) -> float | None:
        """Get wind direction at 10m for a given hour."""
        point = self.get_point(offset)
        return bearing_to_direction(point.get('wind_direction_10m'))

    def get_uv_index(self, offset: int = 0) -> float | None:
        """Get UV index for a given hour."""
        point = self.get_point(offset)
        return round(point.get('uv_index'))

    def get_us_aqi(self, offset: int = 0) -> float | None:
        point = self.get_point(offset)
        return point.get('us_aqi')

    def get_european_aqi(self, offset: int = 0) -> float | None:
        point = self.get_point(offset)
        return point.get('european_aqi')

    def get_pm2_5(self, offset: int = 0) -> float | None:
        point = self.get_point(offset)
        return point.get('pm2_5')

    def get_pm10(self, offset: int = 0) -> float | None:
        point = self.get_point(offset)
        return point.get('pm10')

    def get_ozone(self, offset: int = 0) -> float | None:
        point = self.get_point(offset)
        return point.get('ozone')

    def get_grass_pollen(self, offset: int = 0) -> float | None:
        point = self.get_point(offset)
        return point.get('grass_pollen')


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
        times = ts.get('time', [])
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

    def fetch_and_parse_forecast(
        self,
    ) -> tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, str]]:
        """Fetch and return (metadata, timeseries, units dict) as a tuple."""
        # Fetch the full API response
        full_api_response = self.fetch()

        # Set metadata by supplying the full response
        self._get_metadata(full_api_response)

        # Parse and store units by supplying the 'daily' section
        self._get_units(full_api_response, 'daily')

        # Parse timeseries by supplying the full response
        self._get_timeseries(full_api_response)

    def get_temperature_min(self, offset: int = 0) -> float | None:
        """Get minimum 2m temperature for a given day."""
        point = self.get_point(offset)
        if not point:
            return None
        return point.get('temperature_2m_min')

    def get_temperature_max(self, offset: int = 0) -> float | None:
        """Get maximum 2m temperature for a given day."""
        point = self.get_point(offset)
        if not point:
            return None
        return point.get('temperature_2m_max')

    def get_precipitation(self, offset: int = 0) -> float | None:
        """Get precipitation sum for a given day."""
        point = self.get_point(offset)
        if not point:
            return None
        return point.get('precipitation_sum')

    def get_precipitation_probability(self, offset: int = 0) -> float | None:
        """Get precipitation probability for a given day (not always present)."""
        point = self.get_point(offset)
        return round(point.get('precipitation_probability_max'))

    def get_weather_code(self, offset: int = 0, return_emoji: bool = False) -> str:
        """Get weather code for a given day."""
        point = self.get_point(offset)
        code = point.get('weather_code')
        cond = get_condition(code) if code is not None else None
        if not cond:
            return str(code)
        if return_emoji:
            return cond.day_emoji
        return cond.name

    def get_condition_abbreviation(self, offset: int = 0) -> str:
        point = self.get_point(offset)
        code = point.get('weather_code')
        cond = get_condition(code) if code is not None else None
        return cond.abbr if cond else str(code)

    def get_wind_speed(self, offset: int = 0) -> float | None:
        """Get max wind speed at 10m for a given day in the configured API unit."""
        point = self.get_point(offset)
        if not point:
            return None
        return point.get('wind_speed_10m_max')

    def get_wind_gust(self, offset: int = 0) -> float | None:
        """Get max wind gusts at 10m for a given day in the configured API unit."""
        point = self.get_point(offset)
        if not point:
            return None
        return point.get('wind_gusts_10m_max')

    def get_wind_direction(self, offset: int = 0) -> float | None:
        """Get dominant wind direction at 10m for a given day."""
        point = self.get_point(offset)
        if not point:
            return None
        return bearing_to_direction(point.get('wind_direction_10m_dominant'))

    def get_sunrise(self, offset: int = 0) -> Optional[str]:
        """Get sunrise time for a given day."""
        point = self.get_point(offset)
        if not point:
            return None
        return point.get('sunrise')

    def get_sunset(self, offset: int = 0) -> Optional[str]:
        """Get sunset time for a given day."""
        point = self.get_point(offset)
        if not point:
            return None
        return point.get('sunset')

    def get_daylight_duration(self, offset: int = 0) -> Optional[int]:
        """Get daylight duration (in seconds) for a given day."""
        point = self.get_point(offset)
        if not point:
            return None
        return point.get('daylight_duration')


# def fetch_all_forecasts(lat: float, lon: float):
#     """Fetches all forecast types in one call and returns forecast objects."""
#     response = OpenMeteoForecast.fetch_all(lat, lon)
#     metadata = OpenMeteoForecast.extract_metadata(response)
#     current_units = OpenMeteoForecast.extract_units(response, 'current')
#     hourly_units = OpenMeteoForecast.extract_units(response, 'hourly')
#     daily_units = OpenMeteoForecast.extract_units(response, 'daily')
#     current = CurrentOpenMeteoForecast(metadata, current_units, response.get('current', {}))
#     hourly = HourlyOpenMeteoForecast(metadata, hourly_units, response.get('hourly', {}))
#     daily = DailyOpenMeteoForecast(metadata, daily_units, response.get('daily', {}))
#     return current, hourly, daily


if __name__ == '__main__':
    import asyncio

    async def main():
        # Few test calls
        lat, lon = 51.5074, -0.1278  # London
        response = await OpenMeteoForecast.fetch_all(lat, lon)
        metadata = OpenMeteoForecast.extract_metadata(response)
        daily_units = OpenMeteoForecast.extract_units(response, 'daily')
        daily = DailyOpenMeteoForecast(metadata, daily_units, response.get('daily', {}))

        print('Metadata:')
        print(metadata)
        print('Sunset tomorrow:')
        print(f' {daily.get_sunset(1)}')

    asyncio.run(main())
