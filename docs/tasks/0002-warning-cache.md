# Task 0002: Cache warning lookups during a TUI session

## Status

Completed

## Context

Warning lookups can be slow because some providers require country-wide feeds,
linked warning documents, and point/geometry matching. Switching between saved
locations can repeat that work even when the recent result is still useful.

## Problem

The TUI always starts a new background warning query for a refreshed location.
Repeated lookups can take minutes and needlessly re-run unchanged provider
work.

## Desired outcome

Within one TUI session, country-level warning candidates are reused for 15
minutes when the same country and effective warning language are requested.
Each requested point is matched against those cached candidates before display.
An explicit `r` refresh bypasses that cached country result and starts a new
warning query.

## Scope

- Add a small in-memory country-level warning-candidate cache owned by the TUI
  session.
- Key entries by normalized country code and effective warning language. Do
  not include latitude/longitude in this key.
- Cache both non-empty and successfully completed empty candidate results for
  15 minutes.
- Use a monotonic clock for expiry and remove expired entries when they are
  consulted.
- Match cached candidates to the newly requested coordinates, then apply
  time-sensitive expiry filtering before display.
- Reuse cached candidates for programmatic refreshes, location changes, and
  settings changes when the country/language key is unchanged.
- Make the user-triggered `r` action explicitly bypass the cache.
- Preserve the existing generation/location checks and warning-progress UI.

## Non-goals

- Do not persist warnings in configuration or on disk.
- Do not cache weather forecasts, geocoding, air quality, or saved-location
  summaries.
- Do not change the public `wevva` / `wevva-warnings` API contracts.
- Do not cache a failed or cancelled provider lookup as an empty result.
- Do not add a cache framework or a configurable cache policy.

## Relevant code

- `wevva/app.py`
- `wevva/services/alerts.py`
- `wevva/messages.py`
- `wevva/screens/weather_screen.py`
- `wevva/config.py`
- `docs/architecture.md`

## Approach

Keep the cache close to the existing background alert orchestration in
`Wevva`. Before starting a worker-thread lookup, consult a private
session-memory cache. A cache hit should locally match the cached country
candidates to the current point, post the normal final alert update, and not
show progress. A cache miss (or a forced manual refresh) follows the existing
warning-query/progress path and stores the candidates only after a normal
completion.

The warning library now provides separate country-candidate retrieval and local
point matching. Wevva uses those APIs rather than duplicating source selection,
provider queries, geometry resolution, or native point-query handling.

## Acceptance criteria

- Searching Berlin and then Munich within 15 minutes reuses Germany's fetched
  candidates without calling the warning provider again, while displaying only
  warnings that match each city's coordinates.
- Cache identity changes when country code or warning language changes, but
  not when coordinates change within the same country.
- Empty successful candidate results are cached; failed and cancelled lookups
  are not.
- Expired entries cause a new lookup and are discarded.
- A manual `r` refresh bypasses an otherwise valid warning cache entry.
- Cached candidates whose alerts have since expired are not displayed.
- A cache hit does not show the warning progress panel; a cache miss retains
  the existing progress behavior.
- An old refresh/location still cannot overwrite the active location's alerts.

## Verification

- Add focused checks using mocked warning lookups and a controlled clock where
  practical; do not add a new test framework.
- Verify Berlin-to-Munich candidate reuse and matching, TTL expiry, empty
  success, error/cancellation, country/language key changes, and forced refresh
  behavior.
- Run `uv run python -m compileall -q wevva`.
- Perform a manual TUI check by revisiting a location and using `r` to force a
  fresh warning check. Record any live-provider behavior that cannot be
  verified deterministically.

## Decisions and notes

- Cache lifetime is 15 minutes for this task.
- This is intentionally TUI-session-only, not persistent data.
- The published `wevva-warnings>=0.3.5` dependency supplies the candidate-fetch
  and local-match boundary; this repository only consumes it.

## Outcome

Implemented a session-only country/language candidate cache in `Wevva`. A
Berlin lookup can now reuse the same Germany candidates for Munich, with local
coordinate matching on each display path. Empty successful results are cached,
failed or cancelled lookups are not, expiry uses a monotonic clock, and `r`
forces a fresh country query. Existing stale-refresh guards and progress events
remain in place. Focused cache checks and source compilation pass; live provider
and terminal rendering behavior remains environment-dependent. No changes to
`wevva-warnings` were made in this repository.
