"""Shared presentation of official tropical-system products."""

from __future__ import annotations

from typing import Any, Sequence

from rich.console import Group
from rich.style import Style
from rich.table import Table
from rich.text import Text
from textual.widgets import Markdown, Static
from wevva_warnings import TropicalProduct, TropicalSystem


def tropical_product_tab_specs(
    observation: TropicalSystem,
    products: Sequence[TropicalProduct],
    *,
    id_prefix: str = 'tropical-product',
) -> list[tuple[str, str]]:
    """Return stable, content-backed product choices for one observation."""

    specs: list[tuple[str, str]] = []
    if _has_us_forecast_summary(observation):
        specs.append((f'{id_prefix}-forecast', 'Forecast'))
    specs.extend(
        (f'{id_prefix}-{index}', product.label)
        for index, product in enumerate(products)
        if not _is_map_annotation_product(product)
    )
    return specs


def tropical_product_widgets(
    product: TropicalProduct,
) -> list[Static | Markdown]:
    """Convert one provider product to safe Textual content widgets."""

    widgets: list[Static | Markdown] = []
    if product.content:
        if product.content_format == 'markdown':
            widgets.append(Markdown(product.content))
        else:
            # Rich Text is already parsed content, so provider prose cannot be
            # reinterpreted as Rich markup or Markdown.
            widgets.append(Static(Text(product.content)))
    if product.data and set(product.data) != {'product_code'}:
        widgets.append(Static(structured_tropical_product(product.data)))
    if product.url:
        link = Text('View official product', style='markdown.link')
        link.stylize(Style(link=product.url, underline=True))
        widgets.append(Static(link))
    if not product.content and not product.data:
        widgets.append(Static('No product content is available.'))
    return widgets


def tropical_forecast_summary(observation: TropicalSystem) -> Group:
    """Render useful discovery prose for an NHC/CPHC forecast choice."""

    parts: list[Any] = []
    heading = _clean(observation.headline) or _clean(observation.name) or 'Forecast'
    parts.append(Text(heading, style='bold'))
    if summary := _clean(observation.summary):
        parts.extend((Text(''), Text(summary)))
    if url := _clean(observation.url):
        link = Text('View official source', style='markdown.link')
        link.stylize(Style(link=url, underline=True))
        parts.extend((Text(''), link))
    return Group(*parts)


def structured_tropical_product(data: dict[str, Any]) -> Table:
    """Render structured provider data without assuming one feed shape."""

    points = data.get('points')
    if isinstance(points, list) and any(isinstance(point, dict) for point in points):
        rows = [point for point in points if isinstance(point, dict)]
        table = Table(box=None, pad_edge=False, expand=False)
        columns = [
            ('Valid', _point_valid, any(_has_valid(point) for point in rows)),
            ('Type', _point_type, any(_has_type(point) for point in rows)),
            ('Centre', _point_centre, any(_has_centre(point) for point in rows)),
            ('Wind', _point_wind, any(_has_wind(point) for point in rows)),
            (
                'Pressure',
                _point_pressure,
                any(_has_pressure(point) for point in rows),
            ),
        ]
        visible = [
            (label, renderer)
            for label, renderer, present in columns
            if present
        ]
        for label, _renderer in visible:
            table.add_column(label, no_wrap=label != 'Type')
        for point in rows:
            table.add_row(*(renderer(point) for _label, renderer in visible))
        return table

    table = Table(box=None, pad_edge=False, expand=False)
    table.add_column('Field', style='bold')
    table.add_column('Value')
    for label, value in _flatten_data(data):
        table.add_row(label, value)
    return table


def _flatten_data(
    data: dict[str, Any],
    prefix: str = '',
) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for key, value in data.items():
        if key in {'latitude', 'longitude'}:
            continue
        label = f'{prefix} {key}'.strip().replace('_', ' ').title()
        if isinstance(value, dict):
            rows.extend(_flatten_data(value, label))
        elif isinstance(value, (str, int, float)):
            rows.append((label, str(value)))
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    if isinstance(latitude, (int, float)) and isinstance(
        longitude,
        (int, float),
    ):
        rows.insert(
            0,
            (
                f'{prefix} Centre'.strip(),
                _coordinates(float(latitude), float(longitude)),
            ),
        )
    return rows


def _point_valid(point: dict[str, Any]) -> str:
    value = point.get('valid_at') or point.get('time') or point.get('forecast_type')
    if value:
        return str(value)
    lead = point.get('lead_hours')
    return f'+{lead:g} h' if isinstance(lead, (int, float)) else '—'


def _point_type(point: dict[str, Any]) -> str:
    value = (
        point.get('classification')
        or point.get('intensity')
        or point.get('forecast_type')
    )
    cyclone_data = point.get('cyclone_data')
    if value is None and isinstance(cyclone_data, dict):
        value = cyclone_data.get('development')
    return str(value).replace('_', ' ').title() if value else '—'


def _point_centre(point: dict[str, Any]) -> str:
    latitude, longitude = point.get('latitude'), point.get('longitude')
    if isinstance(latitude, (int, float)) and isinstance(
        longitude,
        (int, float),
    ):
        return _coordinates(float(latitude), float(longitude))
    return '—'


def _point_wind(point: dict[str, Any]) -> str:
    for key, unit in (('maximum_wind', ''), ('maximum_wind_mps', ' m/s')):
        value = point.get(key)
        if value is not None:
            return f'{value}{unit}'
    cyclone_data = point.get('cyclone_data')
    if isinstance(cyclone_data, dict):
        wind = cyclone_data.get('maximum_wind')
        if isinstance(wind, dict) and wind.get('wind_speed_kt') is not None:
            gust = (
                f' (gust {wind["wind_speed_gust_kt"]} kt)'
                if wind.get('wind_speed_gust_kt') is not None
                else ''
            )
            return f'{wind["wind_speed_kt"]} kt{gust}'
    return '—'


def _point_pressure(point: dict[str, Any]) -> str:
    for key, unit in (('minimum_pressure', ''), ('minimum_pressure_hpa', ' hPa')):
        value = point.get(key)
        if value is not None:
            return f'{value}{unit}'
    cyclone_data = point.get('cyclone_data')
    if (
        isinstance(cyclone_data, dict)
        and cyclone_data.get('minimum_pressure') is not None
    ):
        return f'{cyclone_data["minimum_pressure"]} hPa'
    return '—'


def _has_valid(point: dict[str, Any]) -> bool:
    return any(
        point.get(key) is not None
        for key in ('valid_at', 'time', 'forecast_type', 'lead_hours')
    )


def _has_type(point: dict[str, Any]) -> bool:
    if any(
        point.get(key)
        for key in ('classification', 'intensity', 'forecast_type')
    ):
        return True
    cyclone_data = point.get('cyclone_data')
    return isinstance(cyclone_data, dict) and bool(cyclone_data.get('development'))


def _has_centre(point: dict[str, Any]) -> bool:
    return isinstance(point.get('latitude'), (int, float)) and isinstance(
        point.get('longitude'),
        (int, float),
    )


def _has_wind(point: dict[str, Any]) -> bool:
    if any(
        point.get(key) is not None
        for key in ('maximum_wind', 'maximum_wind_mps')
    ):
        return True
    cyclone_data = point.get('cyclone_data')
    return isinstance(cyclone_data, dict) and isinstance(
        cyclone_data.get('maximum_wind'),
        dict,
    )


def _has_pressure(point: dict[str, Any]) -> bool:
    if any(
        point.get(key) is not None
        for key in ('minimum_pressure', 'minimum_pressure_hpa')
    ):
        return True
    cyclone_data = point.get('cyclone_data')
    return (
        isinstance(cyclone_data, dict)
        and cyclone_data.get('minimum_pressure') is not None
    )


def _has_us_forecast_summary(observation: TropicalSystem) -> bool:
    source = _clean(observation.source).casefold()
    return source.startswith(('nhc_gis_', 'cphc_gis_')) and bool(
        _clean(observation.headline) or _clean(observation.summary)
    )


def _is_map_annotation_product(product: TropicalProduct) -> bool:
    if (
        product.content
        or not isinstance(product.data, dict)
        or set(product.data) != {'points'}
    ):
        return False
    points = product.data.get('points')
    annotation_fields = {'latitude', 'longitude', 'lead_hours'}
    return bool(points) and isinstance(points, list) and all(
        isinstance(point, dict)
        and {'latitude', 'longitude'} <= set(point)
        and set(point) <= annotation_fields
        for point in points
    )


def _coordinates(latitude: float, longitude: float) -> str:
    return (
        f'{abs(latitude):.1f}°{"N" if latitude >= 0 else "S"} '
        f'{abs(longitude):.1f}°{"E" if longitude >= 0 else "W"}'
    )


def _clean(value: object) -> str:
    return value.strip() if isinstance(value, str) else ''


__all__ = [
    'structured_tropical_product',
    'tropical_forecast_summary',
    'tropical_product_tab_specs',
    'tropical_product_widgets',
]
