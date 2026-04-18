"""Location info table.

Shows selected place with country, admin, coords, elevation, and timezone
as a compact two-column DataTable.
Keeps legacy id so styles still apply.
"""

from __future__ import annotations

import datetime
from typing import Any

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import DataTable
from zoneinfo import ZoneInfo


class LocationInfo(DataTable):
    """Two-column table with location details (legacy id preserved)."""

    # Reactive properties (set by parent ContextBar)
    forecast_metadata: reactive[Any | None] = reactive(None)
    location: reactive[Any | None] = reactive(None)

    DEFAULT_CSS = """
    LocationInfo {
        height: auto;
        width: auto;
        border: round $primary;
        border-title-color: $primary;
        border-title-align: left;
        margin-right: 2;
    }
    """

    def __init__(self, *, id: str = "location-info", classes: str = "weather-widget"):
        """Initialize the two-column location info table."""
        super().__init__(show_header=False, cursor_type="none", id=id, classes=classes)
        self.border_title = "Location Data"
        self.add_column("Label", key="label", width=8)
        self.add_column("Value", key="value")
        self.add_row(Text("", style="dim"), Text("", style="bold dim"), key="date")
        self.add_row(Text("", style="dim"), Text("", style="bold dim"), key="time")
        self.add_row(Text("", style="dim"), Text("", style="bold dim"), key="tz")
        self.add_row(Text("", style="dim"), Text("", style="bold dim"), key="coords")
        self.add_row(Text("", style="dim"), Text("", style="bold dim"), key="elev")

    def on_mount(self) -> None:
        """Trigger initial display after mounting."""
        if self.forecast_metadata is not None or self.location is not None:
            self._update_display()

    def watch_forecast_metadata(self, metadata: Any | None) -> None:
        """React to forecast metadata changes."""
        if self.is_mounted:
            self._update_display()

    def watch_location(self, location: Any | None) -> None:
        """React to location changes."""
        if self.is_mounted:
            self._update_display()

    def refresh_display(self) -> None:
        """Public method to force a display refresh (called by timer for time updates)."""
        if self.is_mounted:
            self._update_display()

    @staticmethod
    def _fmt_lat(val: float | None) -> str:
        if val is None:
            return ""
        hemi = "N" if val >= 0 else "S"
        return f"{abs(val):.3f}°{hemi}"

    @staticmethod
    def _fmt_lon(val: float | None) -> str:
        if val is None:
            return ""
        hemi = "E" if val >= 0 else "W"
        return f"{abs(val):.3f}°{hemi}"

    # date/time helper removed; building inline in `_update_display()` to apply theme colors

    def _update_display(self) -> None:
        """Update table cells using location and forecast metadata."""
        # Cache theme vars for this update
        theme = self.app.theme_variables

        # Extract all data
        data = self._extract_location_data(self.forecast_metadata, self.location)

        # Build datetime displays with timezone
        date_text, time_text, tz_text = self._build_datetime_displays(
            data["tz_identifier"], theme
        )

        # Build coordinate and elevation displays
        coords_text = self._build_coords_display(
            data["lat_val"], data["lon_val"], theme
        )
        elev_text = self._build_elev_display(data["elev_val"], theme)

        self._update_row("date", "Date", date_text)
        self._update_row("time", "Time", time_text)
        self._update_row("tz", "Timezone", tz_text)
        self._update_row("coords", "Coords", coords_text)
        self._update_row("elev", "Elev", elev_text)

        self.refresh()

    def _extract_location_data(
        self, forecast_metadata: object | None, location: object | None
    ) -> dict:
        """Extract all location fields from forecast metadata and location dataclass."""
        # Try forecast metadata first (dict or dataclass)
        lat_val = self._get_attr_or_key(forecast_metadata, "latitude")
        lon_val = self._get_attr_or_key(forecast_metadata, "longitude")
        elev_val = self._get_attr_or_key(forecast_metadata, "elevation")
        tz_identifier = self._get_attr_or_key(forecast_metadata, "timezone")

        # Fallback to location dataclass for timezone
        if not tz_identifier and location:
            tz_identifier = getattr(location, "timezone", "")

        return {
            "lat_val": lat_val,
            "lon_val": lon_val,
            "elev_val": elev_val,
            "tz_identifier": tz_identifier,
        }

    def _get_attr_or_key(self, obj: object | None, key: str) -> object | None:
        """Get value from object (dict or dataclass) or return None."""
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    def _build_datetime_displays(
        self, tz_identifier: str | None, theme: dict
    ) -> tuple[Text, Text, Text]:
        """Build formatted date, time, and timezone displays with theme colors."""
        # Get current time in forecast timezone
        tzinfo = (
            ZoneInfo(tz_identifier)
            if tz_identifier
            else datetime.datetime.now().astimezone().tzinfo
        )
        now = datetime.datetime.now(tzinfo)

        # Build date text
        date_text = Text.from_markup(
            f"[bold {theme.get('primary')}]{now.strftime('%A %d %B %Y')}[/]"
        )

        # Build time text with timezone abbreviation and GMT offset
        tz_abbr = now.tzname() or now.strftime("%Z") or "UTC"
        offset_str = self._format_gmt_offset(now.utcoffset())
        time_text = Text.from_markup(
            f"[bold][{theme.get('secondary')}]{now.strftime('%H:%M:%S')}[/bold] {tz_abbr} ({offset_str})[/]"
        )

        # Build timezone identifier text
        tz_text = (
            Text.from_markup(f"[bold {theme.get('warning')}]{tz_identifier}[/]")
            if tz_identifier
            else Text("")
        )

        return date_text, time_text, tz_text

    def _format_gmt_offset(self, offset: datetime.timedelta | None) -> str:
        """Format UTC offset as GMT±HH:MM string."""
        if offset is None:
            return "GMT+00:00"

        total_seconds = int(offset.total_seconds())
        sign = "+" if total_seconds >= 0 else "-"
        total_seconds = abs(total_seconds)
        hours, rem = divmod(total_seconds, 3600)
        minutes = rem // 60
        return f"GMT{sign}{hours:02}:{minutes:02}"

    def _build_coords_display(
        self, lat_val: float | None, lon_val: float | None, theme: dict
    ) -> Text:
        """Build formatted coordinate display with theme color."""
        lat = self._fmt_lat(lat_val)
        lon = self._fmt_lon(lon_val)
        if lat_val is not None and lon_val is not None:
            url = f"https://www.openstreetmap.org/#map=8/{lat_val:.5f}/{lon_val:.5f}"
            return Text.from_markup(
                f"[link={url}][italic {theme.get('accent')}]{lat}[/], [italic {theme.get('accent')}]{lon}[/][/]"
            )
        return Text.from_markup(
            f"[italic {theme.get('accent')}]{lat}[/], [italic {theme.get('accent')}]{lon}[/]"
        )

    def _build_elev_display(self, elev_val: float | int | None, theme: dict) -> Text:
        """Build formatted elevation display with theme color."""
        elev = (
            str(int(elev_val))
            if isinstance(elev_val, (int, float))
            else (str(elev_val) if elev_val else "")
        )
        return Text.from_markup(
            f"[bold {theme.get('error')}]{f'{elev}m' if elev else ''}[/]"
        )

    def _update_row(self, key: str, label: str, value: Text) -> None:
        """Update a single table row with label and value."""
        self.update_cell(key, "label", Text(label, style="dim"))
        self.update_cell(key, "value", value, update_width=True)
