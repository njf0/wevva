"""Local tropical context and the compact global storm launcher."""

from __future__ import annotations

from rich.console import Group
from rich.markdown import Markdown
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Button, Static
from wevva_warnings import CanonicalTropicalSystem, TropicalSystem

from wevva.services.tropical import (
    NearbyTropicalSystem,
    canonical_sort_distance_km,
    center_distance_km,
    sort_canonical_tropical_systems,
)

_KILOMETRES_TO_MILES = 0.621371192237334


class NearbyTropicalSystemsLauncher(Container):
    """Small dashboard summary that launches the full tropical workspace."""

    MAX_SYSTEMS = 3
    DEFAULT_CSS = """
    NearbyTropicalSystemsLauncher {
        width: 100%;
        height: auto;
        padding: 1;
        border: round $secondary;
        border-title-color: $secondary;
        margin: 0;
    }

    #nearby-tropical-list {
        width: 100%;
        height: auto;
    }

    #open-tropical-systems {
        width: 100%;
        height: 3;
        margin: 1 0 0 0;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.border_title = 'Nearby Tropical Systems'

    def compose(self) -> ComposeResult:
        yield Static('', id='nearby-tropical-list')
        yield Button('t  Tropical Systems', id='open-tropical-systems')

    def update_systems(
        self,
        systems: list[CanonicalTropicalSystem],
        *,
        latitude: float | None,
        longitude: float | None,
        loaded: bool,
    ) -> None:
        rows: list[Text] = []
        ordered = sort_canonical_tropical_systems(systems, latitude, longitude)
        for canonical in ordered[: self.MAX_SYSTEMS]:
            observation = _nearest_observation(canonical, latitude, longitude)
            name = _canonical_name(canonical)
            classification = _classification_code(observation.classification if observation is not None else None)
            distance = (
                canonical_sort_distance_km(canonical, latitude, longitude)
                if latitude is not None and longitude is not None
                else None
            )
            line = Text(name)
            if classification:
                line.append(f'  {classification}', style='dim')
            if distance is not None:
                line.append(f'  {round(distance * _KILOMETRES_TO_MILES):,g} mi', style='dim')
            rows.append(line)
            if observation is not None:
                secondary = ' · '.join(value for value in (_clean(observation.movement), _clean(observation.max_wind)) if value)
                if secondary:
                    rows.append(Text(f'  {secondary}', style='dim'))
        if not rows:
            rows.append(Text('No active tropical systems' if loaded else 'Tropical systems unavailable', style='dim'))
        self.query_one('#nearby-tropical-list', Static).update(Group(*rows))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == 'open-tropical-systems':
            await self.app.open_tropical_systems_screen()


def _nearest_observation(
    system: CanonicalTropicalSystem,
    latitude: float | None,
    longitude: float | None,
) -> TropicalSystem | None:
    if not system.observations:
        return None
    if latitude is None or longitude is None:
        return system.observations[0]
    return min(
        system.observations,
        key=lambda observation: (
            center_distance_km(observation, latitude, longitude) is None,
            center_distance_km(observation, latitude, longitude) or float('inf'),
        ),
    )


def _classification_code(value: object) -> str:
    classification = _clean(value)
    return {
        'tropical depression': 'TD',
        'developing tropical depression': 'TD',
        'tropical storm': 'TS',
        'severe tropical storm': 'STS',
        'hurricane': 'HU',
        'typhoon': 'TY',
        'tropical cyclone': 'TC',
    }.get(classification.casefold(), classification)


def canonical_storm_key(system: CanonicalTropicalSystem) -> str:
    """Return a refresh-stable identity key without inferring storm identity."""
    name = _clean(system.name)
    if name:
        return f'name:{name.casefold()}'
    observations = tuple((item.source, item.id) for item in system.observations)
    return f'observations:{observations!r}'


def source_tab_label(system: TropicalSystem) -> str:
    """Build a concise deterministic label from the source identifier."""
    source = _clean(system.source)
    token = source.split('_', 1)[0] if source else ''
    return token.upper() or 'SOURCE'


def _canonical_name(system: CanonicalTropicalSystem) -> str:
    return _clean(system.name) or (_system_name(system.observations[0]) if system.observations else 'Tropical system')


def build_tropical_system_text(nearby: NearbyTropicalSystem, *, accent: str | None = None) -> Text:
    """Render no more than two lines of nearby-storm context for the panel."""
    system = nearby.system
    title = Text(_panel_headline(system), style=f'bold italic {accent}' if accent else 'bold italic')

    primary_facts: list[Text] = []
    if nearby.distance_km is not None:
        primary_facts.append(Text(f'{_format_miles(nearby.distance_km)} away'))
    if movement := _clean(system.movement):
        primary_facts.append(Text(f'Moving {movement}'))
    if basin := _clean(system.basin):
        primary_facts.append(Text(basin))
    if not primary_facts:
        return title

    result = Text()
    result.append_text(title)
    result.append('\n')
    for index, fact in enumerate(primary_facts):
        if index:
            result.append(' · ', style='dim')
        result.append_text(fact)
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


def build_tropical_system_details(
    nearby: NearbyTropicalSystem,
    theme: dict[str, str],
) -> Group:
    """Build a compact Markdown detail reader without displaying missing fields."""
    system = nearby.system
    accent = theme.get('text-accent')
    headline = _clean(system.headline) or _system_name(system)
    details = [Markdown(f'### {headline}')]

    leading_facts = []
    if name := _clean(system.name):
        leading_facts.append(f'- **Name:** {name}')
    if classification := _clean(system.classification):
        leading_facts.append(f'- **Classification:** {classification}')
    if nearby.distance_km is not None:
        leading_facts.append(
            f'- **Centre distance:** {_format_kilometres(nearby.distance_km)} ({_format_miles(nearby.distance_km)})'
        )
    if leading_facts:
        details.append(Markdown('\n'.join(leading_facts)))
    if system.center_lat is not None and system.center_lon is not None:
        centre = Text(' ● ')
        centre.append('Centre: ', style='bold')
        centre.append_text(build_tropical_coordinates_text(system.center_lat, system.center_lon, accent=accent))
        details.append(centre)
    trailing_facts = []
    if max_wind := _clean(system.max_wind):
        trailing_facts.append(f'- **Maximum wind:** {max_wind}')
    if movement := _clean(system.movement):
        trailing_facts.append(f'- **Movement:** {movement}')
    if pressure := _clean(system.min_pressure):
        trailing_facts.append(f'- **Minimum pressure:** {pressure}')
    if basin := _clean(system.basin):
        trailing_facts.append(f'- **Basin:** {basin}')
    if advisory_number := _clean(system.advisory_number):
        trailing_facts.append(f'- **Advisory:** {advisory_number}')
    if system.issued_at is not None:
        trailing_facts.append(f'- **Issued:** {_format_issued_at(system.issued_at)}')
    if source_name := _clean(getattr(system.source_info, 'name', None)):
        trailing_facts.append(f'- **Source:** {source_name}')
    if trailing_facts:
        details.append(Markdown('\n'.join(trailing_facts)))
    if url := _clean(system.url):
        details.extend((Text(''), Markdown(f'[View official source]({url})')))
    return Group(*details)


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


def _clean(value: object) -> str:
    return value.strip() if isinstance(value, str) else ''


__all__ = [
    'NearbyTropicalSystemsLauncher',
    'build_tropical_coordinates_text',
    'build_tropical_system_details',
    'build_tropical_system_text',
    'build_tropical_tab_label',
    'canonical_storm_key',
    'source_tab_label',
]
