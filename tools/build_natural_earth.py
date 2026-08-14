"""Build wevva's compact Natural Earth map-unit resource.

This maintenance script requires ``pyshp`` but the generated runtime resource
does not. Example:

    uv run --with pyshp python tools/build_natural_earth.py \
        /tmp/ne_50m_admin_0_map_units/ne_50m_admin_0_map_units.shp \
        wevva/data/natural_earth_50m_map_units.json.gz
"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
from typing import Any

import shapefile


def _iso_code(properties: dict[str, Any]) -> str | None:
    for key in ('ISO_A2', 'ISO_A2_EH', 'POSTAL'):
        value = properties.get(key)
        if isinstance(value, str) and len(value) == 2 and value.isalpha():
            return value.upper()
    return None


def _rounded_ring(raw_ring: Any) -> list[list[float]]:
    ring: list[list[float]] = []
    for raw_point in raw_ring if isinstance(raw_ring, (list, tuple)) else ():
        if not isinstance(raw_point, (list, tuple)) or len(raw_point) < 2:
            continue
        point = [round(float(raw_point[0]), 4), round(float(raw_point[1]), 4)]
        if not ring or point != ring[-1]:
            ring.append(point)
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring if len(ring) >= 4 else []


def _polygons(geometry: dict[str, Any]) -> list[list[list[list[float]]]]:
    geometry_type = geometry.get('type')
    coordinates = geometry.get('coordinates')
    if geometry_type == 'Polygon':
        raw_polygons = [coordinates]
    elif geometry_type == 'MultiPolygon':
        raw_polygons = coordinates
    else:
        return []

    polygons = []
    for raw_polygon in raw_polygons if isinstance(raw_polygons, (list, tuple)) else ():
        rings = [_rounded_ring(raw_ring) for raw_ring in raw_polygon]
        rings = [ring for ring in rings if ring]
        if rings:
            polygons.append(rings)
    return polygons


def build_resource(shapefile_path: Path) -> dict[str, Any]:
    units: dict[str, dict[str, Any]] = {}
    reader = shapefile.Reader(str(shapefile_path))
    for shape_record in reader.iterShapeRecords():
        properties = shape_record.record.as_dict()
        code = _iso_code(properties)
        if code is None:
            continue
        polygons = _polygons(shape_record.shape.__geo_interface__)
        if not polygons:
            continue
        unit = units.setdefault(code, {'names': [], 'polygons': []})
        name = str(properties.get('NAME') or properties.get('GEOUNIT') or code).strip()
        if name and name not in unit['names']:
            unit['names'].append(name)
        unit['polygons'].extend(polygons)

    return {
        'source': 'Natural Earth 1:50m Admin-0 Map Units',
        'version': '5.1.1',
        'precision': 4,
        'units': dict(sorted(units.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('shapefile', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()

    resource = build_resource(args.shapefile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(resource, ensure_ascii=False, separators=(',', ':')).encode()
    with gzip.GzipFile(filename=str(args.output), mode='wb', mtime=0) as archive:
        archive.write(payload)


if __name__ == '__main__':
    main()
