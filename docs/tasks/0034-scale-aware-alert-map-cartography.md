# Task 0034: Scale-aware alert-map cartography

## Status

Proposed — design investigation complete; implementation not started

## Depends on

- Task 0020 supplies the completed Alerts Centre, truthful provider polygons,
  selected-alert automatic fit, whole-country fallback, severity styling,
  settlement interaction, and the current focused-map implementation.
- Task 0030 reuses that same `CountryAlertsMap` for the Dashboard's selected
  alert `Map` / `Alert` reader. The motivating screenshots exercise this shared
  path, so improvements must appear consistently in Dashboard and Alerts
  Centre.
- Task 0019 supplies the separate forecast-location `WarningAreaScope`. Its
  whole-context framing and location marker remain distinct, but it may adopt
  the chosen low-level outline/warning-polygon grammar after the focused map
  proves it.
- Task 0021 owns contextual point and text data: the denser gazetteer,
  country filtering, adaptive administrative depth, independent administrative
  label points, named physical-feature labels, ranking, category balance, and
  collision policy. Task 0021 is now a hard evaluation gate: implement and
  inspect its label fixtures before beginning Task 0034 rendering work. This
  task owns only any later base-map geometry, polygon treatment, raster layer
  hierarchy, and focused automatic framing which remain justified. A named
  river label remains Task 0021; drawing a scale-qualified river line would be
  Task 0034.
- Task 0023 supplies the shared native-callout planner. This task may change
  the cells underneath a callout but must not move its marker away from the
  projected anchor or grow a second placement engine.
- Task 0024 may later supply manual pan/zoom and a scale bar. Task 0034 may
  improve the automatic focused viewport which Reset restores, but it does not
  add controls, manual viewport state, or navigation performance work.

Task 0021 and Task 0024 currently describe the existing tight alert fit as a
correct viewport. Preserve it through the label-first evaluation. Only if the
revised labels remain context-poor should this task compare wider automatic
framing; Task 0024 Reset would then restore that accepted automatic view.

## Context

Wevva's Braille maps are effective when the available geography already forms
a recognisable composition. The world overview has unmistakable continental
silhouettes. Tropical tracks combine large coastlines, a compact storm cone,
and a few ranked labels. The shared Alerts Centre/Dashboard focused map for a
Frost Advisory around Delaware and New Jersey works especially well because
coastline, state names, cities, and the warning footprint all happen to
intersect the viewport.

Other focused alerts reduce to a coloured shape on a uniform field of Braille
dots. A long inland Flood warning can be geographically accurate yet provide
no clue which part of a state it occupies or which named feature it follows.
That is not principally a failure of polygon resolution. It is a failure of
cartographic context and visual hierarchy.

The current focused-alert pipeline explains the difference:

- `_alert_viewport()` fits the warning bounds with `0.05` padding, so the
  warning can occupy almost the complete width or height of the map.
- The land layer contains the selected country's map-unit polygons. This is a
  useful relevance boundary, but an inland viewport within one component is
  therefore entirely filled land with no internal structure.
- Land and every warning are rasterized as solid filled Braille layers. In a
  fully terrestrial viewport the land becomes a wall of `U+28FF`-like cells,
  and the selected warning becomes the same wall in another colour.
- Warning polygons have no separately styled outline. Shape recognition
  depends almost entirely on the edge between two solid dot fields.
- The only internal reference features are Natural Earth settlements and
  Admin-1 names inferred from those settlements. Task 0021 correctly identifies
  the resulting coverage and ranking gaps.
- `GeographicCanvas.frame()` gives one character cell to the visually highest
  layer. Its Braille mask offers eight binary subcells, but the complete glyph
  has only one foreground style and one cell background. Recolouring an overlap
  cannot preserve independently coloured warning, coast, boundary, and river
  dots inside the same cell.

The good result is therefore contingent on a warning being near a coastline
and several existing labels. It is not a generally available rendering mode.

The France `CoastalEvent` and the older `docs/assets/name-bug*.png` captures add
an important correction: a map may already contain many names and still fail
because they are the wrong names. Global focused candidates admit Brighton and
Hove, UK local authorities, Swiss cantons, and neighbouring-country cities onto
a France warning; the Brazil view is surrounded by foreign departments and
provinces. The current “preserve every region label” fallback also allows long
names to overlap and concatenate. This is a label relevance/hierarchy failure
which must be fixed before concluding that more drawn geography is needed.

## Problem

- Selected warnings and base land use the same dense visual mark, so the map
  has weak figure/ground separation and can feel like two coloured blobs.
- Tight geometry fitting leaves little surrounding context and makes the
  thematic polygon dominate the composition.
- Current labels are not country-scoped or hierarchy-aware and may be actively
  less useful than a smaller, correctly chosen set. Rendering work begun before
  Task 0021 would confound label and raster improvements.
- Labels can name visible places and often provide enough local context after
  correction. Only the remaining fixtures justify coast, administrative, lake,
  or river linework.
- Adding every available geographic layer would replace emptiness with noise.
  Terminal cells cannot support the line weights, transparency, colour range,
  and fine geometry used by a conventional slippy map.
- Natural Earth is a small-scale country/region dataset. Its 1:10m data cannot
  honestly become street-, county-, or creek-level mapping merely because a
  tiny alert is enlarged to fill the terminal.
- Globally useful layers are uneven. Natural Earth's detailed roads are mainly
  North American, and its Admin-2 counties are US-only. Adopting either as the
  normal context would undermine the provider-neutral, worldwide Alerts Centre.
- Colour alone is not a sufficient selection or severity cue across terminal
  palettes, themes, and colour-vision differences.

## Design conclusion

First build a **hierarchical country-relevant label map**. Only if its fixture
matrix remains visually under-specified should the Alerts Centre add a
**boundary-first thematic locator map**, not a terminal topographic map.

Its purpose is to answer, in priority order:

1. Which correctly scoped administrative names and settlements locate this
   warning at the current depth?
2. What is the selected provider-issued warning footprint?
3. Does the selected country's outline or one matching administrative boundary
   tier add information which the labels do not?
4. Is there one major physical feature which materially improves orientation?
5. What is the approximate visible scale when Task 0024 is present?

It does not need to classify every cell of the world. In particular, ordinary
land, forest, desert, farmland, and urban land cover do not need distinct fills.
Those categories compete with warning colour without reliably helping someone
locate the warning. Named mountain ranges, deserts, islands, or bays may later
appear as subordinate Task 0021 labels; their area cover should not become a
base-map texture.

Real map systems solve this with visual hierarchy, generalisation, scale
ranges, layer filtering, restrained linework, transparent thematic fills, and
prioritized labels. Wevva should apply the same decisions within a much smaller
terminal vocabulary rather than imitate the number of layers in a web map.

## Terminal rendering envelope

The implementation should embrace these constraints explicitly:

- One Braille character provides a useful `2 × 4` binary mask, but all set dots
  share one foreground colour. The cell can also carry one background colour.
- Textual can blend alpha colours while composing widgets, but the terminal
  still receives a final foreground/background pair per cell. Alpha does not
  recover independently coloured subpixels.
- A later layer may replace or combine a Braille mask, but it cannot preserve
  arbitrarily many coincident symbols. Layer priority must be part of the map
  design, not an implementation accident.
- Two overlapping filled polygons expose the sharpest limitation. One layer
  may need a detailed partial-cell mask to retain its boundary while the other
  covers the complementary dots. Because those dots cannot keep independent
  colours, `GeographicCanvas` must choose a top mask/style; where solid layers
  together cover the cell it may snap ownership to one full Braille cell. This
  is why a well-shaped tropical cone still sits beside full-cell land and why
  merely changing the land colour does not solve the composition.
- Native labels occupy rectangular terminal cells. A small knockout or blended
  background may improve legibility, but truly transparent vector text is not
  available.
- Braille dot shape, apparent spacing, cell aspect, colour fidelity, and emoji
  width vary by terminal and font. A design which works only because one font
  makes `U+28FF` look like a continuous solid block is not robust.
- Image protocols, sixel/Kitty graphics, canvas emulators, custom fonts, and
  half-cell pixel libraries would create a different compatibility surface.
  They are not part of this task.

The safest grammar therefore uses one neutral background and spends the
high-resolution Braille foreground on boundaries, labels, and at most one
sparse filled thematic layer. It does not overlap a filled land mask with a
filled warning mask.

## Proposed cartographic grammar

### Visual hierarchy

Use this semantic order from lowest to highest priority:

1. one neutral map background;
2. selected-country coastline/boundary outline;
3. optional boundary tier corresponding to Task 0021's chosen administrative
   depth;
4. optional scale-qualified major hydrography;
5. unselected warning outlines;
6. optional selected-warning sparse screen-tone;
7. selected or previewed warning outline;
8. administrative and physical labels;
9. settlement callouts and interactive markers; and
10. focus/hover treatment.

When foreground features collide in one terminal cell, the higher item wins.
Losing a few boundary dots under the selected warning is acceptable; losing
the warning edge under a river is not. Labels may knock out the raster beneath
them because readable text is more valuable than the covered dots.

### Selected-country outline

Stop describing a completely terrestrial viewport with a solid Braille fill.
Use one neutral background for both sides of a low-contrast selected-country
outline. The outline supplies the useful coast/border silhouette without
spending a second fill colour or implying that the map needs a conventional
blue-water/green-land palette.

Keep the selected country as the map's geographic relevance boundary. Do not
add neighbouring land merely because it intersects the viewport, and align
Task 0021's settlement and political label filtering with the same rule. The
existing checked-in selected map-unit polygons can supply the outline without a
new resource. Marine/physical labels may later receive an explicit
country-neutral exception when real coordinates justify it.

Whole-country overview maps may retain their current dense silhouette if the
comparison fixtures show it remains clearer at that scale. The focused and
overview grammars do not have to use identical area marks.

### Warning polygons

Give every warning a real boundary layer. First test a strong continuous
severity-coloured outline with no interior fill. Then test the same outline
plus a deterministic sparse interior screen-tone. The screen-tone is the
terminal analogue of a translucent thematic fill: enough marks to associate
the interior with severity without recreating an opaque block.

If warning screen-tone is accepted, land remains unfilled. Keep the pattern
sparse enough that no ordinary interior cell becomes a full `U+28FF` solely
because of shading. Use the same severity style for selected outline and tone
so their masks can be combined exactly, then suppress tone in outline-touched
cells or remove tone dots which would complete a full boundary cell. At an
intersection, the selected warning outline owns the cell over
country/admin/hydrographic lines; this loses a few lower-priority dots but
avoids a ring of full-cell compositing around two overlapping fills.

Unselected warnings should normally be dim outlines only. Preview remains
above ordinary context, and selection remains above both. Do not require hue
alone to communicate selected versus contextual state.

Patterns must be anchored in geographic/projected space or a stable global
pixel origin so they do not shimmer when the widget is redrawn. Avoid fragile
ASCII hatching which produces diagonal text-like noise. A small deterministic
Braille mask family should be compared across common fonts and dark/light
themes before one is accepted.

The warning outline is authoritative provider geometry. A patterned interior,
base-map line, or nearby label never changes applicability.

### Framing

Preserve the current five-percent fit while Task 0021's deeper labels are
evaluated. Only if a labelled fixture still lacks context should this task
compare a small set of deterministic proportional margins. Any chosen change
must keep the complete warning visible and must not search outward without
bound until a favoured city or coastline appears.

Choose the final margin/occupancy band from representative fixtures and map
dimensions. The policy may distinguish a tiny compact map from a large map,
but it must be pure, bounded, stable, antimeridian-safe, and independent of
provider or country. Task 0024 Reset should restore this result exactly.

### Scale-qualified context

Use a small number of stable geographic scale bands. Feature eligibility is
driven by geographic span and source scale; terminal dimensions then decide
whether the eligible geometry and labels can be rendered legibly.

- **Country overview:** retain the existing country silhouette, top
  settlements, and warning footprints where that grammar remains clearer.
- **Regional focus:** neutral background, selected-country outline, Task 0021
  administrative and settlement labels, warning outlines, and only a boundary
  tier or major named lake/river which survives the label-first audit.
- **Local focus:** admit denser Task 0021 points and labels, but do not magnify
  coarse Natural Earth linework as though it were complete local mapping. A
  sparse honest map is preferable to false creek, road, or land-cover detail.

Use projected geographic span or approximate kilometres-per-cell in the pure
policy rather than naming the bands after web-map zoom levels. Source
`scalerank` or equivalent remains a candidate filter, not a guarantee that the
feature will survive rasterization.

### Candidate feature decisions

| Feature | Locator value | Initial decision |
| --- | --- | --- |
| Task 0021 country-scoped hierarchical labels | Highest expected value for close/context-poor views and fixes demonstrated clutter without using another raster channel | Implement and evaluate first |
| Selected-country outline | High for coastal/island context and consistent with the map's country scope | Core rendering prototype |
| Neighbouring-country land/outlines | Can orient some border views but admitted irrelevant names and conflicts with the selected-country scope in demonstrated fixtures | Exclude initially |
| Administrative boundary tier | Potentially useful when it matches Task 0021's chosen semantic depth; fixed Admin-1 is not equivalent across countries | Conditional after label audit and only with suitable global hierarchy data |
| Significant lakes and reservoirs | High where visible, but adds a second area problem if filled | Conditional outline/shore prototype after labels |
| Major named rivers | Sometimes high, especially for flood corridors, but Natural Earth will not contain many local waterways | Conditional, scale-ranked, never promised as exhaustive |
| Physical feature labels | Useful for marine and remote alerts without adding visual linework | Task 0021 |
| Roads | Familiar in some places, but the candidate global source is uneven and transportation is not central to warning interpretation | Exclude initially; no North-America-only tier |
| Admin-2/county boundaries | Useful locally but Natural Earth coverage is US-only | Exclude from the global grammar |
| Forest, desert, farmland, urban, and other land-cover fills | Low locator value relative to colour/texture cost | Exclude |
| Terrain shading or contours | Requires another dense visual channel and a much more detailed source | Exclude |
| Minor rivers, streets, buildings, and addresses | Need local multiscale data or tiles and imply unavailable precision | Exclude |
| Graticule | Adds regular noise without usually identifying a place | Exclude from the normal view |

Hydrography is deliberately conditional. Major lakes and rivers are the only
extra line/area theme with a plausible weather and orientation benefit, but it
must improve the motivating fixtures in practice. If Natural Earth's ranked
features miss the relevant local river, Task 0034 must not grow an OpenStreetMap
extract pipeline merely to make that example pass.

## Context fallback

Some tiny inland or offshore alerts may remain sparse after Task 0021's
country-scoped hierarchy and denser labels are applied. Conventional
cartography often uses a locator inset when one scale cannot show both footprint
detail and regional position. Wevva should evaluate that only after the label
policy and minimal outline grammar are tested.

The preferred fallback order is:

1. Task 0021's chosen administrative tier and nearest truthful settlement or
   physical label;
2. a bounded wider automatic context margin, only if the label-first fixtures
   justify it;
3. Task 0024's scale bar when that task is implemented; and
4. only if deterministic fixtures remain ungrounded, a small responsive
   regional locator inset or concise context line using the same offline data.

An inset must show only the focused extent/centroid inside a wider country or
the administrative outline matching Task 0021's chosen depth, hide completely
at compact sizes, and reuse the existing projection/raster path. A textual
fallback must say “near” or give a direction and distance; it must not imply
that the nearby place is affected. Arbitrary provider `area_names` must not be
assigned invented map coordinates.

Do not disguise missing context with decorative dots, invented rivers, denser
land texture, or a random graticule.

## Data and resource boundary

Start with what is already packaged:

- complete 1:50m map-unit polygons for the selected-country outline;
- 1:10m populated places for current focused labels; and
- provider warning geometry for the thematic layer.

For any new vector resource, use Natural Earth as the first prototype because
it already matches the project's offline, reproducible, global data boundary.
Candidate 1:10m themes, only after the label gate, are coastline, a
hierarchy-compatible administrative boundary set, lake shores, and ranked
rivers/lake centre-lines. Do not commit the upstream archives. Do not add a
fixed Admin-1 line layer when Task 0021 selected a different meaningful depth.

A development-only builder should emit only what runtime rendering needs:

```text
stable feature/category id
feature class and scale rank
name only when line/area labeling is actually consumed
quantized longitude/latitude paths or rings
wrapped geographic bounds and a simple country/grid bucket
```

Clip, simplify, or quantize only at build time with documented tolerances.
Retain enough precision for a Braille cell at the smallest supported regional
span, not the precision of the upstream shapefile. Sort deterministically and
use reproducible gzip metadata like the existing builders.

Before accepting each resource, record upstream version/licence, source record
count, generated count, compressed size, load time, retained memory, viewport
query time, and actual fixture coverage. Missing or corrupt optional resources
must degrade to the selected-country outline/warning/label map without
suppressing provider geometry.

Natural Earth explicitly describes 1:10m as country/region-scale data. Establish
a lower useful-span threshold during the audit and do not claim greater local
detail below it.

## Architectural boundary

Keep the map specialization in `CountryAlertsMap`. Extend
`GeographicCanvas` only with small source-neutral primitives which another map
could honestly reuse, such as polygon outlines or stable patterned fills. Do
not introduce a declarative style language, generic
layer tree, vector-tile model, spatial database, or universal map widget.

`CountryAlertsMap` is one implementation shared by Alerts Centre and Dashboard;
do not fork its styling between those consumers. `WarningAreaScope` is a
separate one-warning, forecast-location surface. It may reuse the chosen canvas
primitives and polygon grammar, but it does not gain the focused-map gazetteer,
administrative-boundary layer, automatic-fit policy, or settlement interaction
as part of this task.

Separate three concerns in pure functions where practical:

1. **eligibility:** which pre-ranked features remain justified after the label
   policy at the geographic scale;
2. **raster priority:** which foreground/background mark owns a colliding
   subcell or terminal cell; and
3. **presentation:** theme-derived colours, density, dimming, and selection.

This makes the design testable without teaching the shared canvas about
warnings, severities, countries, or provider identities.

Feature queries must use cached packaged data and cheap bounds/buckets. Resize,
hover, preview, selection, pan, and zoom must not reload a resource or perform
network work. Keep existing merged-style warning layers and duplicate-polygon
elimination unless profiling demonstrates a better bounded representation.

## Implementation slices

### Slice A — Task 0021 label-first gate

- Implement and manually evaluate Task 0021's country filtering,
  administrative-depth selection, category quotas, de-duplication, and strict
  non-overlap before changing a raster layer.
- Use the context-poor inland Flood, successful Delaware/New Jersey Frost
  Advisory, France `CoastalEvent`, both `name-bug` captures, UK, Brazil,
  coastal/marine, island, dense urban, tiny rural, and antimeridian fixtures.
- Record exactly which administrative, settlement, and optional physical names
  survive at compact and wide sizes. Confirm that foreign labels and
  concatenated long names are gone.
- Reassess every later slice. If corrected close-scale labels make the map
  useful, narrow or stop Task 0034 rather than changing rendering for its own
  sake.

### Slice B — boundary-only renderer study

- Capture the post-Task-0021 baseline in dark and light themes.
- Prototype, without committing all variants:
  1. current solid selected-country land + solid warning;
  2. neutral background + selected-country outline + warning outline; and
  3. the previous option plus a sparse, geographically stable warning-only
     screen-tone.
- Include explicit country/warning, administrative/warning, and
  hydrographic/warning intersection fixtures. Verify that line priority loses
  only the lower-priority dots and does not produce neighbouring full Braille
  cells from complementary filled masks. Verify that warning tone is suppressed
  where it would square off or complete an outline cell.
- Compare alert silhouette, label readability, selection without hue, resize
  stability, and visual density across common fonts. Prefer outline-only unless
  sparse tone has a clear benefit.

### Slice C — minimal focused rendering

- Add a separately styled provider-polygon outline while preserving holes and
  disconnected parts.
- Replace focused-view solid land with the selected-country outline on one
  neutral background. Keep the existing whole-country overview fill when its
  silhouette remains clearer.
- Add warning screen-tone only if Slice B selected it; keep land unfilled and
  prevent the pattern from producing ordinary full interior cells.
- Encode explicit priority for country boundary, context warning, selected
  warning, preview, and labels. Keep the map scoped to the selected country.
- Preserve severity colour, alert identity, selection order, geometry-less
  fallback, marker truth, and settlement interaction. Any deliberate removal
  of the old land/sea overlap colour must be documented as part of the accepted
  grammar.

### Slice D — conditional administrative and hydrographic lines

- Proceed only for fixtures still under-specified after Slices A–C.
- If administrative boundaries are needed, use a global source capable of the
  same semantic level selected by Task 0021; do not draw fixed Admin-1 lines
  behind labels which intentionally selected a different depth.
- Prototype significant lake shores without an area fill, then only
  scale-ranked major rivers/lake centre-lines which survive for a useful number
  of terminal cells.
- Measure artifact cost, load/query time, clutter, and improvement. Reject a
  layer which does not repeatedly add information beyond the labels.
- Preserve the source's documented boundary worldview and attribution; do not
  invent disputed-boundary policy.

### Slice E — sparse-context fallback and framing

- Only after the label and outline work, compare bounded wider automatic
  margins for remaining sparse fixtures. Keep the existing five-percent fit if
  wider framing does not add useful names or outlines.
- If cases remain ungrounded, prototype the small locator inset or truthful
  context line. Adopt it only if it remains legible without taking useful space
  from compact maps.
- Keep Task 0024's future scale bar and navigation controls outside this task.

### Slice F — accessibility, performance, and integration

- Verify selected versus unselected geometry in monochrome/reduced-colour
  captures as well as normal themes; outline/density/order must carry meaning
  when hues converge.
- Check native label knockout against the neutral field and retain visible
  keyboard focus.
- Profile focused selection, preview, resize, and representative large-alert
  collections. Add bounds/buckets or cached projected inputs only where the
  measurements justify them.
- Apply the accepted outline/screen-tone grammar to `WarningAreaScope` only if
  its existing Ghana, Britain, disconnected-polygon, and forecast-marker
  fixtures remain clearer. Preserve its stable complete location context and
  do not add focused-map labels or data queries.
- Update architecture, development/data provenance, Tasks 0021/0024 ownership
  notes, and user-facing map help if new marks need explanation.

## Non-goals

- Raster/slippy tiles, Mapbox/OSM runtime services, live reverse geocoding, or
  downloading map data on install/first use.
- A terminal graphics protocol, image widget, custom font, or replacement for
  Textual/Rich rendering.
- A complete street, topographic, hydrological, ecological, or land-use map.
- Forest, desert, terrain, elevation, bathymetry, urban-area, parcel, building,
  address, or ordinary road layers.
- US-only counties, NWS zones, road supplements, or provider-specific map
  presentation.
- Neighbouring-country land, political labels, or outlines in the initial
  selected-country grammar merely because the focused viewport crosses a
  border.
- Inferring affected geography from nearby features, labels, provider prose,
  or `area_names`.
- New pan/zoom controls, scale-bar ownership, or navigation history from Task
  0024.
- Reworking the successful world overview or tropical cone merely for visual
  uniformity.
- A generic GIS API or common base class for every map widget.
- Perfect line/label retention when multiple features compete for one terminal
  cell.

## Acceptance criteria

- Task 0021's revised France, UK, Brazil, rural, coastal, and compact label
  fixtures are implemented and manually evaluated before any Task 0034 raster
  change. The decision to continue, narrow, or stop is recorded.
- The motivating context-poor inland fixture no longer appears as only one
  dense alert-coloured blob on a second dense land-coloured field, whether the
  decisive improvement came from labels alone or the later outline grammar.
- The Delaware/New Jersey-style coastal fixture retains recognisable coastline,
  administrative context, and readable city labels; the new treatment does
  not regress the case which already works.
- The shared selected-alert map has the same geometry and cartographic grammar
  in Dashboard and Alerts Centre; consumer-specific frames/tabs do not fork it.
- If rendering proceeds, a selected warning has a continuous recognisable
  boundary. Any accepted sparse interior treatment is stable and never fills
  ordinary interior cells completely or completes a boundary cell at the
  expense of its detailed mask; selection remains distinguishable from context
  in a reduced-colour/monochrome inspection, not only by hue.
- Focused views remain scoped to the selected country. Political and settlement
  labels, country outline, and any later administrative boundaries follow that
  same relevance rule.
- The automatic viewport preserves complete provider geometry and remains
  stable for disconnected and antimeridian geometry. It changes from the
  existing fit only when post-label fixtures demonstrate a bounded benefit.
- Focused land is not a second filled Braille layer. The selected-country and
  warning edges remain legible on one neutral background in dark and light
  themes without requiring different land and sea colours.
- Any administrative boundary layer matches Task 0021's selected hierarchy
  depth and follows documented global scale rules. Fixed Admin-1 or US-only
  detail is not introduced as the normal grammar.
- No land-cover, terrain, road, or minor-water layer is added unless this task
  is explicitly revised with a global source, measured benefit, and new scope.
- Feature and label density decreases at wider geographic extents. Zooming into
  a span below the source's useful scale does not claim exhaustive local
  detail.
- Provider polygon coordinates remain the only authority for warning extent.
  Nearby lines, labels, or fallback copy never imply applicability.
- Geometry holes, disjoint polygons, selected/preview draw order, severity
  semantics, geometry-less fallback, callout marker truth, tooltips,
  activation, and whole-country maps retain coverage. Any deliberate removal
  of focused land/sea overlap colouring is fixture-reviewed and documented.
- Resize, selection, preview, and future navigation perform no network request
  and do not reload packaged geography.
- Every accepted new artifact has reproducible build instructions,
  licence/version attribution, measurements, deterministic ordering, packaged
  wheel/sdist coverage, and a corrupt/missing-data fallback.
- Indicative raster/query timings and retained memory are recorded for compact,
  wide, dense, sparse, and large-alert fixtures. No fragile wall-clock test is
  added.
- Other maps change only if they intentionally adopt a small shared canvas
  primitive and retain their existing visual/interaction tests.
- If `WarningAreaScope` adopts the new primitive, it retains the forecast
  location marker/label, whole-context viewport, compact height policy, and
  weather-modal/sidebar behavior.

## Verification

Automated tests must use checked-in generated resources or compact fixtures and
must not access a map/geocoding service.

```bash
uv run python -m compileall -q wevva
uv run python -m unittest tests.test_geography
uv run python -m unittest tests.test_alerts_centre_map
uv run python -m unittest tests.test_alerts_centre_layout
uv run python -m unittest tests.test_alerts_centre_screen
uv run python -m unittest tests.test_map_callouts
uv run python -m unittest tests.test_warning_area
uv run python -m unittest tests.test_dashboard_screen
uv run python -m unittest tests.test_tropical_track tests.test_world_locations_map
uv run python -m unittest discover -s tests
uv build
```

Add pure coverage for outline rasterization, holes, optional stable screen-tone
origin, line intersection/layer priority, selected-country scoping, scale-band
thresholds, framing when changed, wrapped bounds, resource fallback, and
deterministic viewport queries. Mounted tests should cover
selection/preview/theme/resize plus label focus and activation over the revised
backdrop.

Manual verification is essential because counts of coloured cells cannot prove
good cartography. Compare the complete fixture matrix at a minimum of 80×24
and one wide/tall layout, in dark and light themes, with at least two common
terminal/font combinations where available. Record screenshots, dimensions,
font/terminal, visible feature set, artifact measurements, and known sparse
failures. Do not claim fine-feature, colour, or font fidelity which was not
actually exercised.

## Relevant code

- `wevva/widgets/country_alerts_map.py`
- `wevva/widgets/warning_area.py`
- `wevva/widgets/geographic_scope.py`
- `wevva/widgets/map_callouts.py`
- `wevva/geography.py`
- `wevva/data/README.md`
- `tools/build_natural_earth.py`
- `tools/build_natural_earth_places.py`
- `tests/test_alerts_centre_map.py`
- `tests/test_warning_area.py`
- `tests/test_dashboard_screen.py`
- `tests/test_geography.py`
- `tests/test_map_callouts.py`
- `docs/architecture.md`
- `docs/development.md`
- Tasks 0019, 0020, 0021, 0023, 0024, and 0030

## Research basis

- Ordnance Survey's cartographic design guidance emphasizes designing for the
  final display medium, figure/ground hierarchy, simplicity, legibility,
  consistency, accessibility, and scale-appropriate generalisation. Those
  principles support a quiet locator base and selective context rather than
  filling every available category:
  <https://www.ordnancesurvey.co.uk/blog/what-is-cartography>
- ArcGIS' multiscale-map guidance treats generalised geometry, scale-based
  layer visibility, and scale-based symbology as complementary tools, and
  warns against displaying data at a larger scale than its capture scale:
  <https://pro.arcgis.com/en/pro-app/3.4/help/mapping/map-authoring/author-a-multiscaled-map.htm>
- ArcGIS' label guidance confirms the practical pattern already used by Wevva:
  rank important label classes first, try alternatives, and omit lower-priority
  conflicts:
  <https://pro.arcgis.com/en/pro-app/3.5/help/mapping/text/prioritize-labels.htm>
- Mapbox's style specification separates background, fill, line, and symbol
  layers; supports min/max zoom filtering; and uses polygon opacity plus a
  stroked edge for thematic overlays. Wevva cannot reproduce arbitrary alpha
  or line weights, but screen-tone, outline, scale bands, and prioritized
  labels are the relevant terminal equivalents:
  <https://docs.mapbox.com/style-spec/reference/layers/>
- Natural Earth publishes country/region-scale 1:10m land, coastline, lakes,
  ranked rivers/lake centre-lines, physical labels, Admin-0 boundaries, and
  Admin-1 boundaries. It also documents the uneven scope of roads and US-only
  Admin-2 data, which is why those layers are excluded:
  <https://www.naturalearthdata.com/downloads/10m-physical-vectors/>
  <https://www.naturalearthdata.com/downloads/10m-cultural-vectors/>
- Textual can blend alpha-bearing style colours during composition. This is
  useful for deriving quiet theme-relative tones but does not change the final
  terminal-cell foreground/background limit:
  <https://textual.textualize.io/guide/styles/>
- Unicode defines the 256 eight-dot Braille patterns used by the current
  `2 × 4` raster, while deliberately leaving physical glyph dimensions to the
  rendering environment:
  <https://www.unicode.org/versions/Unicode16.0.0/UnicodeStandard-16.0.pdf>

## Decisions and notes

- The first demonstrated failure is label relevance and hierarchy, not missing
  raster detail. Task 0021 is therefore the first implementation and may remove
  the need for most of this task.
- The rendering limitation is not simply “Braille is too low resolution.” Two
  differently coloured filled masks cannot both preserve their detailed
  complementary subcells. The initial renderer prototype uses one neutral
  field, selected-country and warning outlines, and at most warning-only sparse
  tone; land remains unfilled.
- Neighbouring countries are not initial context. The selected country is the
  shared relevance boundary for its outline, political labels, and settlements.
- A fixed Admin-1 boundary layer is not the strongest next step: administrative
  meaning varies by country. Any later boundary tier must correspond to Task
  0021's adaptively selected semantic depth.
- Lakes/major rivers are a measured optional layer, not a promise of local
  flood-corridor coverage.
- Roads, counties, land cover, forest/desert fills, and terrain are explicitly
  rejected for the initial grammar.
- If a tiny warning remains context-free, the honest answer is a locator
  inset/textual reference or user navigation—not invented map detail.
- Task 0034 changes the shared `CountryAlertsMap` used by Alerts Centre and
  Dashboard. `WarningAreaScope` may adopt the proven low-level polygon grammar;
  world and tropical maps remain unchanged. Their existing designs are
  evidence that the current renderer can work when composition and data suit
  the scale.

## Outcome

Not yet implemented.
