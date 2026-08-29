"""Focused regressions for the global canonical tropical-system sidebar."""

from __future__ import annotations

import unittest

from wevva_warnings import CanonicalTropicalSystem, DisplayGeography, TropicalSystem
from wevva_warnings.registry import get_source

from wevva.geography import map_unit, resolve_display_geography, subunit
from wevva.services.tropical import (
    canonical_tropical_severity_rank,
    canonical_sort_distance_km,
    sort_canonical_tropical_systems,
    sort_canonical_tropical_systems_by_severity,
)
from wevva.widgets.tropical_track import (
    ScopePalette,
    build_storm_scope_geometry,
    render_braille_scope,
)


def _observation(
    system_id: str,
    source: str,
    name: str,
    *,
    center_lat: float | None,
    center_lon: float | None,
    classification: str | None = None,
    pressure: str | None = None,
    movement: str | None = None,
    track: list[list[float]] | None = None,
    basin: str | None = None,
) -> TropicalSystem:
    source_info = get_source(source)
    return TropicalSystem(
        id=system_id,
        source=source,
        classification=classification or ('Typhoon' if source.startswith('jma') else 'Tropical Storm'),
        name=name,
        headline=name,
        basin=basin,
        center_lat=center_lat,
        center_lon=center_lon,
        min_pressure=pressure,
        movement=movement,
        geometries=(
            {'forecast_track': {'type': 'LineString', 'coordinates': track}}
            if track is not None
            else {}
        ),
        source_info=source_info,
    )


def _bounds(unit) -> tuple[float, float, float, float]:
    points = [point for polygon in unit.polygons for ring in polygon for point in ring]
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


class CanonicalOrderingTests(unittest.TestCase):
    def test_dedicated_workspace_orders_by_strongest_source_classification(self) -> None:
        nearby_depression = CanonicalTropicalSystem(
            name='NEAR',
            observations=[
                _observation(
                    'near',
                    'cma_tropical',
                    'NEAR',
                    center_lat=0.0,
                    center_lon=0.1,
                    classification='Tropical Depression',
                )
            ],
        )
        multi_source_storm = CanonicalTropicalSystem(
            name='FAR',
            observations=[
                _observation(
                    'far-ts',
                    'cma_tropical',
                    'FAR',
                    center_lat=0.0,
                    center_lon=30.0,
                    classification='Tropical Storm',
                ),
                _observation(
                    'far-ty',
                    'jma_tropical',
                    'FAR',
                    center_lat=0.0,
                    center_lon=31.0,
                    classification='Typhoon',
                ),
            ],
        )

        ordered = sort_canonical_tropical_systems_by_severity(
            [nearby_depression, multi_source_storm]
        )

        self.assertEqual([system.name for system in ordered], ['FAR', 'NEAR'])
        self.assertGreater(
            canonical_tropical_severity_rank(multi_source_storm),
            canonical_tropical_severity_rank(nearby_depression),
        )

    def test_minimum_source_distance_orders_each_canonical_storm(self) -> None:
        far_and_near = CanonicalTropicalSystem(
            name='NANGKA',
            observations=[
                _observation('far', 'jma_tropical', 'NANGKA', center_lat=0.0, center_lon=20.0),
                _observation('near', 'cma_tropical', 'NANGKA', center_lat=0.0, center_lon=1.0),
            ],
        )
        middle = CanonicalTropicalSystem(
            name='LALA',
            observations=[
                _observation('middle', 'jma_tropical', 'LALA', center_lat=0.0, center_lon=5.0),
            ],
        )
        unknown = CanonicalTropicalSystem(
            name='UNKNOWN',
            observations=[
                _observation('unknown', 'jma_tropical', 'UNKNOWN', center_lat=None, center_lon=None),
            ],
        )

        ordered = sort_canonical_tropical_systems(
            [middle, unknown, far_and_near],
            0.0,
            0.0,
        )

        self.assertEqual([system.name for system in ordered], ['NANGKA', 'LALA', 'UNKNOWN'])
        self.assertAlmostEqual(
            canonical_sort_distance_km(far_and_near, 0.0, 0.0) or 0.0,
            111.195080,
            places=5,
        )
        self.assertIsNone(canonical_sort_distance_km(unknown, 0.0, 0.0))

    def test_changing_selected_location_changes_order_only(self) -> None:
        east = CanonicalTropicalSystem(
            name='EAST',
            observations=[_observation('east', 'jma_tropical', 'EAST', center_lat=0.0, center_lon=10.0)],
        )
        west = CanonicalTropicalSystem(
            name='WEST',
            observations=[_observation('west', 'cma_tropical', 'WEST', center_lat=0.0, center_lon=-10.0)],
        )

        self.assertEqual(
            [item.name for item in sort_canonical_tropical_systems([east, west], 0.0, 9.0)],
            ['EAST', 'WEST'],
        )
        self.assertEqual(
            [item.name for item in sort_canonical_tropical_systems([east, west], 0.0, -9.0)],
            ['WEST', 'EAST'],
        )
        self.assertEqual((east.observations[0].center_lon, west.observations[0].center_lon), (10.0, -10.0))


class DisplayGeographyTests(unittest.TestCase):
    def test_cphc_subunit_is_hawaii_not_full_sovereign_us(self) -> None:
        source = get_source('cphc_gis_central_pacific')
        assert source is not None and source.display_geography is not None

        hawaii = resolve_display_geography(source.display_geography)
        united_states = map_unit('US')

        assert hawaii is not None and united_states is not None
        hawaii_bounds = _bounds(hawaii)
        us_bounds = _bounds(united_states)
        self.assertEqual(hawaii.code, 'US-HI')
        self.assertGreater(hawaii_bounds[0], -162.0)
        self.assertLess(hawaii_bounds[2], -154.0)
        self.assertLess(us_bounds[0], -170.0)
        self.assertGreater(us_bounds[2], -70.0)

    def test_display_geography_kind_is_not_treated_as_one_code_namespace(self) -> None:
        self.assertIsNotNone(
            resolve_display_geography(DisplayGeography('subunit', 'US-HI', 'Hawaii'))
        )
        self.assertIsNone(
            resolve_display_geography(DisplayGeography('map_unit', 'US-HI', 'Hawaii'))
        )
        self.assertIsNone(subunit('RE'))
        reunion = resolve_display_geography(DisplayGeography('map_unit', 'RE', 'Réunion'))
        self.assertIsNotNone(reunion)
        self.assertEqual(reunion.names, ('Réunion',))
        japan = resolve_display_geography(
            DisplayGeography('country', 'JP'),
            latitude=28.0,
            longitude=135.0,
        )
        self.assertIsNotNone(japan)
        self.assertEqual(japan.code, 'JP')

    def test_global_backdrop_ignores_selected_edinburgh_context(self) -> None:
        cphc = _observation(
            'lala-cphc',
            'cphc_gis_central_pacific',
            'LALA',
            center_lat=15.2,
            center_lon=-145.5,
            track=[[-145.5, 15.2], [-150.0, 17.0], [-155.0, 19.0]],
        )

        edinburgh_scope = build_storm_scope_geometry(
            cphc,
            location_latitude=55.9533,
            location_longitude=-3.1883,
            location_name='Edinburgh',
            country_code='GB',
        )
        neutral_scope = build_storm_scope_geometry(cphc)

        assert edinburgh_scope is not None and neutral_scope is not None
        self.assertEqual(edinburgh_scope, neutral_scope)
        self.assertTrue(edinburgh_scope.land)
        rendered = render_braille_scope(edinburgh_scope, width=68, height=13)
        self.assertNotIn('Hawaii', rendered.plain)

    def test_global_backdrop_draws_only_land_visible_to_each_track(self) -> None:
        jma = _observation(
            'nangka-jma',
            'jma_tropical',
            'NANGKA',
            center_lat=28.0,
            center_lon=135.0,
            track=[[135.0, 28.0], [136.0, 29.0]],
        )
        cma = _observation(
            'nangka-cma',
            'cma_tropical',
            'NANGKA',
            center_lat=20.0,
            center_lon=120.0,
            track=[[120.0, 20.0], [119.0, 21.0]],
        )

        jma_scope = build_storm_scope_geometry(jma)
        cma_scope = build_storm_scope_geometry(cma)

        assert jma_scope is not None and cma_scope is not None
        self.assertFalse(jma_scope.land)
        self.assertTrue(cma_scope.land)
        self.assertNotEqual(jma_scope.viewport, cma_scope.viewport)
        self.assertNotEqual(jma_scope.land, cma_scope.land)
        self.assertNotIn('Japan', render_braille_scope(jma_scope, width=60, height=16).plain)
        self.assertNotIn('China', render_braille_scope(cma_scope, width=60, height=16).plain)

    def test_inland_china_track_is_labelled_with_nearby_cities_not_issuer(self) -> None:
        saudel = _observation(
            'saudel-cma',
            'cma_tropical',
            'SAUDEL',
            center_lat=26.9,
            center_lon=114.6,
            track=[[114.6, 26.9], [113.2, 26.5], [111.8, 25.9]],
        )

        scope = build_storm_scope_geometry(saudel)

        assert scope is not None
        rendered = render_braille_scope(scope, width=60, height=20)
        self.assertIn('Hengyang', rendered.plain)
        self.assertNotIn('China', rendered.plain)

    def test_reunion_track_uses_all_global_land_visible_in_its_viewport(self) -> None:
        reunion = _observation(
            'reunion-system',
            'meteofrance_reunion_tropical',
            'ANCHA',
            center_lat=-19.0,
            center_lon=54.0,
            track=[[54.0, -19.0], [55.0, -20.0]],
        )

        scope = build_storm_scope_geometry(reunion)

        assert scope is not None
        self.assertFalse(scope.land)
        self.assertNotIn('Réunion', render_braille_scope(scope, width=60, height=16).plain)

    def test_open_ocean_track_does_not_force_remote_mexico_into_view(self) -> None:
        eastern_pacific = _observation(
            'hernan-nhc',
            'nhc_gis_eastern_pacific',
            'HERNAN',
            center_lat=16.1,
            center_lon=-134.9,
            basin='Eastern Pacific',
            track=[
                [-134.9, 16.1],
                [-136.6, 16.2],
                [-138.9, 16.4],
                [-140.9, 16.5],
                [-142.8, 16.7],
                [-144.8, 16.9],
            ],
        )

        scope = build_storm_scope_geometry(eastern_pacific)

        assert scope is not None
        self.assertFalse(scope.land)
        rendered = render_braille_scope(
            scope,
            width=48,
            height=29,
            palette=ScopePalette(land='red'),
        )
        self.assertFalse(any(span.style == 'red' for span in rendered.spans))
        self.assertNotIn('United States', rendered.plain)
        self.assertNotIn('✦', rendered.plain)
        track_columns = [
            column
            for line in rendered.plain.splitlines()
            for column, character in enumerate(line)
            if character != ' '
        ]
        self.assertGreater(max(track_columns) - min(track_columns), 20)


if __name__ == '__main__':
    unittest.main()
