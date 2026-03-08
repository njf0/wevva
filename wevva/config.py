"""Persistence helpers for Wevva user preferences."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from wevva.constants import (
    DEFAULT_EMOJI_ENABLED,
    DEFAULT_PRECIPITATION_UNIT,
    DEFAULT_TEMPERATURE_UNIT,
    DEFAULT_THEME,
    DEFAULT_WIND_SPEED_UNIT,
    VALID_PRECIPITATION_UNITS,
    VALID_TEMPERATURE_UNITS,
    VALID_WIND_SPEED_UNITS,
)

DEFAULT_PREFERENCES: dict[str, Any] = {
    "temperature_unit": DEFAULT_TEMPERATURE_UNIT,
    "wind_speed_unit": DEFAULT_WIND_SPEED_UNIT,
    "precipitation_unit": DEFAULT_PRECIPITATION_UNIT,
    "theme": DEFAULT_THEME,
    "emoji_enabled": DEFAULT_EMOJI_ENABLED,
    "default_location": None,
    "default_location_metadata": None,
}

_UNSET = object()


def _normalize_unit(value: Any, *, allowed: tuple[str, ...], default: str) -> str:
    """Return a validated unit string with fallback.

    Parameters
    ----------
    value: Any
        Raw unit value loaded from config/CLI.
    allowed: tuple[str, ...]
        Allowed unit strings for the field.
    default: str
        Default value when ``value`` is invalid.

    Returns
    -------
    str
        A valid unit value.
    """
    if isinstance(value, str) and value in allowed:
        return value
    return default


def _normalize_location(value: Any) -> str | None:
    """Return a normalized default location string.

    Parameters
    ----------
    value: Any
        Raw location value loaded from config/CLI.

    Returns
    -------
    str | None
        A stripped location string, or ``None`` when empty/invalid.
    """
    if not isinstance(value, str):
        return None
    location = value.strip()
    return location or None


def _normalize_theme(value: Any) -> str:
    """Return a normalized theme name.

    Parameters
    ----------
    value: Any
        Raw theme value loaded from config/CLI.

    Returns
    -------
    str
        Normalized theme string.
    """
    if isinstance(value, str):
        theme = value.strip()
        if theme:
            return theme
    return DEFAULT_THEME


def _normalize_emoji_enabled(value: Any) -> bool:
    """Return a normalized emoji-enabled flag.

    Parameters
    ----------
    value: Any
        Raw emoji preference loaded from config/CLI.

    Returns
    -------
    bool
        ``True`` when emoji rendering should be enabled.
    """
    if isinstance(value, bool):
        return value
    return DEFAULT_EMOJI_ENABLED


def _normalize_location_metadata(value: Any) -> dict[str, Any] | None:
    """Return a normalized default location metadata object.

    Parameters
    ----------
    value: Any
        Raw metadata loaded from config/CLI.

    Returns
    -------
    dict[str, Any] | None
        Normalized metadata dict with coordinates, or ``None`` when invalid.
    """
    if not isinstance(value, dict):
        return None

    latitude = value.get("latitude")
    longitude = value.get("longitude")
    if not isinstance(latitude, (int, float)) or not isinstance(
        longitude, (int, float)
    ):
        return None

    def _string_field(key: str) -> str:
        raw = value.get(key)
        return raw.strip() if isinstance(raw, str) else ""

    elevation_raw = value.get("elevation")
    elevation = int(elevation_raw) if isinstance(elevation_raw, (int, float)) else None

    return {
        "latitude": float(latitude),
        "longitude": float(longitude),
        "elevation": elevation,
        "name": _string_field("name"),
        "admin": _string_field("admin"),
        "country": _string_field("country"),
        "country_code": _string_field("country_code"),
        "timezone": _string_field("timezone"),
        "timezone_abbreviation": _string_field("timezone_abbreviation"),
    }


def get_config_path() -> Path:
    """Return the config path, creating directories when needed.

    Returns
    -------
    Path
        Path to ``~/.config/wevva/config.json``.
    """
    # Ensure the standard per-user config directory exists.
    config_dir = Path.home() / ".config" / "wevva"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "config.json"


def load_preferences() -> dict[str, Any]:
    """Load and validate user preferences from disk.

    Returns
    -------
    dict[str, Any]
        Validated preference values for display, units, and default location.
    """
    config_path = get_config_path()
    if not config_path.exists():
        return dict(DEFAULT_PREFERENCES)

    try:
        with open(config_path) as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        # Fall back to defaults on corrupt/unreadable config.
        return dict(DEFAULT_PREFERENCES)

    if not isinstance(raw, dict):
        return dict(DEFAULT_PREFERENCES)

    # Normalize every persisted field so downstream code sees valid values.
    return {
        "temperature_unit": _normalize_unit(
            raw.get("temperature_unit"),
            allowed=VALID_TEMPERATURE_UNITS,
            default=DEFAULT_TEMPERATURE_UNIT,
        ),
        "wind_speed_unit": _normalize_unit(
            raw.get("wind_speed_unit"),
            allowed=VALID_WIND_SPEED_UNITS,
            default=DEFAULT_WIND_SPEED_UNIT,
        ),
        "precipitation_unit": _normalize_unit(
            raw.get("precipitation_unit"),
            allowed=VALID_PRECIPITATION_UNITS,
            default=DEFAULT_PRECIPITATION_UNIT,
        ),
        "theme": _normalize_theme(raw.get("theme")),
        "emoji_enabled": _normalize_emoji_enabled(raw.get("emoji_enabled")),
        "default_location": _normalize_location(raw.get("default_location")),
        "default_location_metadata": _normalize_location_metadata(
            raw.get("default_location_metadata")
        ),
    }


def _write_preferences(preferences: dict[str, Any]) -> None:
    """Write preferences to disk.

    Parameters
    ----------
    preferences: dict[str, Any]
        Preferences dictionary to persist.

    Returns
    -------
    None
        The config file is updated in place.
    """
    config_path = get_config_path()
    try:
        with open(config_path, "w") as f:
            json.dump(preferences, f, indent=2)
    except OSError:
        # Avoid crashing the TUI when config cannot be written.
        pass


def save_preferences(
    temperature_unit: str,
    wind_speed_unit: str,
    precipitation_unit: str,
    default_location: str | None | object = _UNSET,
    theme: str | object = _UNSET,
    emoji_enabled: bool | object = _UNSET,
    default_location_metadata: dict[str, Any] | None | object = _UNSET,
) -> None:
    """Persist preferences and optionally update display/location values.

    Parameters
    ----------
    temperature_unit: str
        Requested temperature unit value.
    wind_speed_unit: str
        Requested wind speed unit value.
    precipitation_unit: str
        Requested precipitation unit value.
    default_location: str | None | object
        Optional default location update. When omitted, existing value is preserved.
    theme: str | object
        Optional theme update. When omitted, existing value is preserved.
    emoji_enabled: bool | object
        Optional emoji toggle update. When omitted, existing value is preserved.
    default_location_metadata: dict[str, Any] | None | object
        Optional default location metadata update. When omitted, existing value is preserved.

    Returns
    -------
    None
        Preferences are written to disk when possible.
    """
    # Start from existing preferences so partial updates preserve other fields.
    preferences = load_preferences()
    preferences["temperature_unit"] = _normalize_unit(
        temperature_unit,
        allowed=VALID_TEMPERATURE_UNITS,
        default=DEFAULT_TEMPERATURE_UNIT,
    )
    preferences["wind_speed_unit"] = _normalize_unit(
        wind_speed_unit,
        allowed=VALID_WIND_SPEED_UNITS,
        default=DEFAULT_WIND_SPEED_UNIT,
    )
    preferences["precipitation_unit"] = _normalize_unit(
        precipitation_unit,
        allowed=VALID_PRECIPITATION_UNITS,
        default=DEFAULT_PRECIPITATION_UNIT,
    )
    if default_location is not _UNSET:
        preferences["default_location"] = _normalize_location(default_location)
    if theme is not _UNSET:
        preferences["theme"] = _normalize_theme(theme)
    if emoji_enabled is not _UNSET:
        preferences["emoji_enabled"] = _normalize_emoji_enabled(emoji_enabled)
    if default_location_metadata is not _UNSET:
        preferences["default_location_metadata"] = _normalize_location_metadata(
            default_location_metadata
        )

    _write_preferences(preferences)


def save_default_location(
    default_location: str | None,
    default_location_metadata: dict[str, Any] | None | object = _UNSET,
) -> None:
    """Persist default location data while preserving other preferences.

    Parameters
    ----------
    default_location: str | None
        Location name to save, or ``None`` to clear it.
    default_location_metadata: dict[str, Any] | None | object
        Optional resolved location metadata to persist with the location.

    Returns
    -------
    None
        Preferences are written to disk when possible.
    """
    preferences = load_preferences()
    save_preferences(
        temperature_unit=preferences["temperature_unit"],
        wind_speed_unit=preferences["wind_speed_unit"],
        precipitation_unit=preferences["precipitation_unit"],
        default_location=default_location,
        theme=preferences["theme"],
        emoji_enabled=preferences["emoji_enabled"],
        default_location_metadata=default_location_metadata,
    )
