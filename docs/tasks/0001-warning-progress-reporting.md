# Task 0001: Report warning-query progress

## Status

Complete

## Context

Some warning providers return country-wide feeds and require many linked
warning documents or geometries to be checked for the selected point. The TUI
currently shows nothing until the complete warning query returns.

## Problem

Users cannot tell whether no warnings apply or the warning lookup is still
working, which can take several minutes.

## Desired outcome

Only while individual warning documents, geometries, or candidates are being
checked, the saved-locations sidebar shows a Textual progress bar with the
human warning-provider name. It disappears when the final warning result is
rendered.

## Scope

- Use the public `wevva-warnings` progress callback.
- Route progress safely from its worker thread to the Textual UI.
- Preserve stale-result protection when location or refresh changes.
- Use the local `wevva-warnings` checkout as an editable development source.
- Show no UI during source discovery; show a `ProgressBar` only once a concrete
  individual-work total is available.
- Place the transient progress in the saved-locations sidebar so it does not
  reflow the main forecast layout.

## Non-goals

- Do not reimplement warning-provider querying in `wevva`.
- Do not publish or release either package.
- Do not change final alert filtering or presentation.

## Relevant code

- `wevva/services/alerts.py`
- `wevva/app.py`
- `wevva/messages.py`
- `wevva/screens/weather_screen.py`
- `wevva/widgets/saved_locations.py`
- `pyproject.toml`

## Approach

Forward the optional public callback through the alert service. In `Wevva`,
schedule each worker-thread callback on the running event loop, verify it still
belongs to the active refresh/location, and post a Textual message to the
weather screen.

## Acceptance criteria

- A warning lookup displays progress without delaying the forecast display.
- Source discovery is silent; document, geometry, and matching counts are shown
  with a Textual `ProgressBar` when the warning library provides them.
- No internal warning-provider identifier is displayed.
- Progress does not alter the main weather layout.
- Progress from an older refresh or location is ignored.
- Final alert and no-alert behaviour remains intact.

## Verification

- Refresh a location while using the local editable warning dependency.
- Run the available source compilation check.
- Verify the alert-service callback path without calling an external provider.

## Decisions and notes

The local `wevva-warnings` checkout provides the new public API at version
`0.3.3`. `wevva` must not be released until that dependency version is
published.

## Outcome

- Added an editable local `wevva-warnings` 0.3.3 source override and updated
  the released dependency floor to `>=0.3.3`.
- Forwarded the library's public callback through the alert service, safely
  scheduled worker-thread updates on Textual's event loop, and kept refresh/
  location generation checks before rendering.
- Captured `WarningSource.name` at source start and attached it to later
  document/geometry/matching events, keeping the callback payloads suitable for
  future presentation without exposing an internal source ID.
- Replaced the initial text status with a bordered Textual `ProgressBar` below
  a separately bordered, titled saved-locations panel. Provider discovery is
  silent; the bar appears only for known individual-work totals and leaves the
  main forecast layout stable. The panel now relies on the built-in percentage
  display rather than an additional status label.
- Verified source compilation, editable import resolution, callback forwarding,
  progress formatting, and the headless Textual progress-bar lifecycle. The
  local warning package remains unpublished, so `wevva` must not be released
  until `wevva-warnings` 0.3.3 is published.
