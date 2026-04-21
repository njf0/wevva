"""Utility functions for Wevva.

Submodules:
- colors: Temperature, rain, and wind color mapping
- formatting: Emoji normalization, date suffixes, text formatting
- geo: Bearing conversion, country code to flag
- visualization: Block character generation for charts
"""

# Color utilities
from wevva.utils.colors import rain_colour, temp_colour, wind_colour

# Formatting utilities
from wevva.utils.formatting import date_suffix, norm_character_width, normalize_emoji

# Geographic utilities
from wevva.utils.geo import bearing_to_direction, country_code_to_flag

# Visualization utilities
from wevva.utils.visualization import create_rain_blocks, create_temp_blocks

__all__ = [
    # Colors
    'rain_colour',
    'temp_colour',
    'wind_colour',
    # Formatting
    'date_suffix',
    'norm_character_width',
    'normalize_emoji',
    # Geographic
    'bearing_to_direction',
    'country_code_to_flag',
    # Visualization
    'create_rain_blocks',
    'create_temp_blocks',
]
