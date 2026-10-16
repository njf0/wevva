"""Fixture-driven checks for the alerts-centre workspace."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from io import StringIO
import unittest
from unittest.mock import patch

from rich.console import Console
from textual.app import App
from textual.containers import Container
from textual.widgets import ProgressBar, Select, Static
from wevva_warnings import Alert, WarningSource

from wevva.screens.alerts_centre_screen import AlertFilterDialog, AlertsCentreScreen
from wevva.services.country_alerts import SupportedAlertCountry
from wevva.widgets.country_alerts_map import CountryAlertsMap


GERMANY = SupportedAlertCountry('DE', 'Germany')
FRANCE = SupportedAlertCountry('FR', 'France')
GUAM = SupportedAlertCountry('GU', 'Guam')


def _alert(
    alert_id: str,
    *,
    severity: str,
    event: str,
    headline: str,
    areas: list[str] | None = None,
    urgency: str | None = None,
    certainty: str | None = None,
    onset: datetime | None = None,
    expires: datetime | None = None,
) -> Alert:
    source = WarningSource(
        id='fixture-source',
        name='Fixture Weather Service',
        backend='fixture',
        country_code='DE',
        url='https://example.test/feed',
    )
    return Alert(
        id=alert_id,
        source=source.id,
        source_info=source,
        event=event,
        headline=headline,
        severity=severity,
        urgency=urgency,
        certainty=certainty,
        onset=onset,
        expires=expires,
        description=f'Complete provider document for {alert_id}.',
        instruction='Follow official advice.',
        url=f'https://example.test/alerts/{alert_id}',
        area_names=list(areas or []),
    )


def _rendered(static: Static) -> str:
    console = Console(width=100, file=StringIO(), record=True, color_system=None)
    console.print(static._Static__content)
    return console.export_text()


class _ScreenApp(App[None]):
    def __init__(self, screen: AlertsCentreScreen) -> None:
        super().__init__()
        self.test_screen = screen

    async def on_mount(self) -> None:
        await self.push_screen(self.test_screen)


class _FixtureService:
    def __init__(
        self,
        results: dict[str, list[Alert] | Exception],
        *,
        new_alerts: dict[str, set[tuple[str, str]]] | None = None,
    ) -> None:
        self.results = results
        self.new_alerts = new_alerts or {}
        self.calls: list[tuple[str, bool]] = []
        self.last_country_code: str | None = None

    async def get_alerts(
        self,
        country_code: str,
        *,
        warning_language: str,
        progress,
        refresh: bool,
    ) -> list[Alert]:
        del warning_language
        self.calls.append((country_code, refresh))
        progress('source_started', {'provider_name': 'Fixture Weather Service'})
        result = self.results[country_code]
        if isinstance(result, Exception):
            raise result
        return list(result)

    def new_alert_identities(
        self,
        country_code: str,
        *,
        warning_language: str,
    ) -> frozenset[tuple[str, str]]:
        del warning_language
        return frozenset(self.new_alerts.get(country_code, set()))


class _RaceService(_FixtureService):
    def __init__(self, german: list[Alert], french: list[Alert]) -> None:
        super().__init__({'DE': german, 'FR': french})
        self.german_started = asyncio.Event()
        self.german_list_loaded = asyncio.Event()
        self.german_iterating = asyncio.Event()

    async def get_alerts(
        self,
        country_code: str,
        *,
        warning_language: str,
        progress,
        refresh: bool,
    ) -> list[Alert]:
        del warning_language
        self.calls.append((country_code, refresh))
        if country_code == 'DE':
            progress('sources_total', {'total': 1})
            progress('source_started', {'provider_name': 'Fixture Weather Service'})
            self.german_started.set()
            await self.german_list_loaded.wait()
            progress('alerts_total', {'total': 2})
            progress('alerts_checked', {'completed': 1, 'total': 2})
            self.german_iterating.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                # Simulate a blocking provider which completes after its UI
                # request has already been superseded.
                return list(self.results['DE'])  # type: ignore[arg-type]
        return list(self.results[country_code])  # type: ignore[arg-type]


class AlertsCentreScreenTests(unittest.IsolatedAsyncioTestCase):
    async def test_initial_result_builds_only_empty_and_final_selected_maps(self) -> None:
        alert = _alert(
            'german-flood',
            severity='Severe',
            event='Flood Warning',
            headline='Flooding in Germany',
        )
        screen = AlertsCentreScreen(
            service=_FixtureService({'DE': [alert]}),  # type: ignore[arg-type]
            countries=[GERMANY],
        )
        app = _ScreenApp(screen)
        rebuilds = 0
        original_rebuild = CountryAlertsMap._rebuild_view

        def counted_rebuild(widget: CountryAlertsMap) -> None:
            nonlocal rebuilds
            rebuilds += 1
            original_rebuild(widget)

        with patch.object(CountryAlertsMap, '_rebuild_view', new=counted_rebuild):
            async with app.run_test(size=(100, 30)) as pilot:
                await pilot.pause()

        self.assertEqual(rebuilds, 2)

    async def test_unchanged_layout_budget_skips_child_reapplication(self) -> None:
        screen = AlertsCentreScreen(
            service=_FixtureService({'DE': []}),  # type: ignore[arg-type]
            countries=[GERMANY],
        )
        app = _ScreenApp(screen)

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            with (
                patch.object(
                    screen.country_map,
                    'set_max_city_labels',
                    wraps=screen.country_map.set_max_city_labels,
                ) as set_label_limit,
                patch.object(
                    screen.place_forecast,
                    'set_layout',
                    wraps=screen.place_forecast.set_layout,
                ) as set_place_layout,
            ):
                screen._apply_responsive_layout(
                    screen._layout_width,
                    screen._layout_height,
                )

            set_label_limit.assert_not_called()
            set_place_layout.assert_not_called()

    async def test_country_select_changes_the_loaded_country(self) -> None:
        service = _FixtureService({'DE': [], 'FR': []})
        screen = AlertsCentreScreen(
            service=service,  # type: ignore[arg-type]
            countries=[GERMANY, FRANCE],
            initial_country_code='DE',
        )
        app = _ScreenApp(screen)

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            self.assertEqual(screen.country_select.value, 'DE')
            screen.country_select.value = 'FR'
            await pilot.pause()

            self.assertEqual(screen.selected_country_code, 'FR')
            self.assertEqual(service.calls, [('DE', False), ('FR', False)])

    async def test_filter_modal_retains_the_current_country_on_apply(self) -> None:
        service = _FixtureService({'DE': [], 'FR': []})
        screen = AlertsCentreScreen(
            service=service,  # type: ignore[arg-type]
            countries=[GERMANY, FRANCE],
            initial_country_code='DE',
        )
        app = _ScreenApp(screen)

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            screen.country_select.value = 'FR'
            await pilot.pause()
            screen.alert_filter_button.focus()
            await pilot.press('enter')
            await pilot.pause()

            self.assertIsInstance(app.screen, AlertFilterDialog)
            app.screen.query_one(
                '#alerts-centre-filter-dialog-sort',
                Select,
            ).value = 'new'
            await pilot.click('#alerts-centre-filter-apply')
            await pilot.pause()

            self.assertIs(app.screen, screen)
            self.assertEqual(screen.selected_country_code, 'FR')
            self.assertEqual(screen.country_select.value, 'FR')
            self.assertEqual(screen.alert_sort_value, 'new')
            self.assertEqual(service.calls, [('DE', False), ('FR', False)])

    async def test_country_switch_ignores_the_superseded_result(self) -> None:
        german = _alert(
            'german-flood',
            severity='Severe',
            event='Flood Warning',
            headline='Flooding in Germany',
            areas=['Northern Germany'],
        )
        french = _alert(
            'french-wind',
            severity='Moderate',
            event='Wind Warning',
            headline='Strong winds in France',
            areas=['Brittany'],
        )
        service = _RaceService([german], [french])
        screen = AlertsCentreScreen(
            service=service,  # type: ignore[arg-type]
            countries=[GERMANY, FRANCE],
            initial_country_code='DE',
        )
        app = _ScreenApp(screen)

        async with app.run_test(size=(120, 36)) as pilot:
            await service.german_started.wait()
            progress = screen.query_one('#alerts-centre-list-progress', Container)
            progress_bar = screen.query_one(
                '#alerts-centre-list-progress-bar',
                ProgressBar,
            )
            self.assertTrue(progress.display)
            self.assertIsNone(progress_bar.total)
            self.assertEqual(progress_bar.query_one('#percentage').render(), '--%')
            self.assertFalse(screen.alert_list.display)
            self.assertFalse(
                screen.query_one('#alerts-centre-list-empty', Static).display
            )

            service.german_list_loaded.set()
            await service.german_iterating.wait()
            self.assertEqual(progress_bar.total, 2)
            self.assertEqual(progress_bar.progress, 1)
            self.assertEqual(progress_bar.query_one('#percentage').render(), '50%')

            screen._choose_country('FR')
            await pilot.pause()

            self.assertEqual(screen.selected_country_code, 'FR')
            self.assertEqual([alert.id for alert in screen.alerts], ['french-wind'])
            self.assertEqual(screen.selected_alert_key, ('fixture-source', 'french-wind'))
            self.assertFalse(progress.display)
            self.assertTrue(screen.alert_list.display)
            self.assertIn('Strong winds in France', _rendered(screen.details.content))
            self.assertNotIn('Flooding in Germany', _rendered(screen.details.content))

    async def test_filter_is_local_searches_metadata_and_has_distinct_empty_state(self) -> None:
        flood = _alert(
            'flood',
            severity='Severe',
            event='Flood Warning',
            headline='Flooding expected',
            areas=['North district', 'River district', 'Coast district'],
            urgency='Immediate',
            certainty='Observed',
        )
        wind = _alert(
            'wind',
            severity='Moderate',
            event='Wind Warning',
            headline='Strong winds expected',
            areas=[],
            urgency='Expected',
            certainty='Likely',
        )
        service = _FixtureService({'DE': [flood, wind]})
        screen = AlertsCentreScreen(
            service=service,  # type: ignore[arg-type]
            countries=[GERMANY],
        )
        app = _ScreenApp(screen)

        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            self.assertEqual(service.calls, [('DE', False)])
            first_prompt = screen.alert_list.get_option_at_index(0).prompt
            self.assertEqual(
                first_prompt.plain,
                'Severe Flood\nNorth district, River d…',
            )
            self.assertTrue(first_prompt.no_wrap)
            self.assertEqual(first_prompt.overflow, 'ellipsis')
            self.assertEqual(screen.alert_list.highlighted, 0)
            self.assertIsNotNone(
                screen.alert_list.get_component_rich_style(
                    'option-list--option-highlighted',
                ).bgcolor
            )
            self.assertTrue(screen.alert_list.get_option_at_index(0)._divider)
            self.assertFalse(screen.alert_list.get_option_at_index(1)._divider)

            screen.alert_list.highlighted = 1
            screen.alert_list.action_select()
            await pilot.pause()
            self.assertEqual(screen.selected_alert_key, ('fixture-source', 'wind'))
            self.assertEqual(screen.alert_list.highlighted, 1)

            screen.alert_filter_button.focus()
            await pilot.press('enter')
            await pilot.pause()
            self.assertIsInstance(app.screen, AlertFilterDialog)
            severity_select = app.screen.query_one(
                '#alerts-centre-filter-dialog-severity',
                Select,
            )
            self.assertEqual(
                severity_select._options,
                [
                    ('All severities', ''),
                    ('Severe', 'severe'),
                    ('Moderate', 'moderate'),
                ],
            )
            await pilot.press('escape')
            await pilot.pause()

            screen._on_alert_filter_result(('north district', '', 'severity'))
            await pilot.pause()
            self.assertEqual([alert.id for alert in screen.filtered_alerts], ['flood'])

            screen._on_alert_filter_result(('', 'moderate', 'severity'))
            await pilot.pause()
            self.assertEqual([alert.id for alert in screen.filtered_alerts], ['wind'])

            screen._on_alert_filter_result(('likely', 'moderate', 'severity'))
            await pilot.pause()
            self.assertEqual([alert.id for alert in screen.filtered_alerts], ['wind'])
            self.assertEqual(screen.selected_alert_key, ('fixture-source', 'wind'))
            self.assertIn('Strong winds expected', _rendered(screen.details.content))
            self.assertEqual(service.calls, [('DE', False)])

            screen._on_alert_filter_result(('not-present', '', 'severity'))
            await pilot.pause()
            empty = screen.query_one('#alerts-centre-list-empty', Static)
            self.assertTrue(empty.display)
            self.assertEqual(_rendered(empty).strip(), 'No matching alerts')
            self.assertEqual(service.calls, [('DE', False)])

    async def test_new_badge_and_new_first_sort_are_local_to_latest_refresh(self) -> None:
        severe = _alert(
            'flood',
            severity='Severe',
            event='Flood Warning',
            headline='Flooding expected',
            areas=['North district'],
        )
        newly_observed = _alert(
            'wind',
            severity='Moderate',
            event='Wind Warning',
            headline='Strong winds expected',
            areas=['Coast district'],
        )
        service = _FixtureService(
            {'DE': [severe, newly_observed]},
            new_alerts={'DE': {('fixture-source', 'wind')}},
        )
        screen = AlertsCentreScreen(
            service=service,  # type: ignore[arg-type]
            countries=[GERMANY],
        )
        app = _ScreenApp(screen)

        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            self.assertEqual(screen.alert_sort_value, 'severity')
            self.assertEqual(
                [alert.id for alert in screen.filtered_alerts],
                ['flood', 'wind'],
            )
            new_prompt = screen.alert_list.get_option_at_index(1).prompt
            self.assertEqual(
                new_prompt.plain,
                'NEW Moderate Wind\nCoast district',
            )
            self.assertIn('on ', str(new_prompt.spans[0].style))

            screen._on_alert_filter_result(
                (
                    screen.alert_filter_value,
                    screen.alert_severity_filter,
                    'new',
                )
            )
            await pilot.pause()
            self.assertEqual(
                [alert.id for alert in screen.filtered_alerts],
                ['wind', 'flood'],
            )
            self.assertEqual(
                screen.alert_list.get_option_at_index(0).prompt.plain,
                'NEW Moderate Wind\nCoast district',
            )

    async def test_shared_feed_country_prefills_filter_with_country_name(self) -> None:
        guam_alert = _alert(
            'guam-wind',
            severity='Moderate',
            event='Wind Warning',
            headline='Strong winds in Guam',
            areas=['Guam'],
        )
        mainland_alert = _alert(
            'mainland-wind',
            severity='Moderate',
            event='Wind Warning',
            headline='Strong winds in California',
            areas=['California'],
        )
        service = _FixtureService({'GU': [guam_alert, mainland_alert]})
        screen = AlertsCentreScreen(
            service=service,  # type: ignore[arg-type]
            countries=[GUAM],
        )
        app = _ScreenApp(screen)

        with patch(
            'wevva.screens.alerts_centre_screen.country_alert_default_filter',
            return_value='Guam',
        ):
            async with app.run_test(size=(100, 30)) as pilot:
                await pilot.pause()
                self.assertEqual(screen.alert_filter_value, 'Guam')
                self.assertEqual(
                    [alert.id for alert in screen.filtered_alerts],
                    ['guam-wind'],
                )

    async def test_selected_details_show_active_start_and_end_below_headline(self) -> None:
        alert = _alert(
            'timed-flood',
            severity='Severe',
            event='Flood Warning',
            headline='Flooding expected',
            onset=datetime(2030, 1, 2, 9, 0, tzinfo=UTC),
            expires=datetime(2030, 1, 2, 17, 0, tzinfo=UTC),
        )
        screen = AlertsCentreScreen(
            service=_FixtureService({'DE': [alert]}),  # type: ignore[arg-type]
            countries=[GERMANY],
        )
        app = _ScreenApp(screen)

        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            details = _rendered(screen.details.content)
            self.assertIn('Flooding expected\n\nActive from ', details)
            self.assertIn(' until ', details)

    async def test_successful_empty_and_total_failure_have_inline_states(self) -> None:
        empty_service = _FixtureService({'DE': []})
        empty_screen = AlertsCentreScreen(
            service=empty_service,  # type: ignore[arg-type]
            countries=[GERMANY],
        )
        empty_app = _ScreenApp(empty_screen)

        async with empty_app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            message = empty_screen.query_one('#alerts-centre-list-empty', Static)
            self.assertEqual(_rendered(message).strip(), 'No active alerts')
            detail_prompt = empty_screen.query_one(
                '#alerts-centre-document-empty',
                Static,
            )
            self.assertEqual(
                _rendered(detail_prompt).strip(),
                'Select an alert to view detailed information',
            )

        failed_service = _FixtureService({'DE': RuntimeError('offline')})
        failed_screen = AlertsCentreScreen(
            service=failed_service,  # type: ignore[arg-type]
            countries=[GERMANY],
        )
        failed_app = _ScreenApp(failed_screen)

        async with failed_app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            message = failed_screen.query_one('#alerts-centre-list-empty', Static)
            self.assertIn('Press r to retry', _rendered(message))
            failed_screen.country_select.focus()
            await pilot.press('r')
            await pilot.pause()
            self.assertEqual(failed_service.calls, [('DE', False), ('DE', True)])


if __name__ == '__main__':
    unittest.main()
