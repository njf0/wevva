"""Messages used by the app and widgets.

Simple classes carry small bits of data between parts of the UI.
"""

from textual.message import Message
from wevva_warnings import CanonicalTropicalSystem

from wevva.alerts import Alert
from wevva.location_metadata import LocationMetadata
from wevva.services.tropical import NearbyTropicalSystem


class PlaceSelected(Message):
    """Sent when the user picks a place in search."""

    def __init__(self, *, location: LocationMetadata):
        """Create the message with the chosen location."""
        super().__init__()
        self.location = location


class SearchQueryReady(Message):
    """Emitted when user query is ready (after debounce)."""

    def __init__(self, query: str):
        super().__init__()
        self.query = query


class SavedLocationSelected(Message):
    """Sent when the user chooses a saved location."""

    def __init__(self, *, location: LocationMetadata):
        super().__init__()
        self.location = location


class WeatherUpdated(Message):
    """Sent when fresh weather data arrives.

    Carries models for current, hourly, daily, and alerts data.
    """

    def __init__(self, *, metadata, current, hourly, daily, alerts: list[Alert] | None = None):
        """Create the message with metadata and models."""
        super().__init__()
        self.metadata = metadata
        self.current = current
        self.hourly = hourly
        self.daily = daily
        self.alerts = alerts or []


class WeatherAlertsUpdated(Message):
    """Sent when alert data arrives after the main forecast."""

    def __init__(
        self,
        alerts: list[Alert] | None = None,
        tropical_systems: list[NearbyTropicalSystem] | None = None,
        canonical_tropical_systems: list[CanonicalTropicalSystem] | None = None,
        tropical_systems_pending: bool = False,
        tropical_systems_loaded: bool = False,
    ):
        super().__init__()
        self.alerts = alerts or []
        self.tropical_systems = tropical_systems or []
        self.canonical_tropical_systems = canonical_tropical_systems or []
        self.tropical_systems_pending = tropical_systems_pending
        self.tropical_systems_loaded = tropical_systems_loaded


class NearbyTropicalSystemSelected(Message):
    """Sent when the selected nearby tropical-system tab changes."""

    def __init__(self, *, system: NearbyTropicalSystem):
        super().__init__()
        self.system = system


class WeatherAlertsProgress(Message):
    """Sent while a background warning query is still running."""

    def __init__(self, *, event: str, payload: dict[str, object]):
        """Create a progress update from the public warning-library callback."""
        super().__init__()
        self.event = event
        self.payload = dict(payload)


class TropicalSystemsProgress(Message):
    """Sent while nearby tropical-system context is being refreshed."""

    def __init__(self, *, event: str, payload: dict[str, object]):
        """Create a progress update from the tropical-system background work."""
        super().__init__()
        self.event = event
        self.payload = dict(payload)


class WeatherAlertSelected(Message):
    """Sent when the selected alert tab changes."""

    def __init__(self, *, alert: Alert):
        super().__init__()
        self.alert = alert


class WeatherFetchFailed(Message):
    """Sent when the weather fetch fails.

    Holds the exception that was raised.
    """

    def __init__(self, error: Exception):
        """Create the message with the error."""
        super().__init__()
        self.error = error


class HourHighlighted(Message):
    """Sent when a user picks an hour column."""

    def __init__(self, index: int) -> None:
        """Create the message with the selected column index."""
        super().__init__()
        self.index = index


class DaySelected(Message):
    """Sent when a user picks a day in the daily table."""

    def __init__(self, index: int) -> None:
        """Create the message with the row index."""
        super().__init__()
        self.index = index
