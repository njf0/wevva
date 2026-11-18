"""First-run setup uses isolated profiles and never calls weather providers."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

from typer.testing import CliRunner

from wevva.cli import app
from wevva.config import (
    ConfigWriteError,
    initialize_starter_locations,
    is_first_run,
    load_preferences,
    save_preferences,
    save_saved_locations,
    starter_locations,
)


class FirstRunTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = self.enterContext(TemporaryDirectory())
        self.config = Path(directory) / 'config' / 'wevva' / 'config.json'
        self.cache = Path(directory) / 'cache' / 'wevva'
        self.enterContext(patch('wevva.config.get_config_path', return_value=self.config))
        self.enterContext(patch(
            'wevva.services.warning_cache.get_warning_cache_directory',
            return_value=self.cache / 'warnings',
        ))
        self.launch = self.enterContext(patch('wevva.cli.Wevva'))
        self.lookup = self.enterContext(patch(
            'wevva.cli._lookup_places', side_effect=AssertionError('unexpected geocoding'),
        ))
        self.runner = CliRunner()

    def _setup(self, answers, *, no_launch=True):
        prompts = [Mock(ask=Mock(return_value=value)) for value in answers]
        with (
            patch('wevva.cli.questionary.confirm', side_effect=prompts) as confirm,
            patch('wevva.cli._questionary_select', side_effect=lambda title, options, current: current),
        ):
            result = self.runner.invoke(app, ['setup', *(['--no-launch'] if no_launch else [])])
        self.assertEqual(result.exit_code, 0, result.output)
        return result, confirm

    def test_bundle_contains_verified_places_and_independent_metadata(self) -> None:
        places = starter_locations()
        self.assertEqual({p['name']: p['country_code'] for p in places}, {
            'Yellowknife': 'CA', 'Hilo': 'US', 'Georgetown': 'GY',
            'Accra': 'GH', 'Baguio City': 'PH', 'Westport': 'NZ',
        })
        for place in places:
            self.assertTrue(place['admin'])
            self.assertIsInstance(place['elevation'], int)
            self.assertTrue(-90 <= place['latitude'] <= 90)
            self.assertTrue(-180 <= place['longitude'] <= 180)
            ZoneInfo(place['timezone'])
            self.assertEqual(place['timezone_abbreviation'], '')
        places[0]['name'] = 'Changed'
        self.assertNotEqual(starter_locations()[0]['name'], 'Changed')

    def test_first_launch_seeds_once_without_geocoding_and_uses_dashboard_startup(self) -> None:
        result = self.runner.invoke(app, [])
        self.assertEqual(result.exit_code, 0, result.output)
        preferences = load_preferences()
        self.assertEqual(preferences['saved_locations'], starter_locations())
        self.assertIsNone(preferences['default_location'])
        options = self.launch.call_args.kwargs
        self.assertEqual(len(options['saved_locations']), 6)
        self.assertIsNotNone(options['initial_location'])
        self.assertIsNone(options['default_location'])
        original = self.config.read_bytes()
        result = self.runner.invoke(app, [])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.config.read_bytes(), original)
        self.lookup.assert_not_called()

    def test_deleting_starters_does_not_reseed(self) -> None:
        self.assertTrue(initialize_starter_locations())
        save_saved_locations([])
        result = self.runner.invoke(app, [])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(load_preferences()['saved_locations'], [])

    def test_existing_configs_are_never_seeded_or_rewritten(self) -> None:
        self.config.parent.mkdir(parents=True)
        for content in ('{}', '{broken', '[]', json.dumps({
            'saved_locations': [starter_locations()[0]],
            'default_location': 'My home', 'temperature_unit': 'fahrenheit',
            'default_location_metadata': starter_locations()[0],
        })):
            with self.subTest(content=content):
                self.config.write_text(content)
                self.assertFalse(initialize_starter_locations())
                result = self.runner.invoke(app, [])
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertEqual(self.config.read_text(), content)

    def test_empty_directories_cache_only_and_unreadable_state_are_not_fresh(self) -> None:
        self.assertTrue(is_first_run())
        self.assertFalse(self.config.parent.exists())
        self.assertFalse(self.cache.exists())
        for path in (self.config.parent, self.cache):
            with self.subTest(path=path):
                path.mkdir(parents=True)
                self.assertFalse(initialize_starter_locations())
                self.assertFalse(self.config.exists())
                path.rmdir()
        self.config.parent.symlink_to(self.config.parent.parent / 'missing')
        self.assertFalse(is_first_run())
        self.config.parent.unlink()
        with patch.object(Path, 'lstat', side_effect=PermissionError('unreadable')):
            self.assertFalse(is_first_run())

    def test_setup_accepts_then_launches_with_all_six_places(self) -> None:
        result, confirm = self._setup([True, False, False], no_launch=False)
        self.assertIn('Yellowknife', result.output)
        self.assertIn('Baguio City', result.output)
        self.assertEqual(confirm.call_args_list[0].args[0], 'Add these six starter locations?')
        self.assertTrue(confirm.call_args_list[0].kwargs['default'])
        self.assertEqual(load_preferences()['saved_locations'], starter_locations())
        self.assertEqual(len(self.launch.call_args.kwargs['saved_locations']), 6)

    def test_setup_no_launch_honours_accept_and_decline_across_restart(self) -> None:
        for accept in (True, False):
            with self.subTest(accept=accept):
                self.launch.reset_mock()
                self._setup([accept, False, False])
                self.launch.assert_not_called()
                self.assertTrue(self.config.exists())
                self.assertEqual(len(load_preferences()['saved_locations']), 6 if accept else 0)
                result = self.runner.invoke(app, [])
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertEqual(len(load_preferences()['saved_locations']), 6 if accept else 0)
                self.config.unlink()
                self.config.parent.rmdir()

    def test_existing_setup_skips_starter_prompt_and_preserves_saved_places(self) -> None:
        save_saved_locations(starter_locations()[:1])
        result, confirm = self._setup([False, False])
        self.assertNotIn('Starter locations:', result.output)
        self.assertEqual(confirm.call_count, 2)
        self.assertEqual(load_preferences()['saved_locations'], starter_locations()[:1])

    def test_cancelled_setup_does_not_create_profile_after_accepting(self) -> None:
        with (
            patch('wevva.cli.questionary.confirm', return_value=Mock(ask=Mock(return_value=True))),
            patch('wevva.cli.questionary.select', return_value=Mock(ask=Mock(return_value=None))),
        ):
            result = self.runner.invoke(app, ['setup', '--no-launch'])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn('Setup cancelled', result.output)
        self.assertFalse(self.config.parent.exists())

    def test_help_reads_and_public_api_do_not_initialize(self) -> None:
        from wevva import geocode_sync

        with patch('wevva.api.search_places', new=AsyncMock(return_value=[])):
            self.assertEqual(geocode_sync('a place'), [])
        self.assertEqual(load_preferences()['saved_locations'], [])
        for arguments in (['--help'], ['setup', '--help']):
            self.assertEqual(self.runner.invoke(app, arguments).exit_code, 0)
        self.assertFalse(self.config.parent.exists())
        self.assertFalse(self.cache.exists())

    def test_cli_default_override_is_preserved_alongside_starters(self) -> None:
        with patch('wevva.cli._resolve_first_location', return_value=(None, None)):
            result = self.runner.invoke(app, ['--set-default-location', 'My home'])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(load_preferences()['default_location'], 'My home')
        self.assertEqual(load_preferences()['saved_locations'], starter_locations())

    def test_locations_saved_during_setup_are_preserved(self) -> None:
        # The initial setup eligibility can become stale while prompts are open.
        self.assertTrue(is_first_run())
        save_saved_locations(starter_locations()[:1])
        save_preferences('fahrenheit', 'mph', 'in', add_starter_locations=True)
        self.assertEqual(load_preferences()['saved_locations'], starter_locations()[:1])
        self.assertEqual(load_preferences()['temperature_unit'], 'fahrenheit')

    def test_exclusive_creation_never_overwrites_a_racing_config(self) -> None:
        original_open = Path.open
        existing = json.dumps({'saved_locations': starter_locations()[:1]})

        def racing_open(path, mode='r', *args, **kwargs):
            if path == self.config and mode == 'x':
                with original_open(path, 'w') as file:
                    file.write(existing)
            return original_open(path, mode, *args, **kwargs)

        with patch.object(Path, 'open', racing_open):
            self.assertFalse(initialize_starter_locations())
        self.assertEqual(self.config.read_text(), existing)

    def test_write_failure_reports_error_without_launching_or_claiming_success(self) -> None:
        with patch.object(Path, 'mkdir', side_effect=PermissionError('read-only profile')):
            result = self.runner.invoke(app, [])
        self.assertEqual(result.exit_code, 1)
        self.assertIn('read-only profile', result.output)
        self.launch.assert_not_called()
        self.assertFalse(self.config.exists())

    def test_setup_write_failure_does_not_report_success(self) -> None:
        with (
            patch('wevva.cli.questionary.confirm', side_effect=[
                Mock(ask=Mock(return_value=value)) for value in (True, False, False)
            ]),
            patch('wevva.cli._questionary_select', side_effect=lambda title, options, current: current),
            patch('wevva.config._write_preferences', side_effect=ConfigWriteError('read-only profile')),
        ):
            result = self.runner.invoke(app, ['setup', '--no-launch'])
        self.assertEqual(result.exit_code, 1)
        self.assertIn('read-only profile', result.output)
        self.assertNotIn('Setup saved', result.output)
        self.assertFalse(self.config.exists())
