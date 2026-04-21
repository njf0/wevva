"""Context bar widget.

Displays location metadata, astronomy data (sun/moon), and air quality.
Composite container that coordinates reactive state across child widgets.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Container
from textual.reactive import reactive

from wevva.messages import WeatherUpdated
from wevva.widgets.air_quality import AirQualityWidget
from wevva.widgets.astronomy_info import AstronomyInfo
from wevva.widgets.location_info import LocationInfo


class ContextBar(Container):
    """Container for location info, astronomy data, and air quality widgets."""

    # Reactive state
    forecast_metadata: reactive[Any | None] = reactive(None)
    daily_model: reactive[Any | None] = reactive(None)
    hourly_model: reactive[Any | None] = reactive(None)
    location_metadata: reactive[Any | None] = reactive(None)

    DEFAULT_CSS = """
    ContextBar {
        layout: horizontal;
        height: auto;
        align-vertical: top;
        align-horizontal: center;
        content-align: center middle;
        hatch: right $background-lighten-1;
    }
    """

    def compose(self) -> ComposeResult:  # type: ignore[override]
        """Compose location info and astronomy widgets."""
        yield LocationInfo()
        yield AstronomyInfo()
        yield AirQualityWidget()

    # Property accessors for child widgets
    @property
    def location(self) -> LocationInfo:
        return self.query_one(LocationInfo)

    @property
    def astronomy(self) -> AstronomyInfo:
        return self.query_one(AstronomyInfo)

    @property
    def air_quality(self) -> AirQualityWidget:
        return self.query_one(AirQualityWidget)

    def on_mount(self) -> None:
        """Trigger initial display after mounting."""
        if self.forecast_metadata is not None and self.daily_model is not None:
            self._update_display()

    # Reactive watchers ---------------------------------------------------
    def watch_forecast_metadata(self, metadata: Any | None) -> None:
        """React to forecast metadata changes."""
        if metadata is not None and self.daily_model is not None and self.is_mounted:
            self._update_display()

    def watch_daily_model(self, model: Any | None) -> None:
        """React to daily model changes."""
        if model is not None and self.forecast_metadata is not None and self.is_mounted:
            self._update_display()

    def watch_location_metadata(self, metadata: Any | None) -> None:
        """React to location metadata changes."""
        if metadata is not None and self.is_mounted:
            self._update_display()

    def _update_display(self) -> None:
        """Update all child widgets with current data."""
        if self.forecast_metadata is None or self.daily_model is None:
            return

        # Update location info - set reactive properties (widget updates itself)
        self.location.forecast_metadata = self.forecast_metadata
        self.location.location = self.app.location

        # Update astronomy details - set reactive properties (widget updates itself)
        self.astronomy.forecast_metadata = self.forecast_metadata
        self.astronomy.daily_model = self.daily_model

    def refresh_time_display(self) -> None:
        """Public method to refresh time display (called by timer)."""
        if self.is_mounted and self.forecast_metadata is not None and self.daily_model is not None:
            # Call public refresh methods on child widgets to force time updates
            self.location.refresh_display()
            self.astronomy.refresh_display()

    # ----------------------- Messages -----------------------
    async def on_weather_updated(self, event: WeatherUpdated) -> None:  # type: ignore[override]
        """Update location and info when new data arrives."""
        self.forecast_metadata = event.daily.forecast_metadata
        self.daily_model = event.daily
        self.hourly_model = event.hourly
        self.location_metadata = event.metadata

        # Set air quality widget reactive properties (widget updates itself)
        self.air_quality.hourly_model = event.hourly
        self.air_quality.location = event.metadata
        self.air_quality.hour_index = 0

    # Public API for WeatherScreen to forward hour highlights
    def on_hour_highlighted(self, hour_index: int) -> None:
        """Forward hour highlight to contained widgets (air quality)."""
        self.air_quality.hour_index = hour_index
