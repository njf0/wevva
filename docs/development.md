# Development

## Prerequisites and setup

The project requires Python 3.12+ (`pyproject.toml`) and uses `uv` with the
committed `uv.lock`.

```bash
uv sync --locked
```

Warning progress, the dedicated canonical tropical workspace, and country-level
warning caching use `wevva-warnings`. This development checkout currently resolves the declared
`wevva-warnings==0.5.3` dependency from the editable sibling path
`../wevva-warnings` through `[tool.uv.sources]`; `uv.lock` records the same path.
This allows both projects to be developed and tested together. Remove the
source override and regenerate the lockfile when switching back to a published
release.

The sibling checkout is therefore part of the current development state. When
moving this work between machines, commit or otherwise transfer both
repositories: first `wevva-warnings`, then `wevva`, recording the warning
library commit in the application handoff. Place the clones alongside one
another so the editable path remains `../wevva-warnings`. A commit containing
only this repository is not sufficient to reproduce the tropical APIs until a
compatible warning-library release exists.

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

Warning caching, progress routing, and stale-location safeguards have a smaller
unit and mounted-Textual smoke-test command:

```bash
uv run python -m unittest tests.test_warning_cache tests.test_warning_textual_smoke
```

The warning-cache tests use temporary directories and controlled UTC clocks to
exercise the persistent alert codec, product namespace separation, atomic
replacement, schema/corruption handling, clock skew, and unavailable storage;
they do not read or modify the user's cache directory.

The country Alerts Centre has deterministic service, screen, interactive-map,
settlement-tooltip lifecycle, full-weather navigation, and responsive-budget
coverage, including cache expiry, stale preview results, and country-switch
races:

```bash
uv run python -m unittest tests.test_alerts_centre_service tests.test_alerts_centre_screen
uv run python -m unittest tests.test_alerts_centre_map tests.test_alerts_centre_layout
uv run python -m unittest tests.test_alerts_centre_integration
```

The tropical workspace has separate pure-budget, screen-lifecycle, track
geometry, and native-callout coverage:

```bash
uv run python -m unittest tests.test_tropical_layout
uv run python -m unittest tests.test_tropical_systems_screen tests.test_tropical_track
```

There is no configured linter, formatter, or type checker. `compileall` is the
available basic source-compilation check; choose focused manual TUI checks for
UI behavior.

The checked-in geographic resources are generated from Natural Earth's 1:50m
Admin-0 Map Units and 1:50m/1:10m Populated Places datasets. General maps use
the compact place set; focused alert maps use the denser set. Runtime code uses
only gzip JSON resources; `pyshp` is an optional preprocessing tool.
Regeneration instructions and attribution are in `wevva/data/README.md`.

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

Running the TUI needs an interactive, colour-capable terminal. The primary
forecast instruments have a tested, non-scrolling 80x24 compact mode. At tall
sizes the country map and three context tables grow together through tested
14-, 17-, 20-, and 23-row matrix tiers without changing the page-scroll
contract. The matrix remains eligible at the supported 80-column width, using
compact date/time values in its 37-cell information column. At sufficiently
wide sizes, those same mounted widgets move into a right-hand sidecar when the
viewport cannot yet support the complete bottom matrix. The sidecar shows
location and astronomy above a larger map with at most four city labels; once
all five context rows fit below the forecast, the full bottom matrix wins and
restores air quality. All modes preserve the
102-column central canvas. The tropical workspace has its own tested 80x24
stack with storm/source navigation, complete priority summary rows, and an
internally scrolling information body; maps and centre weather return only
when their complete minimum presentations fit. Emoji output depends on the
terminal, font, and locale; use `--no-emoji` when assessing alignment.

The resize-native design and its manual terminal-size matrix are in
`docs/responsive-layout.md`. Its weather-screen implementation is complete.
The pure budget, rendered terminal matrix, 80x24 no-scroll behavior,
horizontal hourly navigation, resize state, auxiliary rails/modals, context
density boundaries, compact-to-tabbed warning density, direct full-document
warning tabs, warning-notification lifecycle and de-duplication, long warning
labels, longer display units, emoji variants, and contrasting built-in themes
are covered by deterministic tests.
The saved-locations world map additionally has deterministic coverage for its
global Braille raster, collision-free native labels, resize/focus retention,
mouse and keyboard selection, padded screen integration, and return-to-weather
refresh path. The country map has corresponding checks for its native current
and nearby-city callouts, temperature updates, inversion, and in-place weather
selection while retaining the responsive context layouts. Live terminal colour
inversion, font-dependent Braille geometry, mouse behavior, and emoji alignment
still require manual checks.

Live behavior needs network access to Open-Meteo forecast, geocoding, and air
quality APIs. Alert behavior also depends on `wevva-warnings` and its provider
sources; country-wide alert retrieval can be noticeably slow. Do not treat a
network-dependent manual check as deterministic or claim it was performed when
it was not.

User preferences live outside the repository at
`~/.config/wevva/config.json`. Be aware that the setup wizard, CLI default
location options, and in-app settings/save-location actions can modify it.
Reading preferences does not create the directory or file. Writes create the
parent directory when needed and raise `ConfigWriteError` on failure; the CLI
prints that error and explicit mutations exit unsuccessfully, while the TUI
shows an error notification instead of reporting a successful save.
