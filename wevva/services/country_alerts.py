"""Country-level alert discovery for the dedicated alerts centre."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from time import monotonic
from typing import Final

from wevva_warnings import (
    Alert,
    WarningQueryProgress,
    deduplicate_alerts,
    get_alerts_for_country,
    list_sources,
)

from wevva.services.alerts import normalize_country_code
from wevva.utils.country_codes import get_country_name_by_alpha2


COUNTRY_ALERT_CACHE_TTL_SECONDS = 15 * 60
"""Lifetime of one successful country result in the session-only cache."""

_DEFAULT_OBSERVATION_PATH: Final[object] = object()


@dataclass(frozen=True, slots=True)
class SupportedAlertCountry:
    """One country advertised by the warning source registry."""

    code: str
    name: str


@dataclass(frozen=True, slots=True)
class _CountryAlertCacheEntry:
    alerts: tuple[Alert, ...]
    new_alert_identities: frozenset[tuple[str, str]]
    loaded_at: float


class _CountryAlertObservations:
    """Persist the most recent successful alert identities per country."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._snapshots = self._load()

    def observe(
        self,
        country_code: str,
        warning_language: str,
        alerts: Iterable[Alert],
    ) -> frozenset[tuple[str, str]]:
        key = _observation_key(country_code, warning_language)
        current = frozenset(country_alert_identity(alert) for alert in alerts)
        previous = self._snapshots.get(key)
        newly_observed = frozenset() if previous is None else current - previous
        self._snapshots[key] = current
        self._save()
        return newly_observed

    def _load(self) -> dict[str, frozenset[tuple[str, str]]]:
        if self.path is None:
            return {}
        try:
            raw = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
        snapshots = raw.get('snapshots') if isinstance(raw, dict) else None
        if not isinstance(snapshots, dict):
            return {}
        normalized: dict[str, frozenset[tuple[str, str]]] = {}
        for key, identities in snapshots.items():
            if not isinstance(key, str) or not isinstance(identities, list):
                continue
            valid_identities = {
                (identity[0], identity[1])
                for identity in identities
                if isinstance(identity, list)
                and len(identity) == 2
                and all(isinstance(value, str) for value in identity)
            }
            normalized[key] = frozenset(valid_identities)
        return normalized

    def _save(self) -> None:
        if self.path is None:
            return
        payload = {
            'version': 1,
            'snapshots': {
                key: [list(identity) for identity in sorted(identities)]
                for key, identities in sorted(self._snapshots.items())
            },
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.path.with_suffix(f'{self.path.suffix}.tmp')
            temporary_path.write_text(json.dumps(payload, indent=2) + '\n')
            temporary_path.replace(self.path)
        except OSError:
            # Observation state is an enhancement; never fail alert loading
            # because its small local snapshot could not be persisted.
            pass


def get_country_alert_observations_path() -> Path:
    """Return the per-user country-alert observation snapshot path."""

    return Path.home() / '.config' / 'wevva' / 'country-alert-observations.json'


def _observation_key(country_code: str, warning_language: str) -> str:
    return f'{country_code}:{warning_language}'


def list_supported_alert_countries() -> list[SupportedAlertCountry]:
    """Return named country choices from the authoritative source registry.

    The warning library routes country queries only through sources with an
    explicit primary or additional country code. Mirroring that public source
    contract keeps Wevva from maintaining a second provider registry.
    """

    country_codes: set[str] = set()
    for source in list_sources(kind='alert'):
        if source.kind != 'alert':
            continue
        if source.country_code:
            country_codes.add(source.country_code.strip().upper())
        country_codes.update(
            code.strip().upper()
            for code in source.additional_country_codes
            if code.strip()
        )

    countries = [
        SupportedAlertCountry(code=code, name=name)
        for code in country_codes
        if (name := get_country_name_by_alpha2(code)) is not None
    ]
    return sorted(countries, key=lambda country: (country.name.casefold(), country.code))


def country_alert_default_filter(country_code: str, country_name: str) -> str:
    """Return a useful initial filter for a territory using a shared feed.

    Some provider feeds cover a primary country and several territories.  A
    country-specific filter keeps those territory views useful without
    encoding any provider names here.  Countries with their own primary feed
    remain unfiltered, even if another source also lists them as additional.
    """

    normalized_country = normalize_country_code(country_code)
    if normalized_country is None:
        return ''
    has_primary_source = False
    has_shared_source = False
    for source in list_sources(kind='alert'):
        if source.kind != 'alert':
            continue
        if normalize_country_code(source.country_code) == normalized_country:
            has_primary_source = True
        if normalized_country in {
            code
            for value in source.additional_country_codes
            if (code := normalize_country_code(value)) is not None
        }:
            has_shared_source = True
    if has_shared_source and not has_primary_source:
        return country_name.strip()
    return ''


def country_alert_identity(alert: Alert) -> tuple[str, str]:
    """Return the warning library's stable identity for an alert."""

    return alert.source, alert.id


def sort_country_alerts(alerts: Iterable[Alert]) -> list[Alert]:
    """Deduplicate and order country alerts for navigation."""

    return sorted(deduplicate_alerts(alerts), key=_country_alert_sort_key)


def _country_alert_sort_key(alert: Alert) -> tuple[object, ...]:
    severity = (alert.severity or '').strip().casefold()
    severity_rank = {
        'extreme': 0,
        'red': 0,
        'severe': 1,
        'orange': 1,
        'amber': 1,
        'moderate': 2,
        'yellow': 2,
        'minor': 3,
        'green': 3,
    }.get(severity, 4)
    area = ' | '.join(name.strip() for name in alert.area_names if name.strip())
    return (
        severity_rank,
        _datetime_sort_value(alert.expires),
        _datetime_sort_value(alert.onset),
        _condition_sort_name(alert).casefold(),
        area.casefold(),
        alert.source.casefold(),
        alert.id,
    )


def _condition_sort_name(alert: Alert) -> str:
    """Return a stable normalized condition without presentation dependencies."""

    condition = (alert.event or alert.headline or 'Weather Alert').replace('_', ' ')
    return ' '.join(condition.split())


def _datetime_sort_value(value: datetime | None) -> float:
    if value is None:
        return float('inf')
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()


def _fetch_country_alerts(
    country_code: str,
    warning_language: str,
    progress: WarningQueryProgress | None,
) -> list[Alert]:
    lang = 'en' if warning_language == 'en' else None
    alerts = get_alerts_for_country(
        country_code,
        lang=lang,
        active_only=True,
        progress=progress,
    )
    return sort_country_alerts(alerts)


class CountryAlertsService:
    """Own the country cache and latest successful observation snapshots."""

    def __init__(
        self,
        *,
        ttl_seconds: float = COUNTRY_ALERT_CACHE_TTL_SECONDS,
        clock: Callable[[], float] = monotonic,
        observation_path: Path | None | object = _DEFAULT_OBSERVATION_PATH,
    ) -> None:
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self._clock = clock
        self._cache: dict[tuple[str, str], _CountryAlertCacheEntry] = {}
        resolved_observation_path = (
            get_country_alert_observations_path()
            if observation_path is _DEFAULT_OBSERVATION_PATH
            else observation_path
        )
        if resolved_observation_path is not None and not isinstance(
            resolved_observation_path,
            Path,
        ):
            resolved_observation_path = Path(resolved_observation_path)
        self._observations = _CountryAlertObservations(resolved_observation_path)
        self.last_country_code: str | None = None

    async def get_alerts(
        self,
        country_code: str,
        *,
        warning_language: str = 'auto',
        progress: WarningQueryProgress | None = None,
        refresh: bool = False,
    ) -> list[Alert]:
        """Return active alerts, using the isolated country cache when fresh."""

        normalized_country = normalize_country_code(country_code)
        if normalized_country is None:
            raise ValueError(f'Invalid alert country code: {country_code!r}')
        language = 'en' if warning_language == 'en' else 'auto'
        cache_key = normalized_country, language
        cached = self._cache.get(cache_key)
        now = self._clock()
        if (
            not refresh
            and cached is not None
            and now - cached.loaded_at < self.ttl_seconds
        ):
            self.last_country_code = normalized_country
            return list(cached.alerts)

        alerts = await asyncio.to_thread(
            _fetch_country_alerts,
            normalized_country,
            language,
            progress,
        )
        newly_observed = self._observations.observe(
            normalized_country,
            language,
            alerts,
        )
        self._cache[cache_key] = _CountryAlertCacheEntry(
            alerts=tuple(alerts),
            new_alert_identities=newly_observed,
            loaded_at=self._clock(),
        )
        self.last_country_code = normalized_country
        return list(alerts)

    def new_alert_identities(
        self,
        country_code: str,
        *,
        warning_language: str = 'auto',
    ) -> frozenset[tuple[str, str]]:
        """Return identities newly observed by the latest successful fetch."""

        normalized_country = normalize_country_code(country_code)
        if normalized_country is None:
            return frozenset()
        language = 'en' if warning_language == 'en' else 'auto'
        cached = self._cache.get((normalized_country, language))
        return cached.new_alert_identities if cached is not None else frozenset()

    def invalidate(self, country_code: str | None = None) -> None:
        """Discard one country's cached languages, or the complete cache."""

        if country_code is None:
            self._cache.clear()
            return
        normalized_country = normalize_country_code(country_code)
        if normalized_country is None:
            return
        self._cache = {
            key: entry
            for key, entry in self._cache.items()
            if key[0] != normalized_country
        }


__all__ = [
    'COUNTRY_ALERT_CACHE_TTL_SECONDS',
    'CountryAlertsService',
    'SupportedAlertCountry',
    'country_alert_default_filter',
    'country_alert_identity',
    'get_country_alert_observations_path',
    'list_supported_alert_countries',
    'sort_country_alerts',
]
