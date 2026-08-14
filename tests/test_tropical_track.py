"""Focused checks for the geographically aware tropical storm scope."""

from __future__ import annotations

import math
from types import SimpleNamespace
import unittest

from wevva.widgets.tropical_track import (
    GeoTrackPoint,
    ScopePalette,
    build_storm_scope_geometry,
    extract_storm_track,
    project_track_locally,
    render_braille_scope,
)
from wevva.widgets.geographic_scope import preferred_geographic_height


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

        self.assertEqual(points[0].label, 'NOW')
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

    def test_viewport_contains_land_location_and_complete_storm_track(self) -> None:
        scope = build_storm_scope_geometry(
            _cphc_system(),
            location_latitude=19.7297,
            location_longitude=-155.09,
            location_name='Hilo',
            country_code='US',
        )

        assert scope is not None
        all_points = [scope.location, *scope.storm]
        all_points.extend(point for polygon in scope.land for ring in polygon for point in ring)
        self.assertTrue(all(scope.viewport.min_x <= point.x <= scope.viewport.max_x for point in all_points))
        self.assertTrue(all(scope.viewport.min_y <= point.y <= scope.viewport.max_y for point in all_points))
        self.assertTrue(scope.land)
        self.assertEqual(scope.location_name, 'Hilo')
        self.assertEqual(scope.forecast_marker_indices, (2, 4, 6))

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
            10,
        )


class TropicalTrackRenderingTests(unittest.TestCase):
    def test_scope_renders_filled_land_daily_dots_and_only_orientation_labels(self) -> None:
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
            palette=ScopePalette(land='dim blue', track='white', forecast='yellow'),
        )

        self.assertEqual(len(rendered.plain.splitlines()), 13)
        self.assertTrue(all(len(line) == 34 for line in rendered.plain.splitlines()))
        self.assertIn('NOW', rendered.plain)
        self.assertIn('Hilo', rendered.plain)
        self.assertIn('✦ Hilo', rendered.plain)
        self.assertNotIn('+24', rendered.plain)
        self.assertNotIn('LOCATION', rendered.plain)
        self.assertEqual(rendered.plain.count('•'), 3)
        self.assertIn('●', rendered.plain)
        self.assertIn('✦', rendered.plain)
        self.assertTrue(any(0x2801 <= ord(character) <= 0x28FF for character in rendered.plain))
        self.assertFalse(any(0x1CD00 <= ord(character) <= 0x1CDE5 for character in rendered.plain))


if __name__ == '__main__':
    unittest.main()
