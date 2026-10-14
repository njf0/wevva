"""Focused contracts for Open-Meteo forecast model accessors."""

import unittest

from wevva.location_metadata import LocationMetadata
from wevva.openmeteo import (
    CurrentOpenMeteoForecast,
    DailyOpenMeteoForecast,
    HourlyOpenMeteoForecast,
    OpenMeteoForecast,
)


def metadata() -> LocationMetadata:
    return LocationMetadata(latitude=51.5, longitude=-0.1, timezone='UTC')


class ForecastModelAccessTests(unittest.TestCase):
    def test_current_accessors_treat_empty_or_missing_values_as_absent(self) -> None:
        for timeseries in ({}, {'time': '2099-01-01T00:00'}):
            forecast = CurrentOpenMeteoForecast(metadata(), {}, timeseries)

            self.assertEqual(forecast.get_condition(), '')
            for accessor in (
                forecast.get_temperature,
                forecast.get_feels_like,
                forecast.get_humidity,
                forecast.get_wind_speed,
                forecast.get_wind_gust,
                forecast.get_wind_direction,
                forecast.get_pressure,
                forecast.get_precipitation,
                forecast.get_is_day,
            ):
                with self.subTest(timeseries=timeseries, accessor=accessor.__name__):
                    self.assertIsNone(accessor())

        self.assertEqual(CurrentOpenMeteoForecast(metadata(), {}, {}).get_time(), '')

    def test_hourly_accessors_treat_missing_values_and_offsets_as_absent(self) -> None:
        forecast = HourlyOpenMeteoForecast(metadata(), {}, {'time': ['2099-01-01T00:00']})
        optional_accessors = (
            forecast.get_temperature,
            forecast.get_humidity,
            forecast.get_feels_temperature,
            forecast.get_precipitation_probability,
            forecast.get_precipitation,
            forecast.get_rain,
            forecast.get_showers,
            forecast.get_snowfall,
            forecast.get_surface_pressure,
            forecast.get_cloud_cover,
            forecast.get_visibility,
            forecast.get_wind_speed,
            forecast.get_wind_gust,
            forecast.get_wind_direction,
            forecast.get_uv_index,
            forecast.get_us_aqi,
            forecast.get_european_aqi,
            forecast.get_pm2_5,
            forecast.get_pm10,
            forecast.get_ozone,
            forecast.get_grass_pollen,
        )

        for offset in (0, 1, -1):
            for accessor in optional_accessors:
                with self.subTest(offset=offset, accessor=accessor.__name__):
                    self.assertIsNone(accessor(offset))
            self.assertEqual(forecast.get_weather_code(offset), '')
            self.assertEqual(forecast.get_condition_abbreviation(offset), '')
            self.assertEqual(forecast.get_condition_emoji(offset), '')

    def test_daily_accessors_treat_missing_values_and_offsets_as_absent(self) -> None:
        forecast = DailyOpenMeteoForecast(metadata(), {}, {'time': ['2099-01-01']})
        optional_accessors = (
            forecast.get_temperature_min,
            forecast.get_temperature_max,
            forecast.get_precipitation,
            forecast.get_precipitation_probability,
            forecast.get_wind_speed,
            forecast.get_wind_gust,
            forecast.get_wind_direction,
            forecast.get_sunrise,
            forecast.get_sunset,
            forecast.get_daylight_duration,
        )

        for offset in (0, 1, -1):
            for accessor in optional_accessors:
                with self.subTest(offset=offset, accessor=accessor.__name__):
                    self.assertIsNone(accessor(offset))
            self.assertEqual(forecast.get_weather_code(offset), '')
            self.assertEqual(forecast.get_condition_abbreviation(offset), '')

    def test_normal_hourly_values_keep_their_existing_transformations(self) -> None:
        forecast = HourlyOpenMeteoForecast(
            metadata(),
            {},
            {
                'time': ['2099-01-01T00:00'],
                'temperature_2m': [12.5],
                'relative_humidity_2m': [42.6],
                'weather_code': [0],
                'is_day': [0],
                'visibility': [12_500],
                'wind_direction_10m': [270],
            },
        )

        self.assertEqual(forecast.get_temperature(), 12.5)
        self.assertEqual(forecast.get_humidity(), 43)
        self.assertEqual(forecast.get_weather_code(), 'Clear sky')
        self.assertEqual(forecast.get_condition_emoji(), '🌙')
        self.assertEqual(forecast.get_visibility(), 12)
        self.assertEqual(forecast.get_wind_direction(), 'W →')

    def test_structurally_invalid_series_still_raise_during_parsing(self) -> None:
        malformed_hourly = {
            'time': ['2099-01-01T00:00'],
            'temperature_2m': [],
        }
        malformed_daily = {
            'time': ['2099-01-01'],
            'temperature_2m_min': [],
        }

        with self.assertRaises(IndexError):
            HourlyOpenMeteoForecast(metadata(), {}, malformed_hourly)
        with self.assertRaises(IndexError):
            DailyOpenMeteoForecast(metadata(), {}, malformed_daily)


class LegacyForecastModelPathTests(unittest.TestCase):
    def test_nonfunctional_instance_fetch_path_is_not_exposed(self) -> None:
        for model_class in (
            CurrentOpenMeteoForecast,
            HourlyOpenMeteoForecast,
            DailyOpenMeteoForecast,
        ):
            with self.subTest(model_class=model_class.__name__):
                self.assertFalse(hasattr(model_class, 'fetch_and_parse_forecast'))

        self.assertFalse(hasattr(OpenMeteoForecast, '_get_metadata'))
        self.assertFalse(hasattr(OpenMeteoForecast, '_get_units'))


if __name__ == '__main__':
    unittest.main()
