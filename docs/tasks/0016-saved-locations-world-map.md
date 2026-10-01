# Task 0016: Interactive saved-locations world map

## Status

Complete

## Context

The responsive forecast now uses surplus space for weather context before
admitting navigation rails. Saved locations still have only list-based access,
even though the application already ships Natural Earth world geometry, a
Braille geographic canvas, and cached current-weather summaries for those
locations.

## Problem

There is no spatial overview of saved locations, and the existing country map
is deliberately scoped to the active forecast rather than global navigation.

## Desired outcome

A dedicated screen fills its content region with a bordered Braille world map.
Each sidebar location is represented by a temperature-coloured
`• Place temperature` callout which can be focused, hovered, or clicked to open
that location's normal weather forecast.

## Scope

- A full-world Braille land backdrop using the checked-in geometry.
- Native focusable Textual callout widgets positioned over that backdrop.
- Collision-aware callout placement which responds to terminal resizing.
- Cached saved-location temperatures and the existing temperature scale.
- Mouse and keyboard activation through `SavedLocationSelected`.
- A dedicated screen and weather-screen binding.

## Non-goals

- New forecast queries or geographic datasets.
- Pan, zoom, projections selectable by the user, or map scrolling.
- Replacing the existing country-scale current-location map.
- A special glyph for the active location; every city uses `•`.

## Relevant code

- `wevva/widgets/world_locations_map.py`
- `wevva/widgets/geographic_scope.py`
- `wevva/geography.py`
- `wevva/widgets/saved_locations.py`
- `wevva/app.py`
- `wevva/screens/weather_screen.py`

## Approach

The Braille land raster and interactive callouts are separate layers. Each
callout is a focusable `Static` subclass using normal Textual click handling,
bindings, `:hover`, and `:focus` styles. Absolute positioning is used only for
the inherently geographic placement; the map does not manually reproduce
mouse hit testing. Highlighting uses the terminal's reverse style so the
temperature foreground becomes the background.

Implementation is divided into two slices:

1. Build and test the standalone responsive map surface, callouts, placement,
   highlighting, and selection messages.
2. Add the dedicated padded screen, bindings, summary synchronization, and
   transition back to the weather forecast.

## Acceptance criteria

- The map uses one `•` marker treatment for every valid location.
- Each visible callout is a native focusable/clickable Textual widget.
- Hover and focus invert the whole callout's foreground and background.
- Enter, Space, and click emit the existing location-selection message.
- Callouts remain collision-free and are repositioned after resizing.
- The final screen uses one rounded map border with `1 2` spacing outside it.
- Selecting a map callout opens the ordinary weather screen for that location.

## Verification

```bash
uv run python -m compileall -q wevva
uv run python -m unittest tests.test_world_locations_map
uv run python -m unittest discover -s tests
```

Manual terminal checks remain necessary for hover colours, font-dependent
Braille appearance, and very dense real saved-location collections.

## Decisions and notes

- All locations use `•`; active state is represented only by inversion.
- Callouts are separate widgets rather than action metadata embedded in one
  Rich `Text`, preserving native focus and hover behavior.
- The weather screen opens the map with `m`; `w` or Escape returns without
  changing location, while activation returns and refreshes the chosen place.
- Existing saved-summary requests feed the screen live; the map performs no
  additional forecast queries.
- The global viewport ends at 78°S: the Antarctic coast remains recognizable,
  while its southern cap no longer consumes rows that can separate inhabited
  locations.
- Callouts may face either direction: `• City temperature` extends right and
  `City temperature •` extends left, so the marker stays on its projected point.

## Outcome

Both slices are complete. The standalone map surface is mounted in a dedicated
header/footer screen with the requested outer spacing, native focus/hover/click
labels, keyboard traversal, cached and live temperature summaries, and the
ordinary saved-location selection path. Focused widget and screen-integration
tests cover raster output, collision placement, resize identity, interaction,
and navigation back to weather. The complete repository suite passes with 186
tests. Font rendering and hover colours remain manual terminal checks.
