# Task 0004: Share forecast and air-quality assembly

## Status

Proposed

## Context

The TUI controller and public Python API both combine Open-Meteo weather data
with hourly air-quality data before constructing forecast models.

## Problem

`wevva/controller.py` and `wevva/api.py` duplicate the six air-quality field
names and list pad/truncate logic. Their input validation and mutation behavior
are not identical, so future changes could make TUI and library results differ.

## Desired outcome

One small, pure merge operation defines how optional air-quality series are
attached to hourly weather data. Both callers retain their distinct output
requirements.

## Scope

- Move the air-quality field list and alignment logic to one appropriate
  internal location.
- Make both the controller and public API use it.
- Preserve the public API's raw-data copy behavior and the controller's
  `WeatherUpdated` message behavior.
- Add tests for missing, short, long, and malformed air-quality series.

## Non-goals

- Do not add a broad service/model-builder framework.
- Do not change Open-Meteo requests or displayed air-quality fields.
- Do not change public API signatures.

## Relevant code

- `wevva/controller.py`
- `wevva/api.py`
- `wevva/services/air_quality.py`
- `wevva/openmeteo.py`

## Approach

Extract only the shared transformation, with explicit ownership and simple
dictionary inputs. Leave public API metadata overlay and raw snapshot handling
where they are, unless a small adjacent simplification is clearly warranted.

## Acceptance criteria

- TUI and public API use the same alignment rules for all current air-quality
  fields.
- A shorter provider series is padded and a longer series is truncated to the
  weather time series length.
- Absent or malformed optional air-quality data leaves hourly weather usable.
- No public API behavior changes beyond consistent existing behavior.

## Verification

- Add focused `unittest` coverage using static response dictionaries.
- Run `uv run python -m unittest discover -s tests`.
- Run `uv run python -m compileall -q wevva`.

## Decisions and notes

The desired result is less duplicated transformation code, not a new
architecture.

## Outcome

To be completed when the task is finished.
