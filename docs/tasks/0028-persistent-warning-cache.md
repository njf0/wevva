# Task 0028: Persistent warning cache

## Status

Complete

## Context

Warning retrieval can be much slower than forecast retrieval. Large catalogues,
especially the complete United States feed, may take minutes because providers
and the warning library resolve alert documents, affected zones, prose, and
geometry before returning normalized alerts.

Before this task, Wevva kept two successful warning products only in memory:

- the Alerts Centre owns a fifteen-minute cache of complete country catalogues;
- the Weather path owns a thirty-minute cache of reusable country candidates,
  then performs local point matching and a fresh native point query.

The caches deliberately contain different products and must not be substituted
for one another. Both disappear when the process exits, however, so reopening
Wevva shortly afterwards can repeat an unchanged multi-minute country fetch.

## Problem

Recent successful warning work cannot be reused across application sessions.
Cache ownership is also split between `Wevva` and `CountryAlertsService`, which
makes expiry, persistence, corruption handling, and future cache handoffs easy
to implement inconsistently.

## Desired outcome

One small warning-cache boundary owns memory and disk persistence for both
warning products while retaining separate namespaces and semantics. Reopening
Wevva within the existing freshness interval should render the cached country
catalogue or locally match cached reusable candidates without downloading the
same country feed again. Older usable data may provide an immediate provisional
view while a real refresh runs in the background.

## Scope

- Add a versioned, disposable, application-wide warning cache with separate
  entry kinds for complete country catalogues and reusable point candidates.
- Key entries by product kind, normalized country code, and effective warning
  language.
- Persist normalized `Alert` data, fetch time, completion metadata, and the
  Alerts Centre's newly-observed identities where applicable.
- Maintain a bounded first-observed journal for alerts discovered by successful
  complete-country refreshes. Key observations by country, language, source,
  and alert identity so a later dashboard can order recent alerts across
  countries without claiming provider issue times that are not normalized.
- Encode datetimes explicitly, retain GeoJSON/geocodes/parameters without
  lossy transformation, and restore source presentation metadata from the
  installed warning-source registry.
- Write each successful entry atomically after its fetch completes rather than
  relying on application shutdown.
- Perform potentially large serialization, compression, parsing, and disk I/O
  outside Textual's event loop.
- Preserve the existing fresh lifetimes: fifteen minutes for an Alerts Centre
  catalogue and thirty minutes for reusable Weather candidates.
- Retain stale successful entries for a short bounded grace period. Publish
  them only as provisional data while immediately scheduling a provider
  refresh; continue filtering alerts whose expiry has passed.
- Keep failed, incomplete, malformed, incompatible, and cancelled results from
  replacing the last successful entry.
- Let explicit `r` refreshes bypass both fresh and stale entries and replace the
  relevant entry only after successful completion.
- Prune expired, incompatible, and excess files so disk use remains bounded.
- Keep the existing persistent observation snapshot as the baseline for `NEW`
  detection; a cache hit must not count as a new provider observation.
- Preserve request generations, coordinate checks, task cancellation, warning
  progress, and no-toast behavior.

## Non-goals

- Treating the complete Alerts Centre catalogue as reusable Weather candidates,
  or the reverse.
- Persisting native point-query results by country. Native sources continue to
  run for every selected coordinate.
- Caching failed provider calls as successful empty results.
- Creating a general-purpose cache framework for forecasts, geocoding, air
  quality, tropical products, or arbitrary application data.
- Moving provider-specific serialization or query behavior into the UI.
- Guaranteeing that cached warnings are current after their freshness window;
  stale data is only a provisional bridge to an active refresh.
- Adding a cache-management settings screen in the first implementation.

## Implementation scale

This is a best-effort optimization for a personal application, not an
industrial cache subsystem. Keep the implementation small, direct, and easy to
reason about. Prefer covering the common fresh-restart, stale-preview, forced-
refresh, and corrupt-file cases with ordinary standard-library code over
building a general framework or exhaustive machinery for every theoretical
failure mode.

Aim for roughly 95% of the useful behavior with 50% of the code an exhaustive
solution might require. When an uncommon edge case would add substantial
state, abstraction, or coordination, it is acceptable for persistence to
degrade to an ordinary provider fetch. A little focused duplication is better
than speculative layers, and later slices should simplify the Slice A boundary
if integration shows that parts of it are unnecessary.

## Relevant code

- `wevva/app.py`
- `wevva/services/alerts.py`
- `wevva/services/country_alerts.py`
- `wevva/screens/alerts_centre_screen.py`
- `wevva/config.py`
- `tests/test_warning_cache.py`
- `tests/test_warning_textual_smoke.py`
- `tests/test_alerts_centre_service.py`
- `tests/test_alerts_centre_integration.py`
- `docs/architecture.md`
- `docs/development.md`

## Approach

### Slice A — storage and alert codec

Introduce a focused warning-cache service rather than a generic cache base
class. Store cache data beneath the platform/user cache directory, separate
from durable preferences and the Alerts Centre observation snapshot. Use one
atomic, optionally compressed file per cache key so a damaged or interrupted
write cannot invalidate every country.

The on-disk envelope records a schema version, product kind, normalized key,
wall-clock fetch time, completion state, and serialized alerts. The in-memory
layer may continue using a monotonic clock, but persisted expiry must use a UTC
timestamp that survives process restarts. Reject future timestamps beyond a
small clock-skew allowance and discard unknown schema versions cleanly.

Serialize every public normalized alert field. Rebuild `source_info` by alert
source ID from `list_sources()` instead of duplicating the complete registry in
each file. An unknown source may retain the alert with absent presentation
metadata where safe; structurally invalid alert content invalidates that entry.

### Slice B — persistent Alerts Centre catalogues

Move `CountryAlertsService` onto the shared cache boundary. A fresh persisted
catalogue follows the same path as a fresh memory hit and does no network work.
A stale-but-usable catalogue is published immediately with expired alerts
removed, while the ordinary progress and generation-guarded refresh replaces
it in the background.

Preserve the cached `NEW` identities associated with the latest successful
provider observation. Loading or displaying a disk entry must not advance the
observation snapshot. A fresh manual refresh continues to establish the next
observation and badges.

On each successful fresh complete-country result, update a bounded observation
journal with the first time each active identity was seen and its most recent
successful observation. Reusable Weather candidates and native point queries
must not write this journal: doing so would duplicate identities and make the
meaning of “recent” depend on which screen happened to open first.

This slice supplies the main user benefit: reopening the Alerts Centre five
minutes after a completed US fetch should be immediate.

### Slice C — persistent Weather candidates

Move the Weather screen's reusable-candidate cache behind the same service,
using its own product namespace and thirty-minute fresh lifetime. On a fresh
hit, locally match candidates to the newly selected coordinates. On a stale
hit, retain/publish the filtered provisional match while a replacement country
fetch runs.

Always run `get_native_point_alerts_async()` for the selected coordinate and
combine it with the locally matched candidate set. Do not persist that native
result or let a broad country cache suppress it.

### Slice D — lifecycle, pruning, and documentation

Bound retained files by age and total size or entry count, with deterministic
oldest-first pruning. Isolate corrupt entries, tolerate read-only/unavailable
cache directories, and keep persistence an optimization rather than a reason
for warning retrieval to fail. Document ownership, fresh/stale behavior,
manual-refresh semantics, and the distinction between cached country products.

## Acceptance criteria

- A completed US Alerts Centre fetch can be reused after restarting Wevva
  within fifteen minutes without calling the country provider again.
- A persisted reusable-candidate entry can be locally matched after restart
  without repeating its country-wide provider request.
- Alerts Centre catalogues and Weather candidates cannot collide or seed one
  another despite sharing country and language values.
- Every Weather location selection still performs its native point query,
  including two different US locations sharing one candidate entry.
- Fresh cache hits show final data without transient fetch progress.
- A stale hit gives immediate filtered provisional data and starts exactly one
  replacement fetch; a successful replacement updates memory and disk.
- Explicit refresh bypasses fresh and stale entries.
- Expired alerts are never revived merely because their containing entry is
  still usable.
- Successful empty results may be persisted; provider failures, incomplete
  results, and cancellations are not persisted as empty successes.
- A corrupt file, unsupported schema, clock anomaly, or unwritable cache path
  degrades to ordinary provider retrieval without a crash or toast storm.
- Rapid country/location changes cannot publish an obsolete disk read or
  background refresh.
- Cache files remain bounded and contain no preferences, credentials, or
  location history beyond the warning product's country key.
- Existing `NEW` badge behavior remains refresh-scoped across cache hits and
  application restarts.
- First-observed times survive restart, are not advanced by cache reads, and
  are written only by successful complete-country observations.

## Verification

```bash
uv run python -m unittest tests.test_warning_cache tests.test_warning_textual_smoke
uv run python -m unittest tests.test_alerts_centre_service tests.test_alerts_centre_integration
uv run python -m unittest discover -s tests
uv run python -m compileall -q wevva
```

Use temporary cache directories and controlled wall/monotonic clocks for
fresh restart hits, stale-while-revalidate, forced refresh, atomic replacement,
corruption, schema mismatch, pruning, failed writes, cancellation, and clock
skew. Mock provider calls to prove that disk hits suppress only eligible
country-wide requests and never native point requests. A live US fetch/restart
check remains valuable but optional because provider timing is external.

## Decisions and notes

- This task supersedes the session-only persistence non-goals in Tasks 0002,
  0013, 0020, and 0027; their separation of reusable candidates from native
  point results remains authoritative.
- Sharing a cache service means shared storage and policy, not pretending the
  two country products have identical query contracts.
- The cache is disposable acceleration data, not a warning archive or a source
  of truth.
- “First observed” is local application metadata, not a substitute for a
  provider-issued timestamp. Consumers must label it accordingly.
- Prefer standard-library serialization/compression and filesystem operations;
  SQLite or a new caching dependency is not justified for the expected number
  of country/language entries.
- Optimize for clarity and the main user-visible wins rather than exhaustive
  cache engineering; cache failure must remain equivalent to a cache miss.

## Outcome

Slice A introduces `wevva.services.warning_cache`, a focused asynchronous
memory-and-disk boundary with distinct country-catalogue and reusable-candidate
namespaces. It writes one versioned, gzip-compressed JSON file per normalized
country/language/product key using same-directory atomic replacement. The
codec preserves every normalized `Alert` field, uses timezone-explicit UTC
datetimes, validates nested JSON data, and restores source presentation
metadata from the installed warning-source registry. Corrupt, incompatible,
incomplete, malformed, future-dated, and unavailable-storage cases degrade to
cache misses or memory-only operation.

Slice A was subsequently simplified in line with the implementation-scale
guidance above: it uses one compressed format, a private tuple key, direct
best-effort atomic replacement, and only the validation needed to keep bad
files from reaching callers. It deliberately has no generic cache base class,
pluggable codec, alternate storage format, or independent concurrency layer.

Slice A intentionally left both runtime cache owners unchanged until their
respective integration slices.

Slice B moves the Alerts Centre catalogue onto the shared cache. A fresh
persisted hit renders without provider work or transient progress. A catalogue
older than fifteen minutes but within a six-hour grace period is filtered for
expired alerts and shown provisionally while one ordinary, generation-guarded
provider refresh runs with compact background progress. Explicit refresh skips
the cache. Only successful provider refreshes update the durable `NEW` baseline
and the bounded 500-entry first/last-observed journal; cache reads restore the
stored badges without counting as observations.

Slice C replaces the Weather screen's session dictionary with the shared
reusable-candidate namespace. Entries remain fresh for thirty minutes and may
provide a filtered provisional match for a further six hours while one
replacement fetch runs. Native point sources still run once for every selected
coordinate and are combined with both fresh and provisional candidate matches;
they are never persisted. Explicit refresh bypasses the candidate cache, and
only completed country-candidate results replace it.

Slice D completes the lifecycle with opportunistic worker-thread pruning after
successful writes. Cache files older than seven days, malformed or incompatible
files, and entries beyond the newest 32 are removed in deterministic fetch-time
and filename order. Invalid files are also discarded when read. Pruning and
deletion failures remain silent cache misses, so unavailable or read-only cache
storage never becomes an application failure.
