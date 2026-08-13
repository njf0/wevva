"""Tabbed, contextual display for nearby tropical-system reports."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import DataTable

from wevva.services.tropical import NearbyTropicalSystem


_KILOMETRES_TO_MILES = 0.621371192237334


def build_tropical_system_text(nearby: NearbyTropicalSystem, *, accent: str | None = None) -> Text:
    """Render no more than two lines of nearby-storm context for the panel."""
    system = nearby.system
    title = Text(_panel_headline(system), style=f'bold italic {accent}' if accent else 'bold italic')

    primary_facts = []
    if nearby.distance_km is not None:
        primary_facts.append(f'Centre {_format_miles(nearby.distance_km)} away')
    if max_wind := _clean(system.max_wind):
        primary_facts.append(f'{max_wind} winds')
    if pressure := _clean(system.min_pressure):
        primary_facts.append(pressure)
    if movement := _clean(system.movement):
        primary_facts.append(f'Moving {movement}')
    elif basin := _clean(system.basin):
        primary_facts.append(basin)
    if not primary_facts:
        return title

    result = Text()
    result.append_text(title)
    result.append('\n')
    result.append(' · '.join(primary_facts), style='dim')
    return result


def build_tropical_tab_label(nearby: NearbyTropicalSystem, *, accent: str | None = None) -> Text:
    """Build a classification-first tab label, e.g. ``Typhoon DOLPHIN``."""
    system = nearby.system
    classification = _clean(system.classification)
    name = _system_name(system)
    label = Text()
    if classification:
        label.append(classification, style=f'bold {accent}' if accent else 'bold')
        if name:
            label.append(' ')
    label.append(name)
    return label


class TropicalSystemDetailsTable(DataTable):
    """Compact linked field/value table for one selected tropical report."""

    DEFAULT_CSS = """
    TropicalSystemDetailsTable {
        width: 100%;
        height: auto;
        padding: 0 1;
        background: $background;
    }
    """

    def __init__(self, *, id: str = 'tropical-system-details') -> None:
        super().__init__(show_header=False, cursor_type='none', id=id, cell_padding=0)
        self.add_column('Field', key='field', width=16)
        self.add_column('Value', key='value', width=34)

    def update_system(self, nearby: NearbyTropicalSystem) -> None:
        """Replace rows with the available details for one tropical report."""
        self.clear()
        for index, (label, value) in enumerate(tropical_system_detail_rows(nearby, self.app.theme_variables)):
            self.add_row(Text(label, style='bold dim'), value, key=f'tropical-detail-{index}')
        self.refresh()


def tropical_system_detail_rows(
    nearby: NearbyTropicalSystem,
    theme: dict[str, str],
) -> list[tuple[str, Text]]:
    """Build ordered, styled table rows without displaying missing fields."""
    system = nearby.system
    accent = theme.get('text-accent')
    primary_style = f'bold {accent}' if accent else 'bold'
    rows: list[tuple[str, Text]] = [('Name', Text(_system_name(system), style=primary_style))]
    if classification := _clean(system.classification):
        rows.append(('Classification', Text(classification, style=primary_style)))
    if nearby.distance_km is not None:
        rows.append(('Centre distance', Text(f'{_format_kilometres(nearby.distance_km)} ({_format_miles(nearby.distance_km)})')))
    if system.center_lat is not None and system.center_lon is not None:
        rows.append(('Centre', build_tropical_coordinates_text(system.center_lat, system.center_lon, accent=accent)))
    if max_wind := _clean(system.max_wind):
        rows.append(('Maximum wind', Text(max_wind, style=primary_style)))
    if movement := _clean(system.movement):
        rows.append(('Movement', Text(movement)))
    if pressure := _clean(system.min_pressure):
        rows.append(('Minimum pressure', Text(pressure)))
    if basin := _clean(system.basin):
        rows.append(('Basin', Text(basin)))
    if advisory_number := _clean(system.advisory_number):
        rows.append(('Advisory', Text(advisory_number)))
    if system.issued_at is not None:
        rows.append(('Issued', Text(_format_issued_at(system.issued_at))))
    if source_name := _clean(getattr(system.source_info, 'name', None)):
        rows.append(('Source', Text(source_name)))
    if url := _clean(system.url):
        rows.append(('Official source', _linked_text('View official source', url, accent=accent)))
    return rows


def build_tropical_coordinates_text(latitude: float, longitude: float, *, accent: str | None = None) -> Text:
    """Return linked coordinates using the same OpenStreetMap form as location data."""
    latitude_label = _format_latitude(latitude)
    longitude_label = _format_longitude(longitude)
    url = f'https://www.openstreetmap.org/#map=12/{latitude:.5f}/{longitude:.5f}'
    style = f'italic {accent}' if accent else 'italic'
    return Text.from_markup(
        f'[link={url}][{style}]{latitude_label}[/], [{style}]{longitude_label}[/][/]',
    )


def _system_name(system) -> str:
    return _clean(system.name) or _clean(system.headline) or _clean(system.id) or 'Tropical system'


def _panel_headline(system) -> str:
    """Use the provider headline first, matching the ordinary alert panel."""
    if headline := _clean(system.headline):
        return headline
    name = _system_name(system)
    classification = _clean(system.classification)
    return f'{name} — {classification}' if classification else name


def _format_kilometres(distance_km: float) -> str:
    return f'{distance_km:.1f} km'


def _format_miles(distance_km: float) -> str:
    return f'{round(distance_km * _KILOMETRES_TO_MILES):g} mi'


def _format_latitude(latitude: float) -> str:
    return f'{abs(latitude):.2f}° {"N" if latitude >= 0 else "S"}'


def _format_longitude(longitude: float) -> str:
    return f'{abs(longitude):.2f}° {"E" if longitude >= 0 else "W"}'


def _format_issued_at(issued_at) -> str:
    timezone = issued_at.tzname() or issued_at.strftime('%Z')
    timestamp = f'{issued_at.day} {issued_at.strftime("%b %Y, %H:%M")}'
    return f'{timestamp} {timezone}'.rstrip()


def _linked_text(label: str, url: str, *, accent: str | None = None) -> Text:
    text = Text(label, style=f'italic {accent}' if accent else 'italic')
    text.stylize(f'underline link {url}')
    return text


def _clean(value: object) -> str:
    return value.strip() if isinstance(value, str) else ''


__all__ = [
    'TropicalSystemDetailsTable',
    'build_tropical_coordinates_text',
    'build_tropical_system_text',
    'build_tropical_tab_label',
    'tropical_system_detail_rows',
]
