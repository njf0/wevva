"""Visualization utilities for weather data.

Provides block character generation for temperature and rain charts.
"""


def create_temp_blocks(temps: list[float], width: int = 3) -> list[str]:
    """Build block characters representing temperature values.

    Args:
        temps: List of temperature values
        width: Number of block characters per entry (default 3)

    Returns:
        List of block strings, one per temperature

    """
    if not temps:
        return []

    min_temp = min(temps)
    max_temp = max(temps)
    temp_range = max_temp - min_temp

    if temp_range == 0:
        # All temps are the same - use mid-level block
        return ["▄" * width] * len(temps)

    blocks = "▁▂▃▄▅▆▇█"

    result = []
    for temp in temps:
        # Map temperature to block index (0-7)
        fraction = (temp - min_temp) / temp_range
        block_idx = min(7, int(fraction * 8))
        result.append(blocks[block_idx] * width)

    return result


def create_rain_blocks(rain: list[float], width: int = 3) -> list[str]:
    """Build block characters representing rain percentages.

    Args:
        rain: List of rain percentages (0-100)
        width: Number of block characters per entry (default 3)

    Returns:
        List of block strings, one per rain value

    """
    blocks = "▁▂▃▄▅▆▇█"

    result = []
    for value in rain:
        # Map 0-100% to block index (0-7)
        fraction = max(0.0, min(100.0, value)) / 100.0
        block_idx = min(7, int(fraction * 8))
        result.append(blocks[block_idx] * width)

    return result
