"""Wevva package."""

from importlib.metadata import PackageNotFoundError, version

from wevva.alerts import Alert, get_alerts
from wevva.api import (
    LocationNotFoundError,
    WevvaAPIError,
    alerts_by_coordinates,
    alerts_by_coordinates_sync,
    forecast_by_coordinates,
    forecast_by_coordinates_sync,
    forecast_by_place,
    forecast_by_place_sync,
    geocode,
    geocode_sync,
)
from wevva.location_metadata import LocationMetadata
from wevva.models import ForecastBundle
from wevva.openmeteo import (
    CurrentOpenMeteoForecast,
    DailyOpenMeteoForecast,
    HourlyOpenMeteoForecast,
)

CurrentForecast = CurrentOpenMeteoForecast
HourlyForecast = HourlyOpenMeteoForecast
DailyForecast = DailyOpenMeteoForecast

__all__ = [
    'Alert',
    'CurrentForecast',
    'CurrentOpenMeteoForecast',
    'DailyForecast',
    'DailyOpenMeteoForecast',
    'ForecastBundle',
    'HourlyForecast',
    'HourlyOpenMeteoForecast',
    'LocationMetadata',
    'LocationNotFoundError',
    'WevvaAPIError',
    '__version__',
    'alerts_by_coordinates',
    'alerts_by_coordinates_sync',
    'forecast_by_coordinates',
    'forecast_by_coordinates_sync',
    'forecast_by_place',
    'forecast_by_place_sync',
    'geocode',
    'geocode_sync',
    'get_alerts',
]

try:
    __version__ = version('wevva')
except PackageNotFoundError:
    __version__ = '0.0.0'
