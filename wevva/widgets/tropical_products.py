"""Shared presentation of official tropical-system products."""

from __future__ import annotations

from typing import Any, Sequence

from rich.console import Group
from rich.style import Style
from rich.table import Table
from rich.text import Text
from textual.widgets import Markdown, Static
from wevva_warnings import TropicalProduct, TropicalSystem


class TropicalProductMarkdown(Markdown):
    """Provider Markdown with compact root-heading spacing."""

    DEFAULT_CSS = """
    TropicalProductMarkdown MarkdownH1 {
        margin: 1 0;
        width: 100%;
    }

    """


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
            widgets.append(TropicalProductMarkdown(product.content))
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


def structured_tropical_product(data: dict[str, Any]) -> Any:
    """Render structured provider data without assuming one feed shape."""

    points = data.get('points')
    rows = (
        [point for point in points if isinstance(point, dict)]
        if isinstance(points, list)
        else []
    )
    analysis = data.get('analysis')
    analysis_data = analysis if isinstance(analysis, dict) else None
    if rows or analysis_data is not None:
        parts: list[Any] = []
        if analysis_data is not None:
            analysis_table = _fact_table(analysis_data)
            if analysis_table.row_count:
                _append_section(parts, 'Analysis', analysis_table)
        if rows:
            _append_section(parts, 'Forecast', _forecast_table(rows))
        extents = _extent_table(analysis_data, rows)
        if extents.row_count:
            _append_section(parts, 'Official extents', extents)

        extra_data = {
            key: value
            for key, value in data.items()
            if key not in {'analysis', 'points'}
        }
        extra_table = _flat_table(extra_data)
        if extra_table.row_count:
            _append_section(parts, 'Product details', extra_table)
        return Group(*parts)

    return _flat_table(data)


def _append_section(parts: list[Any], title: str, content: Any) -> None:
    if parts:
        parts.append(Text(''))
    parts.extend((Text(title, style='bold'), content))


def _flat_table(data: dict[str, Any]) -> Table:
    table = Table(box=None, pad_edge=False, expand=False)
    table.add_column('Field', style='bold')
    table.add_column('Value')
    for label, value in _flatten_data(data):
        table.add_row(label, value)
    return table


def _forecast_table(rows: list[dict[str, Any]]) -> Table:
    table = Table(box=None, pad_edge=False, expand=False)
    table.add_column('Lead', no_wrap=True)
    table.add_column('Forecast details')
    for point in rows:
        table.add_row(_point_lead(point), _point_details(point))
    return table


def _point_details(point: dict[str, Any]) -> str:
    fields = [
        ('Valid', _point_valid, _has_valid),
        ('Type', _point_type, _has_type),
        ('Centre', _point_centre, _has_centre),
        ('Location', _point_location, _has_location),
        ('Movement', _point_movement, _has_movement),
        ('Wind', _point_wind, _has_wind),
        ('Pressure', _point_pressure, _has_pressure),
    ]
    return '\n'.join(
        f'{label}: {renderer(point)}'
        for label, renderer, present in fields
        if present(point)
    ) or '—'


def _fact_table(data: dict[str, Any]) -> Table:
    table = Table(box=None, pad_edge=False, expand=False)
    table.add_column('Field', style='bold')
    table.add_column('Value')
    fields = [
        ('Valid', _point_valid, _has_valid),
        ('Type', _point_type, _has_type),
        ('Centre', _point_centre, _has_centre),
        ('Location', _point_location, _has_location),
        ('Movement', _point_movement, _has_movement),
        ('Wind', _point_wind, _has_wind),
        ('Pressure', _point_pressure, _has_pressure),
    ]
    for label, renderer, present in fields:
        if present(data):
            table.add_row(label, renderer(data))
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
    return str(value) if value else '—'


def _point_lead(point: dict[str, Any]) -> str:
    lead = point.get('lead_hours')
    if isinstance(lead, (int, float)):
        return f'{lead:g}h'
    return str(point.get('forecast_label') or '—')


def _point_type(point: dict[str, Any]) -> str:
    value = (
        point.get('classification')
        or point.get('intensity')
        or point.get('forecast_type')
    )
    cyclone_data = point.get('cyclone_data')
    if value is None and isinstance(cyclone_data, dict):
        value = cyclone_data.get('development')
    if not value:
        return '—'
    rendered = str(value).replace('_', ' ')
    details = point.get('classification_details')
    if isinstance(details, dict):
        additions = [
            str(detail)
            for detail in details.values()
            if detail and str(detail).casefold() not in rendered.casefold()
        ]
        if additions:
            rendered = f'{rendered} · {" / ".join(dict.fromkeys(additions))}'
    return rendered


def _point_centre(point: dict[str, Any]) -> str:
    latitude, longitude = point.get('latitude'), point.get('longitude')
    if isinstance(latitude, (int, float)) and isinstance(
        longitude,
        (int, float),
    ):
        return _coordinates(float(latitude), float(longitude))
    return '—'


def _point_wind(point: dict[str, Any]) -> str:
    source_values = point.get('source_values')
    source_wind = (
        _measurement_collection(source_values.get('maximum_wind'))
        if isinstance(source_values, dict)
        else ''
    )
    source_gust = (
        _measurement_collection(source_values.get('maximum_gust'))
        if isinstance(source_values, dict)
        else ''
    )
    wind = source_wind
    for key, unit in (('maximum_wind', ''), ('maximum_wind_mps', ' m/s')):
        value = point.get(key)
        if value is not None and not wind:
            wind = f'{value}{unit}'
            break
    gust = source_gust
    for key, unit in (('maximum_gust', ''), ('maximum_gust_mps', ' m/s')):
        value = point.get(key)
        if value is not None and not gust:
            gust = f'{value}{unit}'
            break

    cyclone_data = point.get('cyclone_data')
    if not wind and isinstance(cyclone_data, dict):
        wind = cyclone_data.get('maximum_wind')
        if isinstance(wind, dict) and wind.get('wind_speed_kt') is not None:
            if wind.get('wind_speed_gust_kt') is not None:
                gust = f'{wind["wind_speed_gust_kt"]} kt'
            wind = f'{wind["wind_speed_kt"]} kt'
    if wind and gust:
        return f'{wind}; gust {gust}'
    return wind or (f'gust {gust}' if gust else '—')


def _point_location(point: dict[str, Any]) -> str:
    return str(point.get('location') or '—')


def _point_movement(point: dict[str, Any]) -> str:
    movement = str(point.get('movement') or '')
    source_values = point.get('source_values')
    collection = (
        source_values.get('movement_speed')
        if isinstance(source_values, dict)
        else None
    )
    values, condition = _measurement_parts(collection)
    additions = [value for value in values if value not in movement]
    if condition and condition not in movement:
        additions.append(condition)
    if movement and additions:
        return f'{movement} / {" / ".join(additions)}'
    return movement or ' / '.join(additions) or '—'


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


def _measurement_parts(value: object) -> tuple[list[str], str]:
    if not isinstance(value, dict):
        return [], ''
    measurements: list[str] = []
    values = value.get('values')
    if isinstance(values, list):
        for measurement in values:
            if not isinstance(measurement, dict):
                continue
            raw_value = measurement.get('value')
            condition = measurement.get('condition')
            if raw_value is not None:
                unit = measurement.get('unit')
                rendered = f'{raw_value} {unit}' if unit else str(raw_value)
                if condition:
                    rendered = f'{condition} · {rendered}'
                measurements.append(rendered)
            elif condition:
                measurements.append(str(condition))
    condition = value.get('condition')
    return list(dict.fromkeys(measurements)), str(condition or '')


def _measurement_collection(value: object) -> str:
    measurements, condition = _measurement_parts(value)
    rendered = ' / '.join(measurements)
    if condition and rendered:
        return f'{condition} · {rendered}'
    return rendered or condition


def _extent_table(
    analysis: dict[str, Any] | None,
    points: list[dict[str, Any]],
) -> Table:
    table = Table(box=None, pad_edge=False, expand=False)
    table.add_column('Lead', no_wrap=True)
    table.add_column('Official extent')
    sources: list[tuple[str, dict[str, Any]]] = []
    if analysis is not None:
        sources.append(('Current', analysis))
    sources.extend((_point_lead(point), point) for point in points)
    for horizon, source in sources:
        probability_circle = source.get('probability_circle')
        if isinstance(probability_circle, dict) and probability_circle:
            table.add_row(
                horizon,
                _extent_details(probability_circle, default_type='Probability circle'),
            )
        wind_areas = source.get('wind_areas')
        if not isinstance(wind_areas, list):
            continue
        for area in wind_areas:
            if not isinstance(area, dict):
                continue
            table.add_row(
                horizon,
                _extent_details(area, default_type='Wind area'),
            )
    return table


def _extent_details(value: dict[str, Any], *, default_type: str) -> str:
    details = [str(value.get('type') or default_type)]
    if threshold := _measurement_collection(value.get('threshold')):
        details.append(f'Threshold: {threshold}')
    if extent := _axes_text(value.get('axes')):
        if extent != '—':
            details.append(f'Extent: {extent}')
    return '\n'.join(details)


def _axes_text(value: object) -> str:
    if not isinstance(value, list):
        return '—'
    axes: list[str] = []
    for axis in value:
        if not isinstance(axis, dict):
            continue
        components = []
        if direction := axis.get('direction'):
            components.append(str(direction))
        radius_type = str(axis.get('radius_type') or '')
        radii = axis.get('radii')
        rendered_radii: list[str] = []
        if isinstance(radii, list):
            for radius in radii:
                if not isinstance(radius, dict) or radius.get('value') is None:
                    continue
                unit = radius.get('unit')
                rendered = f'{radius["value"]} {unit}' if unit else str(radius['value'])
                individual_type = radius.get('type')
                if individual_type:
                    rendered = f'{individual_type}: {rendered}'
                rendered_radii.append(rendered)
        if rendered_radii:
            radius_text = ' / '.join(rendered_radii)
            components.append(f'{radius_type}: {radius_text}' if radius_type else radius_text)
        if components:
            axes.append(' · '.join(components))
    return '\n'.join(axes) or '—'


def _has_valid(point: dict[str, Any]) -> bool:
    return any(
        point.get(key) is not None
        for key in ('valid_at', 'time', 'forecast_type')
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


def _has_location(point: dict[str, Any]) -> bool:
    return bool(point.get('location'))


def _has_movement(point: dict[str, Any]) -> bool:
    if point.get('movement'):
        return True
    source_values = point.get('source_values')
    return isinstance(source_values, dict) and bool(source_values.get('movement_speed'))


def _has_wind(point: dict[str, Any]) -> bool:
    if any(
        point.get(key) is not None
        for key in (
            'maximum_wind',
            'maximum_wind_mps',
            'maximum_gust',
            'maximum_gust_mps',
        )
    ):
        return True
    source_values = point.get('source_values')
    if isinstance(source_values, dict) and any(
        source_values.get(key) for key in ('maximum_wind', 'maximum_gust')
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
