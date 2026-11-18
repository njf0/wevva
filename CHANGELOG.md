# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Start fresh installations with six geocoded saved locations: Yellowknife,
  Hilo, Georgetown (Guyana), Accra, Baguio City, and Westport (New Zealand).
  First-time `setup` offers an accept/decline choice; existing profiles and
  caches are preserved, and deleted starters are not restored.
- Mark saved locations covered by fresh cached weather warnings with `!` on
  the Dashboard and full Map View, prioritizing them in the compact Dashboard
  sample.

### Changed

- Keep the Dashboard tropical panel and its compact tab hidden until storms
  are found, giving the selected weather alert the full detail row from
  startup. Hide them after an empty storm result and retain the last layout
  during refreshes or provider failures.
- Update `wevva-warnings` to 0.6.1 for strict tropical discovery that distinguishes
  required provider failures from successful empty results.
- Remove redundant full-location tooltips from Dashboard place labels.

### Fixed

- Keep Dashboard temperature and rain fields separated at `100%`, size hourly
  readings and daily ranges to their content, and keep daily wind readings
  complete when forecasts arrive after the initial layout. Retain the forecast
  panel's outer padding around warnings and other content, and use spare daily
  table width for extra separation after temperature ranges and rain percentages.
- Keep place-search input focused when results arrive so typing can continue
  without clicking back into the field.
- Right-align Dashboard forecast numbers and give wind directions consistent
  spacing. Fit hourly columns to the displayed readings so one-cell padding
  is available in narrower rails while preserving complete values and units.
- Keep crowded Dashboard city labels visible by omitting their temperature
  when a full label cannot fit; restore it as map space becomes available.
- Preserve complete abbreviated dates and their separation from condition
  codes in cramped Dashboard daily forecasts.
- Keep the configured default pinned on the Dashboard map without treating it
  as a saved location, and remove a former default's legacy saved copy when the
  default changes.

## [1.0.0] - 2026-11-08

Initial stable release. See the [1.0.0 release notes](docs/releases/1.0.0.md)
for its major changes.

[Unreleased]: https://github.com/njf0/wevva/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/njf0/wevva/releases/tag/v1.0.0
