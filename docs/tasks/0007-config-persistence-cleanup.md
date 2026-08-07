# Task 0007: Simplify configuration persistence

## Status

Proposed

## Context

User preferences and saved locations are stored in one JSON file and normalized
on load.

## Problem

Saved-location operations repeatedly reload preferences through nested helper
calls. `get_config_path()` creates the user config directory even for a read,
and `_write_preferences()` silently ignores write failures.

## Desired outcome

Configuration reads are side-effect-free, each mutation follows one clear
read/normalize/write path, and write-failure behavior is consciously defined.

## Scope

- Separate locating the config file from creating its parent directory.
- Remove repeated reads from saved-location and default-location mutation
  paths.
- Simplify internal update flow while preserving current normalization and JSON
  compatibility.
- Decide and document whether write errors are returned, raised, or presented
  to the relevant TUI/CLI caller.
- Add focused temporary-directory tests for read and write behavior.

## Non-goals

- Do not change the config path or file format.
- Do not introduce a database, settings framework, migration system, or
  configurable persistence backend.
- Do not silently discard a user-visible write failure without an explicit
  decision.

## Relevant code

- `wevva/config.py`
- `wevva/cli.py`
- `wevva/app.py`
- `docs/development.md`

## Approach

Keep dictionaries and current normalization functions. A small internal update
helper is appropriate only if it removes the existing multiple-read flow.

## Acceptance criteria

- Loading defaults does not create a config directory or file.
- Each saved/default-location mutation loads preferences at most once before
  writing.
- Existing valid configuration and legacy default-location migration continue
  to work.
- Chosen write-failure behavior is testable and visible to the right caller.

## Verification

- Add `unittest` coverage using a temporary home/config directory.
- Run `uv run python -m unittest discover -s tests`.
- Run `uv run python -m compileall -q wevva`.
- Manually save, remove, and set a default location in the TUI or CLI.

## Decisions and notes

The write-error UX needs maintainer agreement before implementation.

## Outcome

To be completed when the task is finished.
