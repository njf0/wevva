"""Checks for shared Natural Earth selection and geographic raster primitives."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from wevva.geography import (
    GeographicViewport,
    ProjectedPoint,
    geojson_polygons,
    polygon_points,
    project_visible_polygons,
    select_geographic_unit,
    short_location_name,
    viewport_from_lonlat,
    world_map_unit_polygons,
    world_populated_places,
)
from wevva.widgets.geographic_scope import (
    GeographicCanvas,
    preferred_geographic_height,
    projected_aspect_ratio,
)


def _bounds(unit) -> tuple[float, float, float, float]:
    points = [point for polygon in unit.polygons for ring in polygon for point in ring]
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


class GeographicUnitSelectionTests(unittest.TestCase):
    def test_hilo_selects_hawaiian_cluster_without_mainland_us(self) -> None:
        unit = select_geographic_unit('US', latitude=19.7297, longitude=-155.09)

        assert unit is not None
        min_lon, min_lat, max_lon, max_lat = _bounds(unit)
        self.assertGreaterEqual(len(unit.polygons), 5)
        self.assertGreater(min_lon, -162.0)
        self.assertLess(max_lon, -154.0)
        self.assertGreater(min_lat, 18.0)
        self.assertLess(max_lat, 23.0)

    def test_reno_selects_contiguous_us_without_hawaii_or_alaska(self) -> None:
        unit = select_geographic_unit('us', latitude=39.5296, longitude=-119.8138)

        assert unit is not None
        min_lon, min_lat, max_lon, max_lat = _bounds(unit)
        self.assertLess(min_lon, -124.0)
        self.assertGreater(max_lon, -68.0)
        self.assertGreater(min_lat, 24.0)
        self.assertLess(max_lat, 50.0)

    def test_ordinary_and_multipart_countries_return_useful_geometry(self) -> None:
        ghana = select_geographic_unit('GH', latitude=5.6037, longitude=-0.1870)
        mauritius = select_geographic_unit('MU', latitude=-20.1609, longitude=57.5012)
        new_zealand = select_geographic_unit('NZ', latitude=-36.8509, longitude=174.7645)

        assert ghana is not None and mauritius is not None and new_zealand is not None
        self.assertEqual(len(ghana.polygons), 1)
        self.assertEqual(len(mauritius.polygons), 1)
        self.assertGreaterEqual(len(new_zealand.polygons), 2)

    def test_unknown_country_has_a_clean_no_land_fallback(self) -> None:
        self.assertIsNone(select_geographic_unit('XX', latitude=0.0, longitude=0.0))


class SharedGeographicRenderingTests(unittest.TestCase):
    def test_world_layer_contains_all_checked_in_map_units(self) -> None:
        world = world_map_unit_polygons()

        self.assertGreater(len(world), 100)

    def test_populated_place_layer_contains_ranked_local_context(self) -> None:
        places = world_populated_places()

        self.assertGreater(len(places), 1000)
        by_name = {place.name: place for place in places}
        self.assertAlmostEqual(by_name['Honolulu'].longitude, -157.8583)
        self.assertEqual(by_name['Nanchang'].scale_rank, 2)

    def test_visible_projection_does_not_wrap_remote_land_across_seam(self) -> None:
        viewport = GeographicViewport(0.0, -135.0, -10.0, -10.0, 10.0, 10.0)
        remote_polygon = (
            (
                (
                    (44.0, -2.0),
                    (46.0, -2.0),
                    (46.0, 2.0),
                    (44.0, 2.0),
                    (44.0, -2.0),
                ),
            ),
        )

        self.assertEqual(project_visible_polygons(remote_polygon, viewport), ())

    def test_projected_aspect_and_preferred_height_use_the_padded_viewport(self) -> None:
        viewport = GeographicViewport(0.0, 0.0, 0.0, 0.0, 8.0, 4.0)

        self.assertEqual(projected_aspect_ratio(viewport), 2.0)
        self.assertEqual(
            preferred_geographic_height(
                viewport,
                available_width=40,
                minimum=7,
                maximum=20,
            ),
            10,
        )

    def test_preferred_height_clamps_wide_and_tall_geography(self) -> None:
        wide = GeographicViewport(0.0, 0.0, 0.0, 0.0, 20.0, 1.0)
        tall = GeographicViewport(0.0, 0.0, 0.0, 0.0, 1.0, 20.0)

        self.assertEqual(
            preferred_geographic_height(wide, available_width=40, minimum=8, maximum=20),
            8,
        )
        self.assertEqual(
            preferred_geographic_height(tall, available_width=40, minimum=8, maximum=20),
            20,
        )

    def test_real_tall_country_context_reaches_a_sensible_maximum(self) -> None:
        chile = select_geographic_unit('CL', latitude=-33.45, longitude=-70.67)
        assert chile is not None
        viewport = viewport_from_lonlat(
            [*polygon_points(chile.polygons), (-70.67, -33.45)],
            origin_latitude=-33.45,
            origin_longitude=-70.67,
            padding=0.08,
        )
        assert viewport is not None

        self.assertLess(projected_aspect_ratio(viewport), 0.25)
        self.assertEqual(
            preferred_geographic_height(viewport, available_width=38, minimum=8, maximum=20),
            20,
        )

    def test_polygon_and_multipolygon_are_normalised_for_shared_consumers(self) -> None:
        polygon = geojson_polygons(
            {'type': 'Polygon', 'coordinates': [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]}
        )
        multipolygon = geojson_polygons(
            {
                'type': 'MultiPolygon',
                'coordinates': [
                    [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                    [[[2, 2], [3, 2], [3, 3], [2, 3], [2, 2]]],
                ],
            }
        )

        self.assertEqual(len(polygon), 1)
        self.assertEqual(len(multipolygon), 2)

    def test_filled_polygon_raster_respects_a_hole(self) -> None:
        viewport = GeographicViewport(0.0, 0.0, 0.0, 0.0, 10.0, 10.0)
        canvas = GeographicCanvas(10, 5, viewport)
        canvas.fill_polygons(
            [
                (
                    (
                        ProjectedPoint(1, 1),
                        ProjectedPoint(9, 1),
                        ProjectedPoint(9, 9),
                        ProjectedPoint(1, 9),
                        ProjectedPoint(1, 1),
                    ),
                    (
                        ProjectedPoint(4, 4),
                        ProjectedPoint(6, 4),
                        ProjectedPoint(6, 6),
                        ProjectedPoint(4, 6),
                        ProjectedPoint(4, 4),
                    ),
                )
            ],
            layer='land',
        )
        frame = canvas.frame((('land', 'dim'),), solid_braille_layers=('land',))

        outer_column, outer_row = canvas.cell_position(ProjectedPoint(2, 2))
        hole_column, hole_row = canvas.cell_position(ProjectedPoint(5, 5))
        self.assertNotEqual(frame.characters[outer_row][outer_column], ' ')
        # The hole shares a cell boundary at this tiny size, but must remove at
        # least one dot from the otherwise full cell.
        self.assertNotEqual(frame.characters[hole_row][hole_column], '⣿')

    def test_solid_braille_uses_full_interiors_and_precise_polygon_edges(self) -> None:
        viewport = GeographicViewport(0.0, 0.0, 0.0, 0.0, 10.0, 10.0)
        canvas = GeographicCanvas(10, 5, viewport)
        canvas.fill_polygons(
            [
                (
                    (
                        ProjectedPoint(2, 2),
                        ProjectedPoint(7, 1),
                        ProjectedPoint(9, 7),
                        ProjectedPoint(4, 9),
                        ProjectedPoint(2, 2),
                    ),
                )
            ],
            layer='warning',
        )

        frame = canvas.frame(
            (('warning', 'yellow'),),
            solid_braille_layers=('warning',),
        )

        self.assertEqual(frame.characters[2][4], '⣿')
        self.assertEqual(frame.styles[2][4], 'yellow')
        self.assertNotEqual(frame.characters[0][3], '⣿')
        self.assertTrue(0x2801 <= ord(frame.characters[0][3]) <= 0x28FE)
        self.assertEqual(frame.characters[0][0], ' ')

    def test_solid_braille_keeps_land_coastline_cells_partial(self) -> None:
        viewport = GeographicViewport(0.0, 0.0, 0.0, 0.0, 10.0, 10.0)
        canvas = GeographicCanvas(10, 5, viewport)
        canvas.fill_polygons(
            [
                (
                    (
                        ProjectedPoint(1, 1),
                        ProjectedPoint(8, 2),
                        ProjectedPoint(7, 8),
                        ProjectedPoint(1, 1),
                    ),
                )
            ],
            layer='land',
        )

        frame = canvas.frame(
            (('land', 'dim blue'),),
            solid_braille_layers=('land',),
        )

        coastline = [
            character
            for row in frame.characters
            for character in row
            if character not in {' ', '⣿'}
        ]
        self.assertTrue(coastline)
        self.assertTrue(all(0x2801 <= ord(character) <= 0x28FE for character in coastline))

    def test_solid_braille_has_no_gaps_at_internal_warning_boundary(self) -> None:
        viewport = GeographicViewport(0.0, 0.0, 0.0, 0.0, 8.0, 8.0)
        canvas = GeographicCanvas(4, 2, viewport)
        canvas.fill_polygons(
            [
                (
                    (
                        ProjectedPoint(0.1, 0.1),
                        ProjectedPoint(7.9, 0.1),
                        ProjectedPoint(7.9, 7.9),
                        ProjectedPoint(0.1, 7.9),
                        ProjectedPoint(0.1, 0.1),
                    ),
                )
            ],
            layer='land',
        )
        canvas.fill_polygons(
            [
                (
                    (
                        ProjectedPoint(2.6, 1.0),
                        ProjectedPoint(6.0, 1.0),
                        ProjectedPoint(6.0, 7.0),
                        ProjectedPoint(2.6, 7.0),
                        ProjectedPoint(2.6, 1.0),
                    ),
                )
            ],
            layer='warning',
        )

        frame = canvas.frame(
            (('land', 'blue'), ('warning', 'yellow')),
            solid_braille_layers=('land', 'warning'),
        )

        self.assertTrue(all(character == '⣿' for row in frame.characters for character in row))
        self.assertTrue(any(style == 'blue' for row in frame.styles for style in row))
        self.assertTrue(any(style == 'yellow' for row in frame.styles for style in row))

    def test_point_and_polyline_primitives_share_the_same_raster(self) -> None:
        viewport = GeographicViewport(0.0, 0.0, 0.0, 0.0, 10.0, 10.0)
        canvas = GeographicCanvas(10, 5, viewport)
        canvas.polyline(
            (ProjectedPoint(1, 1), ProjectedPoint(9, 9)),
            layer='line',
        )
        canvas.point(ProjectedPoint(5, 5), layer='point')
        frame = canvas.frame(
            (('line', 'white'), ('point', 'yellow')),
        )
        column, row = canvas.cell_position(ProjectedPoint(5, 5))

        self.assertNotEqual(frame.characters[row][column], ' ')
        self.assertEqual(frame.styles[row][column], 'yellow')

    def test_visible_raster_has_balanced_margins_after_composition(self) -> None:
        viewport = GeographicViewport(0.0, 0.0, 0.0, 0.0, 10.0, 10.0)
        canvas = GeographicCanvas(12, 6, viewport)
        canvas.fill_polygons(
            [
                (
                    (
                        ProjectedPoint(1, 1),
                        ProjectedPoint(4, 1),
                        ProjectedPoint(4, 8),
                        ProjectedPoint(1, 8),
                        ProjectedPoint(1, 1),
                    ),
                )
            ],
            layer='land',
        )

        frame = canvas.frame((('land', 'blue'),), solid_braille_layers=('land',))
        occupied = [
            (column, row)
            for row, characters in enumerate(frame.characters)
            for column, character in enumerate(characters)
            if character != ' '
        ]
        left = min(column for column, _row in occupied)
        right = canvas.width - 1 - max(column for column, _row in occupied)
        top = min(row for _column, row in occupied)
        bottom = canvas.height - 1 - max(row for _column, row in occupied)

        self.assertLessEqual(abs(left - right), 1)
        self.assertLessEqual(abs(top - bottom), 1)

    def test_viewport_padding_and_aspect_fitting_never_crop_source_points(self) -> None:
        viewport = viewport_from_lonlat(
            [(-2.0, -1.0), (4.0, 3.0)],
            origin_latitude=0.0,
            origin_longitude=0.0,
            padding=0.1,
        )
        assert viewport is not None
        fitted = viewport.fitted(2.0)
        projected = [fitted.project(-2.0, -1.0), fitted.project(4.0, 3.0)]

        self.assertTrue(all(fitted.min_x <= point.x <= fitted.max_x for point in projected))
        self.assertTrue(all(fitted.min_y <= point.y <= fitted.max_y for point in projected))
        self.assertAlmostEqual(fitted.width / fitted.height, 2.0)

    def test_short_location_name_uses_existing_locality_field(self) -> None:
        self.assertEqual(
            short_location_name(SimpleNamespace(name='Hilo', latitude=19.7, longitude=-155.1)),
            'Hilo',
        )
        self.assertEqual(
            short_location_name(SimpleNamespace(name='', latitude=19.7, longitude=-155.1)),
            '19.70, -155.10',
        )


if __name__ == '__main__':
    unittest.main()
