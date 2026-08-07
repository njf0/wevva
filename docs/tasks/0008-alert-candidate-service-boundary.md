# Task 0008: Clarify the alert candidate service boundary

## Status

Proposed

## Context

The session warning cache needs country-level candidates, local point matching,
and an explicit distinction between a successful empty query and a failed one.

## Problem

`Wevva` imports private reusable-candidate, native-point, and combination
helpers from the alert service. The app also catches exceptions around helpers
that already convert provider failures into completion status, obscuring the
intended boundary.

## Desired outcome

The app uses a clearly named internal alert-service interface for candidate
retrieval and matching, with failure/empty-result semantics documented once.

## Scope

- Define a compact internal result/interface for country candidate retrieval.
- Remove redundant exception handling that cannot affect behavior.
- Keep expiry filtering, stale-refresh protection, progress callbacks, and the
  15-minute session cache intact.
- Add tests for successful empty results, unsupported countries, failure, and
  cancellation boundaries.

## Non-goals

- Do not change public `wevva` alert APIs or require another
  `wevva-warnings` release.
- Do not expose raw warning-provider errors in routine background UI flow.
- Do not add a generic result framework or cache framework.

## Relevant code

- `wevva/services/alerts.py`
- `wevva/app.py`
- `wevva/messages.py`
- `tests/test_warning_cache.py`
- `docs/tasks/0002-warning-cache.md`

## Approach

Keep the implementation local to the alert service. A tuple or tiny dedicated
result type is sufficient; choose the least ceremony that makes successful
empty results and failures unambiguous.

## Acceptance criteria

- The app does not depend on underscore-prefixed service functions.
- A successful empty candidate query remains cacheable; a failed or cancelled
  one remains uncacheable.
- Cached matching and warning progress behavior remain unchanged.
- The alert service owns provider-failure normalization in one place.

## Verification

- Extend focused mocked-warning tests.
- Run `uv run python -m unittest discover -s tests`.
- Run `uv run python -m compileall -q wevva`.
- Manually check a warning lookup and cache hit when live providers are
  available.

## Decisions and notes

This is a cleanup of the post-Task-0002 boundary, not a redesign of warnings.

## Outcome

To be completed when the task is finished.
