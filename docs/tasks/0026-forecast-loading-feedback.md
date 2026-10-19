# Task 0026: Forecast loading feedback

## Status

Complete

## Context

Selecting a search result, saved location, or weather-map place starts a full
forecast refresh. Until that request completes, the persistent weather screen
can continue to show the previous location without explaining the delay.

## Problem

Location changes can look frozen while Open-Meteo is returning the new
forecast. Loading every forecast widget independently would add visual noise
and unnecessary lifecycle state.

## Desired outcome

An uncached forecast request visibly covers the stale central forecast and the
header identifies the location being fetched. Cached changes remain immediate.

## Scope

- Add one native loading state to the central weather workspace.
- Show `Fetching forecast for <place>…` in the weather header.
- Preserve the existing background warning-check status and priority.
- Clear loading after successful widget population, failure, or cancellation.
- Cover search, saved-location, world-map, and in-place map selection through
  their shared refresh path.

## Non-goals

- Loading indicators on every forecast child widget.
- Changes to geocoding-search loading or warning-provider progress.
- Changes to forecast caching, request concurrency, or stale-refresh guards.

## Relevant code

- `wevva/app.py`
- `wevva/screens/weather_screen.py`
- `tests/test_forecast_cache.py`
- `tests/test_responsive_weather_screen.py`

## Approach

The application enables the weather screen's loading state only after a cache
miss and before the controller request. `WeatherScreen` uses Textual's native
loading cover on the complete workspace, keeps activity subtitle states
separate, and removes the cover after applying a `WeatherUpdated` event.

## Acceptance criteria

- Every uncached full-forecast request shows one central loading indicator.
- The header names the selected location while the request is pending.
- Existing forecast values are not left visible as if they described the new
  location.
- A cache hit does not flash a loading state.
- Success, failure, and cancellation all clear loading.
- A simultaneous warning check becomes visible after forecast loading ends.

## Verification

```bash
uv run python -m unittest tests.test_forecast_cache tests.test_responsive_weather_screen
uv run python -m compileall -q wevva
```

A live network request and terminal rendering remain optional manual checks.

## Decisions and notes

The central workspace is the smallest useful loading boundary: the header,
footer, and auxiliary navigation remain stable while stale forecast content is
covered as one unit.

## Outcome

The shared full-forecast path now presents native loading feedback only for
real requests, with deterministic coverage for cache, failure, cancellation,
overlay, and subtitle-priority behavior.
