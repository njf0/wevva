"""Text formatting utilities.

Provides emoji normalization, character width handling, and date formatting.
"""

from wcwidth import wcwidth


def normalize_emoji(emoji: str, target_width: int = 2) -> str:
    """Make emoji a consistent width (default 2 cells) by padding with spaces.

    Args:
        emoji: The emoji string to normalize
        target_width: Desired display width in terminal cells (default 2)

    Returns:
        Emoji padded to target width, or original if already wide enough

    """
    if not emoji:
        return emoji

    # Measure display width across codepoints
    width = 0
    for ch in emoji:
        ch_width = wcwidth(ch)
        width += ch_width if ch_width is not None else 1

    # Pad if needed
    if width < target_width:
        return emoji + ' ' * (target_width - width)

    return emoji


def norm_character_width(cell: str, norm_width: bool = True) -> tuple[str, int]:
    """Normalize character width for table alignment.

    Uses wcwidth to measure display width and pads to 2 cells (for emoji).
    Returns the padded string and an adjustment factor for column width.

    Args:
        cell: String to normalize (typically emoji or short text)
        norm_width: Whether to apply normalization (False returns as-is)

    Returns:
        Tuple of (padded_cell, width_adjustment)

    """
    if not norm_width:
        return cell, 1

    actual_width = sum(wcwidth(char) for char in cell)
    target_width = 2
    expected_width = 1

    # Pad to target width if needed
    if actual_width < target_width:
        padded_cell = cell + ' ' * (target_width - actual_width)
    else:
        padded_cell = cell

    # Calculate adjustment for column sizing
    adjustment = actual_width - expected_width
    if adjustment == 0:
        adjustment = -1
    elif adjustment == 1:
        adjustment = 1

    return padded_cell, adjustment


def date_suffix(day: int) -> str:
    """Return ordinal suffix for a day number (st/nd/rd/th).

    Examples:
        1 -> "st", 2 -> "nd", 3 -> "rd", 4 -> "th"
        11 -> "th", 12 -> "th", 13 -> "th" (special cases)
        21 -> "st", 22 -> "nd", 23 -> "rd"

    """
    if not isinstance(day, int):
        raise TypeError('day must be an integer')

    # Special cases: 11th, 12th, 13th
    if 11 <= day % 100 <= 13:
        return 'th'

    # Regular pattern based on last digit
    return {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
