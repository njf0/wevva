# Task 0006: Make forecast model access consistent

## Status

Proposed

## Context

Current, hourly, and daily forecast models provide convenience accessors used
by widgets and library consumers.

## Problem

`get_point()` returns `None` for an invalid offset, and many accessors are
annotated as optional, but several immediately call `.get()` or `round()` on a
possibly absent point or value. Other accessors guard the same conditions.

## Desired outcome

Model accessors follow one small, predictable contract for missing points and
optional values, without scattering defensive branches through every caller.

## Scope

- Define and document the existing intended behavior for invalid offsets and
  missing optional forecast values.
- Apply one compact internal pattern where it removes inconsistent accessor
  logic.
- Ensure model parsing errors caused by invalid provider structure are not
  silently disguised as absent weather values.
- Add focused tests for empty models, invalid offsets, and absent optional
  fields.

## Non-goals

- Do not validate every Open-Meteo field defensively.
- Do not replace the response dictionaries with a large schema system.
- Do not change normal displayed values or units.

## Relevant code

- `wevva/openmeteo.py`
- `wevva/widgets/hourly_forecast.py`
- `wevva/widgets/weather_summary.py`
- `wevva/widgets/current_conditions.py`

## Approach

Favor a single justified internal accessor or value helper over repeated local
guards. Preserve clear failures at the external response-parsing boundary.

## Acceptance criteria

- Documented optional accessors do not raise solely because an offset is out of
  range or an optional scalar is absent.
- Current, hourly, and daily classes behave consistently for equivalent cases.
- Normal provider responses continue to render unchanged.
- Parsing a structurally invalid provider response is not silently treated as
  valid empty data.

## Verification

- Add focused `unittest` coverage using small static forecast dictionaries.
- Run `uv run python -m unittest discover -s tests`.
- Run `uv run python -m compileall -q wevva`.
- Perform a manual TUI smoke check with normal live forecast data if available.

## Decisions and notes

This is contract cleanup, not blanket defensive programming.

## Outcome

To be completed when the task is finished.
