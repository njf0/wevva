"""Geographic utilities.

Provides wind bearing conversion and country code formatting.
"""


def bearing_to_direction(bearing: float) -> str:
    """Convert wind bearing in degrees to compass direction with arrow.

    Args:
        bearing: Bearing angle in degrees (0-360)

    Returns:
        Direction string like 'N ↓', 'NE ↙', 'E ←', etc.

    Raises:
        ValueError: If bearing is out of 0-360 range

    """
    if not 0 <= bearing <= 360:
        raise ValueError(f'Bearing must be 0-360, got {bearing}')

    # Normalize bearing to 0-360 and find sector (8 compass points)
    directions = ['N ↓', 'NE ↙', 'E ←', 'SE ↖', 'S ↑', 'SW ↗', 'W →', 'NW ↘']
    idx = int((bearing + 22.5) / 45) % 8
    return directions[idx]


def country_code_to_flag(code: str) -> str:
    """Convert ISO 3166-1 alpha-2 country code to flag emoji.

    Args:
        code: Two-letter country code (e.g., 'US', 'GB', 'FR')

    Returns:
        Flag emoji if valid code, otherwise uppercase code or '??'

    Examples:
        'US' -> '🇺🇸', 'GB' -> '🇬🇧', 'invalid' -> 'INVALID'

    """
    FLAG_EMOJI_LENGTH = 2
    if not code or len(code) != FLAG_EMOJI_LENGTH or not code.isalpha():
        return str(code).upper() if code else '??'

    code = code.upper()
    flag = ''.join(chr(0x1F1E6 + ord(c) - ord('A')) for c in code)
    # Basic sanity: flags are two regional indicator symbols
    return flag if len(flag) == FLAG_EMOJI_LENGTH else code
