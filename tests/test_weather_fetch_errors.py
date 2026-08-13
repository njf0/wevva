"""Focused checks for concise weather-refresh error notifications."""

from __future__ import annotations

import unittest

import httpx

from wevva.app import _weather_fetch_failure_message


class WeatherFetchErrorTests(unittest.TestCase):
    def test_rate_limit_message_omits_the_request_url(self) -> None:
        request = httpx.Request(
            'GET',
            'https://api.open-meteo.com/v1/forecast?latitude=39.5296&longitude=-119.8138',
        )
        response = httpx.Response(429, request=request)
        error = httpx.HTTPStatusError('long provider error', request=request, response=response)

        self.assertEqual(
            _weather_fetch_failure_message(error),
            '429: Too Many Requests — https://api.open-meteo.com',
        )

    def test_other_http_failures_include_only_the_status(self) -> None:
        request = httpx.Request('GET', 'https://air-quality-api.open-meteo.com/v1/air-quality?hourly=us_aqi')
        response = httpx.Response(503, request=request)
        error = httpx.HTTPStatusError('long provider error', request=request, response=response)

        self.assertEqual(
            _weather_fetch_failure_message(error),
            '503: Service Unavailable — https://air-quality-api.open-meteo.com',
        )

    def test_network_failures_are_also_url_free(self) -> None:
        request = httpx.Request('GET', 'https://api.open-meteo.com/v1/forecast?latitude=39.5296')
        error = httpx.ConnectError('connection refused', request=request)

        self.assertEqual(
            _weather_fetch_failure_message(error),
            'Network error — https://api.open-meteo.com',
        )


if __name__ == '__main__':
    unittest.main()
