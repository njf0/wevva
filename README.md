# wevva

`wevva` is a weather TUI built with [Textual](https://textual.textualize.io/) and powered by [Open-Meteo](https://open-meteo.com/).

The goal is a fast, keyboard-first weather experience in the terminal.

## Highlights

- Place search using Open-Meteo geocoding
- Current, hourly, and daily forecasts
- Unit preferences (temperature, wind, precipitation)
- Theme and emoji toggles
- Interactive setup wizard for defaults
- Reusable Python API (async + sync helpers)

## Quick Start

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run:

```bash
uvx wevva
```

Run from this local checkout:

```bash
uvx --from . wevva
```

Requires Python `>=3.12`.

## First-Time Setup

Run the setup wizard to save defaults:

```bash
uvx wevva setup
```

Save settings without launching:

```bash
uvx wevva setup --no-launch
```

## Useful Commands

```bash
# Start normally (uses saved defaults)
uvx wevva

# Start directly at a location
uvx wevva --location "Edinburgh"

# One-run overrides
uvx wevva --theme dracula --no-emoji
uvx wevva --temperature-unit fahrenheit --wind-speed-unit mph

# Manage saved default location
uvx wevva --set-default-location "New York"
uvx wevva --clear-default-location
```

## Library Usage

Install as a package:

```bash
uv add wevva
```

Simple sync usage (nice for scripts):

```python
from wevva import forecast_by_place_sync

bundle = forecast_by_place_sync("Edinburgh")
print(bundle.metadata.name, bundle.metadata.country)
print(bundle.current.get_temperature(), bundle.current.forecast_units.get("temperature_2m"))
```

Async usage (best for apps/services):

```python
import asyncio
from wevva import forecast_by_coordinates

async def main() -> None:
    bundle = await forecast_by_coordinates(lat=55.9533, lon=-3.1883)
    print(bundle.daily.get_temperature_max(0))
    print(bundle.hourly.get_condition_abbreviation(0))

asyncio.run(main())
```

You can also geocode from Python:

```python
from wevva import geocode_sync

matches = geocode_sync("Glasgow", count=3)
for match in matches:
    print(match.name, match.country, match.latitude, match.longitude)
```

## In-App Keys

- `s` search for place
- `r` refresh weather
- `u` open unit settings
- `h` or `?` open help
- `c` credits
- `q` quit

## Config

Preferences are stored at:

```text
~/.config/wevva/config.json
```

Saved settings include:
- units
- theme
- emoji preference
- default location (and cached resolved location metadata)

## Notes

- Emoji rendering support varies by terminal/font/locale.
- TUI is the primary focus, but a lightweight Python API is now exported too.
