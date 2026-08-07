# wevva agent guide

## Project summary

`wevva` is a personal Python/Textual terminal weather application. It obtains
forecasts, geocoding, and air quality from Open-Meteo, and weather warnings via
the `wevva-warnings` package. It also exposes small async and sync Python APIs.

## Important areas

- `wevva/cli.py` — Typer entry point, setup wizard, preference/launch choices.
- `wevva/app.py` and `wevva/controller.py` — Textual app state and forecast
  orchestration.
- `wevva/screens/`, `wevva/widgets/`, and `wevva/wevva.tcss` — TUI layout,
  interactions, and styling.
- `wevva/openmeteo.py` and `wevva/services/` — API requests and forecast,
  geocoding, air-quality, and warning boundaries.
- Warning progress flows from `wevva/services/alerts.py` through `Wevva` and
  `WeatherAlertsProgress` to `SavedLocationsSidebar`. Reusable country
  candidates are cached, while native point-query sources are refreshed for
  each location; keep worker-thread and stale-refresh safeguards intact.
- `wevva/api.py`, `wevva/models.py`, and `wevva/__init__.py` — public Python
  API and exported models.
- `wevva/config.py` and `wevva/location_metadata.py` — persisted preferences
  and location shape.

Read `docs/architecture.md` before changing a cross-cutting path, and
`docs/development.md` before setting up or validating work.

## Working principles

- Inspect relevant code and execution paths before editing.
- Keep changes small, proportionate, and suitable for a personal project.
- Do not add speculative abstractions or combine unrelated cleanup with a task.
- Preserve documented public imports and behavior unless the task explicitly
  changes them.
- Treat sync and async public paths as separate compatibility surfaces.
- Be cautious with Open-Meteo response assumptions, persisted configuration,
  background refresh tasks, warning-progress callbacks, and terminal layout.
- Update these documents when commands or architectural boundaries change.

## Commands

Requires Python 3.12+ and `uv`.

```bash
# Create/update the locked local environment
uv sync --locked

# Run from this checkout
uv run wevva

# Equivalent module entry point
uv run python -m wevva

# Basic source syntax check
uv run python -m compileall -q wevva

# Focused standard-library regression tests
uv run python -m unittest discover -s tests

# Release workflow — only with explicit approval to publish externally
uv build
uv publish
```

The repository has a small standard-library `unittest` suite but no configured
linter, formatter, or type checker. Hatchling is the configured build backend.
The maintainer's release workflow uses `uv build` followed by `uv publish`;
credentials and index configuration are intentionally not stored in this
repository.

## Completion expectations

Run the checks relevant to the change; report what changed and what could not
be verified. Do not claim success for behavior that depends on live APIs,
warning providers, terminal size, colours, fonts, or emoji support unless it
was actually exercised.
