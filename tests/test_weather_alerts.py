"""Focused warning-detail rendering checks."""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
import unittest

from wevva.alerts import Alert
from rich.console import Console

from wevva.widgets.weather_alerts import (
    WeatherAlertsPanel,
    _normalise_alert_text,
    alert_markdown,
    alert_renderable,
    alert_timing_renderable,
)


class AlertMarkdownTests(unittest.TestCase):
    def test_area_and_timing_form_one_detail_header(self) -> None:
        alert = Alert(
            id='timed-area',
            source='test',
            event='Storm Warning',
            headline='Damaging storms expected',
            area_names=[
                ' NORTH DISTRICT ',
                'North district',
                'River   Valley',
            ],
            onset=datetime(2030, 1, 1, 12, 0, tzinfo=UTC),
            expires=datetime(2030, 1, 1, 14, 0, tzinfo=UTC),
        )

        self.assertEqual(
            alert_markdown(alert),
            '### Damaging storms expected\n\n'
            'Affects: NORTH DISTRICT, River Valley',
        )
        console = Console(
            width=60,
            record=True,
            color_system=None,
            file=StringIO(),
        )
        console.print(alert_renderable(alert, include_timing=True))
        lines = console.export_text().splitlines()
        assert alert.onset is not None
        assert alert.expires is not None
        onset = alert.onset.astimezone().strftime('%H:%M %A')
        expires = alert.expires.astimezone().strftime('%H:%M %A')
        timing = alert_timing_renderable(alert)

        self.assertEqual(lines[0], 'Damaging storms expected')
        self.assertEqual(lines[1], '')
        self.assertEqual(lines[2], 'Affects: NORTH DISTRICT, River Valley')
        self.assertEqual(lines[3], '')
        self.assertEqual(lines[4].strip(), f'{onset} ··· {expires}')
        self.assertEqual(timing.justify, 'center')
        self.assertEqual(timing.style, 'markdown.code')

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
            'The National Emergency Management Agency advises that as storms approach you should:\n'
            '- Take shelter, preferably indoors away from windows;\n'
            '- Avoid sheltering under trees, if outside;\n'
            'During and after the storm, you should also:\n'
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
            '- WHAT...Flash flooding caused by excessive rainfall continues to be possible.\n'
            '- WHERE...A portion of western Nevada, including the following areas, '
            'Greater Reno-Carson City-Minden Area.\n'
            '- WHEN...From Wednesday afternoon through Thursday evening.\n'
            '- ADDITIONAL DETAILS...\n'
            '- Heavy rain from thunderstorms primarily during the afternoon and evening '
            'hours Wednesday and Thursday.\n'
            '- http://www.weather.gov/safety/flood',
        )

    def test_nws_bullet_hard_wraps_become_one_literal_list_item(self) -> None:
        source = (
            'POTENTIAL IMPACTS\n'
            '-----------------\n\n'
            '* WIND:\n'
            'Protect against life-threatening wind having possible extensive\n'
            'impacts across the Big Island. Potential impacts include:\n'
            '- Considerable roof damage to sturdy buildings, with some having\n'
            'window, door, and garage door failures leading to structural\n'
            'damage. Keep [doors] shut and retain *literal* _characters_.\n'
            '- Many large trees snapped or uprooted along with fences and\n'
            'roadway signs blown over.\n\n'
            'NEXT UPDATE\n'
            '-----------'
        )

        self.assertEqual(
            _normalise_alert_text(source),
            'POTENTIAL IMPACTS\n'
            '-----------------\n\n'
            '* WIND:\n'
            'Protect against life-threatening wind having possible extensive impacts '
            'across the Big Island. Potential impacts include:\n'
            '- Considerable roof damage to sturdy buildings, with some having window, '
            'door, and garage door failures leading to structural damage. Keep [doors] '
            'shut and retain *literal* _characters_.\n'
            '- Many large trees snapped or uprooted along with fences and roadway signs '
            'blown over.\n\n'
            'NEXT UPDATE\n'
            '-----------',
        )

        alert = Alert(
            id='nws-tropical',
            source='nws',
            event='Tropical Cyclone Local Statement',
            headline='Tropical Cyclone Local Statement',
            description=source,
        )
        console = Console(width=52, record=True, color_system=None, file=StringIO())
        console.print(alert_renderable(alert))
        rendered = console.export_text()

        self.assertIn('[doors]', rendered)
        self.assertIn('*literal* _characters_.', rendered)
        self.assertNotIn('having\n\nwindow', rendered)
        self.assertTrue(any(line.startswith('  some having') for line in rendered.splitlines()))
        self.assertTrue(any(line.startswith('  fences') for line in rendered.splitlines()))

    def test_instruction_content_is_rendered_in_italics(self) -> None:
        alert = Alert(
            id='instruction-style',
            source='test',
            event='Storm',
            headline='Storm warning',
            description='A description remains regular.',
            instruction='- Take shelter indoors.',
        )

        lines = Console(width=80).render_lines(alert_renderable(alert))
        instruction_segments = [
            segment
            for line in lines
            for segment in line
            if 'Take shelter indoors.' in segment.text
        ]

        self.assertEqual(len(instruction_segments), 1)
        self.assertTrue(instruction_segments[0].style.italic)

    def test_official_link_is_last_in_details_and_not_in_the_tab_preview(self) -> None:
        alert = Alert(
            id='official-link',
            source='test',
            event='Rain',
            headline='Rain warning',
            description='Heavy rain is expected.',
            url='https://example.com/warnings/rain',
        )

        self.assertEqual(
            alert_markdown(alert),
            '### Rain warning\n\nHeavy rain is expected.\n\n'
            '[View official warning](https://example.com/warnings/rain)',
        )
        self.assertNotIn('View official warning', WeatherAlertsPanel([]).build_timing_line(alert))


if __name__ == '__main__':
    unittest.main()
