"""Color utilities for weather visualization.

Provides color interpolation and temperature/wind/rain color mapping.
"""

from collections.abc import Mapping, Sequence


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    """Convert a hex color like "#RRGGBB" to an RGB tuple."""
    v = value.strip().lstrip('#')
    if len(v) != 6:
        raise ValueError('hex value must be 6 characters')
    r = int(v[0:2], 16)
    g = int(v[2:4], 16)
    b = int(v[4:6], 16)
    return (r, g, b)


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Convert an RGB tuple to a hex string like "#RRGGBB"."""
    r, g, b = rgb
    return f'#{r:02x}{g:02x}{b:02x}'


def _interpolate_color(
    fraction: float,
    min_colour: str,
    max_colour: str,
    hex_output: bool = False,
) -> str | tuple[int, int, int]:
    """Interpolate between two colors.

    Args:
        fraction: Value from 0.0 to 1.0 indicating position between colors
        min_colour: Starting color as hex "#RRGGBB"
        max_colour: Ending color as hex "#RRGGBB"
        hex_output: Return hex string if True, RGB tuple if False

    Returns:
        Interpolated color as hex string or RGB tuple

    """
    low = _hex_to_rgb(min_colour)
    high = _hex_to_rgb(max_colour)

    rgb = tuple(int(low[i] + (high[i] - low[i]) * fraction) for i in range(3))

    return _rgb_to_hex(rgb) if hex_output else rgb


ThemeStop = tuple[float, str]

_THEME_TEMP_STOPS_CELSIUS: tuple[ThemeStop, ...] = (
    # (-20, 'secondary'),
    # (-10, 'primary'),
    # (0, 'accent'),
    # (10, 'success'),
    # (20, 'warning'),
    # (30, 'error'),
    (-20, 'secondary'),
    (0, 'primary'),
    (10, 'success'),
    (20, 'warning'),
    (30, 'error'),
)

_THEME_TEMP_STOPS_FAHRENHEIT: tuple[ThemeStop, ...] = tuple(
    (round(celsius * 9 / 5 + 32), colour_name) for celsius, colour_name in _THEME_TEMP_STOPS_CELSIUS
)


def _resolve_theme_colour(theme_colours: Mapping[str, str], name: str) -> str | None:
    """Resolve a named theme color with a small fallback chain."""
    fallbacks = {
        'secondary': ('secondary', 'primary', 'accent', 'foreground'),
        'primary': ('primary', 'accent', 'foreground'),
        'accent': ('accent', 'secondary', 'primary', 'foreground'),
        'success': ('success', 'accent', 'primary', 'foreground'),
        'foreground': ('foreground', 'text', 'primary'),
        'warning': ('warning', 'accent', 'primary', 'foreground'),
        'error': ('error', 'warning', 'accent', 'foreground'),
    }
    for candidate in fallbacks.get(name, (name, 'foreground')):
        colour = theme_colours.get(candidate)
        if isinstance(colour, str) and colour.strip():
            return colour
    return None


def _theme_temperature_colour(
    temp: float,
    *,
    theme_colours: Mapping[str, str] | None,
    theme_stops: Sequence[ThemeStop] | None = None,
    unit: str = 'celsius',
    hex_output: bool = False,
) -> str | tuple[int, int, int] | None:
    """Interpolate temperature using named colors from the active theme."""
    if theme_colours is None:
        return None

    stops = tuple(theme_stops or (_THEME_TEMP_STOPS_FAHRENHEIT if unit == 'fahrenheit' else _THEME_TEMP_STOPS_CELSIUS))
    if not stops:
        return None

    stops = tuple(sorted(stops, key=lambda stop: stop[0]))
    if temp <= stops[0][0]:
        colour = _resolve_theme_colour(theme_colours, stops[0][1])
        if colour is None:
            return None
        try:
            rgb = _hex_to_rgb(colour)
        except ValueError:
            return None
        return _rgb_to_hex(rgb) if hex_output else rgb

    if temp >= stops[-1][0]:
        colour = _resolve_theme_colour(theme_colours, stops[-1][1])
        if colour is None:
            return None
        try:
            rgb = _hex_to_rgb(colour)
        except ValueError:
            return None
        return _rgb_to_hex(rgb) if hex_output else rgb

    for (low_temp, low_name), (high_temp, high_name) in zip(stops, stops[1:]):
        if low_temp <= temp <= high_temp:
            low_colour = _resolve_theme_colour(theme_colours, low_name)
            high_colour = _resolve_theme_colour(theme_colours, high_name)
            if low_colour is None or high_colour is None:
                return None
            fraction = (temp - low_temp) / (high_temp - low_temp)
            try:
                return _interpolate_color(fraction, low_colour, high_colour, hex_output)
            except ValueError:
                return None

    return None


# Temperature color scales (threshold: RGB)
_TEMP_SCALES = {
    'met_interpolated_celsius': [
        (-40, (1, 8, 30)),
        (-39, (1, 8, 32)),
        (-38, (1, 9, 35)),
        (-37, (1, 10, 38)),
        (-36, (1, 10, 40)),
        (-35, (1, 11, 43)),
        (-34, (1, 12, 46)),
        (-33, (1, 12, 48)),
        (-32, (1, 13, 51)),
        (-31, (1, 14, 54)),
        (-30, (2, 15, 57)),
        (-29, (2, 15, 59)),
        (-28, (2, 16, 61)),
        (-27, (2, 16, 63)),
        (-26, (2, 17, 65)),
        (-25, (2, 18, 68)),
        (-24, (2, 18, 70)),
        (-23, (2, 19, 72)),
        (-22, (2, 19, 74)),
        (-21, (2, 20, 76)),
        (-20, (2, 21, 79)),
        (-19, (3, 23, 86)),
        (-18, (4, 26, 94)),
        (-17, (5, 29, 102)),
        (-16, (6, 32, 110)),
        (-15, (8, 35, 118)),
        (-14, (19, 45, 124)),
        (-13, (31, 56, 131)),
        (-12, (43, 66, 137)),
        (-11, (55, 77, 144)),
        (-10, (67, 88, 151)),
        (-9, (50, 101, 159)),
        (-8, (47, 116, 170)),
        (-7, (45, 130, 181)),
        (-6, (29, 146, 193)),
        (-5, (38, 161, 199)),
        (-4, (56, 174, 196)),
        (-3, (74, 187, 194)),
        (-2, (96, 195, 193)),
        (-1, (122, 202, 191)),
        (0, (127, 206, 188)),
        (1, (136, 209, 187)),
        (2, (145, 213, 186)),
        (3, (163, 220, 184)),
        (4, (182, 227, 183)),
        (5, (194, 231, 180)),
        (6, (207, 235, 178)),
        (7, (217, 236, 174)),
        (8, (227, 236, 171)),
        (9, (241, 237, 166)),
        (10, (255, 238, 161)),
        (11, (255, 234, 155)),
        (12, (255, 231, 150)),
        (13, (255, 224, 140)),
        (14, (255, 216, 129)),
        (15, (254, 207, 118)),
        (16, (252, 198, 106)),
        (17, (254, 196, 101)),
        (18, (255, 194, 97)),
        (19, (255, 186, 86)),
        (20, (255, 179, 76)),
        (21, (254, 169, 73)),
        (22, (252, 159, 70)),
        (23, (249, 138, 63)),
        (24, (246, 118, 57)),
        (25, (239, 99, 54)),
        (26, (232, 80, 52)),
        (27, (225, 61, 50)),
        (28, (215, 40, 49)),
        (29, (205, 20, 49)),
        (30, (195, 0, 49)),
        (31, (178, 0, 44)),
        (32, (161, 0, 40)),
        (33, (145, 0, 36)),
        (34, (128, 0, 32)),
        (35, (112, 0, 28)),
        (36, (101, 0, 25)),
        (37, (90, 0, 22)),
        (38, (79, 0, 19)),
        (39, (68, 0, 16)),
        (40, (58, 0, 14)),
    ],
    'met_interpolated_fahrenheit': [
        (-40, (1, 8, 30)),  # -40°F
        (-34, (1, 9, 35)),  # -30°F
        (-29, (2, 11, 43)),  # -20°F
        (-23, (2, 15, 59)),  # -10°F
        (-18, (4, 19, 74)),  # 0°F
        (-12, (8, 26, 94)),  # 10°F
        (-7, (29, 45, 130)),  # 20°F
        (-1, (67, 88, 151)),  # 30°F
        (4, (127, 206, 188)),  # 40°F (freezing)
        (10, (182, 227, 183)),  # 50°F
        (16, (227, 236, 171)),  # 60°F
        (21, (255, 238, 161)),  # 70°F
        (27, (254, 207, 118)),  # 80°F
        (32, (255, 179, 76)),  # 90°F
        (38, (246, 118, 57)),  # 100°F
        (43, (225, 61, 50)),  # 110°F
        (49, (195, 0, 49)),  # 120°F
        (54, (161, 0, 40)),  # 130°F
        (60, (128, 0, 32)),  # 140°F
        (66, (101, 0, 25)),  # 150°F
        (71, (79, 0, 19)),  # 160°F
        (77, (68, 0, 16)),  # 170°F
        (82, (58, 0, 14)),  # 180°F
        (88, (48, 0, 12)),  # 190°F
        (93, (38, 0, 10)),  # 200°F
        (99, (28, 0, 8)),  # 210°F
        (104, (18, 0, 6)),  # 220°F
    ],
}

# Backward compatibility alias
_TEMP_SCALES['met_interpolated'] = _TEMP_SCALES['met_interpolated_celsius']


def temp_colour(
    temp: float,
    scale: str = 'met_interpolated',
    hex: bool = False,
    unit: str = 'celsius',
    *,
    theme_colours: Mapping[str, str] | None = None,
    theme_stops: Sequence[ThemeStop] | None = None,
) -> str | tuple[int, int, int]:
    """Get color for temperature using meteorological color scales.

    Args:
        temp: Temperature value (in the unit specified)
        scale: Color scale to use ('met_interpolated' or 'theme_temperature')
        hex: Return hex string if True, RGB tuple if False
        unit: Temperature unit - 'celsius' or 'fahrenheit'
        theme_colours: Textual theme variables used by the theme temperature scale
        theme_stops: Optional custom sequence of ``(temperature, theme_colour_name)`` stops

    Returns:
        Color as hex string or RGB tuple based on temperature thresholds

    """
    temp = float(temp)

    if scale == 'theme_temperature':
        theme_colour = _theme_temperature_colour(
            temp,
            theme_colours=theme_colours,
            theme_stops=theme_stops,
            unit=unit,
            hex_output=hex,
        )
        if theme_colour is not None:
            return theme_colour

    # Auto-detect scale based on unit if using default
    if scale == 'met_interpolated':
        if unit == 'fahrenheit':
            scale_key = 'met_interpolated_fahrenheit'
        else:
            scale_key = 'met_interpolated_celsius'
    else:
        scale_key = scale

    # Get the appropriate scale
    temp_colors = _TEMP_SCALES.get(scale_key, _TEMP_SCALES['met_interpolated_celsius'])

    # Find matching threshold
    color = temp_colors[-1][1]  # Default to warmest color
    for threshold, rgb in temp_colors:
        if temp <= threshold:
            color = rgb
            break

    return _rgb_to_hex(color) if hex else color


def rain_colour(
    value: float,
    *,
    hex: bool = False,
    min_colour: str,
    max_colour: str,
) -> str | tuple[int, int, int]:
    """Calculate color for rain intensity visualization.

    Linearly interpolates between min_colour (0%) and max_colour (100%).

    Args:
        value: Rain percentage (0-100)
        hex: Return hex string if True, RGB tuple if False
        min_colour: Starting color as hex "#RRGGBB"
        max_colour: Ending color as hex "#RRGGBB"

    Returns:
        Color as hex string or RGB tuple

    """
    fraction = max(0.0, min(100.0, float(value))) / 100.0
    return _interpolate_color(fraction, min_colour, max_colour, hex)


def wind_colour(
    value: float,
    *,
    hex: bool = False,
    min_colour: str,
    max_colour: str,
) -> str | tuple[int, int, int]:
    """Calculate color for wind speed visualization.

    Linearly interpolates between min_colour (0 mph) and max_colour (40 mph).

    Args:
        value: Wind speed in mph (clamped to 0-40 range)
        hex: Return hex string if True, RGB tuple if False
        min_colour: Starting color as hex "#RRGGBB"
        max_colour: Ending color as hex "#RRGGBB"

    Returns:
        Color as hex string or RGB tuple

    """
    fraction = max(0.0, min(40.0, float(value))) / 40.0
    return _interpolate_color(fraction, min_colour, max_colour, hex)
