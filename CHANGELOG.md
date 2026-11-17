# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Mark saved locations covered by fresh cached weather warnings with `!` on
  the Dashboard and full Map View, prioritizing them in the compact Dashboard
  sample.

### Changed

- Hide the Dashboard tropical panel and its compact tab after an empty storm
  result, giving the selected weather alert the full detail row. Restore the
  panel when activity returns and retain the last layout during refreshes or
  provider failures.
- Update `wevva-warnings` to 0.6.1 for strict tropical discovery that distinguishes
  required provider failures from successful empty results.
- Remove redundant full-location tooltips from Dashboard place labels.

### Fixed

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
