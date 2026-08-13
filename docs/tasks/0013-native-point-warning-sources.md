# Task 0013: Support native point-query warning sources with caching

## Status

Completed

## Context

Task 0002 caches country-level warning candidates for 30 minutes, then matches
them locally to each selected location. This is correct for sources whose
alerts can be reused and geometrically matched outside the provider.

## Problem

The U.S. National Weather Service source in `wevva-warnings` is a native
point-query provider. Its correct request includes `point=<latitude>,<longitude>`
and its result is already applicable to that point. The current cache path
instead calls the country-candidate API without coordinates, then applies local
geometry matching; this can discard valid NWS alerts that use zones or lack
usable geometry.

## Desired outcome

Warnings remain correct for both reusable country-level sources and native
point-query sources. Country candidates are cached only where that is valid;
native point-query results are fetched for the current location and never
reused as a whole-country cache entry.

## Scope

- Coordinate with `wevva-warnings` on a small public, source-aware query
  contract that separates reusable country candidates from native point-query
  results.
- Update Wevva's background alert orchestration to combine locally matched
  cached candidates with fresh native point-query results.
- Preserve warning-language selection, expiry filtering, progress callbacks,
  cancellation, stale-refresh guards, and Task 0002's cache semantics for
  eligible sources.
- Add focused tests for the U.S./native-point behavior and a mixed-source case
  if the warning library supports one.
- Update architecture/agent documentation if the warning boundary changes.

## Non-goals

- Do not hard-code `US`, `nws`, or a list of providers in Wevva.
- Do not cache a native point-query response by country.
- Do not remove the existing country-candidate cache for geometry-based
  sources.
- Do not introduce persistent warning storage, a generic cache framework, or
  a provider-specific UI.

## Relevant code

- `wevva/app.py`
- `wevva/services/alerts.py`
- `tests/test_warning_cache.py`
- `docs/tasks/0002-warning-cache.md`
- `wevva-warnings`: query API, warning-source metadata, backend capability
  model, and NWS backend

## Approach

First add the smallest public `wevva-warnings` interface that lets consumers
query a point while distinguishing results safe for country-level reuse from
results that require provider-native point lookup. The interface should be
source/capability based, not country based.

Then make Wevva cache only the reusable part by country/language. On every
location refresh, query the native point part for the active coordinates,
locally match the cached reusable candidates, combine and de-duplicate the
results, and post the normal final update. Decide progress semantics so the
sidebar still appears only when there is meaningful individual-document work.

## Acceptance criteria

- A U.S. location receives the same applicable NWS alerts as the warning
  library's direct point query.
- Changing U.S. coordinates does not reuse another location's native point
  result from the country cache.
- Reusable country candidates remain cached and locally matched as in Task
  0002.
- The design does not contain an NWS/United States conditional in Wevva.
- Failed or cancelled native point queries do not poison the cache or overwrite
  a newer location's alerts.
- Progress, stale-result protection, filtering of expired alerts, and warning
  display behavior remain coherent.

## Verification

- Add deterministic mocked tests for native point-only and reusable candidate
  source behavior; include cache-hit, coordinate-change, failure, and
  cancellation cases.
- Run `uv run python -m unittest discover -s tests`.
- Run `uv run python -m compileall -q wevva`.
- Test a U.S. location with active NWS alerts against a direct
  `wevva-warnings` point query when live network access is available.
- Record any live-provider or terminal-rendering behavior that could not be
  verified.

## Decisions and notes

Task 0002's assumption that all country candidates can be locally matched is
not valid for native point-query sources. This task refines that assumption;
it does not remove the existing cache.

## Outcome

Wevva now caches only `get_reusable_alerts_for_country()` results by
country/language. It performs `get_native_alerts_for_point()` for every warning
refresh, locally matches reusable candidates, combines both lists with
`deduplicate_alerts()`, and filters expired alerts before display. Native query
progress is intentionally not forwarded to avoid a brief sidebar indicator for
short point lookups.

Focused tests cover cache reuse, expiry, cancellation, stale results, and two
U.S. locations receiving separate native point results; the standard-library
suite and source compilation passed against the local `wevva-warnings` checkout.
`wevva-warnings==0.4.0` is now published, pinned in Wevva, and verified through
a clean `uvx --no-cache --from ./ wevva --help` install. No live NWS request or
terminal rendering check was performed.
