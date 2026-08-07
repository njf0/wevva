# Task 0009: Clean up sync API event-loop rejection

## Status

Proposed

## Context

The public library offers synchronous wrappers for its asynchronous geocoding,
forecast, and alert APIs.

## Problem

The wrappers create a coroutine before `_run_sync()` detects an active event
loop and raises `WevvaAPIError`. That rejected coroutine can produce an
unawaited-coroutine warning.

## Desired outcome

Calling a sync API from active async code fails with the existing helpful error
and no leaked coroutine warning.

## Scope

- Adjust the internal sync-wrapper invocation pattern or cleanup behavior.
- Preserve async APIs, sync API names, arguments, return values, and the
  current exception type/message intent.
- Add an async regression test for each shared path as appropriate.

## Non-goals

- Do not support nested event loops.
- Do not add `nest_asyncio`, threads, or another execution runtime.
- Do not change normal synchronous usage.

## Relevant code

- `wevva/api.py`
- `wevva/__init__.py`

## Approach

Keep `_run_sync()` small. Detect the running loop before creating work, or
reliably close a rejected coroutine; use the option with the clearest typing
and simplest call sites.

## Acceptance criteria

- A sync API called from async code raises `WevvaAPIError`.
- The call produces no unawaited-coroutine warning.
- The same API works normally from synchronous code.

## Verification

- Add an `IsolatedAsyncioTestCase` regression test and warning capture.
- Run `uv run python -m unittest discover -s tests`.
- Run `uv run python -m compileall -q wevva`.

## Decisions and notes

This is a small public-API polish task and may be completed independently.

## Outcome

To be completed when the task is finished.
