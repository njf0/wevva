"""Focused checks for the track-fitted global tropical storm scope."""

from __future__ import annotations

import math
import unittest
from types import SimpleNamespace

from wevva.geography import GeographicViewport, ProjectedPoint
from wevva.widgets.geographic_scope import preferred_geographic_height
from wevva.widgets.tropical_track import (
    GeoTrackPoint,
    ScopePalette,
    StormScopeGeometry,
    build_storm_scope_geometry,
    extract_storm_track,
    project_track_locally,
    render_braille_scope,
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
    def test_extracts_current_and_ordered_daily_forecast_points(self) -> None:
        points = extract_storm_track(_system())

        self.assertEqual(points[0].label, '')
        self.assertEqual([point.label for point in points[1:]], ['', '', ''])
        self.assertEqual([point.forecast_marker for point in points], [False, True, True, True])
        self.assertEqual((points[0].latitude, points[0].longitude), (19.7, -151.2))
        self.assertEqual((points[-1].latitude, points[-1].longitude), (21.9, -154.4))

    def test_cphc_intermediate_fixes_smooth_the_line_but_only_full_days_get_markers(self) -> None:
        points = extract_storm_track(_cphc_system())

        self.assertEqual(
            [point.forecast_marker for point in points],
            [False, False, True, False, True, False, True, True, True],
        )
        self.assertTrue(all(not point.label for point in points[1:]))

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

    def test_viewport_contains_global_land_and_complete_storm_track(self) -> None:
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
        self.assertTrue(scope.land)
        self.assertTrue(
            any(
                scope.viewport.min_x <= point.x <= scope.viewport.max_x
                and scope.viewport.min_y <= point.y <= scope.viewport.max_y
                for polygon in scope.land
                for ring in polygon
                for point in ring
            )
        )
        self.assertTrue(scope.places)
        self.assertEqual(scope.forecast_marker_indices, (2, 4, 6, 7, 8))
        storm_width = max(point.x for point in scope.storm) - min(point.x for point in scope.storm)
        self.assertAlmostEqual(scope.viewport.width / storm_width, 1.2)

    def test_wide_hawaii_track_prefers_a_shallow_content_height(self) -> None:
        scope = build_storm_scope_geometry(
            _cphc_system(),
            location_latitude=19.7297,
            location_longitude=-155.09,
            location_name='Hilo',
            country_code='US',
        )
        assert scope is not None

        self.assertEqual(
            preferred_geographic_height(
                scope.viewport,
                available_width=38,
                minimum=7,
                maximum=16,
            ),
            7,
        )

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


class TropicalTrackRenderingTests(unittest.TestCase):
    def test_cone_uses_its_own_braille_palette_layer(self) -> None:
        scope = StormScopeGeometry(
            viewport=GeographicViewport(0.0, 0.0, 0.0, 0.0, 10.0, 10.0),
            land=(),
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
            land=(),
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
            if character == '●'
        }
        self.assertEqual(marker_positions(visible), marker_positions(hidden))
        self.assertEqual(len(marker_positions(hidden)), 3)
        self.assertTrue(any(span.style == 'bright_magenta' for span in visible.spans))
        self.assertFalse(any(span.style == 'bright_magenta' for span in hidden.spans))

    def test_scope_renders_global_land_and_every_daily_forecast_dot(self) -> None:
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
        self.assertIn('✦', rendered.plain)
        self.assertNotIn('+24', rendered.plain)
        self.assertNotIn('LOCATION', rendered.plain)
        self.assertEqual(rendered.plain.count('●'), 6)
        self.assertTrue(any(0x2801 <= ord(character) <= 0x28FF for character in rendered.plain))
        self.assertFalse(any(0x1CD00 <= ord(character) <= 0x1CDE5 for character in rendered.plain))

        compact = render_braille_scope(scope, width=68, height=7)
        self.assertEqual(len(compact.plain.splitlines()), 7)
        self.assertEqual(compact.plain.count('●'), 6)

    def test_discrete_positions_have_balanced_frame_margins(self) -> None:
        scope = StormScopeGeometry(
            viewport=GeographicViewport(0.0, 0.0, 0.0, 0.0, 10.0, 10.0),
            land=(),
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


if __name__ == '__main__':
    unittest.main()
