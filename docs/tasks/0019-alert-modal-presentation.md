# Task 0019: Alert modal presentation and warning-area map

## Status

Complete — implemented with deterministic modal geometry and selection tests

## Context

The weather screen deliberately keeps its compact warning summary small. Its
tabbed modal is therefore the reliable place to inspect the complete provider
document at every weather-screen density. The optional wide warning rail also
shows the selected warning polygon, but the modal currently shows prose alone.

The modal already has the correct document structure: one rounded collection
frame, alert tabs, and a full independently scrolling warning body without the
old nested `Alert Details` border. This task refines that structure rather than
introducing another warning reader.

## Problem

- Compact and ordinary weather layouts expose no warning polygon after opening
  the modal, even when the alert contains usable geometry.
- The modal title is generic instead of matching the established
  `N Severe Weather Alerts` collection title.
- The outer modal border does not follow the selected alert's semantic severity
  colour as the weather-screen warning panel does.
- The title treatment should be bold and centred.
- The dialog can appear visually pinned toward the top at some terminal sizes;
  its centred geometry is not covered by a rendered regression test.
- Tab selection updates only the prose, so adding a map without one shared
  selection path would risk stale geometry.

## Desired outcome

Opening either compact or tabbed weather warnings produces one centred modal.
Its alert tabs select a complete provider document and, when geometry exists, a
side-by-side warning-area map. The prose and map always describe the same
selected alert. The outer border and title use the selected alert's severity
colour, while the title reads `N Severe Weather Alert(s)` in bold centred text.

## Stable composition

For alerts with geometry at the supported 80-column width and above:

```text
┌──────── N Severe Weather Alerts ────────┐
│ Alert tabs                                      │
│                                                   │
│ Full provider document       Warning Area map    │
│ independently scrollable     selected polygon    │
│                                                   │
└────────────────────────────────────────────────────┘
```

The document remains the larger peer. At 80 columns the map may use a compact
fixed/minimum width while the document uses the remainder; wider terminals may
approach an approximately 60/40 split. Both use the same available height. The
document owns vertical scrolling, not the modal page.

If the selected alert has no polygon, collapse the map region completely and
give its width back to the document. Do not reserve an empty map or invent a
warning footprint from area names. Below the supported width, preserve the
document first; exact fallback behavior is fixture-driven.

## Approach

### One selection path

Extend `WeatherAlertsReader` so `_show_alert(...)` updates a reusable selected
alert presentation rather than only `details.content`. That presentation owns:

- the existing unframed `WeatherAlertDetailsPanel`;
- one `WarningAreaScope`; and
- a selected-alert change message or callback which lets the modal update its
  frame title/colour.

The modal and wide details rail must continue to reuse `alert_renderable(...)`
and `WarningAreaScope`; do not fork provider-text or polygon rendering.

The modal can resolve its forecast location context from the active app in the
same way as `WeatherAlertDetailsSidebar`: prefer forecast metadata coordinates,
fall back to the selected location, and pass its country code and short label
to `WarningAreaScope`.

### Modal frame

- Keep one rounded outer frame.
- Set its border and border-title colour through `alert_severity_color(...)`
  whenever the selected tab changes.
- Set `border_title` to `1 Severe Weather Alert` or
  `N Severe Weather Alerts`.
- Use bold title style and centred title alignment.
- Keep the prose panel unframed. A modest titled border around the distinct map
  peer is acceptable, but must not recreate an `Alert Details` frame.
- Keep Escape dismissal and current tab keyboard behavior.

Severity remains the semantic base colour. Focus and selected-tab styling must
remain visibly distinct without replacing that meaning; exercise every
supported severity with both focused and unfocused tabs under contrasting
built-in themes.

### Centring

Treat centring as geometry, not visual intent. The modal screen and any
intermediate stage must fill the viewport and align the dialog `center middle`.
The dialog should use percentage width/height with useful maxima and no dock or
offset which can pin it to the top.

Rendered tests should compare the free space above/below and left/right the
dialog, allowing at most one terminal cell of rounding difference. Test both a
compact supported terminal and a large terminal.

## Scope

- Add selected warning geometry to the existing tabbed modal.
- Keep prose and geometry synchronized on tab changes.
- Apply selected severity colour to the outer modal frame.
- Use the bold centred alert-count title.
- Correct and test true viewport centring.
- Preserve internal prose scrolling and modal selection through resize.

## Non-goals

- Changing how weather-screen alerts are fetched, filtered, cached, or sorted.
- Showing all country alerts or changing the warning applicability calculation.
- A country selector, list search, or multi-alert map.
- New polygon inference, geocoding, pan, or zoom.
- Replacing the compact weather-screen warning summary or roomy preview tabs.
- Making the warning map interactive.

## Relevant code

- `wevva/widgets/weather_alerts.py`
- `wevva/widgets/warning_area.py`
- `wevva/screens/weather_screen.py`
- `tests/test_warning_area.py`
- `tests/test_responsive_weather_screen.py`

## Acceptance criteria

- Opening warnings from an 80x24 weather screen can show the selected alert's
  real polygon beside its complete provider text.
- Switching tabs updates prose, map geometry, modal border colour, and scrolls
  the new document home as one operation.
- An alert without geometry uses the full document width and shows no empty map
  frame.
- The outer title is bold, centred, and uses the exact singular/plural alert
  count wording.
- The rounded outer border and title use the selected alert's semantic severity
  colour.
- The prose has no nested `Alert Details` border and retains independent
  vertical scrolling.
- The dialog is geometrically centred at compact and large terminal sizes.
- Resize preserves the selected alert tab and never pushes the dialog behind
  the footer or outside the viewport.
- Resizing or changing presentation density performs no warning or weather
  request.
- The optional wide warning rail continues to render the same provider text and
  warning-area geometry.

## Verification

```bash
uv run python -m compileall -q wevva
uv run python -m unittest tests.test_warning_area
uv run python -m unittest tests.test_responsive_weather_screen
uv run python -m unittest discover -s tests
```

Use deterministic polygon fixtures for alerts with different geometry and
severity plus an alert without geometry. Render at 80x24, a medium size, and a
large size, including long prose, missing official links, and each supported
severity with focused and unfocused tabs. Manual checks remain useful for theme
colour balance, mouse tab selection, Braille appearance, and long real provider
prose.

## Decisions and notes

- This is a presentation task; the modal still receives only the alerts already
  applicable to the selected weather location.
- Polygon absence is an ordinary provider-data condition, not an error.
- The existing severity-colour helper remains authoritative across summary,
  tabs, modal frame, and polygon fill.
- The future country alerts centre is Task 0020 and should reuse the document
  presentation produced here rather than expanding this modal into a workspace.
