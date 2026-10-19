# Task 0024: Interactive Alerts Centre map navigation

## Status

Proposed — interaction, performance, and scope boundaries recorded;
implementation not started

## Depends on

- Task 0020 supplies the Alerts Centre, selected-alert automatic viewport,
  warning layers, settlements, administrative labels, current-weather
  tooltips, and full Weather-screen activation.
- Task 0021 owns all contextual map-detail policy: label data sources,
  categories, ranking, candidate/display density, and any response to geographic
  scale. This task supplies an effective viewport and zoom ratio to that policy
  but does not decide how its labels are selected. Either task may be implemented
  first as long as this consumer boundary remains intact.
- Task 0023 supplies the shared terminal-cell callout planner. This task feeds
  new projected anchors into that planner without adding pan/zoom concerns to
  the planner itself.

## Context

The Alerts Centre currently chooses one automatic viewport: the whole country
when no polygonal alert is selected, or a tight fit around the complete
selected provider geometry. That makes warning footprints immediately useful,
but the user cannot inspect nearby geography, move a narrowly fitted warning
away from a label collision, or zoom further into a small affected area.

The existing stack already has the required low-level pieces: immutable
geographic viewports, Natural Earth country and place data, projected polygon
layers, the shared Braille raster, and deterministic callout placement. Recent
Alerts Centre work also coalesces identically styled warning layers and avoids
rasterizing duplicate projected polygons within a merged layer. Interactive
navigation should extend that stack locally rather than introduce a general
map widget.

A compact row of pan, zoom, and reset controls would make the alert map more
exploratory, and a small graphical scale would make the changing viewport
legible. Rebuilding every polygon and re-querying the existing label policy for
every repeated control event could, however, make the interface less responsive
on large alert collections such as the United States.

## Problem

- The automatically fitted viewport cannot be adjusted when useful context is
  just outside it or an alert is too small to inspect clearly.
- The map has no visual indication of distance or current scale.
- Pan and zoom can multiply existing selection/rendering costs unless raw
  geometry, visibility checks, redraw scheduling, and repeated input are kept
  bounded.
- Making viewport interaction a shared mapping abstraction would expand a
  playful Alerts Centre feature into a disproportionate mapping-engine
  project.

## Desired outcome

The Alerts Centre map gains one compact control strip:

```text
←  ↑  ↓  →    −  Reset  +
```

The controls move through a bounded local geographic extent, zoom around the
current viewport centre, and restore the automatic country/selected-alert fit.
Selecting another country or alert also restores that automatic fit.

Labels remain ranked, collision-aware, and geographically truthful under the
existing policy while the viewport moves. A restrained one-line scale bar
reports an appropriate rounded distance at the viewport centre.

Interaction remains responsive for large warning collections. The result is a
specialized `CountryAlertsMap` with a manual viewport override, not a slippy
map or reusable GIS framework.

## Scope

- Add caller-owned automatic and manual viewport state to
  `CountryAlertsMap`.
- Add focusable/clickable pan-left, pan-up, pan-down, pan-right, zoom-out,
  reset, and zoom-in controls in a one-line strip.
- Pan by a stable fraction of the visible span and zoom by a stable factor;
  choose the exact values from mounted interaction tests rather than exposing
  user configuration.
- Clamp minimum/maximum span and movement to a documented local navigable
  extent derived from the country map unit and selected provider geometry,
  with a modest context halo.
- Reset manual navigation when the country or selected alert changes. Preserve
  geographic centre and zoom through an ordinary terminal resize while
  refitting the viewport aspect ratio.
- Recompute visible land, warning layers, settlements, administrative labels,
  and callout placements from the effective viewport without network or file
  work.
- Expose the effective viewport and a stable zoom ratio relative to the
  automatic fit so Task 0021's source-neutral detail policy can consume either
  an automatic or manually navigated view.
- Add a passive graphical distance scale using rounded `1`, `2`, or `5 × 10ⁿ`
  distances calculated near the viewport centre. Use kilometres unless a
  genuine application-wide distance-unit preference exists by implementation
  time.
- Profile representative large-alert transitions and reduce avoidable work.
  Appropriate local techniques include cached normalized alert polygons,
  precomputed geographic bounds, cheap visibility rejection, merged raster
  layers, duplicate-polygon elimination, and one scheduled redraw for a burst
  of input.
- Keep settlement hover previews and activation behavior from Task 0020.

## Non-goals

- A common map base class, generic layer framework, or application-wide
  pan/zoom API.
- Map tiles, roads, buildings, addresses, land use, arbitrary rotation, smooth
  animation, inertial movement, drag gestures, minimaps, or navigation history.
- Unbounded world browsing from the country/alert map.
- Runtime geocoding, network-fetched context, or installation-time downloads.
- Changing contextual label data, categories, ranking, candidate caps, display
  budgets, or scale-adaptive density. All map-detail improvements—including
  showing more existing Natural Earth labels when zoomed—remain Task 0021.
- Changing provider geometry, treating nearby labels as evidence of warning
  applicability, or inventing affected areas from prose.
- Changing the behavior or public contract of the shared Task 0023 callout
  planner.
- Adding the controls to the weather, world, tropical, or warning-area maps.
- Persisting manual viewport state between application sessions or countries.
- Rendering controls or a scale when the terminal cannot spare the required
  row without making the map unusable.

## Interaction contract

### Automatic and manual modes

The existing automatic viewport remains authoritative after loading a country,
selecting an alert, clearing selection, or pressing Reset. The first pan or
zoom action derives a manual viewport from that automatic fit. Subsequent
actions alter only the manual viewport.

Selecting a different warning resets before rendering its geometry, rather
than carrying an unrelated manual centre or scale into the new alert. Resizing
the terminal must not silently reset an intentional manual view; it preserves
the geographic centre/span and fits the new canvas aspect ratio.

### Focus and repeated input

Every control must work by mouse and keyboard activation. Arrow-key shortcuts
may pan only while the map or its control strip owns focus so alert-list
navigation remains unchanged. `+`, `-`, and a reset key may follow the same
focus rule. Footer bindings are unnecessary unless manual testing shows they
improve discovery without clutter.

Holding a control or producing several actions before the next refresh must
coalesce into one pending geographic rebuild where practical. Input should
update the target viewport immediately but not queue an unbounded series of
obsolete rasterizations.

### Compact layouts

The control strip and scale are enhancements, not prerequisites for viewing an
alert. Define a minimum map content width and height. Below it, hide the scale
first and then the complete control strip; never allow partial controls,
wrapping, or a toolbar that consumes the selected-alert map. Reset remains
available programmatically when selection changes.

## Map-detail boundary

| Concern | Owning task |
| --- | --- |
| Which contextual features exist, qualify, rank, and appear at each geographic scale | 0021 |
| Where the user is looking, how they move there, the scale bar, and efficient redraws | 0024 |

Navigation necessarily asks the current label implementation for candidates in
the effective viewport and repositions surviving widgets. It must otherwise
preserve whichever candidate, ranking, display-budget, administrative-label,
and settlement-style policy is active. Avoid remounting unchanged Textual
widgets solely because the viewport moved.

Task 0021 owns any later decision to reveal more labels at closer scales, use a
denser source, separate administrative labels from settlements, or add physical
context. It consumes the effective viewport and zoom ratio established here;
it does not own the controls that produced them.

## Scale-bar contract

The scale is passive and visually subordinate to alert geometry and labels.
Use the effective fitted viewport and the latitude at its visual centre to
choose a distance that occupies a stable fraction of the map width. Round down
to a familiar `1`, `2`, or `5 × 10ⁿ` value and render a compact form such as:

```text
0 ├────┤ 50 km
```

The labelled distance must be derived from the same projection/geodesic
assumptions used to position the bar and remain within a documented tolerance
in high-latitude and wrapped-longitude fixtures. Hide it when there is not
enough horizontal space; never overlap focusable controls.

## Implementation slices

### Slice A — performance baseline and viewport model

- Add deterministic timing fixtures or separately runnable micro-benchmarks
  for a large alert collection, repeated shared zones, many unique polygons,
  and a dense focused viewport. Tests should assert bounded work or structure,
  not fragile wall-clock thresholds.
- Separate the automatically fitted viewport from an optional manual override
  in `CountryAlertsMap`.
- Add pure pan, zoom, clamp, and reset calculations with antimeridian and
  high-latitude coverage.
- Cache or index only the alert-map inputs proven expensive by profiling.
  Preserve recent merged-layer and duplicate-polygon behavior.

### Slice B — control strip and navigation

- Add the one-line controls and wire click, Enter, and Space activation.
- Apply fixed pan/zoom steps, selection reset, manual-view resize semantics,
  bounds, and minimum/maximum zoom.
- Coalesce repeated actions so obsolete intermediate viewport work does not
  accumulate.
- Hide the entire strip below its compact-layout threshold.

### Slice C — graphical scale

- Add a pure rounded-distance selection helper and concise scale-bar renderer.
- Position the passive scale beside or immediately above the control strip
  without covering geographic labels.
- Cover ordinary, high-latitude, tiny-span, very wide, antimeridian, and compact
  fixtures.

### Slice D — integration and performance hardening

- Exercise rapid control input, warning selection during a pending reflow,
  country changes, refreshes, theme changes, settlement hover/activation, pane
  tabs, and terminal resize.
- Compare representative selection and navigation profiles with the Slice A
  baseline and record structural improvements plus indicative local timings.
- Stop if acceptable responsiveness requires moving generic map orchestration
  into unrelated widgets; prefer leaving an identified follow-up over growing
  a framework.

## Acceptance criteria

- The Alerts Centre map exposes all seven controls in layouts that meet the
  documented size threshold and hides them cleanly in smaller layouts.
- Pan and zoom visibly change the effective viewport; Reset exactly restores
  the current automatic country/selected-alert fit.
- Selecting another alert or country resets manual navigation before the new
  map is rendered.
- Terminal resize preserves an intentional manual geographic view while
  adapting it to the new aspect ratio.
- Navigation cannot escape the documented bounded context extent or exceed
  minimum/maximum zoom.
- Alert-list arrow navigation and other global bindings do not pan the map
  unless map controls own focus.
- A burst of repeated input leaves at most one pending map rebuild and does not
  replay obsolete intermediate views.
- Warning polygons retain dim context/full selected styling, correct land/sea
  treatment, selected-alert draw priority, and provider geometry.
- Settlement and administrative candidates follow the pre-task label policy
  for the effective viewport; Task 0024 does not alter their ranking or
  density. Settlement markers remain on their projected cells and keep their
  tooltip and full-forecast activation interaction.
- The graphical scale uses a rounded distance, responds to pan/zoom/resize, and
  stays within the documented calculation tolerance.
- No control action performs network access, reloads packaged geography, or
  blocks on a background provider request.
- Large-alert navigation avoids work proportional to every alert layer when
  cheap bounds can reject it, and duplicate/shared warning polygons are not
  rasterized repeatedly within the same visual layer.
- Existing non-alert maps and Task 0023 callout behavior remain unchanged.

## Relevant code

- `wevva/widgets/country_alerts_map.py`
- `wevva/widgets/geographic_scope.py`
- `wevva/widgets/map_callouts.py` as a stable consumer boundary
- `wevva/geography.py`
- `wevva/screens/alerts_centre_screen.py`
- `wevva/alerts_centre_layout.py`
- `wevva/wevva.tcss`
- `tests/test_alerts_centre_map.py`
- `tests/test_alerts_centre_layout.py`
- `tests/test_alerts_centre_screen.py`
- `docs/architecture.md`
- Tasks 0020, 0021, and 0023

## Verification

```bash
uv run python -m compileall -q wevva
uv run python -m unittest tests.test_alerts_centre_map
uv run python -m unittest tests.test_alerts_centre_layout
uv run python -m unittest tests.test_alerts_centre_screen
uv run python -m unittest tests.test_map_callouts
uv run python -m unittest discover -s tests
```

Use deterministic geometry fixtures for whole-country, focused-alert,
antimeridian, high-latitude, existing-label, repeated-zone, and mostly unique
polygon cases. Patch or instrument projection/raster calls where necessary to
assert coalescing, rejection, and redraw counts without depending on machine
speed.

Manually inspect at least one large US warning collection and representative
small-country, island, cross-border, and marine alerts. Check mouse and
keyboard activation, held controls, focus return to the alert list, existing
label stability while moving, scale plausibility, reset behavior, settlement
preview/activation, and compact layouts. Record terminal dimensions and indicative
timings without claiming universal live-provider performance from one run.

## Decisions and notes

- This is a new task rather than an extension of completed Task 0020 because it
  adds stateful map navigation and a new interaction surface.
- Task 0023 deliberately excluded pan/zoom and remains complete. Its callout
  planner consumes projected candidates but does not own viewport state.
- All contextual label-detail improvements belong to Task 0021. Task 0024 only
  supplies the effective viewport and relative zoom needed to apply them.
- Controls and scale are progressively hidden before sacrificing useful map
  height.
- Performance work must follow measurements and stay local to the alert map.
  Do not introduce a generic spatial engine speculatively.

## Outcome

Not yet implemented.
