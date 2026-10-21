"""Small persistent cache for Wevva's two country warning products."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import gzip
import json
import os
from pathlib import Path
import sys
from typing import Any, Final

from wevva_warnings import Alert, WarningSource, list_sources

from wevva.services.alerts import normalize_country_code


WARNING_CACHE_SCHEMA_VERSION = 1
WARNING_CACHE_CLOCK_SKEW = timedelta(minutes=5)
WARNING_CACHE_MAX_AGE = timedelta(days=7)
WARNING_CACHE_MAX_ENTRIES = 32
WARNING_CACHE_MAX_COUNTRY_CATALOGUES = 128
WARNING_CACHE_MAX_REUSABLE_CANDIDATES = 32
_DEFAULT_CACHE_DIRECTORY: Final[object] = object()


class WarningCacheProduct(StrEnum):
    """The distinct warning products stored by Wevva."""

    COUNTRY_CATALOGUE = 'country_catalogue'
    REUSABLE_CANDIDATES = 'reusable_candidates'


@dataclass(frozen=True, slots=True)
class WarningCacheEntry:
    """One complete successful warning product."""

    alerts: tuple[Alert, ...]
    fetched_at: datetime
    new_alert_identities: frozenset[tuple[str, str]] = frozenset()


def get_warning_cache_directory() -> Path:
    """Return the platform/user cache directory without creating it."""

    if xdg_cache_home := os.environ.get('XDG_CACHE_HOME'):
        return Path(xdg_cache_home).expanduser() / 'wevva' / 'warnings'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Caches' / 'wevva' / 'warnings'
    if os.name == 'nt' and (local_app_data := os.environ.get('LOCALAPPDATA')):
        return Path(local_app_data) / 'wevva' / 'warnings'
    return Path.home() / '.cache' / 'wevva' / 'warnings'


def _normalize_key(
    product: WarningCacheProduct | str,
    country_code: str,
    warning_language: str,
) -> tuple[WarningCacheProduct, str, str]:
    """Validate and normalize a warning-cache key."""

    try:
        normalized_product = WarningCacheProduct(product)
    except (TypeError, ValueError) as error:
        raise ValueError(f'Invalid warning cache product: {product!r}') from error
    normalized_country = normalize_country_code(country_code)
    if normalized_country is None:
        raise ValueError(f'Invalid warning cache country code: {country_code!r}')
    language = (
        'en'
        if isinstance(warning_language, str)
        and warning_language.strip().casefold() == 'en'
        else 'auto'
    )
    return normalized_product, normalized_country, language


class WarningCache:
    """Keep successful warning entries in memory and best-effort disk storage."""

    def __init__(
        self,
        cache_directory: Path | str | None | object = _DEFAULT_CACHE_DIRECTORY,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        clock_skew: timedelta = WARNING_CACHE_CLOCK_SKEW,
        max_age: timedelta = WARNING_CACHE_MAX_AGE,
        max_entries: int | None = None,
        product_max_entries: Mapping[WarningCacheProduct | str, int] | None = None,
    ) -> None:
        resolved_directory = (
            get_warning_cache_directory()
            if cache_directory is _DEFAULT_CACHE_DIRECTORY
            else cache_directory
        )
        self.cache_directory = (
            None if resolved_directory is None else Path(resolved_directory)
        )
        self._clock = clock
        self.clock_skew = max(clock_skew, timedelta(0))
        self.max_age = max(max_age, timedelta(0))
        if max_entries is not None:
            limit = max(1, int(max_entries))
            self.product_max_entries = {
                product: limit for product in WarningCacheProduct
            }
        else:
            limits = {
                WarningCacheProduct.COUNTRY_CATALOGUE: max(
                    WARNING_CACHE_MAX_COUNTRY_CATALOGUES,
                    _registered_alert_country_count() + 16,
                ),
                WarningCacheProduct.REUSABLE_CANDIDATES: WARNING_CACHE_MAX_REUSABLE_CANDIDATES,
            }
            for product, limit in (product_max_entries or {}).items():
                limits[WarningCacheProduct(product)] = max(1, int(limit))
            self.product_max_entries = limits
        self._memory: dict[tuple[WarningCacheProduct, str, str], WarningCacheEntry] = {}

    async def load(
        self,
        product: WarningCacheProduct | str,
        country_code: str,
        warning_language: str = 'auto',
    ) -> WarningCacheEntry | None:
        """Load one valid completed entry from memory or disk."""

        key = _normalize_key(product, country_code, warning_language)
        if entry := self._memory.get(key):
            if self._entry_is_retained(entry):
                return entry
            del self._memory[key]
        path = _cache_path(self.cache_directory, key)
        if path is None:
            return None
        entry = await asyncio.to_thread(_read_entry, path, key)
        if entry is None or not self._entry_is_retained(entry):
            await asyncio.to_thread(_discard_file, path)
            return None
        self._memory[key] = entry
        return entry

    async def store(
        self,
        product: WarningCacheProduct | str,
        country_code: str,
        warning_language: str,
        alerts: Iterable[Alert],
        *,
        fetched_at: datetime | None = None,
        completed: bool = True,
        new_alert_identities: Iterable[tuple[str, str]] = (),
    ) -> bool:
        """Store a complete entry, returning whether its disk write succeeded."""

        if not completed:
            return False
        key = _normalize_key(product, country_code, warning_language)
        entry = WarningCacheEntry(
            alerts=tuple(alerts),
            fetched_at=_as_utc(fetched_at or self._clock()),
            new_alert_identities=frozenset(new_alert_identities),
        )
        if not self._entry_is_retained(entry):
            return False

        try:
            payload = await asyncio.to_thread(_encode_entry, entry, key)
        except (TypeError, ValueError, OverflowError):
            return False
        self._memory[key] = entry
        self._prune_memory()
        path = _cache_path(self.cache_directory, key)
        if path is None:
            return True
        written = await asyncio.to_thread(_atomic_write, path, payload)
        if written:
            await asyncio.to_thread(
                _prune_cache_directory,
                self.cache_directory,
                _as_utc(self._clock()),
                self.clock_skew,
                self.max_age,
                self.product_max_entries,
            )
        return written

    async def retained_keys(
        self,
        product: WarningCacheProduct | str | None = None,
    ) -> tuple[tuple[WarningCacheProduct, str, str], ...]:
        """Enumerate valid retained keys without loading provider data."""

        selected = None if product is None else WarningCacheProduct(product)
        keys = {
            key
            for key, entry in self._memory.items()
            if (selected is None or key[0] is selected)
            and self._entry_is_retained(entry)
        }
        if self.cache_directory is not None:
            try:
                paths = list(self.cache_directory.glob('*.json.gz'))
            except OSError:
                paths = []
            for path in paths:
                key = _key_from_cache_path(path)
                if key is None or (selected is not None and key[0] is not selected):
                    continue
                entry = await asyncio.to_thread(_read_entry, path, key)
                if entry is not None and self._entry_is_retained(entry):
                    keys.add(key)
        return tuple(sorted(keys, key=lambda key: (key[0].value, key[1], key[2])))

    def _entry_is_retained(self, entry: WarningCacheEntry) -> bool:
        now = _as_utc(self._clock())
        return (
            entry.fetched_at <= now + self.clock_skew
            and now - entry.fetched_at <= self.max_age
        )

    def _prune_memory(self) -> None:
        """Apply the same independent product limits to session entries."""

        for product, limit in self.product_max_entries.items():
            entries = sorted(
                (
                    (entry.fetched_at, key)
                    for key, entry in self._memory.items()
                    if key[0] is product
                ),
                key=lambda item: (item[0], item[1][1], item[1][2]),
            )
            for _, key in entries[: max(0, len(entries) - limit)]:
                self._memory.pop(key, None)


def _cache_path(
    directory: Path | None,
    key: tuple[WarningCacheProduct, str, str],
) -> Path | None:
    if directory is None:
        return None
    product, country_code, warning_language = key
    return directory / f'{product.value}-{country_code}-{warning_language}.json.gz'


def _encode_entry(
    entry: WarningCacheEntry,
    key: tuple[WarningCacheProduct, str, str],
) -> bytes:
    product, country_code, warning_language = key
    identities: list[list[str]] = []
    for identity in sorted(entry.new_alert_identities):
        if len(identity) != 2 or not all(isinstance(value, str) for value in identity):
            raise ValueError('Invalid newly-observed alert identity')
        identities.append(list(identity))
    envelope = {
        'schema_version': WARNING_CACHE_SCHEMA_VERSION,
        'product_kind': product.value,
        'key': {
            'country_code': country_code,
            'warning_language': warning_language,
        },
        'fetched_at': _encode_datetime(entry.fetched_at),
        'completed': True,
        'new_alert_identities': identities,
        'alerts': [_alert_to_dict(alert) for alert in entry.alerts],
    }
    encoded = json.dumps(
        envelope,
        ensure_ascii=False,
        separators=(',', ':'),
        sort_keys=True,
        allow_nan=False,
    ).encode()
    return gzip.compress(encoded, mtime=0)


def _read_entry(
    path: Path,
    expected_key: tuple[WarningCacheProduct, str, str],
) -> WarningCacheEntry | None:
    product, country_code, warning_language = expected_key
    try:
        raw = json.loads(
            gzip.decompress(path.read_bytes()),
            parse_constant=_reject_json_constant,
        )
        if not isinstance(raw, dict):
            return None
        raw_key = raw.get('key')
        if (
            raw.get('schema_version') != WARNING_CACHE_SCHEMA_VERSION
            or raw.get('product_kind') != product.value
            or raw.get('completed') is not True
            or not isinstance(raw_key, dict)
            or raw_key.get('country_code') != country_code
            or raw_key.get('warning_language') != warning_language
            or not isinstance(raw.get('alerts'), list)
            or not isinstance(raw.get('new_alert_identities'), list)
        ):
            return None

        identities = frozenset(
            (identity[0], identity[1])
            for identity in raw['new_alert_identities']
            if isinstance(identity, list)
            and len(identity) == 2
            and all(isinstance(value, str) for value in identity)
        )
        if len(identities) != len(raw['new_alert_identities']):
            return None
        sources = _source_registry()
        return WarningCacheEntry(
            alerts=tuple(_alert_from_dict(alert, sources) for alert in raw['alerts']),
            fetched_at=_decode_datetime(raw.get('fetched_at')),
            new_alert_identities=identities,
        )
    except (OSError, EOFError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return None


_REQUIRED_ALERT_TEXT = ('id', 'source', 'event', 'headline')
_OPTIONAL_ALERT_TEXT = (
    'url',
    'severity',
    'urgency',
    'certainty',
    'description',
    'instruction',
)


def _alert_to_dict(alert: Alert) -> dict[str, object]:
    if not isinstance(alert, Alert):
        raise ValueError('Warning cache values must be Alert instances')
    return {
        **{name: getattr(alert, name) for name in _REQUIRED_ALERT_TEXT},
        **{name: getattr(alert, name) for name in _OPTIONAL_ALERT_TEXT},
        'onset': _encode_datetime(alert.onset) if alert.onset else None,
        'expires': _encode_datetime(alert.expires) if alert.expires else None,
        'area_names': alert.area_names,
        'geocodes': alert.geocodes,
        'parameters': alert.parameters,
        'geometry': alert.geometry,
    }


def _alert_from_dict(
    raw: object,
    sources: Mapping[str, WarningSource],
) -> Alert:
    if not isinstance(raw, dict):
        raise ValueError('Invalid cached alert')
    required = {name: raw.get(name) for name in _REQUIRED_ALERT_TEXT}
    optional = {name: raw.get(name) for name in _OPTIONAL_ALERT_TEXT}
    if not all(isinstance(value, str) for value in required.values()):
        raise ValueError('Invalid required alert text')
    if not all(value is None or isinstance(value, str) for value in optional.values()):
        raise ValueError('Invalid optional alert text')
    geometry = raw.get('geometry')
    if geometry is not None and not isinstance(geometry, dict):
        raise ValueError('Invalid alert geometry')
    source = required['source']
    assert isinstance(source, str)
    return Alert(
        **required,
        **optional,
        onset=_decode_datetime(raw['onset']) if raw.get('onset') is not None else None,
        expires=(
            _decode_datetime(raw['expires'])
            if raw.get('expires') is not None
            else None
        ),
        area_names=_string_list(raw.get('area_names')),
        geocodes=_string_list_mapping(raw.get('geocodes')),
        parameters=_string_list_mapping(raw.get('parameters')),
        geometry=geometry,
        source_info=sources.get(source),
    )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError('Expected a string list')
    return list(value)


def _string_list_mapping(value: object) -> dict[str, list[str]]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError('Expected a string-list mapping')
    return {key: _string_list(items) for key, items in value.items()}


def _source_registry() -> dict[str, WarningSource]:
    try:
        return {source.id: source for source in list_sources()}
    except Exception:
        return {}


def _registered_alert_country_count() -> int:
    """Size catalogue retention from the installed warning-source registry."""

    try:
        sources = list_sources(kind='alert')
    except Exception:
        return 0
    countries = {
        code
        for source in sources
        for value in (source.country_code, *source.additional_country_codes)
        if (code := normalize_country_code(value)) is not None
    }
    return len(countries)


def _encode_datetime(value: datetime) -> str:
    return _as_utc(value).isoformat()


def _decode_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError('Expected an ISO datetime string')
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('Cached datetimes must include a timezone')
    return parsed.astimezone(UTC)


def _as_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError('Expected a datetime')
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f'Invalid JSON constant: {value}')


def _atomic_write(path: Path, payload: bytes) -> bool:
    temporary_path = path.with_name(f'.{path.name}.tmp')
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_bytes(payload)
        temporary_path.replace(path)
        return True
    except OSError:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def _prune_cache_directory(
    directory: Path,
    now: datetime,
    clock_skew: timedelta,
    max_age: timedelta,
    product_max_entries: Mapping[WarningCacheProduct, int],
) -> None:
    """Remove invalid, old, and excess entries without surfacing cache errors."""

    try:
        paths = sorted(directory.glob('*.json.gz'))
    except OSError:
        return

    retained: dict[WarningCacheProduct, list[tuple[datetime, Path]]] = {
        product: [] for product in WarningCacheProduct
    }
    for path in paths:
        key = _key_from_cache_path(path)
        entry = _read_entry(path, key) if key is not None else None
        if (
            entry is None
            or entry.fetched_at > now + clock_skew
            or now - entry.fetched_at > max_age
        ):
            _discard_file(path)
        else:
            assert key is not None
            retained[key[0]].append((entry.fetched_at, path))

    for product, entries in retained.items():
        entries.sort(key=lambda item: (item[0], item[1].name))
        limit = product_max_entries.get(product, 1)
        for _, path in entries[: max(0, len(entries) - limit)]:
            _discard_file(path)


def _key_from_cache_path(
    path: Path,
) -> tuple[WarningCacheProduct, str, str] | None:
    suffix = '.json.gz'
    if not path.name.endswith(suffix):
        return None
    stem = path.name[: -len(suffix)]
    for product in WarningCacheProduct:
        prefix = f'{product.value}-'
        if not stem.startswith(prefix):
            continue
        parts = stem[len(prefix) :].split('-')
        if len(parts) != 2:
            return None
        try:
            return _normalize_key(product, parts[0], parts[1])
        except ValueError:
            return None
    return None


def _discard_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
