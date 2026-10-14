# NHC GIS forecast geometry and explicit fix metadata

## Status

Implemented in the sibling `wevva-warnings` checkout; live integration verified
on 10 October 2026. Release remains a separate step.

## Context

The NHC GIS RSS feed can retain an active cyclone summary after it stops
including the cone, track, and watch/warning asset items. On 10 October 2026,
the Atlantic feed exposed Post-Tropical Cyclone Isaias (`AL092026`) as a
summary-only item while the official GIS page still linked these current
assets:

- `/storm_graphics/api/AL092026_TRACK_latest.kmz`
- `/storm_graphics/api/AL092026_CONE_latest.kmz`
- `/storm_graphics/api/AL092026_WW_latest.kmz`

Consequently `wevva-warnings` returned Isaias with empty `data_urls` and
`geometries`, so Wevva correctly treated its track as unavailable.

The official track KMZ contains separate point placemarks whose descriptions
explicitly identify `12 hr Forecast`, `24 hr Forecast`, and later fixes. It
also contains line placemarks, but NHC explicitly states in the document that
the connecting lines are not forecast products. The current KMZ parser keeps
only placemark geometry and discards the explicit forecast-hour metadata.
Wevva must not reconstruct those hours from coordinate order.

## Required sibling changes

Implement the provider repair in `../wevva-warnings`, which owns NHC network
and format knowledge:

1. When a valid NHC summary has an ATCF identifier but its RSS group omits
   current GIS asset items, use NHC's documented current `/storm_graphics/api/`
   asset URLs for the track, cone, and watch/warning candidates. Missing or
   failed assets remain optional.
2. Parse forecast point placemarks separately from presentation LineStrings.
3. Preserve the explicit forecast hour and coordinates as structured forecast
   product points, using the existing `lead_hours`, `latitude`, and `longitude`
   keys consumed by Wevva.
4. Keep the provider's discrete points authoritative. Do not derive forecast
   hours from vertex order, valid timestamps, or line interpolation.
5. Add fixtures for a normal RSS-linked storm and a summary-only post-tropical
   storm matching the Isaias shape.

## Acceptance criteria

- Isaias-like summary-only entries retain their official available track and
  cone without making those layers mandatory.
- `get_tropical_products()` exposes explicit NHC 12/24/36-hour point data.
- The normalized track contains only official forecast fixes, not duplicate
  line geometry or inferred intermediate positions.
- Existing NHC/CPHC tests and the full `wevva-warnings` suite pass.
- Wevva retains the supplied fixes for viewport fitting and uses explicit daily
  leads for visible markers without adding provider-specific cadence logic.

## Verification

The live Atlantic feed returned Isaias with derived current track, cone, and
watch/warning asset URLs. Its official track resolved to three discrete future
fixes; Wevva retains the complete track and displays its daily fix as `24h`.
The structured coordinate-only product is consumed by the map without adding
a duplicate Forecast information tab.
