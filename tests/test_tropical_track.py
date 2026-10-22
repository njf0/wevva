"""Focused checks for the track-fitted global tropical storm scope."""

from __future__ import annotations

import math
import unittest
from types import SimpleNamespace

from textual.app import App, ComposeResult
from textual.color import Color
from textual.widgets import Static
from wevva_warnings import TropicalProduct

from wevva.geography import GeographicViewport, ProjectedPoint
from wevva.messages import PlaceSelected
from wevva.widgets.geographic_scope import preferred_geographic_height
from wevva.widgets.map_callouts import place_directional_callout
from wevva.widgets.tropical_track import (
    GeoTrackPoint,
    LargeTropicalStormTrackScope,
    ScopePalette,
    StormScopeGeometry,
    TropicalCityLabel,
    TropicalFixLabel,
    build_storm_scope_geometry,
    extract_storm_track,
    project_track_locally,
    render_braille_scope,
    _native_scope_frame,
    _scope_frame,
)


def _system(**overrides):
    values = {
        'source': 'test-source',
        'center_lat': 19.7,
        'center_lon': -151.2,
        'geometries': {
            'forecast_track': {
                'type': 'LineString',
                'coordinates': [
                    [-151.2, 19.7],
                    [-152.0, 20.4],
                    [-153.1, 21.2],
                    [-154.4, 21.9],
                ],
            },
        },
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _cphc_system():
    return _system(
        source='cphc_gis_central_pacific',
        center_lat=15.2,
        center_lon=-145.5,
        geometries={
            'forecast_track': {
                'type': 'LineString',
                'coordinates': [
                    [-145.5, 15.2],
                    [-146.9, 15.9],
                    [-149.2, 16.6],
                    [-151.7, 17.4],
                    [-154.1, 18.0],
                    [-156.3, 18.7],
                    [-159.0, 19.6],
                    [-164.3, 21.0],
                    [-169.5, 22.6],
                ],
            },
        },
    )


class TropicalTrackGeometryTests(unittest.TestCase):
    def test_generic_track_retains_geometry_without_inventing_forecast_leads(self) -> None:
        points = extract_storm_track(_system())

        self.assertEqual(points[0].label, 'Now')
        self.assertEqual([point.label for point in points[1:]], ['', '', ''])
        self.assertEqual(
            [point.forecast_marker for point in points],
            [False, True, True, True],
        )
        self.assertEqual((points[0].latitude, points[0].longitude), (19.7, -151.2))
        self.assertEqual((points[-1].latitude, points[-1].longitude), (21.9, -154.4))

    def test_cphc_track_uses_only_supplied_fixes_without_inferring_leads(self) -> None:
        points = extract_storm_track(_cphc_system())

        self.assertEqual(
            [point.forecast_marker for point in points],
            [False, True, True, True, True, True, True, True, True],
        )
        self.assertEqual(
            [point.label for point in points],
            ['Now', '', '', '', '', '', '', '', ''],
        )

    def test_structured_provider_lead_hours_label_matching_track_fixes(self) -> None:
        product = TropicalProduct(
            kind='forecast',
            label='Forecast',
            data={
                'points': [
                    {'latitude': 20.4, 'longitude': -152.0, 'lead_hours': 12},
                    {'latitude': 21.9, 'longitude': -154.4, 'lead_hours': 36},
                    # A valid time alone must not be reverse-engineered into a lead.
                    {'latitude': 21.2, 'longitude': -153.1, 'valid_at': '2026-08-17T00:00:00Z'},
                ]
            },
        )

        points = extract_storm_track(_system(), (product,))

        self.assertEqual(
            [point.label for point in points],
            ['Now', '12h', '', '36h'],
        )
        self.assertEqual(
            [point.forecast_marker for point in points],
            [False, True, True, True],
        )

    def test_dense_explicit_forecast_fixes_show_only_daily_markers(self) -> None:
        coordinates = [
            [-151.2, 19.7],
            [-152.0, 20.4],
            [-153.1, 21.2],
            [-154.4, 21.9],
            [-155.8, 22.7],
            [-157.3, 23.6],
            [-159.0, 24.5],
        ]
        product = TropicalProduct(
            kind='forecast',
            label='Forecast',
            data={
                'points': [
                    {
                        'latitude': latitude,
                        'longitude': longitude,
                        'lead_hours': lead,
                    }
                    for (longitude, latitude), lead in zip(
                        coordinates[1:],
                        (12, 24, 36, 48, 60, 72),
                        strict=True,
                    )
                ]
            },
        )
        system = _system(
            geometries={
                'forecast_track': {
                    'type': 'LineString',
                    'coordinates': coordinates,
                }
            }
        )

        points = extract_storm_track(system, (product,))
        scope = build_storm_scope_geometry(system, products=(product,))

        self.assertEqual(len(points), 7)
        self.assertEqual(
            [point.label for point in points],
            ['Now', '', '24h', '', '48h', '', '72h'],
        )
        self.assertEqual(
            [point.forecast_marker for point in points],
            [False, False, True, False, True, False, True],
        )
        assert scope is not None
        self.assertEqual(scope.forecast_marker_indices, (2, 4, 6))
        self.assertEqual(
            scope.fix_labels,
            ((0, 'Now'), (2, '24h'), (4, '48h'), (6, '72h')),
        )

    def test_reverses_a_forecast_line_whose_nearest_fix_is_last(self) -> None:
        system = _system(
            geometries={
                'forecast_track': {
                    'type': 'LineString',
                    'coordinates': [[-154.4, 21.9], [-153.1, 21.2], [-152.0, 20.4]],
                },
            },
        )

        points = extract_storm_track(system)

        self.assertEqual((points[1].latitude, points[1].longitude), (20.4, -152.0))
        self.assertEqual((points[-1].latitude, points[-1].longitude), (21.9, -154.4))

    def test_prefers_an_ordered_line_inside_a_geometry_collection(self) -> None:
        system = _system(
            geometries={
                'forecast_track': {
                    'type': 'GeometryCollection',
                    'geometries': [
                        {'type': 'Point', 'coordinates': [-151.2, 19.7]},
                        {
                            'type': 'LineString',
                            'coordinates': [[-151.2, 19.7], [-152.0, 20.4], [-153.1, 21.2]],
                        },
                    ],
                },
            },
        )

        points = extract_storm_track(system)

        self.assertEqual(len(points), 3)

    def test_missing_or_single_position_track_is_not_renderable(self) -> None:
        self.assertEqual(extract_storm_track(_system(geometries={})), ())
        self.assertEqual(
            extract_storm_track(
                _system(
                    geometries={
                        'forecast_track': {'type': 'Point', 'coordinates': [-151.2, 19.7]},
                    },
                )
            ),
            (),
        )
        self.assertIsNone(
            build_storm_scope_geometry(
                _system(center_lat=None),
                location_latitude=19.7,
                location_longitude=-155.1,
                location_name='Hilo',
                country_code='US',
            )
        )

    def test_local_projection_wraps_the_dateline_and_scales_longitude(self) -> None:
        equatorial = project_track_locally(
            [GeoTrackPoint(0.0, -179.0)],
            location_latitude=0.0,
            location_longitude=179.0,
        )[0]
        high_latitude = project_track_locally(
            [GeoTrackPoint(60.0, 1.0)],
            location_latitude=60.0,
            location_longitude=0.0,
        )[0]

        self.assertAlmostEqual(equatorial.x, 2.0)
        self.assertAlmostEqual(high_latitude.x, math.cos(math.radians(60.0)))
        self.assertAlmostEqual(high_latitude.y, 0.0)

    def test_context_floor_preserves_a_complete_dateline_crossing_track(self) -> None:
        scope = build_storm_scope_geometry(
            _system(
                center_lat=12.0,
                center_lon=179.0,
                geometries={
                    'forecast_track': {
                        'type': 'LineString',
                        'coordinates': [
                            [179.0, 12.0],
                            [-179.0, 13.0],
                            [-175.0, 14.0],
                        ],
                    }
                },
            )
        )

        assert scope is not None
        self.assertGreaterEqual(scope.viewport.width, 14.39)
        self.assertGreaterEqual(scope.viewport.height, 14.39)
        self.assertTrue(
            all(
                scope.viewport.min_x <= point.x <= scope.viewport.max_x
                and scope.viewport.min_y <= point.y <= scope.viewport.max_y
                for point in scope.storm
            )
        )

    def test_viewport_contains_complete_storm_track(self) -> None:
        scope = build_storm_scope_geometry(
            _cphc_system(),
            location_latitude=19.7297,
            location_longitude=-155.09,
            location_name='Hilo',
            country_code='US',
        )

        assert scope is not None
        self.assertTrue(all(scope.viewport.min_x <= point.x <= scope.viewport.max_x for point in scope.storm))
        self.assertTrue(all(scope.viewport.min_y <= point.y <= scope.viewport.max_y for point in scope.storm))
        self.assertTrue(scope.places)
        self.assertEqual(scope.forecast_marker_indices, tuple(range(1, 9)))
        storm_width = max(point.x for point in scope.storm) - min(point.x for point in scope.storm)
        self.assertAlmostEqual(scope.viewport.width / storm_width, 1.3)

    def test_hawaii_track_context_floor_reserves_useful_land_height(self) -> None:
        scope = build_storm_scope_geometry(
            _cphc_system(),
            location_latitude=19.7297,
            location_longitude=-155.09,
            location_name='Hilo',
            country_code='US',
        )
        assert scope is not None

        self.assertGreaterEqual(scope.viewport.width, 14.39)
        self.assertGreaterEqual(scope.viewport.height, 14.39)
        self.assertEqual(
            preferred_geographic_height(
                scope.viewport,
                available_width=38,
                minimum=7,
                maximum=16,
            ),
            11,
        )

    def test_short_atlantic_track_context_floor_reveals_bermuda(self) -> None:
        scope = build_storm_scope_geometry(
            _system(
                source='nhc_gis_atlantic',
                center_lat=32.3,
                center_lon=-64.8,
                geometries={
                    'forecast_track': {
                        'type': 'LineString',
                        'coordinates': [[-64.8, 32.3], [-65.8, 33.3]],
                    }
                },
            )
        )

        assert scope is not None
        self.assertGreaterEqual(scope.viewport.width, 14.39)
        self.assertGreaterEqual(scope.viewport.height, 14.39)
        rendered = render_braille_scope(scope, width=60, height=16)
        self.assertTrue(any(0x2801 <= ord(character) <= 0x28FF for character in rendered.plain))

    def test_authoritative_cone_expands_scope_and_is_projected(self) -> None:
        system = _system(
            geometries={
                'forecast_track': {
                    'type': 'LineString',
                    'coordinates': [
                        [-151.2, 19.7],
                        [-152.0, 20.4],
                        [-153.1, 21.2],
                    ],
                },
                'cone': {
                    'type': 'Polygon',
                    'coordinates': [
                        [
                            [-150.7, 19.2],
                            [-151.3, 21.0],
                            [-153.6, 22.0],
                            [-154.0, 20.4],
                            [-150.7, 19.2],
                        ]
                    ],
                },
            },
        )

        scope = build_storm_scope_geometry(system)

        assert scope is not None
        self.assertTrue(scope.cone)
        self.assertTrue(
            all(
                scope.viewport.min_x <= point.x <= scope.viewport.max_x
                and scope.viewport.min_y <= point.y <= scope.viewport.max_y
                for polygon in scope.cone
                for ring in polygon
                for point in ring
            )
        )

    def test_source_without_cone_keeps_cone_layer_empty(self) -> None:
        scope = build_storm_scope_geometry(_system())

        assert scope is not None
        self.assertEqual(scope.cone, ())


class TropicalTrackCalloutPlacementTests(unittest.TestCase):
    def test_callout_prefers_clear_cells_over_forecast_geometry(self) -> None:
        occupied: set[tuple[int, int]] = set()

        placement = place_directional_callout(
            anchor=(5, 2),
            label_width=4,
            canvas_width=12,
            canvas_height=5,
            occupied=occupied,
            preferred_avoidance={(column, 2) for column in range(2, 9)} - {(5, 2)},
            allow_row_shift=True,
        )

        assert placement is not None
        self.assertEqual(placement.row, 1)
        self.assertFalse(
            {
                (placement.column + offset, placement.row)
                for offset in range(placement.width)
            }
            & {(column, 2) for column in range(2, 9)}
        )

    def test_callout_can_fall_back_to_forecast_geometry_when_necessary(self) -> None:
        placement = place_directional_callout(
            anchor=(2, 0),
            label_width=3,
            canvas_width=5,
            canvas_height=1,
            occupied=set(),
            preferred_avoidance={(column, 0) for column in range(5)} - {(2, 0)},
            allow_row_shift=True,
        )

        assert placement is not None
        self.assertEqual((placement.column, placement.row), (2, 0))


class TropicalTrackRenderingTests(unittest.TestCase):
    def test_supplied_fixes_render_as_dots_without_an_interpolated_path(self) -> None:
        scope = StormScopeGeometry(
            viewport=GeographicViewport(0.0, -140.0, -5.0, -5.0, 5.0, 5.0),
            storm=(
                ProjectedPoint(-3.0, 0.0),
                ProjectedPoint(0.0, 2.0),
                ProjectedPoint(3.0, 0.0),
            ),
            forecast_marker_indices=(1, 2),
        )

        rendered = render_braille_scope(scope, width=40, height=10)

        self.assertEqual(rendered.plain.count('◆'), 3)
        self.assertFalse(
            any(0x2801 <= ord(character) <= 0x28FF for character in rendered.plain)
        )

    def test_cone_uses_its_own_braille_palette_layer(self) -> None:
        scope = StormScopeGeometry(
            viewport=GeographicViewport(0.0, 0.0, 0.0, 0.0, 10.0, 10.0),
            storm=(ProjectedPoint(2.0, 5.0), ProjectedPoint(8.0, 5.0)),
            forecast_marker_indices=(),
            cone=(
                (
                    (
                        ProjectedPoint(1.0, 3.0),
                        ProjectedPoint(9.0, 3.0),
                        ProjectedPoint(9.0, 7.0),
                        ProjectedPoint(1.0, 7.0),
                        ProjectedPoint(1.0, 3.0),
                    ),
                ),
            ),
        )

        rendered = render_braille_scope(
            scope,
            width=40,
            height=12,
            palette=ScopePalette(cone='bright_magenta'),
        )

        self.assertTrue(any(span.style == 'bright_magenta' for span in rendered.spans))
        self.assertTrue(any(0x2801 <= ord(character) <= 0x28FF for character in rendered.plain))

        hidden = render_braille_scope(
            scope,
            width=40,
            height=12,
            palette=ScopePalette(cone='bright_magenta'),
            show_track=False,
            show_cone=False,
        )
        self.assertNotIn('●', hidden.plain)
        self.assertFalse(any(span.style == 'bright_magenta' for span in hidden.spans))

    def test_hiding_cone_does_not_move_or_clip_track_markers(self) -> None:
        scope = StormScopeGeometry(
            viewport=GeographicViewport(20.0, -150.0, 0.0, 0.0, 12.0, 8.0),
            storm=(
                ProjectedPoint(2.0, 2.0),
                ProjectedPoint(5.0, 4.0),
                ProjectedPoint(9.0, 6.0),
            ),
            forecast_marker_indices=(1, 2),
            cone=(
                (
                    (
                        ProjectedPoint(1.0, 1.0),
                        ProjectedPoint(11.0, 1.0),
                        ProjectedPoint(10.0, 7.0),
                        ProjectedPoint(1.0, 5.0),
                        ProjectedPoint(1.0, 1.0),
                    ),
                ),
            ),
        )
        palette = ScopePalette(cone='bright_magenta', current='red', forecast='yellow')

        visible = render_braille_scope(scope, width=40, height=12, palette=palette)
        hidden = render_braille_scope(
            scope,
            width=40,
            height=12,
            palette=palette,
            show_cone=False,
        )

        marker_positions = lambda text: {
            (column, row)
            for row, line in enumerate(text.plain.splitlines())
            for column, character in enumerate(line)
            if character == '◆'
        }
        self.assertEqual(marker_positions(visible), marker_positions(hidden))
        self.assertEqual(len(marker_positions(hidden)), 3)
        self.assertTrue(any(span.style == 'bright_magenta' for span in visible.spans))
        self.assertFalse(any(span.style == 'bright_magenta' for span in hidden.spans))

    def test_scope_renders_global_land_and_every_supplied_forecast_dot(self) -> None:
        scope = build_storm_scope_geometry(
            _cphc_system(),
            location_latitude=19.7297,
            location_longitude=-155.09,
            location_name='Hilo',
            country_code='US',
        )
        assert scope is not None

        rendered = render_braille_scope(
            scope,
            width=34,
            height=13,
            palette=ScopePalette(land='dim blue', forecast='yellow'),
        )

        self.assertEqual(len(rendered.plain.splitlines()), 13)
        self.assertTrue(all(len(line) == 34 for line in rendered.plain.splitlines()))
        self.assertNotIn('NOW', rendered.plain)
        self.assertIn('Honolulu', rendered.plain)
        self.assertIn('Hilo', rendered.plain)
        self.assertIn('•', rendered.plain)
        self.assertNotIn('+24', rendered.plain)
        self.assertNotIn('LOCATION', rendered.plain)
        self.assertEqual(rendered.plain.count('◆'), 9)
        self.assertTrue(any(0x2801 <= ord(character) <= 0x28FF for character in rendered.plain))
        self.assertFalse(any(0x1CD00 <= ord(character) <= 0x1CDE5 for character in rendered.plain))

        compact = render_braille_scope(scope, width=68, height=7)
        self.assertEqual(len(compact.plain.splitlines()), 7)
        self.assertEqual(compact.plain.count('◆'), 9)

    def test_discrete_positions_have_balanced_frame_margins(self) -> None:
        scope = StormScopeGeometry(
            viewport=GeographicViewport(0.0, 0.0, 0.0, 0.0, 10.0, 10.0),
            storm=(ProjectedPoint(7.0, 5.0), ProjectedPoint(3.0, 5.0)),
            forecast_marker_indices=(1,),
        )

        rendered = render_braille_scope(
            scope,
            width=40,
            height=10,
            palette=ScopePalette(land='blue'),
        )
        lines = rendered.plain.splitlines()
        self.assertNotIn('NOW', rendered.plain)
        occupied = [
            (column, row) for row, line in enumerate(lines) for column, character in enumerate(line) if character != ' '
        ]
        left = min(column for column, _row in occupied)
        right = len(lines[0]) - 1 - max(column for column, _row in occupied)
        top = min(row for _column, row in occupied)
        bottom = len(lines) - 1 - max(row for _column, row in occupied)

        self.assertLessEqual(abs(left - right), 1)
        self.assertLessEqual(abs(top - bottom), 1)


class _TropicalTrackApp(App[None]):
    def __init__(self) -> None:
        super().__init__()
        self.selected = []

    def compose(self) -> ComposeResult:
        yield LargeTropicalStormTrackScope()

    def on_place_selected(self, event: PlaceSelected) -> None:
        self.selected.append(event.location)


class TropicalTrackWidgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_reflow_reuses_immutable_backdrop_frame(self) -> None:
        _native_scope_frame.cache_clear()
        app = _TropicalTrackApp()
        async with app.run_test(size=(70, 24)) as pilot:
            widget = app.query_one(LargeTropicalStormTrackScope)
            widget.styles.width = 66
            widget.set_layout(visible=True, height=18)
            widget.update_system(_cphc_system())
            for _ in range(3):
                await pilot.pause()

            backdrop = widget.query_one(
                '.tropical-track-backdrop', Static
            ).render().plain
            placements = widget.placements
            before = _native_scope_frame.cache_info()

            widget._reflow()

            after = _native_scope_frame.cache_info()
            self.assertEqual(after.misses, before.misses)
            self.assertEqual(after.hits, before.hits + 1)
            self.assertEqual(
                widget.query_one('.tropical-track-backdrop', Static).render().plain,
                backdrop,
            )
            self.assertEqual(widget.placements, placements)
        _native_scope_frame.cache_clear()

    async def test_cone_uses_subdued_theme_warning_colour(self) -> None:
        system = _cphc_system()
        system.geometries['cone'] = {
            'type': 'Polygon',
            'coordinates': [
                [
                    [-145.0, 14.0],
                    [-170.0, 14.0],
                    [-170.0, 24.0],
                    [-145.0, 24.0],
                    [-145.0, 14.0],
                ]
            ],
        }
        app = _TropicalTrackApp()
        async with app.run_test(size=(70, 24)) as pilot:
            widget = app.query_one(LargeTropicalStormTrackScope)
            widget.styles.width = 66
            widget.set_layout(visible=True, height=18)
            widget.update_system(system)
            for _ in range(3):
                await pilot.pause()

            warning = app.theme_variables['text-warning']
            backdrop = widget.query_one('.tropical-track-backdrop', Static).render()
            expected = Color.parse(warning)
            self.assertTrue(
                any(
                    getattr(span.style, 'foreground', None) == expected
                    and getattr(span.style, 'dim', False) is True
                    for span in backdrop.spans
                )
            )

    async def test_native_fix_and_city_callouts_layer_over_track_raster(self) -> None:
        app = _TropicalTrackApp()
        async with app.run_test(size=(70, 24)) as pilot:
            widget = app.query_one(LargeTropicalStormTrackScope)
            widget.styles.width = 66
            widget.set_layout(visible=True, height=18)
            widget.update_system(_cphc_system())
            for _ in range(3):
                await pilot.pause()

            fixes = list(widget.query(TropicalFixLabel))
            cities = list(widget.query(TropicalCityLabel))
            self.assertEqual(
                [fix._body_text for fix in fixes],
                ['Now', '', '', '', '', '', '', '', ''],
            )
            self.assertTrue(all(not fix.can_focus for fix in fixes))
            self.assertTrue(cities)
            self.assertTrue(all(city.can_focus for city in cities))
            self.assertTrue(
                all(
                    city.label_text.startswith('• ')
                    or city.label_text.endswith(' •')
                    for city in cities
                )
            )
            self.assertTrue(any(item.kind == 'fix' for item in widget.placements))
            self.assertTrue(any(item.kind == 'city' for item in widget.placements))
            assert widget._scope is not None
            frame = _scope_frame(
                widget._scope,
                width=widget.content_size.width,
                height=widget.content_size.height,
                palette=ScopePalette(),
            )
            city_points = {
                f'city-{label.place.latitude:.6f},{label.place.longitude:.6f}': (
                    frame.canvas.viewport.project(
                        label.place.longitude,
                        label.place.latitude,
                    )
                )
                for label in cities
            }
            for placement in widget.placements:
                marker_column = (
                    placement.column + placement.width - 1
                    if placement.marker_on_right
                    else placement.column
                )
                point = (
                    widget._scope.storm[int(placement.key.removeprefix('fix-'))]
                    if placement.kind == 'fix'
                    else city_points[placement.key]
                )
                self.assertEqual(
                    (marker_column, placement.row),
                    frame.canvas.cell_position(point),
                )

            backdrop = widget.query_one('.tropical-track-backdrop', Static).render()
            self.assertNotIn('Now', backdrop.plain)
            self.assertNotIn('Honolulu', backdrop.plain)
            self.assertTrue(
                any(0x2801 <= ord(character) <= 0x28FF for character in backdrop.plain)
            )

            visible_city_keys = {
                placement.key
                for placement in widget.placements
                if placement.kind == 'city'
            }
            city = next(
                label
                for label in cities
                if f'city-{label.place.latitude:.6f},{label.place.longitude:.6f}'
                in visible_city_keys
            )
            city.focus()
            await pilot.press('enter')
            await pilot.press('space')
            self.assertTrue(await pilot.click(city))
            await pilot.pause()
            self.assertEqual([place.name for place in app.selected], [city.place.name] * 3)
            self.assertTrue(city.has_focus)

    async def test_resize_reflows_without_replacing_native_labels(self) -> None:
        app = _TropicalTrackApp()
        async with app.run_test(size=(70, 24)) as pilot:
            widget = app.query_one(LargeTropicalStormTrackScope)
            widget.set_layout(visible=True, height=18)
            widget.update_system(_cphc_system())
            for _ in range(3):
                await pilot.pause()
            labels = {
                **{f'fix:{label._body_text}': id(label) for label in widget.query(TropicalFixLabel)},
                **{f'city:{label.place.name}': id(label) for label in widget.query(TropicalCityLabel)},
            }

            await pilot.resize_terminal(100, 30)
            await pilot.pause()
            await pilot.pause()

            self.assertEqual(
                {
                    **{
                        f'fix:{label._body_text}': id(label)
                        for label in widget.query(TropicalFixLabel)
                    },
                    **{
                        f'city:{label.place.name}': id(label)
                        for label in widget.query(TropicalCityLabel)
                    },
                },
                labels,
            )


if __name__ == '__main__':
    unittest.main()
