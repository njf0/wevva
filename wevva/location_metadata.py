"""Location metadata container.

Typed dataclass holding place details (name, coordinates, timezone, etc.).
"""

from dataclasses import dataclass


@dataclass
class LocationMetadata:
    """Place information from geocoding and weather API.

    All fields are optional since location data is built up incrementally:
    1. From geocoding: name, country, admin, coordinates, timezone
    2. From weather API: elevation, timezone_abbreviation
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
