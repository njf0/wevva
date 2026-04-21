"""Weather condition model and mapping.

Defines a dataclass for WMO weather codes with full name, abbreviation,
day/night emojis, and a theme color variable hint. Supersedes WEATHER_CODES.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Condition:
    code: int
    name: str
    abbr: str
    day_emoji: str
    night_emoji: str
    color_var: str | None = None  # e.g., 'warning', 'danger', 'primary'


# Minimal mapping covering common codes; extend as needed.
CONDITIONS: dict[int, Condition] = {
    0: Condition(0, 'Clear sky', 'CS', '☀️', '🌙', 'text-warning'),
    1: Condition(1, 'Mainly clear', 'MC', '🌤️', '🌙', 'text-warning'),
    2: Condition(2, 'Partly cloudy', 'PC', '⛅', '🌙', 'foreground-darken-1'),
    3: Condition(3, 'Overcast', 'OC', '☁️', '☁️', 'foreground-darken-2'),
    45: Condition(45, 'Fog', 'FG', '🌫️', '🌫️', 'foreground-darken-2'),
    48: Condition(48, 'Fog', 'FG', '🌫️', '🌫️', 'foreground-darken-2'),
    51: Condition(51, 'Light drizzle', 'DZ', '🌦️', '🌦️', 'text-primary'),
    53: Condition(53, 'Moderate drizzle', 'DZ', '🌧️', '🌧️', 'text-primary'),
    55: Condition(55, 'Heavy drizzle', 'DZ', '🌧️', '🌧️', 'text-primary'),
    56: Condition(56, 'Light freezing drizzle', 'DZ', '🌧️', '🌧️', 'text-primary'),
    57: Condition(57, 'Heavy freezing drizzle', 'DZ', '🌧️', '🌧️', 'text-primary'),
    61: Condition(61, 'Light rain', 'RA', '🌧️', '🌧️', 'text-primary'),
    63: Condition(63, 'Moderate rain', 'RA', '🌧️', '🌧️', 'text-primary'),
    65: Condition(65, 'Heavy rain', 'RA', '🌧️', '🌧️', 'text-primary'),
    66: Condition(66, 'Light freezing rain', 'RA', '🌧️', '🌧️', 'text-primary'),
    67: Condition(67, 'Heavy freezing rain', 'RA', '🌧️', '🌧️', 'text-primary'),
    71: Condition(71, 'Light snow', 'SN', '🌨️', '🌨️', 'foreground'),
    73: Condition(73, 'Moderate snow', 'SN', '🌨️', '🌨️', 'foreground'),
    75: Condition(75, 'Heavy snow', 'SN', '🌨️', '🌨️', 'foreground'),
    77: Condition(77, 'Moderate snow', 'SN', '🌨️', '🌨️', 'foreground'),
    80: Condition(80, 'Light rain showers', 'RA', '🌦️', '🌦️', 'text-primary'),
    81: Condition(81, 'Moderate rain showers', 'RA', '🌧️', '🌧️', 'text-primary'),
    82: Condition(82, 'Heavy rain showers', 'RA', '🌧️', '🌧️', 'text-primary'),
    85: Condition(85, 'Light snow showers', 'SN', '🌨️', '🌨️', 'foreground'),
    86: Condition(86, 'Heavy snow showers', 'SN', '🌨️', '🌨️', 'foreground'),
    95: Condition(95, 'Thunderstorm', 'TS', '⛈️', '⛈️', 'text-accent'),
    96: Condition(96, 'Thunderstorm with light hail', 'TS', '⛈️', '⛈️', 'text-accent'),
    99: Condition(99, 'Thunderstorm with heavy hail', 'TS', '⛈️', '⛈️', 'text-accent'),
}


def get_condition(code: int) -> Condition | None:
    return CONDITIONS.get(code)
