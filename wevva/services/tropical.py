"""Independent nearby tropical-system retrieval and ordering helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from math import atan2, cos, isfinite, radians, sin, sqrt
import re
import unicodedata

from wevva_warnings import (
    TropicalSystem,
    WarningQueryProgress,
    get_tropical_systems,
    get_tropical_systems_near,
    match_tropical_systems_to_point,
)


TROPICAL_SYSTEMS_RADIUS_KM = 250.0
"""Distance within which a tropical-system report is considered nearby."""

_EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True, slots=True)
class NearbyTropicalSystem:
    """A provider report paired with its locally calculated centre distance."""

    system: TropicalSystem
    distance_km: float | None


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance between two WGS84 coordinates."""
    phi1 = radians(lat1)
    phi2 = radians(lat2)
    delta_phi = radians(lat2 - lat1)
    delta_lambda = radians(lon2 - lon1)
    a = sin(delta_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(delta_lambda / 2) ** 2
    return _EARTH_RADIUS_KM * 2 * atan2(sqrt(a), sqrt(1 - a))


def center_distance_km(system: TropicalSystem, lat: float, lon: float) -> float | None:
    """Calculate a local centre distance when the provider supplied a centre."""
    center_lat = system.center_lat
    center_lon = system.center_lon
    if center_lat is None or center_lon is None:
        return None
    try:
        finite_coordinates = all(isfinite(value) for value in (center_lat, center_lon, lat, lon))
    except TypeError:
        return None
    if not finite_coordinates:
        return None
    return haversine_distance_km(lat, lon, center_lat, center_lon)


def get_nearby_tropical_systems(
    lat: float,
    lon: float,
    *,
    selected_country_code: str | None,
) -> list[NearbyTropicalSystem]:
    """Use the simple one-call tropical query without the application cache.

    Matched reports are normalised so one official report represents a named
    system: a local issuer wins, otherwise the newest report is used.
    """
    try:
        systems = get_tropical_systems_near(lat, lon, radius_km=TROPICAL_SYSTEMS_RADIUS_KM)
    except Exception:
        # A blank tropical section is deliberately inconclusive: provider
        # failures and an empty response both must not claim no storms exist.
        return []

    return _nearby_systems_from_matched(systems, lat, lon, selected_country_code)


def get_tropical_system_candidates() -> tuple[list[TropicalSystem], bool]:
    """Fetch raw source-wide tropical reports for the session-only cache.

    The returned reports are deliberately not associated with a country or a
    location.  A caller must match them again for every selected point.
    """
    try:
        return get_tropical_systems(), True
    except Exception:
        # An incomplete global source refresh is inconclusive.  Do not cache
        # this empty fallback or use it as evidence of no tropical activity.
        return [], False


def nearby_tropical_systems_from_candidates(
    systems: Iterable[TropicalSystem],
    lat: float,
    lon: float,
    *,
    selected_country_code: str | None,
    progress: WarningQueryProgress | None = None,
) -> list[NearbyTropicalSystem]:
    """Locally match raw reports and add location-specific distances/order.

    When requested, report matching progress for each cached raw report.  The
    global retrieval remains cacheable while this location-specific work can
    run in a worker thread.
    """
    candidates = list(systems)
    _report_progress(progress, 'tropical_check_total', total=len(candidates))
    try:
        matched = _match_candidates_with_progress(candidates, lat, lon, progress)
    except Exception:
        return []
    return _nearby_systems_from_matched(matched, lat, lon, selected_country_code)


def _match_candidates_with_progress(
    candidates: list[TropicalSystem],
    lat: float,
    lon: float,
    progress: WarningQueryProgress | None,
) -> list[TropicalSystem]:
    """Match one cached report at a time so progress tracks real local work."""
    matched: list[TropicalSystem] = []
    total = len(candidates)
    for completed, candidate in enumerate(candidates, start=1):
        candidate_matches = match_tropical_systems_to_point(
            [candidate],
            lat=lat,
            lon=lon,
            radius_km=TROPICAL_SYSTEMS_RADIUS_KM,
        )
        matched.extend(candidate_matches)
        _report_progress(progress, 'tropical_checked', completed=completed, total=total)
    return matched


def _report_progress(
    progress: WarningQueryProgress | None,
    event: str,
    **payload: object,
) -> None:
    """Send advisory UI progress without allowing it to affect matching."""
    if progress is None:
        return
    try:
        progress(event, payload)
    except Exception:
        pass


def _nearby_systems_from_matched(
    systems: Iterable[TropicalSystem],
    lat: float,
    lon: float,
    selected_country_code: str | None,
) -> list[NearbyTropicalSystem]:
    """Normalise matched reports, then add local display-specific values."""
    selected_country = (selected_country_code or '').strip().upper()
    nearby = [
        NearbyTropicalSystem(system=system, distance_km=center_distance_km(system, lat, lon)) for system in systems
    ]
    return _normalise_nearby_systems(nearby, selected_country)


def _normalise_nearby_systems(
    nearby: list[NearbyTropicalSystem],
    selected_country_code: str,
) -> list[NearbyTropicalSystem]:
    """Choose one useful report per named storm in a single normalisation pass.

    Source/ID repeats are reduced first. For a named storm, a report issued by
    the selected country's operational centre is preferred; otherwise the
    most recently issued matched report wins. Reports without a usable name
    cannot be safely grouped, so they remain distinct after source/ID
    deduplication.
    """
    source_unique: dict[tuple[str, str], NearbyTropicalSystem] = {}
    for item in nearby:
        key = (item.system.source, item.system.id)
        existing = source_unique.get(key)
        if existing is None or _issued_timestamp(item) > _issued_timestamp(existing):
            source_unique[key] = item

    named_groups: dict[str, list[NearbyTropicalSystem]] = {}
    normalised: list[NearbyTropicalSystem] = []
    for item in source_unique.values():
        name = _storm_name_key(item.system)
        if not name:
            normalised.append(item)
            continue
        named_groups.setdefault(name, []).append(item)

    for reports in named_groups.values():
        local_reports = [
            item for item in reports if _issuer_country_code(item.system) == selected_country_code
        ]
        normalised.append(_newest_report(local_reports or reports, selected_country_code))

    normalised.sort(key=lambda item: _nearby_system_sort_key(item, selected_country_code))
    return normalised


def _newest_report(
    reports: list[NearbyTropicalSystem],
    selected_country_code: str,
) -> NearbyTropicalSystem:
    """Return the newest report, retaining the display order as a stable tie-breaker."""
    ordered_reports = sorted(reports, key=lambda item: _nearby_system_sort_key(item, selected_country_code))
    return max(ordered_reports, key=_issued_timestamp)


def _issued_timestamp(nearby: NearbyTropicalSystem) -> float:
    """Return an orderable report timestamp, treating missing times as oldest."""
    issued_at = nearby.system.issued_at
    if not isinstance(issued_at, datetime):
        return float('-inf')
    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=UTC)
    return issued_at.timestamp()


def _issuer_country_code(system: TropicalSystem) -> str:
    """Return a normalised optional operational issuing-centre country code."""
    issuer_country = getattr(system.source_info, 'issuer_country_code', None)
    return issuer_country.strip().upper() if isinstance(issuer_country, str) else ''


def _storm_name_key(system: TropicalSystem) -> str:
    """Return a conservative cross-provider name key, never inferred from a headline."""
    name = system.name
    if not isinstance(name, str) or not name.strip():
        return ''
    normalised = unicodedata.normalize('NFKC', name).casefold()
    return re.sub(r'[^\w]+', '', normalised, flags=re.UNICODE)


async def get_nearby_tropical_systems_async(
    lat: float,
    lon: float,
    *,
    selected_country_code: str | None,
) -> list[NearbyTropicalSystem]:
    """Run the blocking tropical-provider query outside the Textual event loop."""
    return await asyncio.to_thread(
        get_nearby_tropical_systems,
        lat,
        lon,
        selected_country_code=selected_country_code,
    )


async def get_tropical_system_candidates_async() -> tuple[list[TropicalSystem], bool]:
    """Run the cacheable raw tropical-source fetch outside the TUI loop."""
    return await asyncio.to_thread(get_tropical_system_candidates)


def _nearby_system_sort_key(
    nearby: NearbyTropicalSystem,
    selected_country_code: str,
) -> tuple[int, float, str, str, str]:
    system = nearby.system
    same_issuer_country = bool(selected_country_code) and _issuer_country_code(system) == selected_country_code
    distance = nearby.distance_km if nearby.distance_km is not None else float('inf')
    name = (system.name or system.headline or system.id or '').casefold()
    return (0 if same_issuer_country else 1, distance, name, system.source, system.id)


__all__ = [
    'NearbyTropicalSystem',
    'TROPICAL_SYSTEMS_RADIUS_KM',
    'center_distance_km',
    'get_tropical_system_candidates',
    'get_tropical_system_candidates_async',
    'get_nearby_tropical_systems',
    'get_nearby_tropical_systems_async',
    'haversine_distance_km',
    'nearby_tropical_systems_from_candidates',
]
