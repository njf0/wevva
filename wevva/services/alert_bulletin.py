"""Session-owned scheduling for complete-country alert catalogues."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import random
import time

from wevva_warnings import Alert

from wevva.services.alerts import normalize_country_code
from wevva.services.country_alerts import (
    CountryAlertsService,
    country_alert_identity,
)
from wevva.services.warning_cache import WarningCacheProduct


BulletinKey = tuple[str, str]


@dataclass(frozen=True, slots=True)
class BulletinCatalogue:
    """One complete country observation available to bulletin consumers."""

    country_code: str
    warning_language: str
    alerts: tuple[Alert, ...]
    fetched_at: datetime


@dataclass(frozen=True, slots=True)
class BulletinAlert:
    """One current cross-country-deduplicated bulletin row."""

    country_code: str
    alert: Alert
    first_observed: datetime


class AlertBulletinCoordinator:
    """Refresh priority countries promptly and rotate fairly through the rest."""

    def __init__(
        self,
        service: CountryAlertsService,
        country_codes: Sequence[str],
        *,
        warning_language: str = 'auto',
        priority_interval_seconds: float = 15 * 60,
        rolling_cycle_seconds: float = 2 * 60 * 60,
        priority_cap: int = 8,
        max_concurrency: int = 2,
        retry_base_seconds: float = 60,
        retry_max_seconds: float = 15 * 60,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        jitter: Callable[[float], float] = (
            lambda value: random.uniform(0.9, 1.1) * value
        ),
        on_update: Callable[[int], None] | None = None,
    ) -> None:
        supported = {
            code
            for value in country_codes
            if (code := normalize_country_code(value)) is not None
        }
        self.service = service
        self._supported = tuple(sorted(supported))
        self._language = _language(warning_language)
        self.priority_interval_seconds = max(0.0, priority_interval_seconds)
        self.rolling_cycle_seconds = max(1.0, rolling_cycle_seconds)
        self.priority_cap = max(1, priority_cap)
        self.retry_base_seconds = max(0.1, retry_base_seconds)
        self.retry_max_seconds = max(self.retry_base_seconds, retry_max_seconds)
        self._clock = clock
        self._wall_clock = wall_clock
        self._jitter = jitter
        self._on_update = on_update
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._rolling = deque(self._supported)
        self._priority: tuple[str, ...] = ()
        self._recent: deque[str] = deque(maxlen=self.priority_cap)
        self._catalogues: dict[BulletinKey, BulletinCatalogue] = {}
        self._last_success: dict[BulletinKey, float] = {}
        self._last_rolling_attempt: dict[BulletinKey, float] = {}
        self._failures: dict[BulletinKey, int] = {}
        self._retry_not_before: dict[BulletinKey, float] = {}
        self._next_dispatch_at = 0.0
        self._next_rolling_at = 0.0
        self._prefer_rolling = False
        self._generation = 0
        self._schedule_generation = 0
        self._needs_hydration = True
        self._task: asyncio.Task[None] | None = None
        self._hard_tasks: set[asyncio.Task[object]] = set()
        self._wake = asyncio.Event()

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def generation(self) -> int:
        return self._generation

    def catalogues_snapshot(self) -> tuple[BulletinCatalogue, ...]:
        """Return immutable catalogue state for the effective language."""

        return tuple(
            self._catalogues[key]
            for key in sorted(self._catalogues)
            if key[1] == self._language
        )

    def recent_alerts_snapshot(self) -> tuple[BulletinAlert, ...]:
        """Return current alerts ordered by Wevva's first observation time."""

        now = _as_utc(self._wall_clock())
        observations = {
            (
                item.country_code,
                item.warning_language,
                item.source,
                item.alert_id,
            ): item.first_observed
            for item in self.service.observation_journal()
        }
        rows: dict[tuple[str, str], BulletinAlert] = {}
        for catalogue in self.catalogues_snapshot():
            for alert in catalogue.alerts:
                if alert.expires is not None and _as_utc(alert.expires) < now:
                    continue
                identity = country_alert_identity(alert)
                first_observed = observations.get(
                    (
                        catalogue.country_code,
                        catalogue.warning_language,
                        *identity,
                    ),
                    catalogue.fetched_at,
                )
                candidate = BulletinAlert(
                    catalogue.country_code,
                    alert,
                    first_observed,
                )
                current = rows.get(identity)
                if current is None or (
                    candidate.first_observed,
                    candidate.country_code,
                ) < (
                    current.first_observed,
                    current.country_code,
                ):
                    rows[identity] = candidate
        return tuple(
            sorted(
                rows.values(),
                key=lambda row: (
                    -row.first_observed.timestamp(),
                    row.alert.source.casefold(),
                    row.alert.id,
                ),
            )
        )

    def set_priority_countries(self, country_codes: Iterable[str]) -> None:
        """Replace the bounded active/selected/saved priority lane."""

        self._priority = self._bounded_codes(country_codes)
        self._wake.set()

    def note_country_used(self, country_code: str | None) -> None:
        """Move a recently used Alerts Centre country into the priority lane."""

        code = normalize_country_code(country_code)
        if code is None or code not in self._supported:
            return
        try:
            self._recent.remove(code)
        except ValueError:
            pass
        self._recent.appendleft(code)
        self._wake.set()

    def set_warning_language(self, warning_language: str) -> None:
        """Rebuild scheduling keys when the effective warning language changes."""

        language = _language(warning_language)
        if language == self._language:
            return
        self._language = language
        self._generation += 1
        self._schedule_generation += 1
        self._rolling = deque(self._supported)
        self._catalogues.clear()
        self._last_success.clear()
        self._last_rolling_attempt.clear()
        self._failures.clear()
        self._retry_not_before.clear()
        self._next_dispatch_at = 0.0
        self._next_rolling_at = 0.0
        self._needs_hydration = True
        self._wake.set()
        self._notify_update()

    def start(self) -> None:
        """Start one session scheduler; repeated calls are harmless."""

        if self.is_running or not self._supported:
            return
        self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        """Cancel all coordinator-owned work at application shutdown."""

        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None
        for task in tuple(self._hard_tasks):
            task.cancel()
        self._hard_tasks.clear()
        self.service.cancel_refreshes()

    def schedule_hard_refresh(
        self,
        country_codes: Iterable[str | None],
    ) -> asyncio.Task[object] | None:
        """Bypass freshness for no more than three explicit local keys."""

        codes = self._bounded_codes(country_codes, limit=3)
        if not codes:
            return None
        task: asyncio.Task[object] = asyncio.create_task(
            self._hard_refresh(codes, self._schedule_generation)
        )
        self._hard_tasks.add(task)
        task.add_done_callback(self._hard_tasks.discard)
        return task

    async def hydrate(self) -> None:
        """Load retained catalogues before starting provider work."""

        generation = self._schedule_generation
        keys = await self.service.cache.retained_keys(
            WarningCacheProduct.COUNTRY_CATALOGUE
        )
        for _, country_code, language in keys:
            if (
                generation != self._schedule_generation
                or language != self._language
                or country_code not in self._supported
            ):
                continue
            cached = await self.service.get_retained_alerts(
                country_code,
                warning_language=language,
            )
            if cached is None or cached.fetched_at is None:
                continue
            self._catalogues[(country_code, language)] = BulletinCatalogue(
                country_code,
                language,
                cached.alerts,
                cached.fetched_at,
            )
            age = max(
                0.0,
                (_as_utc(self._wall_clock()) - cached.fetched_at).total_seconds(),
            )
            self._last_success[(country_code, language)] = self._clock() - age
        if self._catalogues:
            self._generation += 1
            self._notify_update()

    async def refresh_due_once(self) -> bool:
        """Refresh at most one due key; useful for deterministic tests."""

        now = self._clock()
        if now < self._next_dispatch_at:
            return False
        selected = self._next_due(now)
        if selected is None:
            return False
        country_code, lane = selected
        key = country_code, self._language
        if lane == 'rolling':
            self._last_rolling_attempt[key] = now
        await self._refresh(country_code, generation=self._schedule_generation)
        now = self._clock()
        self._next_dispatch_at = now + max(0.05, self._jitter(2.0))
        if lane == 'rolling':
            interval = self.rolling_cycle_seconds / max(1, len(self._supported))
            self._next_rolling_at = now + max(0.05, self._jitter(interval))
        return True

    async def _run(self) -> None:
        try:
            while True:
                if self._needs_hydration:
                    self._needs_hydration = False
                    await self.hydrate()
                if await self.refresh_due_once():
                    continue
                delay = max(0.05, min(30.0, self._next_wait()))
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=delay)
                except TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise

    def _next_due(self, now: float) -> tuple[str, str] | None:
        priority = self._due_priority(now)
        rolling = self._due_rolling(now) if now >= self._next_rolling_at else None
        if priority is not None and rolling is not None:
            if self._prefer_rolling:
                self._prefer_rolling = False
                self._advance_rolling(rolling)
                return rolling, 'rolling'
            self._prefer_rolling = True
            return priority, 'priority'
        if priority is not None:
            self._prefer_rolling = True
            return priority, 'priority'
        if rolling is not None:
            self._prefer_rolling = False
            self._advance_rolling(rolling)
            return rolling, 'rolling'
        return None

    def _due_priority(self, now: float) -> str | None:
        codes = self._bounded_codes(
            (*self._priority[:2], *self._recent, *self._priority[2:])
        )
        for code in codes:
            key = code, self._language
            if now < self._retry_not_before.get(key, 0.0):
                continue
            age = now - self._last_success.get(key, float('-inf'))
            if age >= self.priority_interval_seconds:
                return code
        return None

    def _due_rolling(self, now: float) -> str | None:
        for code in self._rolling:
            key = code, self._language
            if now < self._retry_not_before.get(key, 0.0):
                continue
            if key in self._failures:
                return code
            last = max(
                self._last_rolling_attempt.get(key, float('-inf')),
                self._last_success.get(key, float('-inf')),
            )
            if now - last >= self.rolling_cycle_seconds:
                return code
        return None

    def _advance_rolling(self, country_code: str) -> None:
        while self._rolling and self._rolling[0] != country_code:
            self._rolling.rotate(-1)
        if self._rolling:
            self._rolling.rotate(-1)

    async def _hard_refresh(
        self,
        country_codes: tuple[str, ...],
        generation: int,
    ) -> object:
        return await asyncio.gather(
            *(self._refresh(code, generation=generation) for code in country_codes)
        )

    async def _refresh(self, country_code: str, *, generation: int) -> None:
        key = country_code, self._language
        try:
            async with self._semaphore:
                alerts = await self.service.refresh_alerts(
                    country_code,
                    warning_language=key[1],
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            failures = self._failures.get(key, 0) + 1
            self._failures[key] = failures
            backoff = min(
                self.retry_max_seconds,
                self.retry_base_seconds * (2 ** (failures - 1)),
            )
            self._retry_not_before[key] = self._clock() + backoff
            return
        if generation != self._schedule_generation or key[1] != self._language:
            return
        self._failures.pop(key, None)
        self._retry_not_before.pop(key, None)
        self._last_success[key] = self._clock()
        self._catalogues[key] = BulletinCatalogue(
            country_code,
            key[1],
            tuple(alerts),
            _as_utc(self._wall_clock()),
        )
        self._generation += 1
        self._notify_update()

    def _notify_update(self) -> None:
        if self._on_update is not None:
            self._on_update(self._generation)

    def _next_wait(self) -> float:
        now = self._clock()
        if self._next_dispatch_at > now:
            return self._next_dispatch_at - now
        future_times = [
            value
            for value in (
                self._next_rolling_at,
                *self._retry_not_before.values(),
            )
            if value > now
        ]
        return min((value - now for value in future_times), default=30.0)

    def _bounded_codes(
        self,
        country_codes: Iterable[str | None],
        *,
        limit: int | None = None,
    ) -> tuple[str, ...]:
        result: list[str] = []
        cap = self.priority_cap if limit is None else limit
        for value in country_codes:
            code = normalize_country_code(value)
            if code is None or code not in self._supported or code in result:
                continue
            result.append(code)
            if len(result) >= cap:
                break
        return tuple(result)


def _language(value: str) -> str:
    return 'en' if value == 'en' else 'auto'


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = [
    'AlertBulletinCoordinator',
    'BulletinAlert',
    'BulletinCatalogue',
]
