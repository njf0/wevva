"""Shared constants.

Keep simple numbers in one place to avoid magic values.
"""

# Unit defaults and allowed values
DEFAULT_TEMPERATURE_UNIT: str = 'celsius'
DEFAULT_WIND_SPEED_UNIT: str = 'kmh'
DEFAULT_PRECIPITATION_UNIT: str = 'mm'
DEFAULT_THEME: str = 'gruvbox'
DEFAULT_EMOJI_ENABLED: bool = False
DEFAULT_WARNING_LANGUAGE: str = 'auto'

VALID_TEMPERATURE_UNITS: tuple[str, ...] = ('celsius', 'fahrenheit')
VALID_WIND_SPEED_UNITS: tuple[str, ...] = ('kmh', 'ms', 'mph', 'kn')
VALID_PRECIPITATION_UNITS: tuple[str, ...] = ('mm', 'inch')
VALID_WARNING_LANGUAGES: tuple[str, ...] = ('auto', 'en')

# Forecast display settings
HOURS_WINDOW: int = 24  # Hours shown in the hourly view
MAX_TAB_DAYS: int = 7  # Days shown as tabs in hourly forecast (inclusive of today)
DAILY_FORECAST_DAYS: int = 7  # Days shown in daily forecast

# Search screen settings (typing and results)
SEARCH_MIN_CHARS: int = 3  # Minimum characters before search triggers
SEARCH_DEBOUNCE_S: float = 0.3  # Delay before search executes (seconds)
SEARCH_MAX_RESULTS: int = 20  # Maximum number of search results

# Network timeouts (seconds)
REQUEST_TIMEOUT_S: float = 5.0  # Standard API request timeout
WEATHER_FETCH_TIMEOUT_S: float = 30.0  # Weather API fetch timeout (httpx default)

# Time constants
SECONDS_PER_MINUTE: int = 60
SECONDS_PER_HOUR: int = 3600
SECONDS_PER_DAY: int = 86400
