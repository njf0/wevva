"""Alert service helpers built on top of ``wevva_warnings``."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from wevva_warnings import (
    Alert,
    UnsupportedCountryError,
    WarningQueryProgress,
    deduplicate_alerts,
    get_alerts_for_point,
    get_alerts_for_source,
    get_native_alerts_for_point,
    get_reusable_alerts_for_country,
    match_alerts_to_point,
)

from wevva.utils.country_codes import get_alpha2_by_alpha3


def normalize_country_code(country_code: str | None) -> str | None:
    """Normalize app country codes to the alpha-2 format expected downstream."""
    code = (country_code or '').strip().upper()
    if not code:
        return None
    if len(code) == 2:
        return code
    if len(code) == 3:
        return get_alpha2_by_alpha3(code)
    return None


def _filter_visible_alerts(alerts: list[Alert], *, now: datetime | None = None) -> list[Alert]:
    """Return alerts whose expiry has not passed."""
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    else:
        now = now.astimezone(UTC)

    visible_alerts: list[Alert] = []
    for alert in alerts:
        expires = alert.expires
        if expires is None:
            visible_alerts.append(alert)
            continue
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        else:
            expires = expires.astimezone(UTC)
        if expires >= now:
            visible_alerts.append(alert)
    return visible_alerts


def _get_alerts_with_status(
    lat: float,
    lon: float,
    country_code: str | None = None,
    warning_language: str = 'auto',
    progress: WarningQueryProgress | None = None,
) -> tuple[list[Alert], bool]:
    """Fetch alerts, retaining whether an empty result is a success."""
    normalized_country = normalize_country_code(country_code)
    if normalized_country is None:
        return [], True
    lang = 'en' if warning_language == 'en' else None
    try:
        alerts = get_alerts_for_point(
            lat=lat,
            lon=lon,
            country_code=normalized_country,
            lang=lang,
            active_only=False,
            progress=progress,
        )
        return _filter_visible_alerts(alerts), True
    except UnsupportedCountryError:
        return [], True
    except Exception:
        return [], False


def _get_reusable_alerts_with_status(
    country_code: str | None,
    warning_language: str = 'auto',
    progress: WarningQueryProgress | None = None,
) -> tuple[list[Alert], bool]:
    """Fetch reusable country candidates and retain completion status."""
    normalized_country = normalize_country_code(country_code)
    if normalized_country is None:
        return [], True
    lang = 'en' if warning_language == 'en' else None
    try:
        return get_reusable_alerts_for_country(normalized_country, lang=lang, progress=progress), True
    except UnsupportedCountryError:
        return [], True
    except Exception:
        return [], False


def _get_native_alerts_with_status(
    lat: float,
    lon: float,
    country_code: str | None,
    warning_language: str = 'auto',
) -> tuple[list[Alert], bool]:
    """Fetch native point-query alerts and retain completion status."""
    normalized_country = normalize_country_code(country_code)
    if normalized_country is None:
        return [], True
    lang = 'en' if warning_language == 'en' else None
    try:
        return get_native_alerts_for_point(
            lat=lat,
            lon=lon,
            country_code=normalized_country,
            lang=lang,
            active_only=False,
        ), True
    except UnsupportedCountryError:
        return [], True
    except Exception:
        return [], False


def _combine_alerts(
    candidates: list[Alert],
    native_alerts: list[Alert],
    lat: float,
    lon: float,
    *,
    progress: WarningQueryProgress | None = None,
) -> list[Alert]:
    """Match reusable candidates, combine native results, and hide expired alerts.

    Candidate alerts are matched one at a time so the TUI can turn its
    indeterminate fetch indicator into measured local matching progress.
    """
    total = len(candidates)
    _report_progress(progress, 'alerts_total', total=total, phase='matching')
    local_alerts: list[Alert] = []
    for completed, candidate in enumerate(candidates, start=1):
        local_alerts.extend(match_alerts_to_point([candidate], lat=lat, lon=lon))
        _report_progress(
            progress,
            'alerts_checked',
            completed=completed,
            total=total,
            phase='matching',
        )
    return _filter_visible_alerts(deduplicate_alerts([*local_alerts, *native_alerts]))


def _report_progress(
    progress: WarningQueryProgress | None,
    event: str,
    **payload: object,
) -> None:
    """Send advisory UI progress without allowing it to affect alert matching."""
    if progress is None:
        return
    try:
        progress(event, payload)
    except Exception:
        pass


def get_alerts(
    lat: float,
    lon: float,
    country_code: str | None = None,
    warning_language: str = 'auto',
    progress: WarningQueryProgress | None = None,
) -> list[Alert]:
    """Fetch current or future alerts for one point.

    ``progress`` receives optional public progress events from
    ``wevva-warnings``. It runs on this function's calling thread and does not
    affect the returned alert list.
    """
    return _get_alerts_with_status(
        lat,
        lon,
        country_code,
        warning_language,
        progress,
    )[0]


async def _get_alerts_async_with_status(
    lat: float,
    lon: float,
    country_code: str | None = None,
    warning_language: str = 'auto',
    progress: WarningQueryProgress | None = None,
) -> tuple[list[Alert], bool]:
    """Worker-thread version of :func:`_get_alerts_with_status`."""
    return await asyncio.to_thread(
        _get_alerts_with_status,
        lat,
        lon,
        country_code,
        warning_language,
        progress,
    )


async def _get_reusable_alerts_async_with_status(
    country_code: str | None,
    warning_language: str = 'auto',
    progress: WarningQueryProgress | None = None,
) -> tuple[list[Alert], bool]:
    """Worker-thread version of :func:`_get_reusable_alerts_with_status`."""
    return await asyncio.to_thread(
        _get_reusable_alerts_with_status,
        country_code,
        warning_language,
        progress,
    )


async def _get_native_alerts_async_with_status(
    lat: float,
    lon: float,
    country_code: str | None,
    warning_language: str = 'auto',
) -> tuple[list[Alert], bool]:
    """Worker-thread version of :func:`_get_native_alerts_with_status`."""
    return await asyncio.to_thread(
        _get_native_alerts_with_status,
        lat,
        lon,
        country_code,
        warning_language,
    )


async def get_alerts_async(
    lat: float,
    lon: float,
    country_code: str | None = None,
    warning_language: str = 'auto',
    progress: WarningQueryProgress | None = None,
) -> list[Alert]:
    """Async wrapper for point-based alert lookups.

    The optional progress callback runs in the worker thread used for the
    blocking warning-provider query.
    """
    return await asyncio.to_thread(
        get_alerts,
        lat,
        lon,
        country_code,
        warning_language,
        progress,
    )


def get_source_alerts(source_id: str, *, active_only: bool = False) -> list[Alert]:
    """Fetch alerts from one registry source, returning ``[]`` on failure."""
    try:
        return get_alerts_for_source(source_id, active_only=active_only)
    except Exception:
        return []


async def get_source_alerts_async(
    source_id: str,
    *,
    active_only: bool = False,
) -> list[Alert]:
    """Async wrapper for source-based alert lookups."""
    return await asyncio.to_thread(
        get_source_alerts,
        source_id,
        active_only=active_only,
    )


__all__ = [
    'Alert',
    'get_alerts',
    'get_alerts_async',
    'get_source_alerts',
    'get_source_alerts_async',
    'normalize_country_code',
]
