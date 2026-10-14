# Task 0004: Share forecast and air-quality assembly

## Status

Archived — completed. The TUI controller and public API now share one pure
air-quality series alignment operation.

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

Moved the air-quality field definition and alignment logic into
`wevva.services.air_quality`. The request field list, TUI controller, and public
API now use that shared definition. The merge returns a new hourly dictionary,
pads or truncates valid lists to the weather timeline, and ignores malformed
optional data without damaging the weather series.

Focused tests cover missing, malformed, short, exact, and long series; input
immutability; equivalent controller/API output; and preservation of the public
API's copied raw response. Source compilation and the complete 280-test suite
pass.
