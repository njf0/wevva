"""Build wevva's compact Natural Earth populated-place resource.

This maintenance script requires ``pyshp`` but the generated runtime resource
does not. Example:

    uv run --with pyshp python tools/build_natural_earth_places.py \
        /tmp/ne_50m_populated_places/ne_50m_populated_places.shp \
        wevva/data/natural_earth_50m_populated_places.json.gz
"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
from typing import Any

import shapefile


def _integer(properties: dict[str, Any], key: str, default: int) -> int:
    value = properties.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    return default


def build_resource(shapefile_path: Path) -> dict[str, Any]:
    places: list[list[object]] = []
    reader = shapefile.Reader(str(shapefile_path))
    for shape_record in reader.iterShapeRecords():
        properties = shape_record.record.as_dict()
        name = str(properties.get('NAME') or '').strip()
        points = shape_record.shape.points
        if not name or not points:
            continue
        longitude, latitude = points[0]
        places.append(
            [
                name,
                round(float(longitude), 4),
                round(float(latitude), 4),
                _integer(properties, 'SCALERANK', 10),
                _integer(properties, 'LABELRANK', 50),
                _integer(properties, 'POP_MAX', 0),
            ]
        )

    places.sort(key=lambda place: (place[3], place[4], -int(place[5]), place[0]))
    return {
        'source': 'Natural Earth 1:50m Populated Places',
        'version': '5.1.2',
        'precision': 4,
        'fields': ['name', 'longitude', 'latitude', 'scale_rank', 'label_rank', 'population'],
        'places': places,
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
