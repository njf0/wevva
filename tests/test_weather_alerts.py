"""Focused warning-detail rendering checks."""

from __future__ import annotations

import unittest

from wevva.alerts import Alert
from wevva.widgets.weather_alerts import alert_markdown


class AlertMarkdownTests(unittest.TestCase):
    def test_instruction_keeps_indented_provider_list_items(self) -> None:
        alert = Alert(
            id='nz-storm',
            source='nz-metservice',
            event='Thunderstorm',
            headline='Severe thunderstorm warning',
            instruction=(
                'The National Emergency Management Agency advises that as storms approach you should:\n'
                '    - Take shelter, preferably indoors away from windows;\n'
                '    - Avoid sheltering under trees, if outside;\n'
                'During and after the storm, you should also:\n'
                '    - Beware of fallen trees and power lines;'
            ),
        )

        self.assertEqual(
            alert_markdown(alert),
            '### Severe thunderstorm warning\n\n'
            'The National Emergency Management Agency advises that as storms approach you should:\n\n'
            '- Take shelter, preferably indoors away from windows;\n'
            '- Avoid sheltering under trees, if outside;\n\n'
            'During and after the storm, you should also:\n\n'
            '- Beware of fallen trees and power lines;',
        )

    def test_existing_markdown_and_ordered_lists_are_preserved(self) -> None:
        alert = Alert(
            id='markdown',
            source='test',
            event='Rain',
            headline='Rain warning',
            description='Read the [official guidance](https://example.com).',
            instruction='  1. Stay indoors\r\n  2. Avoid flooded roads',
        )

        self.assertEqual(
            alert_markdown(alert),
            '### Rain warning\n\n'
            'Read the [official guidance](https://example.com).\n\n'
            '1. Stay indoors\n'
            '2. Avoid flooded roads',
        )

    def test_nws_labelled_bullet_continuations_stay_in_their_list_items(self) -> None:
        alert = Alert(
            id='nws-flood',
            source='nws',
            event='Flood',
            headline='Flood watch',
            instruction=(
                '* WHAT...Flash flooding caused by excessive rainfall continues to\n'
                'be possible.\n'
                '* WHERE...A portion of western Nevada, including the following\n'
                'areas, Greater Reno-Carson City-Minden Area.\n'
                '* WHEN...From Wednesday afternoon through Thursday evening.\n'
                '* ADDITIONAL DETAILS...\n'
                '- Heavy rain from thunderstorms primarily during the afternoon\n'
                'and evening hours Wednesday and Thursday.\n'
                '- http://www.weather.gov/safety/flood'
            ),
        )

        self.assertEqual(
            alert_markdown(alert),
            '### Flood watch\n\n'
            '- WHAT...Flash flooding caused by excessive rainfall continues to\n'
            '  be possible.\n'
            '- WHERE...A portion of western Nevada, including the following\n'
            '  areas, Greater Reno-Carson City-Minden Area.\n'
            '- WHEN...From Wednesday afternoon through Thursday evening.\n'
            '- ADDITIONAL DETAILS...\n'
            '  - Heavy rain from thunderstorms primarily during the afternoon\n'
            '    and evening hours Wednesday and Thursday.\n'
            '  - http://www.weather.gov/safety/flood',
        )


if __name__ == '__main__':
    unittest.main()
