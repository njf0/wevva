# Task 0005: Retire obsolete Open-Meteo model paths

## Status

Proposed

## Context

Forecast models are now constructed from data fetched by `OpenMeteoForecast`
and consumed by the controller and public API.

## Problem

Each model still has a `fetch_and_parse_forecast()` method that calls a
nonexistent `self.fetch()`, returns no value despite its annotation, and has no
in-repository caller. The old `_get_metadata()` and `_get_units()` helpers only
support those methods while static extraction helpers are used instead.

## Desired outcome

The model module exposes only supported, working forecast construction paths,
with any compatibility decision made explicitly.

## Scope

- Confirm whether the obsolete methods are documented or relied upon outside
  this repository.
- If removal is accepted, remove the three broken methods and their now-unused
  private helpers and imports.
- If compatibility must be retained, replace the broken behavior with a clear,
  tested supported contract or an explicit deprecation path.
- Remove stale comments adjacent to retired code.

## Non-goals

- Do not redesign the forecast model classes.
- Do not change the supported public forecast functions in `wevva.api`.
- Do not make network requests from individual model instances without an
  explicit compatibility decision.

## Relevant code

- `wevva/openmeteo.py`
- `wevva/__init__.py`
- `wevva/api.py`
- `README.md`
- package release notes, if any

## Approach

Treat the classes exported from `wevva.__init__` as a compatibility surface.
Prefer removing unreferenced, non-working legacy methods only after recording
that choice in the task outcome.

## Acceptance criteria

- No retained method calls a nonexistent method or promises a return it does
  not provide.
- The supported fetch path used by the TUI and public API remains unchanged.
- Removed code has no remaining repository references.
- The compatibility decision is recorded.

## Verification

- Search the repository and published documentation for affected methods.
- Add or update focused model/API tests as appropriate.
- Run `uv run python -m unittest discover -s tests`.
- Run `uv run python -m compileall -q wevva`.

## Decisions and notes

This task may intentionally be deferred if preserving these methods is more
important than removing dead code.

## Outcome

To be completed when the task is finished.
