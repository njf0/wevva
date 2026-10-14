# Geographic data

`natural_earth_50m_map_units.json.gz` is generated from Natural Earth 5.1.1's
1:50m Admin-0 Map Units dataset. The 1:50m and 1:10m populated-place resources
are generated from Natural Earth 5.1.2; general maps use the former and focused
alert maps use the latter. Natural Earth data is public domain. The compact
resources contain only the geometry or label fields used by wevva, including
place ISO country codes used to avoid repeated polygon scans and Admin-1 names
used for focused-map regional context. Coordinates are rounded to four decimal
places and gzip-compressed; shapefile tooling is not required at runtime.

Regenerate them from the downloaded Natural Earth shapefiles with:

```bash
uv run --with pyshp python tools/build_natural_earth.py \
    path/to/ne_50m_admin_0_map_units.shp \
    wevva/data/natural_earth_50m_map_units.json.gz

uv run --with pyshp python tools/build_natural_earth_places.py \
    path/to/ne_50m_populated_places.shp \
    wevva/data/natural_earth_50m_populated_places.json.gz

uv run --with pyshp python tools/build_natural_earth_places.py \
    path/to/ne_10m_populated_places.shp \
    wevva/data/natural_earth_10m_populated_places.json.gz
```
