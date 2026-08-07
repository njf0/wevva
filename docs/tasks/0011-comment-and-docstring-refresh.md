# Task 0011: Refresh source comments and docstrings

## Status

Proposed

## Context

The repository has accumulated historical comments, generated-style parameter
docstrings on private helpers, and implementation comments that repeat nearby
code.

## Problem

Some comments describe removed implementation paths or offer little more than
the code itself. They make core modules such as the CLI, controller, config,
and forecast models longer to scan without preserving useful rationale.

## Desired outcome

Comments and docstrings explain non-obvious intent, external constraints,
compatibility choices, or user-visible behavior; redundant narration is
removed.

## Scope

- Review comments/docstrings in the frequently changed core modules.
- Remove stale historical notes and generated-style repetition.
- Shorten private helper documentation where signature and name are already
  clear.
- Preserve public API documentation and comments that record external API,
  Textual lifecycle, cache, or compatibility constraints.

## Non-goals

- Do not run an indiscriminate repository-wide deletion pass.
- Do not rename symbols or refactor behavior solely to alter documentation.
- Do not rewrite README or architecture documents wholesale.

## Relevant code

- `wevva/cli.py`
- `wevva/controller.py`
- `wevva/config.py`
- `wevva/openmeteo.py`
- `wevva/app.py`
- `wevva/services/`
- `docs/architecture.md`

## Approach

Make small grouped edits by module. Keep a comment when removing it would make
the reason for a surprising constraint less clear. Record noteworthy retained
constraints in the task outcome rather than replacing them with generic prose.

## Acceptance criteria

- Removed comments/docstrings were redundant, stale, or misleading.
- Retained documentation explains meaningful rationale or public behavior.
- No production behavior, public interface, or configuration format changes.
- The resulting diff remains reviewable by module.

## Verification

- Review the diff for unrelated wording churn.
- Run `uv run python -m compileall -q wevva`.
- Run `uv run python -m unittest discover -s tests` if touched modules have
  relevant tests.

## Decisions and notes

Prefer several compact commits if the review is broader than expected.

## Outcome

To be completed when the task is finished.
