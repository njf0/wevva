"""Typer CLI to launch and configure Wevva.

Examples:
  wevva
  wevva -l "Edinburgh"
  wevva setup

"""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any

import questionary
import typer
from questionary import Choice, Style
from textual.theme import BUILTIN_THEMES

from wevva.app import Wevva
from wevva.config import add_saved_location, load_preferences, location_metadata_from_config, save_default_location, save_preferences
from wevva.constants import (
    DEFAULT_EMOJI_ENABLED,
    DEFAULT_PRECIPITATION_UNIT,
    DEFAULT_TEMPERATURE_UNIT,
    DEFAULT_THEME,
    DEFAULT_WARNING_LANGUAGE,
    DEFAULT_WIND_SPEED_UNIT,
)
from wevva.location_metadata import LocationMetadata
from wevva.services.geocoding import search_places

app = typer.Typer(add_completion=False, invoke_without_command=True)

# Questionary style tokens use its grammar (qmark, question, answer, pointer, etc.).
SETUP_STYLE = Style(
    [
        ('qmark', 'fg:#5fd7ff bold'),
        ('question', 'fg:#8be9fd bold'),
        ('answer', 'fg:#50fa7b bold'),
        ('pointer', 'fg:#ffb86c bold'),
        ('highlighted', 'fg:#ffb86c bold'),
        ('selected', 'fg:#50fa7b'),
        ('instruction', 'fg:#6272a4 italic'),
        ('text', 'fg:#f8f8f2'),
        ('disabled', 'fg:#6c7086 italic'),
    ]
)


def _to_ident(name: str) -> str:
    """Convert a theme string into a safe enum identifier.

    Parameters
    ----------
    name: str
        Textual theme name.

    Returns
    -------
    str
        Enum-safe identifier.

    """
    return ''.join(ch if ch.isalnum() else '_' for ch in name).upper()


ThemeName = Enum('ThemeName', {_to_ident(n): n for n in BUILTIN_THEMES}, type=str)


class TemperatureUnit(str, Enum):
    """Temperature unit options."""

    CELSIUS = 'celsius'
    FAHRENHEIT = 'fahrenheit'


class WindSpeedUnit(str, Enum):
    """Wind speed unit options."""

    KMH = 'kmh'
    MS = 'ms'
    MPH = 'mph'
    KNOTS = 'kn'


class PrecipitationUnit(str, Enum):
    """Precipitation unit options."""

    MM = 'mm'
    INCH = 'inch'


def _require_answer(answer: Any) -> Any:
    """Ensure interactive prompt returns a value.

    Parameters
    ----------
    answer: Any
        Return value from ``questionary`` prompt.

    Returns
    -------
    Any
        Non-``None`` answer value.

    """
    if answer is None:
        typer.secho('Setup cancelled.', fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)
    return answer


def _format_place(place: dict[str, Any]) -> str:
    """Format a geocoding result for display.

    Parameters
    ----------
    place: dict[str, Any]
        Geocoding result entry.

    Returns
    -------
    str
        Human-readable location label.

    """
    name = place.get('name') or '?'
    admin = (place.get('admin') or '').replace(';', ', ')
    country = place.get('country') or '?'
    if admin:
        return f'{name}, {admin}, {country}'
    return f'{name}, {country}'


def _location_metadata_from_place(place: dict[str, Any]) -> LocationMetadata:
    """Build ``LocationMetadata`` from a geocoding result.

    Parameters
    ----------
    place: dict[str, Any]
        Geocoding result entry.

    Returns
    -------
    LocationMetadata
        Normalized location metadata object.

    """
    return LocationMetadata(
        latitude=place.get('latitude'),
        longitude=place.get('longitude'),
        name=place.get('name') or '',
        admin=place.get('admin') or '',
        country=place.get('country') or '',
        country_code=place.get('country_code') or '',
        timezone=place.get('tz_identifier') or place.get('timezone') or '',
    )


def _location_config_from_metadata(location: LocationMetadata) -> dict[str, Any]:
    """Serialize ``LocationMetadata`` for config persistence.

    Parameters
    ----------
    location: LocationMetadata
        Location metadata object.

    Returns
    -------
    dict[str, Any]
        JSON-serializable location metadata.

    """
    return {
        'latitude': location.latitude,
        'longitude': location.longitude,
        'elevation': location.elevation,
        'name': location.name,
        'admin': location.admin,
        'country': location.country,
        'country_code': location.country_code,
        'timezone': location.timezone,
        'timezone_abbreviation': location.timezone_abbreviation,
    }


def _location_from_saved_metadata(raw: Any) -> LocationMetadata | None:
    """Build ``LocationMetadata`` from saved config metadata.

    Parameters
    ----------
    raw: Any
        Raw value from config.

    Returns
    -------
    LocationMetadata | None
        Parsed location object or ``None`` when metadata is invalid.

    """
    if not isinstance(raw, dict):
        return None
    lat = raw.get('latitude')
    lon = raw.get('longitude')
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    return LocationMetadata(
        latitude=float(lat),
        longitude=float(lon),
        elevation=int(raw['elevation']) if isinstance(raw.get('elevation'), (int, float)) else None,
        name=raw.get('name') or '',
        admin=raw.get('admin') or '',
        country=raw.get('country') or '',
        country_code=raw.get('country_code') or '',
        timezone=raw.get('timezone') or '',
        timezone_abbreviation=raw.get('timezone_abbreviation') or '',
    )


def _lookup_places(query: str, *, count: int = 1) -> list[dict[str, Any]]:
    """Run geocoding lookup with error handling.

    Parameters
    ----------
    query: str
        Location query string.
    count: int
        Maximum number of geocoding candidates.

    Returns
    -------
    list[dict[str, Any]]
        Normalized geocoding candidates.

    """
    try:
        return asyncio.run(search_places(query, count=count, language='en'))
    except Exception as error:
        typer.secho(f'Geocoding failed: {error}', fg=typer.colors.RED)
        return []


def _resolve_first_location(
    query: str,
) -> tuple[LocationMetadata | None, dict[str, Any] | None]:
    """Resolve the first geocoding match for a query.

    Parameters
    ----------
    query: str
        Location query string.

    Returns
    -------
    tuple[LocationMetadata | None, dict[str, Any] | None]
        Parsed location metadata and the raw geocoding entry.

    """
    results = _lookup_places(query, count=1)
    if not results:
        return None, None
    place = results[0]
    return _location_metadata_from_place(place), place


def _questionary_select(title: str, options: list[tuple[str, str]], current: str) -> str:
    """Show a styled single-select prompt and return selected value.

    Parameters
    ----------
    title: str
        Prompt title.
    options: list[tuple[str, str]]
        Sequence of ``(label, value)`` pairs.
    current: str
        Current value shown as selected reference.

    Returns
    -------
    str
        Selected option value.

    """
    ordered = options[:]
    ordered.sort(key=lambda item: item[1] != current)
    choices = [Choice(title=f'{label}{" (current)" if value == current else ""}', value=value) for label, value in ordered]
    return _require_answer(questionary.select(title, choices=choices, style=SETUP_STYLE).ask())


def _run_setup_wizard(preferences: dict[str, Any]) -> dict[str, Any]:
    """Run interactive setup and persist selected defaults.

    Parameters
    ----------
    preferences: dict[str, Any]
        Existing preference values.

    Returns
    -------
    dict[str, Any]
        Reloaded preferences after saving setup selections.

    """
    typer.secho('\nWevva setup wizard\n', fg=typer.colors.CYAN, bold=True)

    theme = _questionary_select(
        'Choose default theme',
        [(name, name) for name in BUILTIN_THEMES],
        str(preferences.get('theme') or DEFAULT_THEME),
    )
    typer.secho(
        'Note: emoji rendering depends on your terminal, font, and locale settings.',
        fg=typer.colors.YELLOW,
    )
    emoji_enabled = bool(
        _require_answer(
            questionary.confirm(
                'Enable emoji rendering by default? (Support varies by terminal/font)',
                default=bool(preferences.get('emoji_enabled', DEFAULT_EMOJI_ENABLED)),
                style=SETUP_STYLE,
            ).ask()
        )
    )

    temperature_unit = _questionary_select(
        'Choose temperature unit',
        [('Celsius (°C)', 'celsius'), ('Fahrenheit (°F)', 'fahrenheit')],
        str(preferences.get('temperature_unit') or DEFAULT_TEMPERATURE_UNIT),
    )
    wind_speed_unit = _questionary_select(
        'Choose wind speed unit',
        [
            ('Kilometers per hour (km/h)', 'kmh'),
            ('Meters per second (m/s)', 'ms'),
            ('Miles per hour (mph)', 'mph'),
            ('Knots (kn)', 'kn'),
        ],
        str(preferences.get('wind_speed_unit') or DEFAULT_WIND_SPEED_UNIT),
    )
    precipitation_unit = _questionary_select(
        'Choose precipitation unit',
        [('Millimeters (mm)', 'mm'), ('Inches (in)', 'inch')],
        str(preferences.get('precipitation_unit') or DEFAULT_PRECIPITATION_UNIT),
    )
    warning_language = _questionary_select(
        'Choose warning language',
        [('Auto (provider default)', 'auto'), ('English', 'en')],
        str(preferences.get('warning_language') or DEFAULT_WARNING_LANGUAGE),
    )

    use_default_location = bool(
        _require_answer(
            questionary.confirm(
                'Set a default location?',
                default=bool(preferences.get('default_location')),
                style=SETUP_STYLE,
            ).ask()
        )
    )
    default_location: str | None = None
    default_location_metadata: dict[str, Any] | None = None
    if use_default_location:
        current_location = str(preferences.get('default_location') or '')
        location_query = str(
            _require_answer(
                questionary.text(
                    'Location search',
                    default=current_location,
                    style=SETUP_STYLE,
                ).ask()
            )
        ).strip()
        if location_query:
            candidates = _lookup_places(location_query, count=5)
            if candidates:
                selected = _require_answer(
                    questionary.select(
                        'Select default location',
                        choices=[Choice(title=_format_place(place), value=place) for place in candidates],
                        style=SETUP_STYLE,
                    ).ask()
                )
                selected_location = _location_metadata_from_place(selected)
                default_location = _format_place(selected)
                default_location_metadata = _location_config_from_metadata(selected_location)
            else:
                save_raw = bool(
                    _require_answer(
                        questionary.confirm(
                            'No geocoding matches found. Save raw location text anyway?',
                            default=True,
                            style=SETUP_STYLE,
                        ).ask()
                    )
                )
                if save_raw:
                    default_location = location_query

    save_preferences(
        temperature_unit=temperature_unit,
        wind_speed_unit=wind_speed_unit,
        precipitation_unit=precipitation_unit,
        default_location=default_location,
        theme=theme,
        emoji_enabled=emoji_enabled,
        warning_language=warning_language,
        default_location_metadata=default_location_metadata,
    )
    typer.secho('\nSetup saved.', fg=typer.colors.GREEN)
    return load_preferences()


def _resolve_initial_location(preferences: dict[str, Any], cli_location: str | None) -> LocationMetadata | None:
    """Resolve startup location with CLI and config precedence.

    Parameters
    ----------
    preferences: dict[str, Any]
        Current preference values.
    cli_location: str | None
        Explicit location from CLI.

    Returns
    -------
    LocationMetadata | None
        Initial location metadata for app startup.

    """
    if cli_location:
        location, _ = _resolve_first_location(cli_location)
        if location is None:
            typer.secho('No results found; starting with search screen.', fg=typer.colors.YELLOW)
        return location

    saved_locations = [
        location_metadata_from_config(item) for item in preferences.get('saved_locations', [])
    ]
    saved_locations = [location for location in saved_locations if location is not None]
    if saved_locations:
        return saved_locations[0]

    from_metadata = _location_from_saved_metadata(preferences.get('default_location_metadata'))
    if from_metadata is not None:
        return from_metadata

    saved_query = preferences.get('default_location')
    if isinstance(saved_query, str) and saved_query.strip():
        location, _ = _resolve_first_location(saved_query)
        if location is not None:
            save_default_location(
                saved_query,
                default_location_metadata=_location_config_from_metadata(location),
            )
        return location
    return None


def _apply_default_location_mutations(
    *,
    set_default_location: str | None,
    clear_default_location: bool,
) -> dict[str, Any]:
    """Apply CLI default-location update flags and return fresh preferences.

    Parameters
    ----------
    set_default_location: str | None
        Location text to persist as default.
    clear_default_location: bool
        Whether to clear saved default location.

    Returns
    -------
    dict[str, Any]
        Reloaded preferences after applying updates.

    """
    if clear_default_location:
        save_default_location(None, default_location_metadata=None)
        typer.secho('Cleared saved default location.', fg=typer.colors.GREEN)

    if set_default_location:
        location_meta, place = _resolve_first_location(set_default_location)
        if location_meta is not None and place is not None:
            label = _format_place(place)
            save_default_location(
                label,
                default_location_metadata=_location_config_from_metadata(location_meta),
            )
            add_saved_location(location_meta)
            typer.secho(f'Saved default location: {label}', fg=typer.colors.GREEN)
        else:
            save_default_location(set_default_location, default_location_metadata=None)
            typer.secho(
                'Saved location text, but geocoding failed; Wevva will retry at launch.',
                fg=typer.colors.YELLOW,
            )

    return load_preferences()


def _launch_wevva(
    preferences: dict[str, Any],
    *,
    location: str | None,
    theme: ThemeName | None,
    emoji: bool | None,
    temperature_unit: TemperatureUnit | None,
    wind_speed_unit: WindSpeedUnit | None,
    precipitation_unit: PrecipitationUnit | None,
) -> None:
    """Launch the app using saved preferences with optional CLI overrides.

    Parameters
    ----------
    preferences: dict[str, Any]
        Loaded preference values.
    location: str | None
        Optional startup location override.
    theme: ThemeName | None
        Optional theme override.
    emoji: bool | None
        Optional emoji toggle override.
    temperature_unit: TemperatureUnit | None
        Optional temperature unit override.
    wind_speed_unit: WindSpeedUnit | None
        Optional wind speed unit override.
    precipitation_unit: PrecipitationUnit | None
        Optional precipitation unit override.

    Returns
    -------
    None
        Runs the Textual app.

    """
    final_temp = temperature_unit.value if temperature_unit else preferences.get('temperature_unit', DEFAULT_TEMPERATURE_UNIT)
    final_wind = wind_speed_unit.value if wind_speed_unit else preferences.get('wind_speed_unit', DEFAULT_WIND_SPEED_UNIT)
    final_precip = (
        precipitation_unit.value if precipitation_unit else preferences.get('precipitation_unit', DEFAULT_PRECIPITATION_UNIT)
    )

    saved_theme = preferences.get('theme')
    if not isinstance(saved_theme, str) or saved_theme not in BUILTIN_THEMES:
        saved_theme = DEFAULT_THEME
    theme_name = theme.value if theme else saved_theme
    emoji_enabled = emoji if emoji is not None else bool(preferences.get('emoji_enabled', DEFAULT_EMOJI_ENABLED))
    warning_language = str(preferences.get('warning_language', DEFAULT_WARNING_LANGUAGE))
    initial_location = _resolve_initial_location(preferences, location)
    saved_locations = [
        location_metadata_from_config(item) for item in preferences.get('saved_locations', [])
    ]
    saved_locations = [saved_location for saved_location in saved_locations if saved_location is not None]

    Wevva(
        initial_location=initial_location,
        emoji_enabled=emoji_enabled,
        theme_name=theme_name,
        warning_language=warning_language,
        temperature_unit=final_temp,
        wind_speed_unit=final_wind,
        precipitation_unit=final_precip,
        saved_locations=saved_locations,
    ).run()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    location: str | None = typer.Option(
        None,
        '--location',
        '-l',
        help='Location name to start at, bypassing search screen.',
    ),
    set_default_location: str | None = typer.Option(
        None,
        '--set-default-location',
        help='Save a default location used when --location is not supplied.',
    ),
    clear_default_location: bool = typer.Option(
        False,
        '--clear-default-location',
        help='Clear any saved default location.',
    ),
    theme: ThemeName | None = typer.Option(
        None,
        '--theme',
        '-t',
        help='Textual theme to use (defaults to saved preference).',
    ),
    emoji: bool | None = typer.Option(
        None,
        '--emoji/--no-emoji',
        help='Enable or disable emoji globally (support varies by terminal/font; defaults to saved preference).',
    ),
    temperature_unit: TemperatureUnit | None = typer.Option(
        None,
        '--temperature-unit',
        '-temp',
        help='Temperature unit (defaults to saved preference)',
    ),
    wind_speed_unit: WindSpeedUnit | None = typer.Option(
        None,
        '--wind-speed-unit',
        '-wind',
        help='Wind speed unit (defaults to saved preference)',
    ),
    precipitation_unit: PrecipitationUnit | None = typer.Option(
        None,
        '--precipitation-unit',
        '-precip',
        help='Precipitation unit (defaults to saved preference)',
    ),
) -> None:
    """Launch the Wevva TUI."""
    if ctx.invoked_subcommand is not None:
        return

    preferences = _apply_default_location_mutations(
        set_default_location=set_default_location,
        clear_default_location=clear_default_location,
    )
    _launch_wevva(
        preferences,
        location=location,
        theme=theme,
        emoji=emoji,
        temperature_unit=temperature_unit,
        wind_speed_unit=wind_speed_unit,
        precipitation_unit=precipitation_unit,
    )


@app.command()
def setup(
    no_launch: bool = typer.Option(False, '--no-launch', help='Save setup and exit without launching the TUI.'),
) -> None:
    """Run interactive setup for defaults using a styled questionary flow."""
    preferences = load_preferences()
    preferences = _run_setup_wizard(preferences)
    if no_launch:
        return
    _launch_wevva(
        preferences,
        location=None,
        theme=None,
        emoji=None,
        temperature_unit=None,
        wind_speed_unit=None,
        precipitation_unit=None,
    )
