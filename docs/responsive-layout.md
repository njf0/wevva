# Responsive layout language

## Status

Under revision. This document records the broader responsive-design language
and some earlier exploratory compositions. The current implementation plan is
the budget-driven, stable-composition approach in
`docs/tasks/0015-responsive-layout-redesign.md`; where the two differ, that task
sheet is authoritative until this document is reconciled in its documentation
slice.

## Intent

Wevva should feel composed for the terminal it is currently occupying, rather
than like a fixed-width dashboard surrounded by unused space or squeezed into a
viewport. A large terminal should reveal more of the existing weather context.
An 80x24 terminal should remain a useful, deliberate weather instrument rather
than a warning that the application is too small.

This is a resize-native language, not a collection of desktop, tablet, and
mobile mock-ups. Width decides how instruments are arranged and how much of a
time series is visible. Height decides which representation of an instrument is
used and how many complete rows are shown. A resize must not fetch data, reset
selection, or replace a useful view with decorative whitespace.

## Product principles

### Preserve the application's strongest instruments

The redesign should retain and improve:

- the large `Digits` treatment for current temperature and similarly immediate
  measurements when space permits;
- compact numeric current-condition fields when height is scarce;
- warning tabs and the separation between warning selection and warning detail;
- hourly forecast day tabs and their visible day boundaries;
- complete, readable daily rows;
- the country-scale location map and its live city temperatures;
- the tropical system and source tabs, storm track, and provider products.

Responsive variants should present the same weather model at different
densities. They should not behave like unrelated screens.

### Earn every panel

The redesign must not manufacture telemetry to fill wide terminals. In
particular, it should not add separate 24-hour trend cards when the hourly
forecast already describes those trends, or a speculative “next events” panel
whose definition changes with the weather. Wider layouts should spend their
space on more of the existing hourly horizon, more complete daily and warning
information, larger maps, and existing location, astronomy, and air-quality
context.

No extra API request should exist solely to make a layout look busier.

### Reflow before scrolling

Normal forecast use should require as little vertical scrolling as possible.
The first responses to reduced space are:

1. reflow peer instruments;
2. switch an instrument to its compact representation;
3. reduce a bounded horizon while keeping complete rows or columns;
4. move extended detail into an explicit secondary view.

Scrolling remains appropriate for documents and genuinely unbounded
collections: warning prose, tropical products, and saved-location lists. It is
not the primary layout mechanism for the current forecast.

### Preserve operational state

Resizing must retain the selected warning, selected hour and day, tropical
system and source, product tab, keyboard focus, and meaningful document scroll
position. User-hidden sidebars stay hidden until the user asks for them again.

## The resize vocabulary

Profiles are named for their behavior rather than for devices. Thresholds are
initial hypotheses and must be tuned against rendered fixtures. Width is the
usable weather workspace after any visible outer sidebar, not necessarily the
terminal's total width.

| Width profile | Provisional usable width | Behavior |
| --- | ---: | --- |
| `compact` | 80–99 columns | One primary column; abbreviated instruments; detail replaces rather than crowds the forecast. |
| `stacked` | 100–139 columns | One broad column with small peer panels arranged in rows where useful. |
| `dashboard` | 140–179 columns | Forecast and existing context can share the canvas. |
| `console` | 180+ columns | More simultaneous context, wider time horizons, and larger maps; no arbitrary central maximum width. |

Terminals narrower than 80 columns are best effort. They must fail softly—no
tracebacks or irrecoverable navigation—but are not the primary design target.

Height is classified independently, excluding the application header and
footer:

| Height profile | Provisional content height | Behavior |
| --- | ---: | --- |
| `short` | up to 22 rows | Natural-language current conditions, bounded hourly and daily horizons, secondary detail views. |
| `regular` | 23–42 rows | Dense current-condition tiles, with compact context where necessary. |
| `tall` | 43+ rows | Larger maps and documents, more complete existing context. |

An 80x50 terminal and a 160x24 terminal therefore do not receive the same
layout. CSS breakpoints alone are insufficient; a small central layout state
should combine width and height into a profile that widgets can consume.

## Information priority

When not everything fits simultaneously, the order is:

1. current location, condition, temperature, and essential measurements;
2. active warning presence and severity;
3. hourly forecast, including day boundaries;
4. daily forecast;
5. existing context: map, location facts, sun and moon, and air quality;
6. navigation help and extended inspection.

Warnings may temporarily move above the hourly forecast when their severity
requires attention, but warning prose should not permanently consume the
primary forecast canvas.

## Profile compositions

The diagrams describe regions and hierarchy, not exact box drawing.

### Compact, especially 80x24

```text
┌ Wevva · Edinburgh ─────────────────────────────────────────────── 12:42 ┐
│ ╭─ Weather Summary ─────────────────────────────────────────────────╮ │
│ │ Light rain in Edinburgh on Wed 23 Sep at 12:42                    │ │
│ ╰────────────────────────────────────────────────────────────────────╯ │
│                                                                        │
│ ╭────────────────────────────────────────────────────────────────────╮ │
│ │ Severe Flood Warning · +1 more                                    │ │
│ ╰────────────────────────────────────────────────────────────────────╯ │
│                                                                        │
│ Temperature     Precipitation    Wind             Detail              │
│ 9°C             82%              18mph SW         Humidity 91%        │
├ Hourly ─ Today ───────── Wed ───────────────────────────────────────────┤
│ Time      13  14  15  16  17  18  19  20                             │
│ Weather   LR  LR  OC  OC  OC  PC  PC  CL                             │
│ Temp °C    9   9   9   8   8   8   7   7                             │
│ ◀━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━───────────────────────────────▶ │
│                                                        ←/→ scroll      │
└ t Tropical  l Locations  d Details  m Map  r Refresh  q Quit ──────────┘
```

The exact fields may vary with configured units and data availability. The
important behavior is:

- summary, warning, current-condition, and hourly frames share a centred
  98-cell upper bound rather than stretching across a very wide terminal;
- the complete visible forecast stack is vertically centred when the terminal
  has surplus rows, while exact-fit compact layouts retain their padding;
- the visual `Digits` cards collapse before hourly value rows are removed;
  smaller variants keep the main and supporting values on adjacent lines;
- current-detail labels remain abbreviated in constrained layouts, then regain
  their full names and an eleven-cell label field at 102 usable columns;
- the hourly day tabs and full represented horizon remain present in a
  horizontally scrolling viewport with an explicit position indicator; the
  selected hour remains visible, while wide layouts retain compact four-cell
  columns inside a centred 98-cell frame;
- daily forecast appears only when at least two complete rows fit, then shows
  as many complete rows and fields as the budget allows, never clipped
  fragments; its centred frame follows the active column width, and rain/wind
  shrink when amount/gust receive their own columns; rain amount sits between
  rain probability and wind speed; at 102 or more usable columns it restores
  the original 96-cell table with full weekday and condition names, combined
  wind/gust values, and a separate direction field; the complete outlook
  remains available as a secondary view;
- active warnings consume one focusable severity/count card; opening it uses a
  dedicated reader containing the established tabs and independently scrolling
  provider text;
- the map and lower-priority context are available through direct actions and
  do not push the forecast below a mandatory scroll boundary.

The compact composition is not a separate “lite” product. It is the same
widgets in compact presentation modes, with the same selections and keyboard
language.

### Stacked

This is the natural successor to today's central stack. It uses the available
width, combines compatible current-condition instruments into rows, and keeps
hourly and daily forecast full-width. Context instruments may occupy a compact
grid below the forecast when height allows. The location map may be prominent,
but it must yield height before primary forecast rows do.

### Dashboard and console

```text
┌ locations ┐ ┌ current + warnings + hourly + daily ─────┐ ┌ context ──┐
│ saved     │ │                                           │ │ location   │
│ places    │ │ primary forecast remains the visual anchor│ │ sun/moon   │
│           │ │ and gains useful hourly/daily resolution  │ │ air quality│
│           │ ├ country map ──────────────────────────────┤ │ warning    │
│           │ │ larger existing map and city temperatures │ │ detail     │
└───────────┘ └───────────────────────────────────────────┘ └────────────┘
```

The centre is not constrained to the width of exactly 24 hourly cells. The
hourly viewport can reveal more of data already present, while the forecast
column remains readable rather than stretching prose to the full terminal.
Additional width becomes an **existing-context rail**—not a new telemetry
column—and can hold the panels Wevva already owns. At tall dashboard and
console sizes, the implemented weather grid puts the forecast stack in the
wider left column and lets the country map span the bounded right column. The
map therefore uses otherwise idle space without pushing the daily forecast
below it.

Outer sidebars should have bounded proportional widths and sensible minima and
maxima. When both are visible, the primary forecast still receives its minimum
usable width. If that is impossible, a sidebar becomes an overlay or explicit
view instead of compressing the forecast into broken columns.

## Instrument variants

Each compound widget should define its own full and compact semantics. The
screen selects a profile; it should not reach into dozens of child labels to
construct a special case.

| Instrument | Full form | Compact form |
| --- | --- | --- |
| Summary | Framed descriptive sentence | Natural-language essential conditions |
| Current temperature | `Digits`, unit, feels-like | Bold numeric field with feels-like directly below |
| Precipitation | Numeric treatment and rate | Label/value in measurement strip |
| Wind | Direction, speed, gust treatment | One labelled inline field |
| Detail | Humidity, cloud, visibility, UV, pressure | Wrapped measurement strip using available values |
| Warnings | Tabs, summary card, selected detail | Focusable severity/condition/count card; tabs and detail open in a dedicated reader |
| Hourly | Day tabs and broad hourly matrix | Same full horizon in a horizontally scrolling viewport; fewer complete rows |
| Daily | Full forecast rows | Hidden until two complete rows fit; then fewer complete rows with dense columns |
| Location data | Framed table | One-line coordinates/time-zone summary or secondary view |
| Sun and moon | Framed table | Sunrise/sunset and phase inline |
| Air quality | Framed table | AQI category/value inline |
| Country map | Large labelled map | Smaller bounded map or direct secondary view |

Compact does not mean inventing derived scores. It means using typography,
abbreviations, and layout to express existing values efficiently.

## Scrolling policy

- The normal 80x24 forecast composition should have no vertical page
  scrollbar.
- The main weather workspace should avoid nested vertical scrolling.
- Warning documents, tropical products, and saved-location collections retain
  their own scrolling because their length is not predictable.
- Hourly forecast may use a keyboard-controlled horizontal window. A resize
  changes its capacity but not the selected hour or day.
- Daily forecast reduces its visible horizon to complete rows; a dedicated
  outlook view exposes all available days.
- Maps scale or move to a secondary view; they do not scroll internally.
- Focused scrollable areas must have visible focus and predictable escape back
  to the parent workspace.

## Warning behavior

Warnings use a master/detail relationship whose arrangement changes without
changing state:

- `compact`: a warning severity/condition/count card stays in the forecast;
  activating it opens the existing tabs and detail in a full-workspace reader;
- `stacked`: warning summary can sit above hourly forecast; detail remains an
  explicit reader unless there is enough width and height;
- `dashboard` and `console`: selected detail may occupy the existing right
  rail, preserving the current independent document scrolling.

This keeps warning tabs—one of the interface's strongest interactions—without
making long CAP prose dictate the height of every forecast screen.

## Tropical workspace

The tropical screen follows the same vocabulary while preserving its own
purpose:

- compact terminals expose system/source tabs and three stable views:
  `Overview`, `Track`, and `Products`; no view is a truncated sliver of another;
- stacked terminals may place summary and conditions above the track, with the
  selected product as an explicit view;
- dashboard terminals retain the current track/product master-detail layout;
- console terminals expand into the available canvas, giving the track more
  resolution and the product reader a bounded readable width instead of
  retaining a small centred island.

System, source, and product selection must survive every profile transition.
The track remains a primary instrument and is never replaced by fabricated
storm telemetry.

## Textual implementation strategy

Textual 8 can support this design if the widget tree is built for reflow.

### Stable siblings, responsive grids

Major weather instruments should be composed once as stable siblings under a
small number of grid containers. Profile classes on the screen/container alter
grid columns, rows, spans, visibility, and instrument variants. Grid layout can
reflow these siblings without replacing their state.

`Widget.move_child` can reorder children only within one parent. It is useful
for a small number of sibling-order changes, but it is not a general mechanism
for moving live instruments between unrelated desktop and compact containers.
The layout should therefore avoid duplicate target containers that require
cross-parent remounting.

Repeated `recompose()` on resize is specifically undesirable: it removes and
mounts children again, which makes preservation of focus, cursor, tab, scroll,
and loading state fragile. Recomposition should be reserved for a true content
model change, not ordinary geometry changes.

### Central profile calculation

A small `LayoutProfile` value should be calculated from the actual content
region. It includes independent width and height classes and exposes explicit
capabilities such as `show_context_rail`, `use_compact_current`, and the number
of visible daily rows. Threshold crossings update CSS classes and widget
variants; every single resize event should not churn the tree.

The profile calculation should be pure and table-tested. Width thresholds must
account for currently visible sidebars. Height calculations must account for
the header/footer rather than assuming total terminal rows are content rows.

### Resize is presentation-only

Resizing must never initiate Open-Meteo, air-quality, alert, or tropical
requests. Widgets rerender from the latest model. Expensive map rasters may be
cached by geometry and viewport size, and recalculation should be debounced if
Textual emits a burst of resize events.

### State and focus invariants

The screen, not the geometry, owns selection. Before and after a profile
transition:

- selected hour/day and visible-hour anchoring remain meaningful;
- selected warning/system/source/product is unchanged if still present;
- focus remains on the same logical control where possible, otherwise moves to
  the nearest visible parent action;
- warning/product scroll offsets are retained while their document exists;
- user-controlled sidebar visibility remains independent from automatic
  layout decisions.

## Verification matrix

Responsive work is incomplete until it is exercised at representative sizes:

| Terminal | Purpose |
| --- | --- |
| 80x24 | First-class compact target; no primary page scroll |
| 80x40 | Narrow/tall independence |
| 100x30 | Compact-to-stacked boundary |
| 120x40 | Typical medium terminal |
| 160x24 | Wide/short independence |
| 160x45 | Dashboard composition |
| 186x53 | Regression against the previous documented minimum |
| 220x60 | Console use of added area |
| 267x75 | Very wide terminal; no centred island |

For each size, verify:

- no overlap, clipped labels, half-visible daily rows, or inaccessible focus;
- useful current and hourly information without main-page vertical scrolling
  at 80x24; daily information returns when two complete rows fit;
- day tabs and warning tabs remain usable;
- opening and closing sidebars causes a coherent profile transition;
- resizing repeatedly preserves selection and focus;
- warning fixtures cover none, one, and many warnings plus long prose;
- tropical fixtures cover one and many systems, multiple sources, absent
  track/cone data, and long products;
- map content remains legible or is deliberately moved to its secondary view;
- no network request is caused by resize.

Tests should use fixed forecast and warning fixtures so geometry can be
assessed independently of live services, local time, and provider availability.

## Deliberately deferred details

Exact breakpoint numbers, field abbreviations, border density, and whether a
particular context instrument spans one or two grid cells should follow render
measurements. They are tuning decisions, not reasons to weaken the structural
rules above.
