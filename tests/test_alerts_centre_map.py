"""Whole-country alert-map geometry and enrichment checks."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from textual.app import App, ComposeResult
from wevva_warnings import Alert

from wevva.geography import map_unit
from wevva.alerts_centre_layout import alerts_centre_layout_for
from wevva.screens.alerts_centre_screen import AlertsCentreScreen
from wevva.services.country_alerts import SupportedAlertCountry, country_alert_identity
from wevva.widgets.country_alerts_map import (
    CountryAlertCityLabel,
    CountryAlertRegionLabel,
    CountryAlertSettlementSelected,
    CountryAlertsMap,
    build_country_alert_polygon_layers,
    build_country_alerts_map_geometry,
    build_country_alerts_map_view,
    country_alert_city_label_budget,
    render_country_alerts_map,
)
from wevva.widgets.geographic_scope import GeographicCanvas
from wevva.widgets.weather_alerts import (
    alert_severity_color,
    alert_severity_surface_color,
)
from tests.weather_fixtures import hourly_forecast


GERMANY = SupportedAlertCountry('DE', 'Germany')
FRANCE = SupportedAlertCountry('FR', 'France')


def _alert(
    alert_id: str,
    *,
    severity: str,
    geometry: dict | None,
    area_names: list[str] | None = None,
) -> Alert:
    return Alert(
        id=alert_id,
        source='fixture',
        event=f'{alert_id.title()} Warning',
        headline=f'{alert_id.title()} warning headline',
        severity=severity,
        description=f'Complete {alert_id} provider document.',
        area_names=area_names or [f'{alert_id.title()} district'],
        geometry=geometry,
    )


WEST_GERMANY = {
    'type': 'Polygon',
    'coordinates': [[[6.2, 49.2], [9.2, 49.2], [9.2, 51.6], [6.2, 51.6], [6.2, 49.2]]],
}
EAST_GERMANY = {
    'type': 'Polygon',
    'coordinates': [[[11.0, 50.5], [14.5, 50.5], [14.5, 53.2], [11.0, 53.2], [11.0, 50.5]]],
}


class CountryAlertsMapGeometryTests(unittest.TestCase):
    def test_moderate_warning_uses_text_colour_at_sea_and_surface_colour_on_land(
        self,
    ) -> None:
        alert = _alert('wind', severity='Moderate', geometry=WEST_GERMANY)
        theme = {
            'text-warning': '#f1d58a',
            'warning': '#e2a93b',
            'warning-darken-2': '#a56f16',
            'text-accent': '#abcdef',
            'accent': '#123456',
        }

        self.assertEqual(alert_severity_color(theme, alert), '#f1d58a')
        self.assertEqual(alert_severity_surface_color(theme, alert), '#a56f16')

    def test_country_view_retains_every_disconnected_map_unit_component(self) -> None:
        scope = build_country_alerts_map_geometry('US')
        unit = map_unit('US')

        assert scope is not None
        assert unit is not None
        self.assertGreater(len(unit.polygons), 100)
        self.assertEqual(scope.component_count, len(unit.polygons))
        self.assertEqual(len(scope.land), len(unit.polygons))
        self.assertGreater(len(scope.places), 4)
        self.assertLessEqual(len(scope.places), 32)
        self.assertEqual(scope.country_polygons, unit.polygons)

    def test_ranked_city_set_retains_original_leaders_and_temperature_cap(self) -> None:
        scope = build_country_alerts_map_geometry('DE')
        uk_scope = build_country_alerts_map_geometry('GB')

        assert scope is not None
        assert uk_scope is not None
        self.assertEqual(
            [place.name for place, _point in scope.places[:4]],
            ['Berlin', 'Frankfurt', 'Hamburg', 'Munich'],
        )
        self.assertEqual(
            [place.name for place, _point in uk_scope.places[:4]],
            ['London', 'Glasgow', 'Birmingham', 'Manchester'],
        )

    def test_only_provider_polygons_become_alert_layers(self) -> None:
        scope = build_country_alerts_map_geometry('DE')
        assert scope is not None
        severe = _alert('flood', severity='Severe', geometry=WEST_GERMANY)
        moderate = _alert('wind', severity='Moderate', geometry=EAST_GERMANY)
        geometry_missing = _alert('heat', severity='Minor', geometry=None)

        layers = build_country_alert_polygon_layers(
            [severe, moderate, geometry_missing],
            scope.viewport,
        )

        self.assertEqual([layer.key for layer in layers], [('fixture', 'flood'), ('fixture', 'wind')])

    def test_selected_polygon_uses_full_style_above_dim_context(self) -> None:
        scope = build_country_alerts_map_geometry('DE')
        assert scope is not None
        severe = _alert('flood', severity='Severe', geometry=WEST_GERMANY)
        moderate = _alert('wind', severity='Moderate', geometry=EAST_GERMANY)
        layers = build_country_alert_polygon_layers([severe, moderate], scope.viewport)

        rendered = render_country_alerts_map(
            scope,
            layers,
            width=60,
            height=20,
            land_style='blue',
            alert_styles={
                ('fixture', 'flood'): 'red',
                ('fixture', 'wind'): 'dim yellow',
            },
            alert_land_styles={
                ('fixture', 'flood'): 'dark_red',
                ('fixture', 'wind'): 'dim dark_orange',
            },
            selected_alert_key=('fixture', 'flood'),
        )

        styles = {str(span.style) for span in rendered.spans}
        self.assertIn('dark_red', styles)
        self.assertIn('dim dark_orange', styles)
        self.assertIn('blue', styles)
        self.assertTrue(any(0x2801 <= ord(character) <= 0x28FF for character in rendered.plain))

    def test_consecutive_context_polygons_with_the_same_style_share_a_layer(
        self,
    ) -> None:
        scope = build_country_alerts_map_geometry('DE')
        assert scope is not None
        first = _alert('first', severity='Moderate', geometry=WEST_GERMANY)
        second = _alert('second', severity='Moderate', geometry=WEST_GERMANY)
        selected = _alert('selected', severity='Severe', geometry=WEST_GERMANY)
        alert_layers = build_country_alert_polygon_layers(
            [first, second, selected],
            scope.viewport,
        )
        frame_layers: list[tuple[str, str | None]] = []
        filled_alert_polygons: dict[str, int] = {}
        original_frame = GeographicCanvas.frame
        original_fill_polygons = GeographicCanvas.fill_polygons

        def capture_frame(canvas, layers, **kwargs):
            frame_layers.extend(layers)
            return original_frame(canvas, frame_layers, **kwargs)

        def capture_fill_polygons(canvas, polygons, *, layer):
            polygons = tuple(polygons)
            if layer.startswith('alert-'):
                filled_alert_polygons[layer] = (
                    filled_alert_polygons.get(layer, 0) + len(polygons)
                )
            return original_fill_polygons(canvas, polygons, layer=layer)

        with (
            patch(
                'wevva.widgets.country_alerts_map.GeographicCanvas.frame',
                new=capture_frame,
            ),
            patch(
                'wevva.widgets.country_alerts_map.GeographicCanvas.fill_polygons',
                new=capture_fill_polygons,
            ),
        ):
            render_country_alerts_map(
                scope,
                alert_layers,
                width=60,
                height=20,
                land_style='blue',
                alert_styles={
                    ('fixture', 'first'): 'dim yellow',
                    ('fixture', 'second'): 'dim yellow',
                    ('fixture', 'selected'): 'red',
                },
                alert_land_styles={
                    ('fixture', 'first'): 'dim dark_orange',
                    ('fixture', 'second'): 'dim dark_orange',
                    ('fixture', 'selected'): 'dark_red',
                },
                selected_alert_key=('fixture', 'selected'),
            )

        self.assertEqual(
            frame_layers,
            [('land', 'blue'), ('alert-0', 'dim yellow'), ('alert-1', 'red')],
        )
        self.assertEqual(filled_alert_polygons, {'alert-0': 1, 'alert-1': 1})

    def test_selected_polygon_fits_a_smaller_view_and_prioritizes_inside_places(self) -> None:
        flood = _alert('flood', severity='Severe', geometry=WEST_GERMANY)
        country = build_country_alerts_map_geometry('DE')
        focused = build_country_alerts_map_view(
            'DE',
            [flood],
            ('fixture', 'flood'),
        )

        assert country is not None
        assert focused is not None
        self.assertLess(focused.viewport.width, country.viewport.width)
        self.assertLess(focused.viewport.height, country.viewport.height)
        self.assertEqual(focused.selected_alert_key, ('fixture', 'flood'))
        self.assertEqual(focused.places[0][0].name, 'Frankfurt')
        self.assertTrue(focused.region_annotations)
        self.assertGreater(len(focused.region_annotations), 1)

    def test_geometry_less_selection_uses_whole_country_fallback(self) -> None:
        alert = _alert('heat', severity='Minor', geometry=None)
        country = build_country_alerts_map_geometry('DE')
        selected = build_country_alerts_map_view(
            'DE',
            [alert],
            ('fixture', 'heat'),
        )

        assert country is not None
        assert selected is not None
        self.assertEqual(selected.viewport, country.viewport)
        self.assertFalse(selected.selected_alert_polygons)
        self.assertFalse(selected.region_annotations)

    def test_disconnected_and_wrapped_selected_geometry_remains_in_view(self) -> None:
        geometry = {
            'type': 'MultiPolygon',
            'coordinates': [
                [[[179.4, 10.0], [179.8, 10.0], [179.8, 10.4], [179.4, 10.4], [179.4, 10.0]]],
                [[[-179.8, 10.1], [-179.4, 10.1], [-179.4, 10.5], [-179.8, 10.5], [-179.8, 10.1]]],
            ],
        }
        alert = _alert('wind', severity='Moderate', geometry=geometry)
        focused = build_country_alerts_map_view(
            'DE',
            [alert],
            ('fixture', 'wind'),
        )

        assert focused is not None
        self.assertEqual(len(focused.selected_alert_polygons), 2)
        self.assertLess(focused.viewport.width, 2.0)
        for polygon in focused.selected_alert_polygons:
            for ring in polygon:
                for longitude, latitude in ring:
                    point = focused.viewport.project(longitude, latitude)
                    self.assertGreaterEqual(point.x, focused.viewport.min_x)
                    self.assertLessEqual(point.x, focused.viewport.max_x)
                    self.assertGreaterEqual(point.y, focused.viewport.min_y)
                    self.assertLessEqual(point.y, focused.viewport.max_y)

    def test_tiny_geometry_receives_stable_minimum_span(self) -> None:
        tiny = {
            'type': 'Polygon',
            'coordinates': [[[8.0, 50.0], [8.0001, 50.0], [8.0001, 50.0001], [8.0, 50.0]]],
        }
        alert = _alert('fog', severity='Minor', geometry=tiny)
        focused = build_country_alerts_map_view(
            'DE',
            [alert],
            ('fixture', 'fog'),
        )

        assert focused is not None
        self.assertGreaterEqual(focused.viewport.width, 0.2)
        self.assertGreaterEqual(focused.viewport.height, 0.2)

    def test_tiny_us_alert_can_select_a_scale_rank_eight_settlement(self) -> None:
        mendocino = {
            'type': 'Polygon',
            'coordinates': [[
                [-123.85, 39.25],
                [-123.75, 39.25],
                [-123.75, 39.35],
                [-123.85, 39.35],
                [-123.85, 39.25],
            ]],
        }
        alert = _alert('coastal', severity='Minor', geometry=mendocino)
        focused = build_country_alerts_map_view(
            'US',
            [alert],
            ('fixture', 'coastal'),
        )

        assert focused is not None
        self.assertEqual(focused.places[0][0].name, 'Mendocino')
        self.assertEqual(focused.places[0][0].population, 548)

    def test_region_labels_do_not_come_from_provider_area_names(self) -> None:
        ambiguous = _alert(
            'flood',
            severity='Severe',
            geometry=WEST_GERMANY,
            area_names=['North district', 'South district'],
        )
        long_named = _alert(
            'wind',
            severity='Moderate',
            geometry=WEST_GERMANY,
            area_names=['A provider area name much too long for the map'],
        )

        ambiguous_view = build_country_alerts_map_view(
            'DE',
            [ambiguous],
            country_alert_identity(ambiguous),
        )
        long_view = build_country_alerts_map_view(
            'DE',
            [long_named],
            country_alert_identity(long_named),
        )

        assert ambiguous_view is not None
        assert long_view is not None
        self.assertEqual(
            ambiguous_view.region_annotations,
            long_view.region_annotations,
        )
        region_names = {
            annotation.text for annotation in ambiguous_view.region_annotations
        }
        self.assertNotIn('North district', region_names)
        self.assertNotIn('South district', region_names)

    def test_city_label_budget_scales_with_map_size_and_respects_ceiling(self) -> None:
        self.assertEqual(country_alert_city_label_budget(20, 8), 1)
        self.assertEqual(country_alert_city_label_budget(48, 24), 4)
        self.assertEqual(country_alert_city_label_budget(120, 40), 8)
        self.assertEqual(country_alert_city_label_budget(120, 40, maximum=2), 2)

class _MapApp(App[None]):
    def __init__(self) -> None:
        super().__init__()
        self.selected_places = []

    def compose(self) -> ComposeResult:
        yield CountryAlertsMap()

    def on_country_alert_settlement_selected(
        self,
        event: CountryAlertSettlementSelected,
    ) -> None:
        self.selected_places.append(event.place)


class CountryAlertsMapWidgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_reflow_reuses_render_canvas_for_callout_placement(self) -> None:
        app = _MapApp()
        flood = _alert('flood', severity='Severe', geometry=WEST_GERMANY)
        wind = _alert('wind', severity='Moderate', geometry=EAST_GERMANY)

        async with app.run_test(size=(100, 32)) as pilot:
            widget = app.query_one(CountryAlertsMap)
            widget.update_country(
                'DE',
                'Germany',
                [flood, wind],
                selected_alert_key=('fixture', 'flood'),
            )
            for _ in range(3):
                await pilot.pause()

            filled_layers: list[str] = []
            original_fill = GeographicCanvas.fill_polygons

            def counted_fill(canvas, polygons, *, layer):
                filled_layers.append(layer)
                return original_fill(canvas, polygons, layer=layer)

            with patch.object(
                GeographicCanvas,
                'fill_polygons',
                new=counted_fill,
            ):
                widget._reflow()

            self.assertEqual(filled_layers.count('land'), 1)
            self.assertTrue(widget.placements)

    async def test_alert_selection_rebuilds_focused_geography_without_network_work(self) -> None:
        app = _MapApp()
        flood = _alert('flood', severity='Severe', geometry=WEST_GERMANY)
        wind = _alert('wind', severity='Moderate', geometry=EAST_GERMANY)

        async with app.run_test(size=(100, 32)) as pilot:
            widget = app.query_one(CountryAlertsMap)
            widget.update_country(
                'DE',
                'Germany',
                [flood, wind],
                selected_alert_key=('fixture', 'flood'),
            )
            for _ in range(3):
                await pilot.pause()
            self.assertEqual(widget.border_title, 'Map of Alerts for Germany')
            geometry = widget.geometry
            assert geometry is not None
            widget.update_selected_alert(('fixture', 'wind'))
            await pilot.pause()

            assert widget.geometry is not None
            self.assertNotEqual(widget.geometry.viewport, geometry.viewport)
            self.assertEqual(widget.geometry.selected_alert_key, ('fixture', 'wind'))
            self.assertEqual(len(widget.alert_layers), 1)

    async def test_city_callouts_are_directional_interactive_name_only_and_capped(self) -> None:
        app = _MapApp()
        async with app.run_test(size=(48, 28)) as pilot:
            widget = app.query_one(CountryAlertsMap)
            widget.styles.width = 44
            widget.update_country('DE', 'Germany', [])
            for _ in range(3):
                await pilot.pause()

            labels = list(widget.query(CountryAlertCityLabel))
            self.assertTrue(labels)
            self.assertLessEqual(len(labels), 32)
            self.assertTrue(all('•' in label.label_text for label in labels))
            self.assertTrue(all('°' not in label.label_text for label in labels))
            self.assertTrue(all(label.can_focus for label in labels))
            self.assertTrue(widget.placements)

            visible_keys = {placement.key for placement in widget.placements}
            assert widget.geometry is not None
            canvas = GeographicCanvas(
                widget.content_size.width,
                widget.content_size.height,
                widget.geometry.viewport,
            )
            canvas.fill_polygons(widget.geometry.land, layer='land')
            canvas.frame(
                (('land', None),),
                centering_layers=(
                    () if widget.geometry.selected_alert_polygons else ('land',)
                ),
            )
            points = {
                (place.latitude, place.longitude): point
                for place, point in widget.geometry.places
            }
            for placement in widget.placements:
                marker_column = (
                    placement.column + placement.width - 1
                    if placement.marker_on_right
                    else placement.column
                )
                self.assertEqual(
                    (marker_column, placement.row),
                    canvas.cell_position(points[placement.key]),
                )
            label = next(
                label
                for label in labels
                if (label.place.latitude, label.place.longitude) in visible_keys
            )
            label.focus()
            await pilot.press('enter')
            await pilot.press('space')
            self.assertTrue(await pilot.click(label))
            await pilot.pause()
            self.assertEqual(app.selected_places, [label.place, label.place, label.place])
            self.assertTrue(label.has_focus)

            widget.set_max_city_labels(2)
            await pilot.pause()
            self.assertEqual(widget.max_city_labels, 2)
            self.assertLessEqual(len(widget.placements), 2)

    async def test_region_annotations_are_passive_and_have_no_marker_dots(self) -> None:
        app = _MapApp()
        flood = _alert('flood', severity='Severe', geometry=WEST_GERMANY)
        async with app.run_test(size=(100, 32)) as pilot:
            widget = app.query_one(CountryAlertsMap)
            widget.update_country(
                'DE',
                'Germany',
                [flood],
                selected_alert_key=('fixture', 'flood'),
            )
            for _ in range(3):
                await pilot.pause()

            annotations = list(widget.query(CountryAlertRegionLabel))
            self.assertTrue(annotations)
            self.assertTrue(all(not annotation.can_focus for annotation in annotations))
            self.assertTrue(all('•' not in annotation.render().plain for annotation in annotations))
            self.assertTrue(all(annotation.display for annotation in annotations))

    async def test_country_and_city_names_render_without_weather_enrichment(self) -> None:
        app = _MapApp()
        async with app.run_test(size=(100, 32)) as pilot:
            widget = app.query_one(CountryAlertsMap)
            widget.update_country('DE', 'Germany', [])
            for _ in range(3):
                await pilot.pause()

            self.assertIsNotNone(widget.geometry)
            self.assertIn('Berlin', {label.place.name for label in widget.query(CountryAlertCityLabel)})
            self.assertTrue(any(0x2801 <= ord(character) <= 0x28FF for character in widget.query_one('#country-alerts-map-backdrop').render().plain))


class _FixtureCountryService:
    def __init__(self, alerts: dict[str, list[Alert]]) -> None:
        self.alerts = alerts
        self.last_country_code: str | None = None

    async def get_alerts(
        self,
        country_code: str,
        *,
        warning_language: str,
        progress,
        refresh: bool,
    ) -> list[Alert]:
        del warning_language, progress, refresh
        return list(self.alerts[country_code])


class _ScreenApp(App[None]):
    def __init__(self, screen: AlertsCentreScreen) -> None:
        super().__init__()
        self.temperature_unit = 'celsius'
        self.wind_speed_unit = 'kmh'
        self.precipitation_unit = 'mm'
        self.test_screen = screen

    async def on_mount(self) -> None:
        await self.push_screen(self.test_screen)


class CountryAlertPlaceHourlyLoadingTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _visible_places(screen: AlertsCentreScreen) -> list:
        visible_keys = {placement.key for placement in screen.country_map.placements}
        return [
            label.place
            for label in screen.country_map.query(CountryAlertCityLabel)
            if (label.place.latitude, label.place.longitude) in visible_keys
        ]

    async def test_selection_loads_once_and_resize_and_cache_hit_do_not_refetch(self) -> None:
        requests = []
        forecast = hourly_forecast()

        async def loader(latitude, longitude, temperature_unit, wind_speed_unit):
            requests.append((latitude, longitude, temperature_unit, wind_speed_unit))
            return forecast

        screen = AlertsCentreScreen(
            service=_FixtureCountryService({'DE': []}),  # type: ignore[arg-type]
            countries=[GERMANY],
            place_hourly_loader=loader,
        )
        app = _ScreenApp(screen)

        async with app.run_test(size=(120, 36)) as pilot:
            for _ in range(3):
                await pilot.pause()
            self.assertEqual(requests, [])
            place = self._visible_places(screen)[0]
            screen._select_settlement(place)
            for _ in range(2):
                await pilot.pause()

            self.assertEqual(
                requests,
                [(place.latitude, place.longitude, 'celsius', 'kmh')],
            )
            self.assertIs(screen.selected_place_forecast, forecast)
            self.assertEqual(screen.place_forecast_state, 'ready')
            strip = screen.place_forecast
            self.assertTrue(strip.display)
            self.assertEqual(strip.state, 'ready')
            self.assertEqual(strip.border_title, f'Hourly forecast — {place.name}')
            self.assertGreater(strip.hour_count, 0)

            expected_heights = {
                (80, 24): 4,
                (100, 30): 0,
                (140, 40): 9,
                (180, 50): 9,
                (220, 50): 9,
            }
            for size, expected_height in expected_heights.items():
                await pilot.resize_terminal(*size)
                await pilot.pause()
                self.assertEqual(
                    strip.region.height if strip.display else 0,
                    expected_height,
                    size,
                )
                self.assertLessEqual(
                    expected_height,
                    alerts_centre_layout_for(
                        *size,
                        place_forecast_state='ready',
                        place_forecast_has_data=True,
                    ).map_workspace_height
                    // 4,
                )
            screen._select_settlement(place)
            await pilot.pause()
            self.assertEqual(len(requests), 1)

    async def test_expired_cache_and_unit_change_refetch(self) -> None:
        now = [100.0]
        requests = []

        async def loader(latitude, longitude, temperature_unit, wind_speed_unit):
            requests.append((temperature_unit, wind_speed_unit))
            return hourly_forecast()

        screen = AlertsCentreScreen(
            service=_FixtureCountryService({'DE': []}),  # type: ignore[arg-type]
            countries=[GERMANY],
            place_hourly_loader=loader,
            place_hourly_cache_ttl_seconds=10,
            clock=lambda: now[0],
        )
        app = _ScreenApp(screen)

        async with app.run_test(size=(120, 36)) as pilot:
            for _ in range(3):
                await pilot.pause()
            place = self._visible_places(screen)[0]
            screen._select_settlement(place)
            await pilot.pause()
            now[0] += 10
            screen._select_settlement(place)
            await pilot.pause()
            app.temperature_unit = 'fahrenheit'
            app.wind_speed_unit = 'mph'
            screen.apply_preferences(
                warning_language='auto',
                units_changed=True,
                appearance_changed=False,
            )
            await pilot.pause()

            self.assertEqual(
                requests,
                [('celsius', 'kmh'), ('celsius', 'kmh'), ('fahrenheit', 'mph')],
            )

    async def test_second_settlement_load_keeps_the_rendered_strip_height(self) -> None:
        release_second = asyncio.Event()
        requests = 0

        async def loader(*_args):
            nonlocal requests
            requests += 1
            if requests == 2:
                await release_second.wait()
            return hourly_forecast()

        screen = AlertsCentreScreen(
            service=_FixtureCountryService({'DE': []}),  # type: ignore[arg-type]
            countries=[GERMANY],
            place_hourly_loader=loader,
        )
        app = _ScreenApp(screen)

        async with app.run_test(size=(180, 50)) as pilot:
            for _ in range(3):
                await pilot.pause()
            first, second = self._visible_places(screen)[:2]
            screen._select_settlement(first)
            for _ in range(2):
                await pilot.pause()
            established_height = screen.place_forecast.region.height
            self.assertEqual(established_height, 9)

            screen._select_settlement(second)
            await pilot.pause()

            self.assertEqual(screen.place_forecast_state, 'loading')
            self.assertEqual(screen.place_forecast.region.height, established_height)
            self.assertTrue(screen.place_forecast.loading_indicator.display)
            self.assertFalse(screen.place_forecast.content.display)

            release_second.set()
            await pilot.pause()
            self.assertEqual(screen.place_forecast_state, 'ready')

    async def test_rapid_selection_rejects_a_cancelled_stale_result(self) -> None:
        releases: dict[str, asyncio.Event] = {}
        results = {}

        async def loader(latitude, longitude, _temperature_unit, _wind_speed_unit):
            key = f'{latitude},{longitude}'
            release = releases.setdefault(key, asyncio.Event())
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
            result = hourly_forecast()
            results[key] = result
            return result

        screen = AlertsCentreScreen(
            service=_FixtureCountryService({'DE': []}),  # type: ignore[arg-type]
            countries=[GERMANY],
            place_hourly_loader=loader,
        )
        app = _ScreenApp(screen)

        async with app.run_test(size=(120, 36)) as pilot:
            for _ in range(3):
                await pilot.pause()
            first, second = self._visible_places(screen)[:2]
            screen._select_settlement(first)
            await pilot.pause()
            screen._select_settlement(second)
            await pilot.pause()
            second_key = f'{second.latitude},{second.longitude}'
            releases[second_key].set()
            await pilot.pause()
            selected_result = results[second_key]
            first_key = f'{first.latitude},{first.longitude}'
            releases[first_key].set()
            await pilot.pause()

            self.assertEqual(screen.selected_place, second)
            self.assertIs(screen.selected_place_forecast, selected_result)

    async def test_alert_change_clears_selection_and_failure_is_retryable(self) -> None:
        attempts = 0

        async def loader(*_args):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError('offline')
            return hourly_forecast()

        flood = _alert('flood', severity='Severe', geometry=WEST_GERMANY)
        wind = _alert('wind', severity='Moderate', geometry=EAST_GERMANY)
        service = _FixtureCountryService({'DE': [flood, wind], 'FR': []})
        screen = AlertsCentreScreen(
            service=service,  # type: ignore[arg-type]
            countries=[GERMANY, FRANCE],
            place_hourly_loader=loader,
        )
        app = _ScreenApp(screen)

        async with app.run_test(size=(120, 36)) as pilot:
            for _ in range(4):
                await pilot.pause()
            place = self._visible_places(screen)[0]
            screen._select_settlement(place)
            await pilot.pause()
            self.assertEqual(screen.place_forecast_state, 'failed')
            self.assertTrue(screen.place_forecast.display)
            self.assertIn(
                'unavailable',
                screen.place_forecast.content.render().plain,
            )

            screen.action_refresh_alerts()
            for _ in range(3):
                await pilot.pause()
            self.assertEqual(screen.place_forecast_state, 'ready')
            self.assertEqual(attempts, 2)

            screen._select_alert(wind)
            await pilot.pause()
            self.assertIsNone(screen.selected_place)
            self.assertIsNone(screen.selected_place_forecast)
            self.assertEqual(screen.place_forecast_state, 'idle')

            for _ in range(2):
                await pilot.pause()
            screen._select_settlement(self._visible_places(screen)[0])
            await pilot.pause()
            screen._choose_country('FR')
            await pilot.pause()
            self.assertIsNone(screen.selected_place)
            self.assertIsNone(screen.selected_place_forecast)
            self.assertEqual(screen.place_forecast_state, 'idle')


if __name__ == '__main__':
    unittest.main()
