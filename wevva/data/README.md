# Geographic data

`natural_earth_50m_map_units.json.gz` is generated from Natural Earth 5.1.1's
1:50m Admin-0 Map Units dataset. Natural Earth data is public domain. The
resource contains only ISO-keyed Polygon/MultiPolygon coordinates, rounded to
four decimal places and gzip-compressed; shapefile tooling is not required at
runtime.

Regenerate it from the downloaded Natural Earth shapefile with:

```bash
uv run --with pyshp python tools/build_natural_earth.py \
    path/to/ne_50m_admin_0_map_units.shp \
    wevva/data/natural_earth_50m_map_units.json.gz
```
