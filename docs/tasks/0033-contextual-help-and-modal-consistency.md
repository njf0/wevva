# Task 0033: Contextual help and modal consistency

## Status

Planned

## Context

The Dashboard is now the navigation hub, with Settings, Help, Credits, and Quit
available consistently from every main workspace. The content and presentation
behind those bindings have not received the same pass.

The current surfaces are small but visibly unrelated:

- `HelpScreen` is a wide scrolling Markdown panel with a heavy muted border and
  no header;
- `SettingsScreen` uses a thick primary border, a separate title row, generous
  padding, and an unconstrained auto-height form;
- `AuthorScreen` uses a panel border, its own hatch/background choices, and
  inline theme-derived Rich colours; and
- `AirQualityHelp` is a second help modal with a full-width accent frame,
  commented-out CSS, and a large fixed table.

The general help text now describes the navigation model accurately, but it is
the same from every screen. The only contextual behavior is Weather's special
case for a focused `AirQualityWidget`. Dashboard, World Map, Tropical Systems,
and Alerts Centre each have a few non-obvious interactions which deserve a
short reminder without turning Help into a manual.

## Desired outcome

Help, Settings, Credits, and Air Quality help should look like a restrained
family of Wevva modals and remain usable at supported terminal sizes. General
help should retain a concise common section and add a small section relevant to
the current screen. A very small number of focused widgets may refine that
section when their interaction or terminology genuinely needs explanation.

This is presentation and copy maintenance, not a new help system. Prefer a few
explicit context choices and modest shared styling over a modal superclass,
help registry, widget protocol, or documentation framework.

## Scope

### Consistent modal presentation

- Give Help, Settings, Credits, and Air Quality help the same basic backdrop,
  panel background, border/title treatment, padding rhythm, and close behavior.
- Use one header/footer policy across the four surfaces, including the standard
  clock and visible Escape/Close affordance where appropriate.
- Retain different sensible widths: Credits may remain compact, Settings should
  fit its controls, and Help may be wider and scrollable. Consistency does not
  require identical dimensions.
- Make the panels responsive rather than assuming the preferred width is
  available. Settings and help content must scroll within the modal instead of
  overflowing at `80x24`.
- Remove obsolete commented CSS and avoid inline theme lookups where ordinary
  Textual theme variables can express the same styling.
- A tiny shared presentation helper or CSS constant is acceptable only if it
  clearly removes duplication. Repeating a few direct CSS declarations is
  preferable to inventing a base modal class.

### Concise contextual help

- Keep a short common section for the Dashboard navigation hub and the shared
  Settings, Help, Credits, and Quit bindings.
- Add a small active-screen section selected explicitly from the current
  screen. Each section should normally be three to six bullets:
  - Weather: forecast navigation, saved-location/warning rails, and Dashboard;
  - Dashboard: selecting map features, the forecast/detail regions, compact
    tabs, and specialist-workspace shortcuts;
  - World Map: moving between labels, activation, and return to Dashboard;
  - Tropical Systems: storm/source/product selection, refresh, map-place
    activation, and return to Dashboard; and
  - Alerts Centre: country/filter navigation, preview versus selection, map
    places, document reading, refresh, and return to Dashboard.
- Preserve useful Air Quality terminology and units, but bring its presentation
  into the same modal family. It may remain a focused help view rather than
  forcing a large glossary into every general-help opening.
- Add another focused-widget variation only where testing the application
  identifies a genuinely non-obvious interaction. Do not add help hooks to
  every widget or make widgets publish their own prose.
- Keep copy close to implemented behavior and current bindings. Do not document
  planned controls, live-provider guarantees, or terminal rendering behavior
  which the application cannot promise.

### Settings and credits copy

- Add only brief Settings guidance where the consequence is not self-evident:
  the difference between applying for the session and saving defaults, warning
  language behavior, terminal-dependent emoji rendering, and default-location
  actions.
- Keep labels and capitalization consistent and avoid turning the form into a
  long preferences guide.
- Refresh Credits to acknowledge the primary application, weather/warning, map
  data, and terminal UI sources actually used by Wevva. Keep it short and use
  clickable links only where Textual already supports them.
- Do not attempt an exhaustive transitive-dependency or legal-notice screen.

## Non-goals

- Redesigning Search, saved-location, warning-reader, or alert-filter modals.
- A generic modal framework, help registry, context-provider protocol, command
  palette, tour, onboarding flow, or per-widget documentation API.
- Adding new settings or changing preference persistence, application bindings,
  screen navigation, forecast behavior, provider calls, or cache ownership.
- Rewriting the README or architecture documentation into the modal. User help
  should remain concise and task-oriented.
- Perfect prose for every possible focus state. Screen-level help with a few
  high-value refinements is sufficient.

## Approach

### Step 1 — one small visual language

Choose the common panel chrome from the application's existing header, footer,
hatch, theme, and bordered-panel language. Apply it directly to Help, Settings,
Credits, and Air Quality help, including responsive width/height and scrolling.
Remove dead CSS while preserving each modal's content and result contract.

### Step 2 — contextual content and concise copy

Pass the active screen context into Help through the existing app action and
render one common binding section plus one short screen section. Retain the Air
Quality focused path in the simplest form that fits the common presentation.
Polish the small Settings explanations and Credits attribution at the same
time.

### Step 3 — focused verification and documentation

Add compact tests for context selection, modal composition, Escape/result
behavior, and the Settings Apply/Save distinction. Exercise the four surfaces
at `80x24` and a comfortable larger size, then update README/architecture only
where the user-visible help contract or ownership boundary needs recording.

These are implementation steps, not independent feature slices; they may land
together when the diff remains easy to review.

## Acceptance criteria

- Help, Settings, Credits, and Air Quality help share recognizable backdrop,
  panel, title, spacing, and close treatment without a new modal framework.
- All four remain contained and usable at `80x24`, with internal scrolling where
  content exceeds the available height.
- `h` and `?` show the correct concise section for Weather, Dashboard, World
  Map, Tropical Systems, and Alerts Centre.
- Focused Air Quality help still explains the displayed measures and units.
- Help content matches the Dashboard-hub bindings and does not advertise stale
  Weather-to-specialist shortcuts.
- Settings clearly distinguishes Apply from Save Defaults and preserves its
  existing result payload and persistence behavior.
- Credits remain compact while covering Wevva's principal data/UI sources.
- Escape closes each modal and returns to the same underlying screen without
  changing its selection, scroll, or fetch state.
- Opening help, settings, or credits starts no provider request and introduces
  no screen-owned background task.

## Relevant code

- `wevva/app.py`
- `wevva/screens/help.py`
- `wevva/screens/air_quality_help.py`
- `wevva/screens/settings_screen.py`
- `wevva/screens/author_screen.py`
- `wevva/screens/weather_screen.py`
- `wevva/screens/dashboard_screen.py`
- `wevva/screens/world_locations_screen.py`
- `wevva/screens/tropical_systems_screen.py`
- `wevva/screens/alerts_centre_screen.py`
- `wevva/wevva.tcss`
- `tests/test_navigation_bindings.py`

## Verification

```bash
UV_CACHE_DIR=/tmp/wevva-uv-cache uv run python -m unittest \
  tests.test_navigation_bindings tests.test_settings_screen tests.test_help_screens
UV_CACHE_DIR=/tmp/wevva-uv-cache uv run python -m compileall -q wevva
```

Create the two focused test modules named above if they do not yet exist. Manual
checks should cover Help, Settings, Credits, and focused Air Quality help over
Weather and at least one specialist screen at `80x24` and a larger terminal.
Do not claim exact colour, link, font, or scroll presentation from mounted tests
alone.

## Dependencies and decisions

- This task starts after the Dashboard-hub binding change in `dd78d7e` and must
  preserve that binding order and ownership.
- It is independent of Task 0031 tropical viewport framing.
- The default implementation is explicit screen-context selection in the
  existing app/help boundary. Introduce a shared abstraction only if the first
  implementation clearly becomes smaller and easier to read because of it.
- Three to six useful bullets for a screen are better than exhaustive help for
  every control.
