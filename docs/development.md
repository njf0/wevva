# Development

## Prerequisites and setup

The project requires Python 3.12+ (`pyproject.toml`) and uses `uv` with the
committed `uv.lock`.

```bash
uv sync --locked
```

Warning progress and country-level warning caching use `wevva-warnings`. The
native point-query split introduced by Task 0013 must use the corresponding
published warning-library release. Before that release, a local sibling checkout
can be used by temporarily adding a `tool.uv.sources` override; do not commit
that override or its lockfile result for a release.

The following local commands have been checked in this repository:

```bash
uv run wevva
uv run python -m wevva
uv run python -m compileall -q wevva
```

`wevva setup` starts the interactive preference wizard; use
`uv run wevva setup --no-launch` to save setup choices without starting the
TUI. The README also documents `uvx --from . wevva` for running a checkout.

## Validation and packaging

The focused regression suite uses the standard library:

```bash
uv run python -m unittest discover -s tests
```

There is no configured linter, formatter, or type checker. `compileall` is the
available basic source-compilation check; choose focused manual TUI checks for
UI behavior.

The checked-in geographic resource is generated from Natural Earth 5.1.1's
1:50m Admin-0 Map Units dataset. Runtime code uses only the compact gzip JSON
resource; `pyshp` is an optional preprocessing tool. Regeneration instructions
and attribution are in `wevva/data/README.md`.

The package uses Hatchling (`pyproject.toml`) and declares the `wevva` console
script. The maintainer-confirmed release workflow is:

```bash
uv build
uv publish
```

`uv publish` makes an external change and needs explicit release approval plus
the relevant credentials/index configuration; neither is stored in this
repository. There is no CI procedure in the repository.

## Local verification constraints

Running the TUI needs an interactive, colour-capable terminal. The full layout
is documented as needing at least 186x53. Emoji output depends on the terminal,
font, and locale; use `--no-emoji` when assessing alignment.

Live behavior needs network access to Open-Meteo forecast, geocoding, and air
quality APIs. Alert behavior also depends on `wevva-warnings` and its provider
sources; country-wide alert retrieval can be noticeably slow. Do not treat a
network-dependent manual check as deterministic or claim it was performed when
it was not.

User preferences live outside the repository at
`~/.config/wevva/config.json`. Be aware that the setup wizard, CLI default
location options, and in-app settings/save-location actions can modify it.
