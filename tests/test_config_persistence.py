"""Configuration persistence and write-failure contracts."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import typer

from wevva.app import Wevva
from wevva.cli import _apply_default_location_mutations
from wevva.config import (
    DEFAULT_PREFERENCES,
    ConfigWriteError,
    add_saved_location,
    get_config_path,
    load_preferences,
    remove_saved_location,
    save_default_location,
    save_preferences,
    save_saved_locations,
)
from wevva.location_metadata import LocationMetadata


LONDON = LocationMetadata(
    latitude=51.5072,
    longitude=-0.1276,
    elevation=11,
    name='London',
    country='United Kingdom',
    country_code='GB',
    timezone='Europe/London',
)


class ConfigPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.home = Path(self.temporary_directory.name)
        self.home_patcher = patch('wevva.config.Path.home', return_value=self.home)
        self.home_patcher.start()

    def tearDown(self) -> None:
        self.home_patcher.stop()
        self.temporary_directory.cleanup()

    def test_loading_defaults_does_not_create_a_config_directory(self) -> None:
        config_path = get_config_path()

        self.assertEqual(load_preferences(), DEFAULT_PREFERENCES)
        self.assertFalse(config_path.parent.exists())
        self.assertFalse(config_path.exists())

    def test_write_creates_the_parent_and_round_trips_preferences(self) -> None:
        save_preferences(
            temperature_unit='fahrenheit',
            wind_speed_unit='mph',
            precipitation_unit='inch',
            theme='nord',
            emoji_enabled=False,
            warning_language='en',
        )

        self.assertTrue(get_config_path().is_file())
        preferences = load_preferences()
        self.assertEqual(preferences['temperature_unit'], 'fahrenheit')
        self.assertEqual(preferences['wind_speed_unit'], 'mph')
        self.assertEqual(preferences['precipitation_unit'], 'inch')
        self.assertEqual(preferences['theme'], 'nord')
        self.assertFalse(preferences['emoji_enabled'])
        self.assertEqual(preferences['warning_language'], 'en')

    def test_legacy_default_metadata_is_retained_and_migrated_to_saved_locations(self) -> None:
        config_path = get_config_path()
        config_path.parent.mkdir(parents=True)
        metadata = {
            'latitude': LONDON.latitude,
            'longitude': LONDON.longitude,
            'elevation': LONDON.elevation,
            'name': LONDON.name,
            'country': LONDON.country,
            'country_code': LONDON.country_code,
            'timezone': LONDON.timezone,
        }
        config_path.write_text(
            json.dumps(
                {
                    'default_location': 'London, United Kingdom',
                    'default_location_metadata': metadata,
                }
            )
        )

        preferences = load_preferences()

        self.assertEqual(preferences['default_location'], 'London, United Kingdom')
        self.assertEqual(preferences['default_location_metadata'], preferences['saved_locations'][0])

    def test_each_mutation_loads_preferences_once(self) -> None:
        save_preferences(
            temperature_unit='celsius',
            wind_speed_unit='kmh',
            precipitation_unit='mm',
        )
        location_config = {
            'latitude': LONDON.latitude,
            'longitude': LONDON.longitude,
            'name': LONDON.name,
            'country': LONDON.country,
        }
        operations = (
            lambda: save_preferences('celsius', 'kmh', 'mm', theme='nord'),
            lambda: save_saved_locations([location_config]),
            lambda: add_saved_location(LONDON),
            lambda: remove_saved_location(LONDON),
            lambda: save_default_location('London', default_location_metadata=location_config),
        )

        for operation in operations:
            with self.subTest(operation=operation):
                with patch('wevva.config.load_preferences', wraps=load_preferences) as loader:
                    operation()
                loader.assert_called_once_with()

    def test_write_failure_raises_a_specific_error(self) -> None:
        with patch.object(Path, 'mkdir', side_effect=PermissionError('read-only directory')):
            with self.assertRaisesRegex(ConfigWriteError, 'Could not save preferences'):
                save_preferences('celsius', 'kmh', 'mm')


class ConfigWriteFailurePresentationTests(unittest.TestCase):
    def test_tui_save_action_notifies_on_write_failure(self) -> None:
        app = Wevva(initial_location=LONDON)
        error = ConfigWriteError('Preferences could not be saved.')

        with (
            patch('wevva.app.add_saved_location', side_effect=error),
            patch.object(app, 'notify') as notify,
        ):
            app.action_save_current_location()

        notify.assert_called_once_with(str(error), severity='error')

    def test_cli_mutation_prints_write_failure_and_exits(self) -> None:
        error = ConfigWriteError('Preferences could not be saved.')

        with (
            patch('wevva.cli.save_default_location', side_effect=error),
            patch('wevva.cli.typer.secho') as secho,
            self.assertRaises(typer.Exit) as raised,
        ):
            _apply_default_location_mutations(
                set_default_location=None,
                clear_default_location=True,
            )

        self.assertEqual(raised.exception.exit_code, 1)
        secho.assert_called_once_with(str(error), fg=typer.colors.RED, err=True)


if __name__ == '__main__':
    unittest.main()
