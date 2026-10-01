# Task 0017: Interactive country and regional location map

## Status

Complete

## Context

The weather screen already shows a responsive country/component map, ranked
nearby cities, and lightweight current temperatures. Its labels were embedded
in one Rich render, so they could not participate in Textual interaction.

## Outcome

The existing map geometry and enrichment path are retained, but the widget now
renders land beneath native `LocationMapLabel` children. Every callout uses
`•`; the active forecast location is distinguished by permanent colour
inversion, and nearby cities invert on hover or focus. Click, Enter, or Space
emits the ordinary `PlaceSelected` message and refreshes that city's forecast
without pushing a duplicate weather screen.

The existing density contract remains unchanged: the normal map can admit up
to eight ranked cities, while the narrow sidecar admits four. Temperature
updates and resizes reflow the same mounted labels through collision-aware
placement. Labels face right as `• City temperature` or left as
`City temperature •`, keeping the marker on its projected point rather than
shifting the whole callout away from that anchor.

## Non-goals

- New city-ranking data, queries, or geocoding requests.
- A bespoke map keyboard-navigation mode.
- Changing country-component selection, including the Hawaii behavior.
- Making the map visible at layout heights where it was previously omitted.

## Verification

```bash
uv run python -m compileall -q wevva
uv run python -m unittest tests.test_location_map
uv run python -m unittest tests.test_responsive_weather_screen
uv run python -m unittest discover -s tests
```

Manual terminal checks remain useful for hover inversion, mouse behavior, and
font-dependent Braille alignment.

The complete repository suite passes with 189 tests.
