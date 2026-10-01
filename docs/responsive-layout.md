# Responsive layout language

## Status

Implemented for the primary weather screen. The tropical workspace remains a
separate composition and is not yet driven by this allocator.

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

Resizing retains the selected hour and day, hourly scroll anchor, and focus on
the mounted forecast controls. Warning-modal tab selection survives resizing
while that reader remains open. Auxiliary sidebars are derived from width and
available content, so they return automatically when their full central-width
threshold is restored. Cross-shell focus and document-scroll continuity may be
refined when real use exposes a concrete need.

## The resize vocabulary

The implementation uses a continuous row-and-column budget rather than named
device profiles. Width is measured after the context sidecar and automatic
rails have been allocated; height is the content viewport after the one-row
header and footer.

| Terminal width | Implemented behavior |
| ---: | --- |
| below 80 | Best effort; not a guaranteed product target |
| 80–101 | Supported compact canvas with abbreviated detail/daily fields |
| 102–143 | Full 102-column central canvas and original wide daily fields |
| 144–185 | At sufficient height, the existing context moves beside the full forecast; short windows may instead admit one auxiliary rail |
| 186–227 | Context sidecar plus one automatic auxiliary rail when height permits |
| 228+ | Context sidecar plus both automatic auxiliary rails when all contain data |

The forecast frames themselves stop at 98 cells and remain centred. The first
useful block of surplus width is therefore spent on location, astronomy,
air-quality, and map context rather than stretching hourly columns, tables, or
prose. Saved locations and warning documents receive later surplus blocks.

Height is allocated row by row. At the 22-row content baseline (an 80x24
terminal), the screen retains both summary cards when a warning exists, the
smallest current-condition row, and required hourly condition, temperature,
and time rows. Additional rows restore hourly rain and wind, richer current
conditions, the classic tabbed warning preview, complete daily rows, graph
rows, and finally the bottom context matrix. When sufficient width and height
exist together, that same context uses an independently budgeted right-hand
column: its tables gain priority rows first and its map receives the remaining
bounded height.

An 80x50 terminal and a 160x24 terminal therefore receive different density
decisions without switching to unrelated screen compositions.

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

## Implemented compositions

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
└ t Tropical  l Locations  i Warning details  r Refresh  q Quit ─────────┘
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
  wind/gust values, and a separate direction field;
- active warnings consume one focusable severity/count card at compact heights;
  after the current instruments regain their standard presentation, three
  surplus rows upgrade that card to the established tabs and two-line preview;
  activating either warning body opens a dedicated reader whose tabs directly
  select the complete, independently scrolling provider document within one
  rounded modal frame, without a nested detail border;
- while the saved-locations progress rail is absent, a refresh uses one
  informational start notification and at most one terminal empty-success or
  error notification; provider progress does not create notification stacks,
  and active results use the warning card or tabs instead;
- once the higher-priority forecast is complete and 14 rows remain, location,
  astronomy, and air-quality cards stack beside the no-padding country map in
  a centred two-column matrix; all three cards and the map grow together at
  14-, 17-, 20-, and 23-row tiers before the matrix disappears as one unit;
  at the supported 80-column width the matrix contracts to two 37-cell columns.

The compact composition is not a separate “lite” product. It is the same
widgets in compact presentation modes, with the same selections and keyboard
language.

### Wider terminals

```text
┌ forecast ─────────────────────────┐ ┌ context ───────┐ ┌ warning ──┐
│ summary + warnings + current      │ │ location       │ │ detail     │
├ hourly + daily ───────────────────┤ │ astronomy      │ │ document   │
│                                   │ ├ country map ───┤ │ + map      │
│                                   │ │                │ │            │
└───────────────────────────────────┘ └────────────────┘ └────────────┘
```

The forecast retains the same composition and bounded frames. At standard
aspect ratios the context remains below it as the two-column matrix described
above. Once the full forecast canvas and a useful minimum context height fit,
the same mounted location and astronomy widgets move into a 40-cell sidecar
above a larger country map. Air quality remains part of the complete bottom
matrix rather than crowding this narrow presentation. The sidecar map renders
at most four ranked city labels to preserve the country outline. This is
existing information, not a new telemetry surface, and it no longer pushes the
daily forecast downward.

Outer sidebars have bounded widths and margins. A rail appears only after the
full 102-column weather canvas and, when vertically useful, the 42-column
context allocation have been preserved. Rails therefore use genuine surplus
width; otherwise they remain modal views instead of pushing the forecast back
into a compact variant.

Rail visibility is automatic rather than a user preference. After context has
first claim on suitable surplus space, warning details receive the next block
when both auxiliary surfaces have content; saved locations use it otherwise,
and both appear when two further blocks fit. Their bindings focus a visible
rail or open the modal fallback. In a very short wide terminal, where the
context sidecar cannot meet its minimum height, the older auxiliary rails may
use that width instead.

## Instrument variants

Each compound widget defines its own full and compact semantics. The screen
applies a budget result through narrow `set_layout(...)` methods rather than
reaching into dozens of child labels to construct a special case.

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
| Location data | Five prioritized rows | Two to four prioritized rows |
| Sun and moon | Five prioritized rows | Two to four prioritized rows |
| Air quality | Five prioritized rows | Two to four prioritized rows |
| Country map | Labelled country map | Same map in the matched context height |

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
- Daily forecast reduces its visible horizon to complete rows.
- Maps scale with their bounded context area or disappear atomically; they do
  not scroll internally.
- Focused scrollable areas must have visible focus and predictable escape back
  to the parent workspace.

## Warning behavior

Warnings use a master/detail relationship:

- a fixed-height severity/condition/count card is the supported compact
  baseline;
- once height permits, the card grows into the classic tabbed warning preview;
  selecting a tab changes its headline/timing preview and activating the body
  opens that selected warning;
- the modal uses the same tab selector over the complete warning body shown in
  the detail rail, without a duplicate compact preview above it; the document
  scrolls independently from the tabs;
- after eligible forecast context takes the first surplus block, warning detail
  receives the next before saved locations; when two further blocks fit, both
  auxiliary surfaces appear;
- the `i` command focuses a visible warning rail or opens the modal fallback.

This keeps warning tabs—one of the interface's strongest interactions—without
making long CAP prose dictate the height of every forecast screen.

## Tropical workspace

The tropical screen retains its existing system/source selector, analysis,
track, and product-reader composition. It does not yet consume the weather
screen's row-and-column budget; adapting it is separate follow-up work.

## Textual implementation strategy

The implementation uses Textual's stable widget tree and presentation updates.

### Stable siblings, responsive grids

Major weather instruments are composed once as stable siblings under a small
number of containers. The budget alters exact heights, visibility, complete
table rows/columns, and density variants without replacing widget state.

`Widget.move_child` can reorder children only within one parent. It is useful
for a small number of sibling-order changes, but it is not a general mechanism
for moving live instruments between unrelated desktop and compact containers.
The layout therefore avoids duplicate target containers that require
cross-parent remounting.

Repeated `recompose()` on resize is specifically undesirable: it removes and
mounts children again, which makes preservation of focus, cursor, tab, scroll,
and loading state fragile. Recomposition remains reserved for a true content
model change, not ordinary geometry changes.

### Central budget calculation

`weather_layout_for(...)` calculates an immutable `WeatherLayoutBudget` from
the actual viewport, warning presence, and available auxiliary surfaces. It
returns explicit current and warning density, hourly rows, daily columns and
rows, context placement and table/map heights, and modal/rail choices.

The calculation is pure and table-tested. Width thresholds account for rails;
height calculations use the content viewport rather than assuming total
terminal rows are available.

### Resize is presentation-only

Resizing does not initiate Open-Meteo, air-quality, alert, or tropical
requests. Widgets rerender from the latest model and the map reuses its loaded
geography.

### State and focus invariants

The screen, not the geometry, owns selection. Before and after a budget
transition:

- selected hour/day and visible-hour anchoring remain meaningful;
- hourly and daily focus remains on the same mounted logical control;
- an open warning reader retains its selected tab and focus while resizing;
- the mounted context tables and map survive transitions between bottom matrix
  and sidecar placement;
- automatic rails never squeeze the central forecast or trigger data fetches.

## Verification matrix

The deterministic rendered suite exercises these representative sizes:

| Terminal | Purpose |
| --- | --- |
| 80x24 | First-class compact target; no primary page scroll |
| 80x40 | Narrow/tall independence |
| 100x30 | Compact width with additional height |
| 120x40 | Typical medium terminal |
| 160x24 | Wide/short independence |
| 160x45 | Context sidecar before auxiliary rails |
| 160x60 | Tall context sidecar with bounded map |
| 186x53 | Context sidecar plus one auxiliary rail |
| 220x24 | Two auxiliary rails in a window too short for the sidecar |
| 220x45 | Context sidecar plus one auxiliary rail |
| 220x60 | Tall context sidecar plus one auxiliary rail |
| 267x75 | Context sidecar plus both bounded auxiliary rails |

For each size, verify:

- no overlap, clipped labels, half-visible daily rows, or inaccessible focus;
- useful current and hourly information without main-page vertical scrolling
  at 80x24; daily information returns when two complete rows fit;
- day tabs and warning tabs remain usable;
- automatic rail appearance and removal causes a coherent budget transition;
- resizing repeatedly preserves selection and focus;
- warning fixtures cover none, one, and many warnings plus long prose;
- country-map content remains bounded within each complete context tier;
- no network request is caused by resize.

Tests should use fixed forecast and warning fixtures so geometry can be
assessed independently of live services, local time, and provider availability.

## Usage-driven refinements

The implemented thresholds and abbreviations are now regression-tested.
Further changes should respond to concrete terminal, font, or interaction
issues observed during use. In particular, cross-shell focus and document
scroll continuity may be refined without reopening the layout architecture.
