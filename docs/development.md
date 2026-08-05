# Development

## Prerequisites and setup

The project requires Python 3.12+ (`pyproject.toml`) and uses `uv` with the
committed `uv.lock`.

```bash
uv sync --locked
```

Warning progress and country-level warning caching use the published
`wevva-warnings>=0.3.5` dependency. A local sibling checkout can still be used
for warning-library development by temporarily adding a `tool.uv.sources`
override, but that override must not be committed for a release.

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

There are currently no repository-configured tests, linter, formatter, or type
checker. `compileall` is the available basic source-compilation check;
choose focused manual TUI checks for UI behavior.

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
is documented as needing at least 192x53. Emoji output depends on the terminal,
font, and locale; use `--no-emoji` when assessing alignment.

Live behavior needs network access to Open-Meteo forecast, geocoding, and air
quality APIs. Alert behavior also depends on `wevva-warnings` and its provider
sources; country-wide alert retrieval can be noticeably slow. Do not treat a
network-dependent manual check as deterministic or claim it was performed when
it was not.

User preferences live outside the repository at
`~/.config/wevva/config.json`. Be aware that the setup wizard, CLI default
location options, and in-app settings/save-location actions can modify it.
