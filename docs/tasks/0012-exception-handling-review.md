# Task 0012: Clarify exception handling and remove redundant catches

## Status

Proposed

## Context

The TUI must remain usable when network providers fail, while configuration and
public-library operations need failure behavior that callers can understand.

## Problem

Several broad `except Exception` blocks intentionally keep the UI responsive,
but some hide failures without an explicit policy or duplicate handling already
performed at a lower layer. Others are appropriate cancellation boundaries.

## Desired outcome

Each remaining broad exception boundary has a clear, documented reason. Redundant
or misleading catches are removed, and user-visible operations do not falsely
report success after a swallowed failure.

## Scope

- Audit broad exception boundaries in app refreshes, saved-location summary
  fetches, alerts, geocoding search, config writes, and selection widgets.
- Categorize each as: propagate, convert to a user-visible error, deliberately
  degrade, or preserve cancellation.
- Narrow catches where a concrete exception is known and appropriate.
- Remove catches that are unreachable or duplicate lower-layer normalization.
- Add focused tests for chosen behavior at altered boundaries.

## Non-goals

- Do not make every warning-provider failure a modal error.
- Do not create a global exception framework or error-reporting dependency.
- Do not catch `BaseException` or interfere with `CancelledError` propagation.
- Do not change unrelated normal application behavior.

## Relevant code

- `wevva/app.py`
- `wevva/services/alerts.py`
- `wevva/screens/search_screen.py`
- `wevva/widgets/saved_locations.py`
- `wevva/config.py`
- `wevva/cli.py`
- `tests/`

## Approach

Start with a short decision table in the task notes before editing. Treat
foreground weather refresh, background saved-location refresh, background
warning lookup, CLI geocoding, and config persistence as distinct experiences.
Preserve `asyncio.CancelledError` re-raising wherever it already exists.

## Acceptance criteria

- Every remaining broad catch has a specific behavioral reason.
- Redundant broad catches identified in the audit are removed.
- Failed background warning queries do not poison the warning cache.
- A failed user-visible save or foreground operation cannot be reported as a
  confirmed success without an explicit decision.
- Cancellation continues to stop background tasks normally.

## Verification

- Add focused mocked failure/cancellation tests.
- Run `uv run python -m unittest discover -s tests`.
- Run `uv run python -m compileall -q wevva`.
- Manually exercise one foreground network failure and one background warning
  failure if practical.

## Decisions and notes

This is a behavior-policy cleanup. Complete it after Task 0008 if both touch
alert failure handling.

## Outcome

To be completed when the task is finished.
