# Task 0014: Tropical systems screen handoff

## Status

In progress; implementation is substantially complete and awaiting final live
visual verification and the normal dependency release transition.

## Context

The tropical-system work spans sibling `wevva` and `wevva-warnings`
repositories. During development, `wevva` deliberately uses the editable local
checkout at `../wevva-warnings`; the warning library is authoritative for
canonical grouping, display-geography metadata, source observations, and lazy
supplementary products.

## Problem

The work must be reproducible on another machine without losing either half of
the implementation or mistaking the local dependency override for the eventual
release configuration. A concise list of completed behaviour, remaining checks,
and release cleanup is needed before committing the two worktrees.

## Desired outcome

Both repositories can be committed and transferred together, the dedicated
screen remains testable against the sibling checkout, and the remaining work is
explicit rather than hidden in conversation history.

## Scope

- Record the implemented global tropical workspace and its data boundaries.
- Record the correct two-repository handoff and later release sequence.
- Identify deterministic checks and provider-dependent manual checks still due.
- Preserve the local weather alert and CAP paths independently.

## Non-goals

- Publishing either package as part of this handoff.
- Canonical meteorology, source ranking, fuzzy storm matching, or averaging.
- CAP-to-canonical-storm association.
- New provider acquisition, forecast cones, or map-framework features in
  `wevva`.

## Relevant code

- `wevva/screens/tropical_systems_screen.py`
- `wevva/widgets/tropical_summary.py`
- `wevva/widgets/tropical_centre_weather.py`
- `wevva/widgets/tropical_track.py`
- `wevva/services/tropical.py`
- `wevva/geography.py`
- sibling `wevva-warnings` public models, query functions, and tropical backends
- `pyproject.toml`, `uv.lock`, and `docs/development.md`

## Approach

The weather screen keeps a compact Nearby Tropical Systems launcher and its
existing location-specific tropical/CAP alert tabs. The dedicated screen owns
global storm investigation: severity-ordered canonical storm tabs,
source-specific observations, current weather near the selected centre, a
persistent fitted track/cone pane, and lazy official products.

The map always uses the fitted global Natural Earth backdrop. Declarative
`DisplayGeography` metadata contributes only a source-context label when that
geography is visible; the selected forecast location never determines the map.
Track dots and cone visibility are independent, but hidden layers remain part
of layout so toggles do not move or clip the remaining marks.

## Acceptance criteria

- One canonical name appears once and retains separate source observations.
- Product requests are lazy, cached, format-aware, and failure-isolated.
- The weather-screen launcher and location-specific alert tabs remain intact.
- Wide and compact layouts keep the summary/weather/track column beside the
  product reader without crushing its document width.
- `r` refreshes tropical systems and selected-source products while the track
  updates in place; `t` and `c` independently toggle dots and cone.
- HKO forecast tracks contain only genuine timed forecast fixes, not untimed
  smooth-curve vertices.
- Both repositories pass their documented test and build commands.

## Verification

Deterministic checks:

```bash
# In ../wevva-warnings
uv run python -m unittest discover -s tests -v
uv build

# In ../wevva
uv run python -m compileall -q wevva
uv run python -m unittest discover -s tests
uv build
```

Manual provider-dependent checks still required when representative systems are
active:

- CPHC: Hawaii label, complete official cone, products, and centre weather.
- NHC Eastern Pacific: visible nearby global land and unclipped cone/track.
- HKO: only timed 24-hour forecast dots through the available horizon.
- Météo-France La Réunion: Réunion context when it lies in the fitted view.
- Wide and compact terminal sizes: stable two-column framing, scrolling product
  body, loading overlays, and unchanged positions when toggling the cone.

These are live-source and terminal-rendering checks, not deterministic tests.

## Decisions and notes

- Storm tabs are ordered by declared classification severity, not distance.
- No source observation is merged or averaged.
- Single-source storms omit the redundant source tab row.
- The screen uses full classification names in storm tabs.
- Current centre weather is a separate Open-Meteo request and may fail without
  affecting source analysis, products, or the track.
- The sibling HKO parser now filters `ForecastInformation` to entries carrying
  both a timestamp and numeric forecast-hour index; its fixture covers the
  untimed-curve regression.
- Optional future changes to display-geography component selection and named
  smooth-curve geometry are deliberately deferred to sibling task 0017; they
  are not required to commit or reproduce the current global-backdrop screen.
- The editable source and lock entry intentionally remain for development.

## Outcome

Before transferring work, commit `wevva-warnings` first and record that commit,
then commit `wevva`. Clone both repositories as siblings on the next machine and
check out those matching commits before running `uv sync --locked` in `wevva`.

Before a normal `wevva` release, publish a compatible `wevva-warnings` release,
update the declared dependency version, remove `[tool.uv.sources]`, regenerate
`uv.lock`, and rerun both projects' tests/builds. Publishing remains an explicit
maintainer action and is not part of this task.
