# Task 0036: First-run saved locations

## Status

Complete — implemented and verified on 17 November 2026.

## Context

A fresh Wevva profile should open onto a useful Dashboard with six saved
locations showing varied weather. Existing installations and the maintainer's
own saved locations must be preserved.

The requested places are:

| Location | Country | Country code |
| --- | --- | --- |
| Yellowknife | Canada | CA |
| Hilo | United States | US |
| Georgetown | Guyana | GY |
| Accra | Ghana | GH |
| Baguio City | Philippines | PH |
| Westport | New Zealand | NZ |

Use ordinary place metadata and names; the supplied emojis and weather
descriptions are not part of the seed data.

## Problem

An installation without saved locations has no useful initial Dashboard map.
Checking only whether the normalized saved list is empty would also mistake
existing profiles, deliberate deletions, or unreadable configuration for new
users. Repeated initialization could restore unwanted locations or overwrite
personal data.

The Dashboard already gives its place-sampling limit a floor of six. That
numerical limit alone does not establish that all six seed labels survive
collision placement and are visible at supported terminal sizes.

## Desired outcome

On an ordinary first launch with no existing Wevva configuration, locations,
or cache, copy a bundled six-location starter list into saved locations and
open the Dashboard through the existing startup path.

When a fresh user runs `wevva setup` first, offer an explicit accept/decline
choice before applying the starter list. Honour the same choice with
`setup --no-launch`. Existing profiles receive no automatic additions.

## Scope and approach

1. During implementation, resolve each place through the existing
   `services.geocoding.search_places()` functionality. Inspect candidates and
   verify the intended country and administrative area, especially Hilo,
   Georgetown, Baguio City, and Westport. Convert the chosen results through
   `location_metadata_from_place()` and the shared configuration serializer.
2. Check in the resulting complete starter metadata in a small bundled data
   definition: coordinates, elevation where supplied, canonical name,
   administrative area, country, country code, and IANA timezone. Record the
   lookup provenance/date. Preserve provider omissions rather than inventing
   values, including timezone abbreviations. Startup copies this data without
   needing six live geocoding requests.
3. Detect fresh-profile eligibility before any CLI mutation, setup save, or
   launch can create configuration/cache state. Use the existing configuration
   path and platform/environment-aware Wevva cache location. Treat existing
   configuration or cache state conservatively as an existing installation;
   an empty, malformed, or unreadable config is not proof of a fresh profile.
   Do not create directories merely to inspect eligibility.
4. Keep automatic initialization in the CLI startup/setup boundary, with
   persistence helpers in `config.py` where appropriate. Loading preferences,
   importing the package, asking for CLI help, and using the public Python API
   must remain free of initialization writes.
5. For an eligible ordinary launch, persist a copy of the six entries once,
   using the existing normalization and coordinate deduplication. Retain
   explicit CLI location/default choices and other preferences. Do not make a
   starter place the user's configured default implicitly; the current saved
   location fallback can provide initial Dashboard coordinates.
6. For eligible setup, show the six names and an "Add these six starter
   locations?" confirmation, defaulting to accept. Apply the choice only when
   setup completes successfully. A decline must persist across later launches;
   cancellation must not seed or partially save setup. Existing profiles skip
   automatic seeding and the fresh-profile prompt.
7. Persist enough initialization/decision state to prevent reseeding after
   the user deletes some or all starter locations. Recheck existing saved
   data before writing; never replace an existing list from a stale initial
   eligibility decision. Follow existing `ConfigWriteError` reporting and do
   not claim a successful save after a write failure.
8. Retain a Dashboard place limit of at least six whenever six places are
   available. Verify actual rendered visibility and interaction for all six
   starters in compact and normal Dashboard map presentations. Adjust only
   the relevant sampling/placement behavior if that check exposes a problem.
9. Document first-run behavior and the setup choice in the README and record
   the user-facing change under `CHANGELOG.md` → `Unreleased`. Update the
   architecture/development notes if persistence or startup boundaries change.

## Non-goals

- Adding starters to an existing user's list or replacing their default place.
- Topping up a user-managed list to six after deletions or a setup decline.
- A general-purpose starter-pack manager, reset action, or migration framework.
- Bundling forecasts or warning data, or changing weather/provider refreshes.
- Unrelated changes to the current uncommitted Dashboard/release work.

## Relevant code

- `wevva/cli.py`: `main`, `setup`, `_run_setup_wizard`,
  `_apply_default_location_mutations`, `_resolve_initial_location`.
- `wevva/config.py`: paths, normalized preferences, saved-location persistence.
- `wevva/location_metadata.py` and `wevva/services/geocoding.py`.
- `wevva/services/warning_cache.py`: existing platform-aware cache path.
- `wevva/app.py`: `locations_for_dashboard` and saved-summary ownership.
- `wevva/widgets/dashboard_world_map.py`: `_place_label_limit`, sampling,
  and callout placement.
- `tests/test_config_persistence.py`, `tests/test_geocoding.py`,
  `tests/test_dashboard_screen.py`, and focused CLI/setup coverage as needed.

## Acceptance criteria

- The bundled list contains exactly the six intended places, with metadata
  obtained through Wevva's geocoding functionality and verified by country.
- An eligible ordinary first launch saves all six once and reaches Dashboard.
- Fresh setup accepts or declines the complete list, including with
  `--no-launch`; decline and subsequent deletion do not trigger reseeding.
- Existing saved locations, default locations, and preferences are preserved.
  Existing empty/corrupt profiles and cache-only installations are not seeded.
- Help, preference reads, and Python API use do not create starter state.
- Initialization itself needs no network; provider failures do not remove the
  saved starters. Forecast and warning fetching keep their existing behavior.
- All six starter places are visible and selectable in the Dashboard map at
  supported compact and normal sizes. Lists with fewer than six stay as chosen
  by the user; larger lists retain the current sampling policy and six-place
  minimum budget.
- Verification never writes the maintainer's real config or cache directories.

## Verification

Keep testing narrow: the maintainer explicitly requests avoiding long runs.

- Use temporary config/cache directories and mocked launch/provider boundaries
  for a small set of first-run, existing-profile, setup-choice, deletion, and
  write-failure regressions. Include an existing saved list appearing between
  the initial eligibility check and persistence.
- Validate bundled metadata and independent copies without live API calls.
- Run only the affected test cases, plus a focused rendered Dashboard check
  using the actual six locations at compact and normal sizes. Reuse existing
  harnesses; do not run full unittest discovery or broad warning-provider tests.
- Run `uv run python -m compileall -q wevva` after implementation.
- Report the live geocoding lookup separately from deterministic tests and
  clearly state any unexercised terminal/font or live forecast behavior.

## Decisions and notes

- Implemented behavior: ordinary fresh launches seed automatically; fresh setup
  offers the choice before seeding. Existing profiles are never auto-filled.
- Six is the minimum display capacity when enough places exist, not a forced
  minimum number of user-owned locations.
- The pre-existing working-tree changes were committed separately before
  implementation; the application version remains 1.0.0.
- Config-file existence records the first-run decision. No additional marker
  or preference schema field is needed. Even an empty config directory or a
  cache-only installation blocks automatic initialization.
- At 120×30, Georgetown's full name and temperature collided with Accra's
  callout. Dashboard places now use the shared planner's name-only fallback
  when complete text cannot fit. The marker stays on its projected cell;
  larger maps restore the temperature. Full World Locations labels keep their
  existing complete-text policy.

## Outcome

Bundled all six locations in `wevva/data/starter_locations.json`, obtained
through live `search_places()` calls on 17 November 2026 and converted through
the shared metadata/configuration helpers. Country and administrative area
checks disambiguated the returned candidates. The JSON records the source and
lookup date; startup needs no further geocoding.

Fresh CLI launches save the six places once before applying explicit default
location changes. Fresh setup offers accept/decline before its other prompts,
including with `--no-launch`; cancellation saves nothing. Configuration/cache
checks and exclusive first-run file creation protect existing profiles,
including a config created while setup is open. Preference reads, help, and
Python geocoding API calls remain free of initialization writes. Declining or
deleting all starters does not restore them later.

Verification:

- The final focused run passed 25 tests in 28.825 seconds:
  `tests.test_first_run`, `tests.test_config_persistence`, and
  `DashboardScreenTests.test_six_starters_remain_visible_and_selectable_after_resize`.
- The Dashboard test exercised initial Dashboard startup, all six visible and
  non-overlapping labels, keyboard selection at 80×24, 120×30, and 160×45,
  temperature restoration after expansion, and mixed tropical/location labels.
- Eight shared callout-planner tests and one mounted full World Locations map
  check also passed during the placement fix.
- `uv run --no-sync python -m compileall -q wevva` and `git diff --check` passed.
  Validation used a temporary uv cache because the sandbox disallows the
  default uv cache path.

Tests used temporary config/cache paths and mocked launch/provider boundaries;
the maintainer's real locations and caches were not written. Live forecasts,
warning-provider responses, and real terminal/font/emoji presentation were not
exercised. No broad test discovery, release build, or publication was run.
