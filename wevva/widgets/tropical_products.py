"""Shared presentation of official tropical-system products."""

from __future__ import annotations

from datetime import datetime
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
    for index, product in enumerate(products):
        if _is_map_annotation_product(product):
            continue
        views = _product_views(product)
        for view in views:
            tab_id = f'{id_prefix}-{index}'
            if view != 'product':
                tab_id = f'{tab_id}-{view}'
            specs.append((tab_id, _product_view_label(product, view)))
    return specs


def tropical_product_widgets(
    product: TropicalProduct,
    *,
    view: str = 'product',
) -> list[Static | Markdown]:
    """Convert one provider product to safe Textual content widgets."""

    widgets: list[Static | Markdown] = []
    if product.content and view == 'product':
        if product.content_format == 'markdown':
            widgets.append(TropicalProductMarkdown(product.content))
        else:
            # Rich Text is already parsed content, so provider prose cannot be
            # reinterpreted as Rich markup or Markdown.
            widgets.append(Static(Text(product.content)))
    has_separate_data_view = any(
        candidate != 'product' for candidate in _product_views(product)
    )
    if (
        product.data
        and set(product.data) != {'product_code'}
        and (view != 'product' or not product.content or not has_separate_data_view)
    ):
        rendered = structured_tropical_product(product.data, view=view)
        if rendered is not None:
            widgets.append(Static(rendered))
    if product.url:
        link = Text('View official product', style='markdown.link')
        link.stylize(Style(link=product.url, underline=True))
        widgets.append(Static(link))
    if not widgets:
        widgets.append(Static('No product content is available.'))
    return widgets


def tropical_product_tab_target(
    tab_id: str,
    *,
    id_prefix: str = 'tropical-product',
) -> tuple[int, str] | None:
    """Resolve a generated product tab ID to its product and presentation."""

    prefix = f'{id_prefix}-'
    if not tab_id.startswith(prefix):
        return None
    suffix = tab_id[len(prefix):]
    view = 'product'
    for candidate in ('analysis', 'forecast', 'extents'):
        marker = f'-{candidate}'
        if suffix.endswith(marker):
            suffix = suffix.removesuffix(marker)
            view = candidate
            break
    if not suffix.isdigit():
        return None
    return int(suffix), view


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


def structured_tropical_product(
    data: dict[str, Any],
    *,
    view: str = 'product',
) -> Any | None:
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
        if view == 'analysis':
            return _analysis_table(analysis_data) if analysis_data else None
        if view == 'forecast':
            return (
                _forecast_table(rows, agency=_clean(data.get('agency')))
                if rows
                else None
            )
        if view == 'extents':
            extents = _extent_table(analysis_data, rows)
            return extents if extents.row_count else None
        if rows:
            return _forecast_table(rows, agency=_clean(data.get('agency')))
        if analysis_data is not None and _has_analysis_facts(analysis_data):
            return _analysis_table(analysis_data)
        return _flat_table(data)

    if view == 'analysis':
        return _analysis_table(data)
    if view == 'extents':
        extents = _extent_table(data, [])
        return extents if extents.row_count else None

    return _flat_table(data)


def _flat_table(data: dict[str, Any]) -> Table:
    table = Table(box=None, pad_edge=False, expand=False)
    table.add_column('Field', style='bold')
    table.add_column('Value')
    for label, value in _flatten_data(data):
        table.add_row(label, value)
    return table


def _analysis_table(data: dict[str, Any]) -> Table:
    table = Table(box=None, pad_edge=False, expand=False)
    table.add_column('Field', style='bold', no_wrap=True)
    table.add_column('Value')
    fields = [
        ('Type', _point_type, _has_type),
        ('Centre', _point_centre, _has_centre),
        ('Location', _point_location, _has_location),
        ('Movement', _point_movement, _has_movement),
        ('Wind', _point_wind, _has_wind),
        ('Pressure', _point_pressure, _has_pressure),
        ('Position accuracy', _point_accuracy, _has_accuracy),
    ]
    for label, renderer, present in fields:
        if present(data):
            table.add_row(label, renderer(data))
    return table


def _forecast_table(
    rows: list[dict[str, Any]],
    *,
    agency: str = '',
) -> Table:
    title_parts = [f'{agency} forecast'] if agency else []
    base_times = list(
        dict.fromkeys(
            _format_time(point.get('forecast_base_at'))
            for point in rows
            if point.get('forecast_base_at')
        )
    )
    if len(base_times) == 1:
        title_parts.append(f'base {base_times[0]}')
    title = ' · '.join(title_parts) or None
    table = Table(
        box=None,
        pad_edge=False,
        expand=False,
        title=title,
        title_justify='left',
    )
    fields = [
        ('Lead', _point_lead, lambda _point: True, True),
        ('Type', _point_type, _has_type, False),
        ('Centre', _point_centre, _has_centre, True),
        ('Location', _point_location, _has_location, False),
        ('Movement', _point_movement, _has_movement, False),
        ('Wind', _point_wind, _has_wind, False),
        ('Pressure', _point_pressure, _has_pressure, True),
        ('Accuracy', _point_accuracy, _has_accuracy, True),
    ]
    visible_fields = [
        field for field in fields if any(field[2](point) for point in rows)
    ]
    for label, _renderer, _present, no_wrap in visible_fields:
        table.add_column(label, no_wrap=no_wrap)
    for point in rows:
        table.add_row(
            *(
                renderer(point)
                for _label, renderer, _present, _no_wrap in visible_fields
            )
        )
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


def _point_lead(point: dict[str, Any]) -> str:
    lead = point.get('lead_hours')
    if isinstance(lead, (int, float)):
        return f'{lead:g}h'
    return str(point.get('forecast_label') or '')


def _format_time(value: object) -> str:
    if not value:
        return ''
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        return text
    rendered = parsed.strftime('%d %b %H:%M')
    offset = parsed.strftime('%z')
    if offset:
        rendered = f'{rendered} {offset[:3]}:{offset[3:]}'
    return rendered


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
        return ''
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
    return ''


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
    return wind or (f'gust {gust}' if gust else '')


def _point_location(point: dict[str, Any]) -> str:
    return str(point.get('location') or '')


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
    if movement or additions:
        return movement or ' / '.join(additions)

    cyclone_data = point.get('cyclone_data')
    storm_motion = (
        cyclone_data.get('storm_motion')
        if isinstance(cyclone_data, dict)
        else None
    )
    if not isinstance(storm_motion, dict):
        return ''
    direction = storm_motion.get('direction_toward')
    speed = storm_motion.get('speed_kt')
    parts: list[str] = []
    if direction is not None:
        parts.append(f'toward {direction}°')
    if speed is not None:
        parts.append(f'{speed} kt')
    return ' at '.join(parts)


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
    return ''


def _point_accuracy(point: dict[str, Any]) -> str:
    value = point.get('position_accuracy')
    return str(value) if value is not None else ''


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
    sources: list[tuple[str, dict[str, Any]]] = []
    if analysis is not None:
        sources.append(('Current', analysis))
    sources.extend((_point_lead(point), point) for point in points)
    extent_rows: list[tuple[str, str, str, str]] = []
    for horizon, source in sources:
        probability_circle = source.get('probability_circle')
        if isinstance(probability_circle, dict) and probability_circle:
            extent_rows.append(
                _extent_row(
                    horizon,
                    probability_circle,
                    default_type='Probability circle',
                )
            )
        wind_areas = source.get('wind_areas')
        if isinstance(wind_areas, list):
            for area in wind_areas:
                if isinstance(area, dict):
                    extent_rows.append(
                        _extent_row(
                            horizon,
                            area,
                            default_type='Wind area',
                        )
                    )
        wind_radii = source.get('wind_radii')
        if isinstance(wind_radii, list):
            for radius in wind_radii:
                if not isinstance(radius, dict):
                    continue
                extent_rows.append(
                    (
                        horizon,
                        'Wind radius',
                        _measurement_text(radius.get('threshold')),
                        _quadrant_radii_text(radius.get('radii')),
                    )
                )
        cyclone_data = source.get('cyclone_data')
        wind_contours = (
            cyclone_data.get('wind_contours')
            if isinstance(cyclone_data, dict)
            else None
        )
        if isinstance(wind_contours, list):
            for contour in wind_contours:
                if not isinstance(contour, dict):
                    continue
                wind_speed = contour.get('wind_speed_kt')
                threshold = f'{wind_speed} kt' if wind_speed is not None else ''
                radii = _named_radii_text(contour.get('radius_nm'), unit='nm')
                if threshold or radii:
                    extent_rows.append(
                        (horizon, 'Wind contour', threshold, radii)
                    )

    table = Table(box=None, pad_edge=False, expand=False)
    table.add_column('Lead', no_wrap=True)
    table.add_column('Type', no_wrap=True)
    table.add_column('Threshold', no_wrap=True)
    table.add_column('Extent')
    for row in extent_rows:
        table.add_row(*row)
    return table


def _extent_row(
    horizon: str,
    value: dict[str, Any],
    *,
    default_type: str,
) -> tuple[str, str, str, str]:
    return (
        horizon,
        str(value.get('type') or default_type),
        _measurement_text(value.get('threshold')),
        _axes_text(value.get('axes')),
    )


def _measurement_text(value: object) -> str:
    collection = _measurement_collection(value)
    if collection:
        return collection
    if not isinstance(value, dict) or value.get('value') is None:
        return ''
    unit = value.get('unit')
    return f'{value["value"]} {unit}' if unit else str(value['value'])


def _quadrant_radii_text(value: object) -> str:
    if not isinstance(value, dict):
        return ''
    unit = value.get('unit')
    labels = (
        ('northeast', 'NE'),
        ('southeast', 'SE'),
        ('southwest', 'SW'),
        ('northwest', 'NW'),
    )
    parts = [
        f'{label} {value[key]} {unit}'.rstrip()
        for key, label in labels
        if value.get(key) is not None
    ]
    return ' · '.join(parts)


def _named_radii_text(value: object, *, unit: str) -> str:
    if not isinstance(value, dict):
        return ''
    preferred = ('NE', 'SE', 'SW', 'NW', 'N', 'E', 'S', 'W')
    parts = [
        f'{key} {value[key]} {unit}'
        for key in preferred
        if value.get(key) is not None
    ]
    extras = sorted(
        (
            str(key),
            radius,
        )
        for key, radius in value.items()
        if radius is not None and str(key) not in preferred
    )
    parts.extend(
        f'{key} {radius} {unit}'
        for key, radius in extras
    )
    return ' · '.join(parts)


def _axes_text(value: object) -> str:
    if not isinstance(value, list):
        return ''
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
            components.append(
                f'{radius_type}: {radius_text}' if radius_type else radius_text
            )
        if components:
            axes.append(' · '.join(components))
    return '\n'.join(axes)


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
    if isinstance(source_values, dict) and source_values.get('movement_speed'):
        return True
    cyclone_data = point.get('cyclone_data')
    return isinstance(cyclone_data, dict) and isinstance(
        cyclone_data.get('storm_motion'),
        dict,
    )


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


def _has_accuracy(point: dict[str, Any]) -> bool:
    return point.get('position_accuracy') is not None


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


def _product_views(product: TropicalProduct) -> tuple[str, ...]:
    if not isinstance(product.data, dict):
        return ('product',)
    points = product.data.get('points')
    rows = (
        [point for point in points if isinstance(point, dict)]
        if isinstance(points, list)
        else []
    )
    analysis = product.data.get('analysis')
    analysis_data = analysis if isinstance(analysis, dict) else None
    standalone_analysis = (
        analysis_data is None
        and not rows
        and product.kind == 'analysis'
        and _has_analysis_facts(product.data)
    )
    views: list[str] = []
    if product.content:
        views.append('product')
    if analysis_data is not None and _has_analysis_facts(analysis_data):
        views.append('analysis')
    elif standalone_analysis:
        views.append('analysis')
    if rows:
        views.append('forecast')
    extent_analysis = (
        product.data
        if analysis_data is None and not rows and product.kind == 'analysis'
        else analysis_data
    )
    if _extent_table(extent_analysis, rows).row_count:
        views.append('extents')
    if (
        analysis_data is None
        and not rows
        and not product.content
        and not standalone_analysis
    ):
        views.append('product')
    if not views and analysis_data is None and not isinstance(points, list):
        views.append('product')
    return tuple(views)


def _has_analysis_facts(data: dict[str, Any]) -> bool:
    checks = (
        _has_type,
        _has_centre,
        _has_location,
        _has_movement,
        _has_wind,
        _has_pressure,
        _has_accuracy,
    )
    return any(check(data) for check in checks)


def _product_view_label(product: TropicalProduct, view: str) -> str:
    if view == 'analysis':
        return product.label if product.kind == 'analysis' else 'Analysis'
    if view == 'forecast':
        return product.label if product.kind == 'forecast' else 'Forecast'
    if view == 'extents':
        return 'Extents'
    return product.label


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
    'tropical_product_tab_target',
    'tropical_product_widgets',
]
