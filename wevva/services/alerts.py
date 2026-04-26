"""Alert service helpers built on top of ``wevva_warnings``."""

from __future__ import annotations

import asyncio

from wevva_warnings import (
    Alert,
    UnsupportedCountryError,
    get_alerts_for_point,
    get_alerts_for_source,
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


def get_alerts(
    lat: float,
    lon: float,
    country_code: str | None = None,
    warning_language: str = 'auto',
) -> list[Alert]:
    """Fetch active alerts for one point, returning ``[]`` on unsupported input."""
    normalized_country = normalize_country_code(country_code)
    if normalized_country is None:
        return []
    lang = 'en' if warning_language == 'en' else None
    try:
        return get_alerts_for_point(
            lat=lat,
            lon=lon,
            country_code=normalized_country,
            lang=lang,
            active_only=True,
        )
    except UnsupportedCountryError:
        return []
    except Exception:
        return []


async def get_alerts_async(
    lat: float,
    lon: float,
    country_code: str | None = None,
    warning_language: str = 'auto',
) -> list[Alert]:
    """Async wrapper for point-based alert lookups."""
    return await asyncio.to_thread(
        get_alerts,
        lat,
        lon,
        country_code,
        warning_language,
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
