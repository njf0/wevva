"""Deterministic weather data shared by layout and widget tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from wevva.alerts import Alert
from wevva.location_metadata import LocationMetadata
from wevva.messages import WeatherUpdated
from wevva.openmeteo import DailyOpenMeteoForecast, HourlyOpenMeteoForecast
from wevva.widgets.location_map import LocationMapGeometry, build_location_map_geometry


FIXTURE_START = datetime(2030, 9, 22, 5, tzinfo=ZoneInfo('America/Chicago'))


def chicago_location() -> LocationMetadata:
    """Return a fresh, fixed location suitable for country-map rendering."""

    return LocationMetadata(
        latitude=41.8781,
        longitude=-87.6298,
        elevation=178,
        name='Chicago',
        admin='Illinois',
        country='United States',
        country_code='US',
        timezone='America/Chicago',
        timezone_abbreviation='CDT',
    )


def hourly_forecast() -> HourlyOpenMeteoForecast:
    """Return 72 fixed hourly observations without consulting wall-clock time."""

    metadata = chicago_location()
    units = {
        'temperature_2m': '°C',
        'apparent_temperature': '°C',
        'precipitation_probability': '%',
        'precipitation': 'mm',
        'wind_speed_10m': 'mp/h',
        'wind_gusts_10m': 'mp/h',
        'surface_pressure': 'hPa',
    }
    forecast = HourlyOpenMeteoForecast(metadata, units, {})
    forecast.forecast_timeseries = []
    for offset in range(72):
        hour = FIXTURE_START + timedelta(hours=offset)
        daytime = 1 if 7 <= hour.hour < 19 else 0
        forecast.forecast_timeseries.append(
            {
                'time': hour,
                'temperature_2m': 13 + (offset % 8),
                'apparent_temperature': 11 + (offset % 8),
                'relative_humidity_2m': 76 - (offset % 12),
                'precipitation_probability': (offset * 3) % 36,
                'precipitation': round((offset % 5) * 0.1, 1),
                'rain': round((offset % 4) * 0.1, 1),
                'showers': 0.0,
                'snowfall': 0.0,
                'weather_code': (3, 2, 61, 1)[offset % 4],
                'is_day': daytime,
                'surface_pressure': 1002 + (offset % 4),
                'cloud_cover': 35 + (offset % 60),
                'visibility': 18_000,
                'wind_speed_10m': 8 + (offset % 9),
                'wind_gusts_10m': 14 + (offset % 12),
                'wind_direction_10m': 90,
                'uv_index': 3 if daytime else 0,
                'us_aqi': 42,
                'european_aqi': 31,
                'pm2_5': 5.4,
                'pm10': 7.1,
                'ozone': 64,
                'grass_pollen': 0,
            }
        )
    return forecast


def daily_forecast() -> DailyOpenMeteoForecast:
    """Return seven fixed daily observations."""

    metadata = chicago_location()
    units = {
        'temperature_2m_min': '°C',
        'temperature_2m_max': '°C',
        'precipitation_probability_max': '%',
        'precipitation_sum': 'mm',
        'wind_speed_10m_max': 'mp/h',
        'wind_gusts_10m_max': 'mp/h',
    }
    dates = [(FIXTURE_START + timedelta(days=offset)).date() for offset in range(7)]
    timeseries = {
        'time': [date.isoformat() for date in dates],
        'weather_code': [3, 3, 61, 2, 80, 61, 3],
        'temperature_2m_min': [13, 14, 15, 14, 15, 15, 16],
        'temperature_2m_max': [16, 19, 20, 17, 18, 20, 21],
        'precipitation_probability_max': [6, 0, 8, 2, 12, 9, 4],
        'precipitation_sum': [0.0, 0.0, 0.4, 0.0, 1.1, 0.3, 0.0],
        'wind_speed_10m_max': [16, 12, 8, 6, 7, 4, 7],
        'wind_gusts_10m_max': [26, 19, 16, 12, 14, 6, 12],
        'wind_direction_10m_dominant': [45, 90, 90, 135, 90, 90, 90],
        'sunrise': [f'{date.isoformat()}T06:{39 + offset:02d}' for offset, date in enumerate(dates)],
        'sunset': [f'{date.isoformat()}T18:{45 - offset:02d}' for offset, date in enumerate(dates)],
        'daylight_duration': [43_560 - offset * 120 for offset in range(7)],
    }
    return DailyOpenMeteoForecast(metadata, units, timeseries)


def warning_alerts() -> list[Alert]:
    """Return fixed alerts with different severities and useful long copy."""

    return [
        Alert(
            id='fixture-heat',
            source='nws',
            event='Heat Warning',
            severity='Severe',
            headline='Severe Heat Warning for Cook County',
            description='Dangerously hot conditions are expected during the afternoon.',
            instruction='Drink water and avoid prolonged exposure to the sun.',
        ),
        Alert(
            id='fixture-beach',
            source='nws',
            event='Beach Hazards Statement',
            severity='Moderate',
            headline='High waves and dangerous currents along Lake Michigan',
            description='Waves of five to eight feet are expected.',
        ),
    ]


def weather_update(*, with_warnings: bool = True) -> WeatherUpdated:
    """Return a complete fixed weather message for rendered layout tests."""

    hourly = hourly_forecast()
    return WeatherUpdated(
        metadata=chicago_location(),
        current=hourly,
        hourly=hourly,
        daily=daily_forecast(),
        alerts=warning_alerts() if with_warnings else [],
    )


def location_map_geometry() -> LocationMapGeometry:
    """Return the fixed US country component used by map layout tests."""

    location = chicago_location()
    geometry = build_location_map_geometry(
        latitude=location.latitude,
        longitude=location.longitude,
        location_name=location.name,
        country_code=location.country_code,
    )
    assert geometry is not None
    return geometry

