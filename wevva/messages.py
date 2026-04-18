"""Messages used by the app and widgets.

Simple classes carry small bits of data between parts of the UI.
"""

from textual.message import Message

from wevva.alerts import Alert
from wevva.location_metadata import LocationMetadata


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


class WeatherUpdated(Message):
    """Sent when fresh weather data arrives.

    Carries models for current, hourly, daily, and alerts data.
    """

    def __init__(
        self, *, metadata, current, hourly, daily, alerts: list[Alert] | None = None
    ):
        """Create the message with metadata and models."""
        super().__init__()
        self.metadata = metadata
        self.current = current
        self.hourly = hourly
        self.daily = daily
        self.alerts = alerts or []


class WeatherAlertsUpdated(Message):
    """Sent when alert data arrives after the main forecast."""

    def __init__(self, alerts: list[Alert] | None = None):
        super().__init__()
        self.alerts = alerts or []


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
