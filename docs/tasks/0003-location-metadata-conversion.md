# Task 0003: Canonicalise location metadata conversion

## Status

Proposed

## Context

Open-Meteo geocoding results are converted to `LocationMetadata` in the CLI,
public API, and search-result widget. The repeated mappings have begun to
diverge.

## Problem

`wevva/cli.py`, `wevva/api.py`, and `wevva/widgets/search_results.py` each
translate the same raw place shape. In particular, the CLI drops elevation and
the API applies coordinate coercion differently from the widget.

## Desired outcome

There is one small, well-named conversion from a normalized geocoder result to
`LocationMetadata`, used consistently wherever a place is selected or returned
by the public API.

## Scope

- Add a canonical conversion at the location/geocoding boundary.
- Replace duplicate geocoder-to-location mappings in the CLI, public API, and
  search results widget.
- Preserve the existing config-specific conversion and normalization path.
- Add focused standard-library tests for complete and incomplete place data.

## Non-goals

- Do not change the persisted location JSON format.
- Do not make `LocationMetadata` immutable or introduce a generic mapper
  framework.
- Do not change geocoding results exposed by `search_places`.

## Relevant code

- `wevva/location_metadata.py`
- `wevva/services/geocoding.py`
- `wevva/cli.py`
- `wevva/api.py`
- `wevva/widgets/search_results.py`
- `wevva/config.py`

## Approach

Use one direct helper or factory appropriate to the existing location module.
It should preserve validated coordinates, elevation, names, country data, and
the normalized `tz_identifier` field. Keep config deserialization separate,
because it validates persisted user input rather than provider output.

## Acceptance criteria

- CLI search, TUI selection, and `geocode()` produce equivalent
  `LocationMetadata` for the same normalized place result.
- Elevation and timezone are retained consistently.
- Existing saved locations and default-location migration continue to work.
- Duplicate raw-place mapping functions are removed.

## Verification

- Add focused `unittest` coverage for conversion behavior.
- Run `uv run python -m unittest discover -s tests`.
- Run `uv run python -m compileall -q wevva`.
- Manually search for a place and confirm its displayed location details.

## Decisions and notes

Keep this boundary deliberately small; it is not a new domain layer.

## Outcome

To be completed when the task is finished.
