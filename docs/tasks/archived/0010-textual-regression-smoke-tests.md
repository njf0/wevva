# Task 0010: Add focused Textual regression smoke tests

## Status

Archived — completed. Mounted smoke tests now protect warning-progress
visibility, quiet empty-cache hits, and stale results after location changes.

## Context

Recent warning progress and caching changes rely on Textual message ordering,
background tasks, and transient sidebar state. Current tests cover most cache
logic with lightweight stand-ins rather than mounted widgets.

## Problem

High-risk TUI state transitions have no small automated smoke checks. Manual
terminal verification remains important, but it is easy to miss regressions in
message routing and transient panel visibility.

## Desired outcome

A minimal set of deterministic Textual tests protects the existing warning and
saved-location interactions without introducing a new testing framework.

## Scope

- Use Textual testing support already supplied by the existing dependency.
- Cover a few critical scenarios: warning progress appears only for individual
  documents, cache-hit completion does not show progress, and switching
  locations cannot display stale results.
- Keep network calls mocked or avoided.
- Document the standard-library/Textual test command in agent/development docs.

## Non-goals

- Do not aim for comprehensive widget snapshot coverage.
- Do not add browser, screenshot, visual-diff, or CI tooling.
- Do not replace manual terminal and live-provider checks.

## Relevant code

- `wevva/app.py`
- `wevva/screens/weather_screen.py`
- `wevva/widgets/saved_locations.py`
- `wevva/messages.py`
- `tests/test_warning_cache.py`
- `AGENTS.md`
- `docs/development.md`

## Approach

Prefer a few readable behavior tests over testing Textual internals. Use the
same task/cancellation safeguards already implemented by the application.

## Acceptance criteria

- Selected message-routing and transient-progress behavior are covered without
  live network access.
- Tests use existing dependencies only.
- Agent and development docs accurately describe the available test command.
- Tests remain fast enough for routine local use.

## Verification

- Run `uv run python -m unittest discover -s tests`.
- Run `uv run python -m compileall -q wevva`.
- Perform a manual terminal check of the warning sidebar when practical.

## Decisions and notes

The smoke coverage follows the current warning pipeline rather than the older
proposal literally: measured document, geometry, and matching work may be
shown, while unsupported aggregate phases are ignored. An empty cached
candidate set remains visually quiet.

## Outcome

Added three deterministic tests around a mounted `WeatherScreen`. They verify
that only supported individual-warning phases reveal measured progress, an
empty reusable-candidate cache hit bypasses provider lookup without revealing
the progress panel, and a delayed result for a superseded location cannot
replace the current location's warning display. All provider calls are mocked.

The focused warning command is documented in `AGENTS.md` and
`docs/development.md`. The 29-test warning group, source compilation, and the
complete 301-test suite pass. No live-provider or interactive terminal check
was performed.
