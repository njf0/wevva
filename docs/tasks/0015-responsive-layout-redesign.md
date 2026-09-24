# Task 0015: Budget-driven weather layout

## Status

In progress — Slices A and B complete; Slice C partially exercised

## Context

The weather screen has a strong existing visual identity: summary, warning
presence, four current-condition instruments, an hourly forecast with day tabs,
a daily forecast, and supporting location/astronomy/air-quality/map context.
The redesign should preserve that hierarchy instead of substituting unrelated
compositions at different breakpoints.

The present layout is centred around fixed-width forecast widgets and can leave
large terminals underused or require full-page scrolling when height is scarce.
The replacement should treat terminal rows and columns as explicit budgets and
let each existing widget select an appropriate density.

`docs/responsive-layout.md` contains the broader design exploration. Where its
older composition examples conflict with this task, this task is the current
implementation source of truth.

## Problem

The current screen has no shared understanding of the space required by its
children. Individual widgets assume relatively fixed dimensions, the hourly
forecast makes the whole screen approximately 24-hour-table width, and the map
adds a large vertical block. Sidebars also subtract width after the central
layout has effectively been chosen.

Ad-hoc breakpoints would move the problem rather than solve it: a warning,
sidebar, long unit label, or one-row terminal resize could still create page
scrolling or clipped widgets. The screen needs a deterministic allocation
contract, while each widget needs a small set of meaningful density choices.

## Desired outcome

The weather screen retains one stable composition and responds to its actual
usable rows and columns by:

- selecting standard, small, or smallest variants of existing instruments;
- adding or removing complete hourly rows, daily columns, and daily rows;
- horizontally scrolling the complete hourly time series;
- presenting locations and warning details in modals unless a side rail can be
  afforded without degrading the central forecast;
- showing supporting context in a two-column matrix with the map spanning the
  three context rows; and
- never requiring the main weather page itself to scroll vertically.

## Stable composition

Major regions remain in this order at every supported size:

```text
Weather summary
Warning summary, when active
Temperature | Precipitation | Wind | Detail
Hourly forecast
Daily forecast
Location    |             |
Astronomy   | Country map |
Air quality |             |
```

The bottom context block is a two-column, three-row grid. Location, astronomy,
and air quality are stacked in the first column; the map occupies the second
column and spans all three rows. The block appears only when it fits as a
coherent unit. It must not push hourly or daily forecast content into page
scrolling.

The main content retains `padding: 1 2` and visible hatched gutters between
bordered instruments at 80x24 and above. Below the supported minimum, content
degrades before gutters are removed.

## Layout budget contract

Introduce a pure, centrally tested calculation based on the main panel's
post-dock width and height. It should return presentation choices, not a named
desktop/mobile screen:

```text
current_density: standard | small | smallest
current_height
detail_rows
full_detail_labels
hourly_rows
daily_columns
daily_row_count
show_context_matrix
locations_presentation: modal | sidebar
warning_details_presentation: modal | sidebar
```

The calculation must account explicitly for borders, tabs, content padding,
and inter-widget gutters. Widgets expose a narrow `set_layout(...)`-style API
and remain mounted; the screen must not reach into numerous child labels or
recompose the widget tree on resize.

At the supported 80x24 baseline, with an active warning, the screen should fit:

- the titled, bordered weather summary and one separating hatch row;
- a fixed-height bordered warning summary;
- one hatched separation row below the warning;
- the smallest one-line four-widget current-condition row;
- hourly condition, temperature, and time rows plus its horizontal
  scrollbar; and
- the standard outer padding and gutters.

At this height hourly rain/wind and the daily table are deliberately omitted.
Without an active warning, rain and wind return and current conditions use the
`small` static presentation. Daily appears only when at least two complete day
rows fit.

If a layout below the supported minimum cannot contain that baseline, remove
the lowest-priority complete region or row rather than enable main-page
scrolling or show partial content.

After satisfying the baseline, spend additional rows in a deterministic order.
The initial order to validate against rendered fixtures is:

1. add hourly rain, then wind;
2. enlarge current conditions from `smallest` to `small`, then to the standard
   `Digits` presentation when row height and per-tile width support it;
3. add the daily table atomically with two complete rows, followed by more
   complete rows;
4. add hourly graph rows in the order temperature, rain, then wind;
5. add the remaining daily rows and wider optional daily fields; and
6. show the complete context/map matrix when its minimum geometry fits.

Active-warning presence is reserved before optional upgrades. When space is
lost, upgrades are removed in reverse order. The precise crossover points are
fixture-driven and may be tuned without changing the public budget contract.

## Widget behavior

### Current conditions

Keep the existing four peers—temperature, precipitation, wind, and detail—in a
single row.

- `standard`: retain the current large `Digits`, units, and lower supporting
  line.
- `small`: replace `Digits` with a coloured bold static value, retain the lower
  line, and use a flexible spacer to absorb one to three available blank rows.
  Supporting text becomes more concise, for example `Feels 14°C`.
- `smallest`: show only the primary static value on one line, for example
  `14°C`; supporting values return in `small`.
- `detail`: retain its table and reduce complete rows as its height falls.
  Initial row priority is humidity, visibility, pressure, UV, then cloud cover;
  validate this order visually and meteorologically before implementation.
  Keep a six-cell abbreviated label field in constrained layouts; at 102 usable
  columns expand it to eleven cells and use the full field names.

Compose standard and static value children once inside the existing metric
widget and switch their visibility. Do not create a separate current-weather
composition.

### Weather warnings

When alerts exist, compact presentation is a one-content-line, bordered,
focusable and clickable static value such as:

```text
Moderate High Temperature Warning · +3 more
```

Do not include an `[open]` label. Use severity colour, focus treatment, mouse
activation, Enter, and Space to communicate interactivity. Activation opens a
modal containing the established warning tabs and an independently scrolling
detail body.

The card has a fixed three-row cost including its border; long provider event
names are shortened or elided rather than wrapped.

### Hourly forecast

Build the complete selected day, up to the existing 24-hour cap, and place the
table in a horizontally scrollable viewport. Resizing changes viewport width,
not the represented hours. Cursor movement must reveal the selected column and
selected hour/day state must survive resize.

At narrow widths, show an explicit `◀`/`▶` track and thumb tied to the real
table scroll position, plus a concise keyboard hint. At widths where all hours
fit, keep the hourly columns at their compact four-cell width and remove the
scroll affordance. Fixed columns keep the dense telemetry rhythm on very wide
terminals instead of adding empty space around every value. Cap and centre the
outer frame at 98 cells: 24 four-cell hours plus the two border cells.

Required rows are:

1. condition;
2. temperature value;
3. time.

Optional rows are enabled in this priority order:

1. rain value;
2. wind value;
3. temperature bars;
4. rain bars; and
5. wind bars.

Keep the existing day tabs and day-boundary language.

### Daily forecast

Width selects complete column groups; height selects complete day rows.

Essential fields, which must fit within the supported 80-column composition,
are:

- short date;
- condition;
- minimum/maximum temperatures;
- combined rain information; and
- combined wind information.

Wider variants may progressively add a full condition label or emoji, separate
precipitation amount, gust detail, longer date, sunrise, and sunset. Narrow
variants may use established condition abbreviations such as `OC` and `TS`.
Never expose a partially clipped field or day row.

Size the centred daily frame to its active columns. Condition abbreviations use
a four-cell field and split rain probability uses six. When precipitation
amount or gusts are absent, rain and wind temporarily reclaim enough width for
their combined compact forms; when those fields split out, that width is
released rather than left as padding. Order split precipitation amount directly
after rain probability, before wind speed and gusts. At 102 or more usable
columns, switch to the original wide table rather than stretching the compact
fields: `Day 13`, `Condition 31`, `Min-Max 8`, `Rain% 5`, `Precip 7`, `Wind 13`,
`Wind Direction 5`, `Sunrise 7`, and `Sunset 7`. This restores full weekday and
condition names, combines gusts inside the wind field, and produces a 96-cell
table in a centred 98-cell frame.

### Context matrix

Refactor `ContextBar` into a stable grid-capable context region. Reuse the
existing location, astronomy, air-quality, and country-map widgets. The map
should be approximately square in its rendered terminal proportions and have a
bounded useful maximum; it should not stretch merely because more width exists.

The context matrix is an optional complete block. Compact variants for its
three information widgets can be added later if fixture measurements show that
they materially improve the useful range of the block.

### Locations and warning details

Factor reusable content from the current docked containers so the same stateful
content can be hosted by either a modal or a sidebar shell.

- Modal is the default presentation.
- A sidebar is eligible only when its width plus gutter can be removed while
  leaving the central weather region above its tested minimum width.
- Opening locations or warning details chooses the eligible shell without
  changing selection, tab, or document-scroll state.
- The compact warning summary specifically opens the modal reader.
- Sidebar appearance must feed back into the usable-width calculation; it may
  not silently squeeze or horizontally clip the central forecast.

## Scrolling policy

- The primary weather panel is not vertically scrollable.
- Hourly forecast scrolls horizontally within its own viewport.
- Warning documents scroll vertically inside their modal or wide sidebar.
- Saved locations scroll vertically inside their modal or wide sidebar.
- Maps never scroll internally.
- Daily forecast changes its complete row count instead of scrolling the main
  page.
- Focused nested scroll areas retain visible focus and predictable keyboard
  escape/navigation.

## Implementation slices

This should not be implemented as one wholesale patch, but the core forecast
must not be split into unrelated widget releases. Use vertically complete
slices:

### Slice A: measurement and budget foundation (complete)

- Add deterministic weather, warning, and map fixtures.
- Record the exact row costs of borders, tabs, gutters, and padding.
- Introduce the pure budget result and threshold/priority tests.
- Add rendered geometry checks for the terminal-size matrix.
- Do not change the visible default layout yet.

### Slice B: compact operational weather screen (complete)

- Add `small` and `smallest` variants within existing current widgets.
- Add collapsible detail rows.
- Make hourly a horizontally scrolling full-day table with budgeted rows.
- Add width-budgeted daily fields and height-budgeted complete rows.
- Add the bordered warning summary and tabbed modal warning reader.
- Integrate these consumers with the budget calculation.
- Enforce and test the 80x24 no-page-scroll contract.

This is the largest slice because these instruments compete for the same rows
and must be evaluated together.

### Slice C: spend surplus space

- Tune standard/small current crossover points.
- Enable graph rows and additional daily rows/fields according to the budget.
- Verify resize preserves hour, day, alert tab, focus, and horizontal position.
- Exercise wide-but-short and narrow-but-tall cases independently.

### Slice D: context matrix

- Move the map into the two-column context grid.
- Stack location, astronomy, and air quality in the first column.
- Establish minimum and maximum map geometry.
- Show or remove the block atomically according to the remaining budget.

### Slice E: modal-first auxiliary surfaces and wide rails

- Add the saved-locations modal and reusable content host.
- Make warning details and locations modal-first.
- Promote either surface to a sidebar only when the central-width contract is
  satisfied.
- Verify transitions preserve selection and scroll state.

### Slice F: tuning and documentation

- Tune priorities and thresholds using the full deterministic matrix.
- Check long units, warning names, emoji on/off, and alternate themes.
- Replace superseded examples in `docs/responsive-layout.md`.
- Update architecture, development, and README documentation to describe only
  implemented behavior.

## Scope

- Weather-screen row and column budgeting.
- Density variants of existing weather widgets.
- Horizontal hourly scrolling and stable selection.
- Daily field/day budgeting.
- Compact warning summary and warning modal.
- Modal-first saved locations and warning details with conditional wide rails.
- Bottom context/map matrix.
- Deterministic resize and geometry coverage.

## Non-goals

- New weather metrics, synthetic scores, trend cards, or speculative events.
- New API calls solely for presentation.
- Three-hour sampling or removal of hourly day tabs.
- A separate compact weather screen or resize-driven `recompose()`.
- Drag-and-drop or user-configurable dashboards.
- Tropical-workspace redesign in this task; it may later reuse the resulting
  budgeting and modal patterns.
- Guaranteed full information below 80 columns, although the application must
  fail softly and avoid page scrolling.

## Relevant code

- `wevva/screens/weather_screen.py`
- `wevva/widgets/weather_widget.py`
- `wevva/widgets/current_conditions.py`
- `wevva/widgets/current_detail.py`
- `wevva/widgets/hourly_forecast.py`
- `wevva/widgets/daily_forecast.py`
- `wevva/widgets/daily_summary.py`
- `wevva/widgets/weather_alerts.py`
- `wevva/widgets/saved_locations.py`
- `wevva/widgets/context_bar.py`
- `wevva/widgets/location_map.py`
- `wevva/wevva.tcss`
- `docs/responsive-layout.md`

## Acceptance criteria

- The major weather regions retain the same order and identity at every size.
- At 80x24, the screen shows current weather and the required hourly values;
  the warning case keeps both bordered summary cards and their separation,
  then collapses current-condition digits before dropping optional hourly
  rows.
- The main weather page has no vertical scrollbar at every tested size.
- Padding and hatched separation remain visible at the 80x24 target.
- Hourly forecast represents the complete selected day and scrolls
  horizontally; resize and navigation keep the selected hour visible.
- Hourly rows appear only in the documented priority order.
- Daily forecast never shows partial columns or rows.
- Current-condition variants retain the four-widget row and use `Digits` only
  when their minimum geometry fits.
- Active-warning presence takes priority over optional forecast decoration.
- Warning and location content are reachable through modals at all supported
  sizes.
- Sidebars appear only when the remaining central width satisfies its tested
  minimum.
- The context matrix appears as a two-column/three-row block and never pushes
  primary forecast content into scrolling.
- Resizing performs no network request and preserves logical selection and
  focus state.
- Public Python APIs and forecast models remain compatible.

## Verification

Automated checks:

```bash
uv run python -m compileall -q wevva
uv run python -m unittest discover -s tests
```

Add pure budget tests at every threshold and Textual geometry tests asserting
that main-panel virtual height does not exceed its viewport. Exercise at least:

- 80x24;
- 80x40;
- 100x30;
- 120x40;
- 160x24;
- 160x45;
- 186x53;
- 220x60; and
- 267x75.

For each relevant size, cover no warning, one warning with a long event name,
multiple warnings, emoji enabled/disabled, and requested auxiliary content.
Use deterministic fixtures rather than live Open-Meteo or warning providers.

Manual verification should additionally inspect mouse activation, keyboard
focus, actual terminal colour/spacing, horizontal scrolling, modal escape, and
repeated resizing across budget boundaries. Live API behavior is not required
to validate layout geometry.

## Decisions and notes

- Preserve one composition; change widget density rather than screen identity.
- Use an ordered deterministic allocator, not a generic optimization or
  knapsack algorithm.
- Treat horizontal hourly scrolling as the canonical narrow-width behavior.
- Treat the 80x24 layout as a tested product target.
- Keep the main weather page non-scrolling by construction and assertion.
- Prefer stable mounted widgets and presentation toggles over recomposition.
- The global order among richer current conditions, graph rows, additional
  daily days, and the context matrix remains deliberately tuneable from
  rendered fixtures without changing the overall contract.

## Outcome

Slices A and B are complete. `wevva/layout.py` defines the pure budget contract,
measured row costs, strict upgrade order, width thresholds, and auxiliary-rail
eligibility. Deterministic
forecast, warning, and country-map fixtures live in `tests/weather_fixtures.py`.
`tests/test_layout_budget.py` covers the 80x24 warning baseline, every upgrade
threshold, width-driven fields and sidebars, and the documented terminal-size
matrix against the real `WeatherScreen` content viewport.

The weather screen now consumes that budget without recomposition. Its current
instruments select standard, small, or smallest mounted presentations; detail,
hourly, and daily tables rebuild only complete budgeted rows or fields. Hourly
retains all 24 represented columns in a horizontally scrolling table and
preserves selection across resize. Active warnings use a fixed bordered summary
card which opens the established tabs and a scrolling provider document in a
modal. At 80x24, both summary cards retain a separating hatch row, current
conditions use their smallest one-line presentation, and the hourly table
retains its required rows and explicit position indicator; daily returns
atomically once two complete days fit. Hourly columns retain their compact
four-cell width when the table has surplus horizontal space.
Rendered tests prove the warning and no-warning 80x24 compositions do not
scroll the main page.

The allocator's graph rows, additional days, and wider daily fields become
active automatically when surplus space permits, so that portion of Slice C is
already exercised. Its threshold tuning and broader focus/day/alert-state
matrix remain. Slices D–F are not started. The legacy map and context row are
intentionally withheld until Slice D can introduce the context matrix as one
budgeted block.
