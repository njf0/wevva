"""Location metadata container.

Typed dataclass holding place details (name, coordinates, timezone, etc.).
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class LocationMetadata:
    """Place information from geocoding and weather API.

    All fields are optional since location data is built up incrementally:
    1. From geocoding: name, country, admin, coordinates, elevation, timezone
    2. From weather API: canonical coordinates, elevation, timezone abbreviation
    """

    # Core geographic data
    latitude: float | None = None
    longitude: float | None = None
    elevation: int | None = None

    # Place identification
    name: str = ''
    admin: str = ''  # Administrative region (e.g., "Scotland")
    country: str = ''
    country_code: str = ''

    # Timezone info
    timezone: str = ''  # IANA identifier (e.g., "Europe/London")
    timezone_abbreviation: str = ''  # e.g., "GMT", "BST"

    @property
    def tz_identifier(self) -> str:
        """Alias for timezone (for backward compatibility)."""
        return self.timezone


def location_metadata_from_place(place: dict[str, Any]) -> LocationMetadata:
    """Build location metadata from one normalized geocoding result."""
    latitude = place.get('latitude')
    longitude = place.get('longitude')
    elevation = place.get('elevation')
    return LocationMetadata(
        latitude=(
            float(latitude)
            if isinstance(latitude, (int, float)) and not isinstance(latitude, bool)
            else None
        ),
        longitude=(
            float(longitude)
            if isinstance(longitude, (int, float)) and not isinstance(longitude, bool)
            else None
        ),
        elevation=(
            int(elevation)
            if isinstance(elevation, (int, float)) and not isinstance(elevation, bool)
            else None
        ),
        name=place.get('name') or '',
        admin=place.get('admin') or '',
        country=place.get('country') or '',
        country_code=place.get('country_code') or '',
        timezone=place.get('tz_identifier') or '',
    )
