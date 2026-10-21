"""Country-level alert discovery for the dedicated alerts centre."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Final

from wevva_warnings import (
    Alert,
    WarningQueryProgress,
    deduplicate_alerts,
    get_alerts_for_country,
    list_sources,
)

from wevva.services.alerts import normalize_country_code
from wevva.services.warning_cache import WarningCache, WarningCacheProduct
from wevva.utils.country_codes import get_country_name_by_alpha2


COUNTRY_ALERT_CACHE_TTL_SECONDS = 15 * 60
"""Fresh lifetime of one successful country catalogue."""

COUNTRY_ALERT_CACHE_STALE_GRACE_SECONDS = 6 * 60 * 60
"""Additional lifetime in which a catalogue may be shown provisionally."""

_MAX_OBSERVATION_JOURNAL_ENTRIES = 4096

_DEFAULT_OBSERVATION_PATH: Final[object] = object()


@dataclass(frozen=True, slots=True)
class SupportedAlertCountry:
    """One country advertised by the warning source registry."""

    code: str
    name: str


@dataclass(frozen=True, slots=True)
class CountryAlertsCacheHit:
    """A usable cached catalogue and whether it needs immediate refresh."""

    alerts: tuple[Alert, ...]
    new_alert_identities: frozenset[tuple[str, str]]
    provisional: bool
    fetched_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AlertObservation:
    """Local first/last observation times for one catalogue identity."""

    country_code: str
    warning_language: str
    source: str
    alert_id: str
    first_observed: datetime
    last_observed: datetime


class _CountryAlertObservations:
    """Persist latest snapshots and a bounded first-observed journal."""

    def __init__(
        self,
        path: Path | None,
        clock: Callable[[], datetime],
    ) -> None:
        self.path = path
        self._clock = clock
        self._snapshots: dict[str, frozenset[tuple[str, str]]] = {}
        self._journal: dict[
            tuple[str, str, str, str],
            tuple[datetime, datetime],
        ] = {}
        self._load()

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
        observed_at = _as_utc(self._clock())
        for source, alert_id in current:
            journal_key = country_code, warning_language, source, alert_id
            first_observed, _ = self._journal.get(
                journal_key,
                (observed_at, observed_at),
            )
            self._journal[journal_key] = first_observed, observed_at
        self._prune_journal()
        self._save()
        return newly_observed

    def journal(self) -> tuple[AlertObservation, ...]:
        return tuple(
            AlertObservation(*key, first_observed, last_observed)
            for key, (first_observed, last_observed) in sorted(
                self._journal.items(),
                key=lambda item: (item[1][0], item[0]),
                reverse=True,
            )
        )

    def _load(self) -> None:
        if self.path is None:
            return
        try:
            raw = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return
        snapshots = raw.get('snapshots') if isinstance(raw, dict) else None
        if isinstance(snapshots, dict):
            for key, identities in snapshots.items():
                if isinstance(key, str) and isinstance(identities, list):
                    self._snapshots[key] = frozenset(
                        (identity[0], identity[1])
                        for identity in identities
                        if isinstance(identity, list)
                        and len(identity) == 2
                        and all(isinstance(value, str) for value in identity)
                    )
        journal = raw.get('journal') if isinstance(raw, dict) else None
        if not isinstance(journal, list):
            return
        for observation in journal:
            if not isinstance(observation, dict):
                continue
            values = tuple(
                observation.get(name)
                for name in ('country_code', 'warning_language', 'source', 'alert_id')
            )
            try:
                first = _parse_datetime(observation.get('first_observed'))
                last = _parse_datetime(observation.get('last_observed'))
            except ValueError:
                continue
            if all(isinstance(value, str) for value in values):
                self._journal[values] = first, last  # type: ignore[index]
        self._prune_journal()

    def _prune_journal(self) -> None:
        """Prefer identities still present in a retained country snapshot."""

        current = {
            (*key.split(':', 1), source, alert_id)
            for key, identities in self._snapshots.items()
            if ':' in key
            for source, alert_id in identities
        }
        ordered = sorted(
            self._journal.items(),
            key=lambda item: (
                item[0] in current,
                item[1][1],
                item[0],
            ),
            reverse=True,
        )
        self._journal = dict(ordered[:_MAX_OBSERVATION_JOURNAL_ENTRIES])

    def _save(self) -> None:
        if self.path is None:
            return
        payload = {
            'version': 2,
            'snapshots': {
                key: [list(identity) for identity in sorted(identities)]
                for key, identities in sorted(self._snapshots.items())
            },
            'journal': [
                {
                    'country_code': key[0],
                    'warning_language': key[1],
                    'source': key[2],
                    'alert_id': key[3],
                    'first_observed': first.isoformat(),
                    'last_observed': last.isoformat(),
                }
                for key, (first, last) in self._journal.items()
            ],
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


def country_alert_search_text(alert: Alert) -> str:
    """Return normalized provider-neutral text used for local alert matching."""

    source_name = getattr(alert.source_info, 'name', None) or ''
    condition = _concise_alert_condition(alert)
    fields = (
        condition,
        alert.event,
        alert.headline,
        *alert.area_names,
        source_name,
        alert.source,
        alert.urgency,
        alert.certainty,
    )
    return ' '.join(
        ' '.join(str(value).casefold().split())
        for value in fields
        if value
    )


def _concise_alert_condition(alert: Alert) -> str:
    words = (
        (alert.event or alert.headline or 'Weather Alert')
        .replace('_', ' ')
        .split()
    )
    prefixes = {
        'extreme',
        'severe',
        'moderate',
        'minor',
        'red',
        'orange',
        'amber',
        'yellow',
        'green',
    }
    while words and words[0].casefold().rstrip(':') in prefixes:
        words.pop(0)
    condition = ' '.join(words).strip()
    return (
        condition[:-8].strip()
        if condition.casefold().endswith(' warning')
        else condition
    )


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


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _parse_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError('Expected an ISO datetime')
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('Expected a timezone')
    return parsed.astimezone(UTC)


def _normalized_request(
    country_code: str,
    warning_language: str,
) -> tuple[str, str]:
    normalized_country = normalize_country_code(country_code)
    if normalized_country is None:
        raise ValueError(f'Invalid alert country code: {country_code!r}')
    return normalized_country, 'en' if warning_language == 'en' else 'auto'


def _filter_unexpired(
    alerts: Iterable[Alert],
    now: datetime,
) -> list[Alert]:
    now = _as_utc(now)
    return [
        alert
        for alert in alerts
        if alert.expires is None or _as_utc(alert.expires) >= now
    ]


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
    """Fetch country catalogues through the shared persistent warning cache."""

    def __init__(
        self,
        *,
        ttl_seconds: float = COUNTRY_ALERT_CACHE_TTL_SECONDS,
        stale_grace_seconds: float = COUNTRY_ALERT_CACHE_STALE_GRACE_SECONDS,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        cache: WarningCache | None = None,
        observation_path: Path | None | object = _DEFAULT_OBSERVATION_PATH,
    ) -> None:
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self.stale_grace_seconds = max(0.0, float(stale_grace_seconds))
        self._wall_clock = wall_clock
        self.cache = cache or WarningCache(clock=wall_clock)
        self._new_alert_identities: dict[
            tuple[str, str],
            frozenset[tuple[str, str]],
        ] = {}
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
        self._observations = _CountryAlertObservations(
            resolved_observation_path,
            wall_clock,
        )
        self._refresh_tasks: dict[
            tuple[str, str],
            asyncio.Task[list[Alert]],
        ] = {}
        self.last_country_code: str | None = None

    async def get_cached_alerts(
        self,
        country_code: str,
        *,
        warning_language: str = 'auto',
    ) -> CountryAlertsCacheHit | None:
        """Return a fresh or provisional catalogue without provider work."""

        normalized_country, language = _normalized_request(
            country_code,
            warning_language,
        )
        entry = await self.cache.load(
            WarningCacheProduct.COUNTRY_CATALOGUE,
            normalized_country,
            language,
        )
        if entry is None:
            return None
        age = max(
            0.0,
            (_as_utc(self._wall_clock()) - entry.fetched_at).total_seconds(),
        )
        if age >= self.ttl_seconds + self.stale_grace_seconds:
            return None
        identities = entry.new_alert_identities
        self._new_alert_identities[(normalized_country, language)] = identities
        self.last_country_code = normalized_country
        return CountryAlertsCacheHit(
            alerts=tuple(_filter_unexpired(entry.alerts, self._wall_clock())),
            new_alert_identities=identities,
            provisional=age >= self.ttl_seconds,
            fetched_at=entry.fetched_at,
        )

    async def get_retained_alerts(
        self,
        country_code: str,
        *,
        warning_language: str = 'auto',
    ) -> CountryAlertsCacheHit | None:
        """Return any retained complete catalogue for warm bulletin startup."""

        normalized_country, language = _normalized_request(
            country_code,
            warning_language,
        )
        entry = await self.cache.load(
            WarningCacheProduct.COUNTRY_CATALOGUE,
            normalized_country,
            language,
        )
        if entry is None:
            return None
        self._new_alert_identities[(normalized_country, language)] = (
            entry.new_alert_identities
        )
        return CountryAlertsCacheHit(
            alerts=tuple(_filter_unexpired(entry.alerts, self._wall_clock())),
            new_alert_identities=entry.new_alert_identities,
            provisional=True,
            fetched_at=entry.fetched_at,
        )

    async def refresh_alerts(
        self,
        country_code: str,
        *,
        warning_language: str = 'auto',
        progress: WarningQueryProgress | None = None,
    ) -> list[Alert]:
        """Fetch, observe, and persist one complete provider catalogue."""

        key = _normalized_request(
            country_code,
            warning_language,
        )
        task = self._refresh_tasks.get(key)
        if task is None:
            task = asyncio.create_task(
                self._refresh_and_store(*key, progress=progress)
            )
            self._refresh_tasks[key] = task
            task.add_done_callback(
                lambda completed, refresh_key=key: self._discard_refresh_task(
                    refresh_key,
                    completed,
                )
            )
        return list(await asyncio.shield(task))

    async def _refresh_and_store(
        self,
        normalized_country: str,
        language: str,
        *,
        progress: WarningQueryProgress | None,
    ) -> list[Alert]:
        """Perform the single provider request for a normalized key."""

        alerts = await asyncio.to_thread(
            _fetch_country_alerts,
            normalized_country,
            language,
            progress,
        )
        fetched_at = _as_utc(self._wall_clock())
        newly_observed = self._observations.observe(
            normalized_country,
            language,
            alerts,
        )
        self._new_alert_identities[(normalized_country, language)] = newly_observed
        await self.cache.store(
            WarningCacheProduct.COUNTRY_CATALOGUE,
            normalized_country,
            language,
            alerts,
            fetched_at=fetched_at,
            new_alert_identities=newly_observed,
        )
        self.last_country_code = normalized_country
        return list(alerts)

    def _discard_refresh_task(
        self,
        key: tuple[str, str],
        task: asyncio.Task[list[Alert]],
    ) -> None:
        if self._refresh_tasks.get(key) is task:
            self._refresh_tasks.pop(key, None)
        if not task.cancelled():
            task.exception()

    def refresh_in_flight(
        self,
        country_code: str,
        *,
        warning_language: str = 'auto',
    ) -> bool:
        """Return whether a complete-country refresh is already running."""

        try:
            key = _normalized_request(country_code, warning_language)
        except ValueError:
            return False
        task = self._refresh_tasks.get(key)
        return task is not None and not task.done()

    def cancel_refreshes(self) -> None:
        """Cancel service-owned wrappers during final application shutdown."""

        for task in tuple(self._refresh_tasks.values()):
            if not task.done():
                task.cancel()
        self._refresh_tasks.clear()

    async def get_alerts(
        self,
        country_code: str,
        *,
        warning_language: str = 'auto',
        progress: WarningQueryProgress | None = None,
        refresh: bool = False,
    ) -> list[Alert]:
        """Return a fresh cache hit or perform an ordinary provider refresh."""

        if not refresh:
            cached = await self.get_cached_alerts(
                country_code,
                warning_language=warning_language,
            )
            if cached is not None and not cached.provisional:
                return list(cached.alerts)
        return await self.refresh_alerts(
            country_code,
            warning_language=warning_language,
            progress=progress,
        )

    def new_alert_identities(
        self,
        country_code: str,
        *,
        warning_language: str = 'auto',
    ) -> frozenset[tuple[str, str]]:
        """Return identities newly observed by the latest successful fetch."""

        try:
            normalized_country, language = _normalized_request(
                country_code,
                warning_language,
            )
        except ValueError:
            return frozenset()
        return self._new_alert_identities.get(
            (normalized_country, language),
            frozenset(),
        )

    def observation_journal(self) -> tuple[AlertObservation, ...]:
        """Return newest local first-observed records first."""

        return self._observations.journal()


__all__ = [
    'AlertObservation',
    'COUNTRY_ALERT_CACHE_STALE_GRACE_SECONDS',
    'COUNTRY_ALERT_CACHE_TTL_SECONDS',
    'CountryAlertsCacheHit',
    'CountryAlertsService',
    'SupportedAlertCountry',
    'country_alert_default_filter',
    'country_alert_identity',
    'country_alert_search_text',
    'get_country_alert_observations_path',
    'list_supported_alert_countries',
    'sort_country_alerts',
]
