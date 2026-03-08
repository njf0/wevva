"""Public data models for library consumers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from wevva.location_metadata import LocationMetadata
from wevva.openmeteo import (
    CurrentOpenMeteoForecast,
    DailyOpenMeteoForecast,
    HourlyOpenMeteoForecast,
)


@dataclass(slots=True)
class ForecastBundle:
    """Container for one complete weather snapshot."""

    metadata: LocationMetadata
    current: CurrentOpenMeteoForecast
    hourly: HourlyOpenMeteoForecast
    daily: DailyOpenMeteoForecast
    raw: dict[str, Any]
