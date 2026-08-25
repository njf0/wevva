"""Shared logical raster and Braille composition for geographic scopes."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import math

from rich.style import Style
from rich.text import Text

from wevva.geography import GeographicViewport, ProjectedPoint


ProjectedPolygon = tuple[tuple[ProjectedPoint, ...], ...]

_BRAILLE_BITS = (0x01, 0x08, 0x02, 0x10, 0x04, 0x20, 0x40, 0x80)


def projected_aspect_ratio(viewport: GeographicViewport) -> float:
    """Return width/height after the same local projection used for drawing."""
    if viewport.width <= 0.0 or viewport.height <= 0.0:
        return 1.0
    return viewport.width / viewport.height


def preferred_geographic_height(
    viewport: GeographicViewport,
    *,
    available_width: int,
    minimum: int,
    maximum: int,
) -> int:
    """Return a clamped content height for a 2×4 terminal-cell raster."""
    minimum = max(1, minimum)
    maximum = max(minimum, maximum)
    available_width = max(1, available_width)
    aspect = projected_aspect_ratio(viewport)
    natural_height = math.ceil(available_width / (2.0 * aspect))
    return min(maximum, max(minimum, natural_height))

@dataclass(slots=True)
class GeographicFrame:
    """Rendered geographic cells that can receive terminal-sized overlays."""

    characters: list[list[str]]
    styles: list[list[Style | str | None]]
    canvas: GeographicCanvas

    def marker(self, point: ProjectedPoint, glyph: str, style: str | None) -> tuple[int, int]:
        column, row = self.canvas.cell_position(point)
        self.characters[row][column] = glyph
        self.styles[row][column] = style
        return column, row

    def label(
        self,
        marker: tuple[int, int],
        label: str,
        style: str | None,
        occupied: set[tuple[int, int]],
        *,
        gap: int = 0,
    ) -> bool:
        if not label:
            return False
        column, row = marker
        width = len(self.characters[0])
        height = len(self.characters)
        candidates = tuple(
            candidate
            for row_offset in (0, -1, 1, -2, 2)
            for candidate in (
                (
                    column + 1 + gap,
                    row + row_offset,
                    range(column + 1, column + 1 + gap),
                ),
                (
                    column - len(label) - gap,
                    row + row_offset,
                    range(column - gap, column),
                ),
            )
        )
        for start, label_row, spacer_columns in candidates:
            label_cells = {(start + offset, label_row) for offset in range(len(label))}
            spacer_cells = {(spacer_column, label_row) for spacer_column in spacer_columns}
            cells = label_cells | spacer_cells
            if start < 0 or start + len(label) > width or label_row < 0 or label_row >= height:
                continue
            if cells & occupied:
                continue
            for spacer_column, spacer_row in spacer_cells:
                self.characters[spacer_row][spacer_column] = ' '
                self.styles[spacer_row][spacer_column] = None
            for offset, character in enumerate(label):
                self.characters[label_row][start + offset] = character
                self.styles[label_row][start + offset] = style
            occupied.update(cells)
            return True
        return False

    def to_text(self) -> Text:
        rendered = Text()
        for row, (characters, styles) in enumerate(zip(self.characters, self.styles)):
            for character, style in zip(characters, styles):
                rendered.append(character, style=style or '')
            if row != len(self.characters) - 1:
                rendered.append('\n')
        return rendered


class GeographicCanvas:
    """Shared 2×4-per-cell raster with Braille terminal composition."""

    def __init__(self, width: int, height: int, viewport: GeographicViewport) -> None:
        self.width = max(1, width)
        self.height = max(1, height)
        self.pixel_width = self.width * 2
        self.pixel_height = self.height * 4
        self.viewport = viewport.fitted(self.pixel_width / self.pixel_height)
        self._layers: dict[str, set[tuple[int, int]]] = {}
        self._offset_x = 0
        self._offset_y = 0

    def fill_polygons(self, polygons: Iterable[ProjectedPolygon], *, layer: str) -> None:
        target = self._layers.setdefault(layer, set())
        for polygon in polygons:
            if not polygon:
                continue
            filled = self._filled_ring(polygon[0])
            for hole in polygon[1:]:
                filled.difference_update(self._filled_ring(hole))
            target.update(filled)

    def polyline(self, points: Iterable[ProjectedPoint], *, layer: str) -> None:
        positions = [self.pixel_position(point) for point in points]
        target = self._layers.setdefault(layer, set())
        for first, second in zip(positions, positions[1:]):
            target.update(_line_points(first, second))
        if len(positions) == 1:
            target.add(positions[0])

    def point(self, point: ProjectedPoint, *, layer: str) -> None:
        self._layers.setdefault(layer, set()).add(self.pixel_position(point))

    def frame(
        self,
        layers: Iterable[tuple[str, str | None]],
        *,
        solid_braille_layers: Iterable[str] = (),
        centering_layers: Iterable[str] | None = None,
    ) -> GeographicFrame:
        layer_list = list(layers)
        solid_layers = set(solid_braille_layers)
        self._offset_x, self._offset_y = self._centering_offset(
            centering_layers
            if centering_layers is not None
            else (layer for layer, _style in layer_list)
        )
        characters = [[' ' for _ in range(self.width)] for _ in range(self.height)]
        styles: list[list[Style | str | None]] = [
            [None for _ in range(self.width)] for _ in range(self.height)
        ]
        layer_masks: list[list[list[int]]] = []
        for layer, _style in layer_list:
            masks = [[0 for _ in range(self.width)] for _ in range(self.height)]
            for raw_x, raw_y in self._layers.get(layer, ()):
                x = raw_x + self._offset_x
                y = raw_y + self._offset_y
                if 0 <= x < self.pixel_width and 0 <= y < self.pixel_height:
                    dot = (y % 4) * 2 + (x % 2)
                    masks[y // 4][x // 2] |= _BRAILLE_BITS[dot]
            layer_masks.append(masks)
        for row in range(self.height):
            for column in range(self.width):
                present = [
                    index
                    for index, masks in enumerate(layer_masks)
                    if masks[row][column]
                ]
                if not present:
                    continue
                top = present[-1]
                mask = layer_masks[top][row][column]
                solid_present = [
                    index
                    for index in present
                    if layer_list[index][0] in solid_layers
                ]
                solid_coverage = 0
                for index in solid_present:
                    solid_coverage |= layer_masks[index][row][column]
                if solid_coverage == 0xFF:
                    # A cell fully covered by filled geography must have one
                    # owner. Snap an internal warning/land boundary to the
                    # dominant layer instead of exposing unset Braille dots.
                    dominant = next(
                        (
                            index
                            for index in reversed(solid_present)
                            if layer_masks[index][row][column].bit_count() >= 4
                        ),
                        solid_present[0],
                    )
                    top = dominant
                    mask = 0xFF
                characters[row][column] = chr(0x2800 + mask)
                styles[row][column] = layer_list[top][1]
        return GeographicFrame(characters, styles, self)

    def pixel_position(self, point: ProjectedPoint) -> tuple[int, int]:
        x_fraction = (point.x - self.viewport.min_x) / self.viewport.width
        y_fraction = (self.viewport.max_y - point.y) / self.viewport.height
        return (
            round(x_fraction * (self.pixel_width - 1)),
            round(y_fraction * (self.pixel_height - 1)),
        )

    def cell_position(self, point: ProjectedPoint) -> tuple[int, int]:
        x, y = self.pixel_position(point)
        x += self._offset_x
        y += self._offset_y
        return (
            min(self.width - 1, max(0, x // 2)),
            min(self.height - 1, max(0, y // 4)),
        )

    def _centering_offset(self, layers: Iterable[str]) -> tuple[int, int]:
        """Balance visible raster margins without changing scale or geometry."""
        occupied = {
            point
            for layer in layers
            for point in self._layers.get(layer, ())
            if 0 <= point[0] < self.pixel_width and 0 <= point[1] < self.pixel_height
        }
        if not occupied:
            return 0, 0
        min_x = min(x for x, _y in occupied)
        max_x = max(x for x, _y in occupied)
        min_y = min(y for _x, y in occupied)
        max_y = max(y for _x, y in occupied)
        horizontal = round(((self.pixel_width - 1 - max_x) - min_x) / 2.0)
        vertical = round(((self.pixel_height - 1 - max_y) - min_y) / 2.0)
        return horizontal, vertical

    def _filled_ring(self, ring: tuple[ProjectedPoint, ...]) -> set[tuple[int, int]]:
        if len(ring) < 3:
            return set()
        points = [self._pixel_position_float(point) for point in ring]
        min_row = max(0, int(min(point[1] for point in points)))
        max_row = min(self.pixel_height - 1, int(max(point[1] for point in points)) + 1)
        filled: set[tuple[int, int]] = set()
        for y in range(min_row, max_row + 1):
            scan_y = y + 0.5
            intersections = []
            for first, second in zip(points, (*points[1:], points[0])):
                x1, y1 = first
                x2, y2 = second
                if (y1 > scan_y) == (y2 > scan_y):
                    continue
                intersections.append(x1 + (scan_y - y1) * (x2 - x1) / (y2 - y1))
            intersections.sort()
            for start, end in zip(intersections[0::2], intersections[1::2]):
                min_column = max(0, int(min(start, end)))
                max_column = min(self.pixel_width - 1, int(max(start, end)))
                for x in range(min_column, max_column + 1):
                    if min(start, end) <= x + 0.5 <= max(start, end):
                        filled.add((x, y))
        return filled

    def _pixel_position_float(self, point: ProjectedPoint) -> tuple[float, float]:
        return (
            (point.x - self.viewport.min_x) / self.viewport.width * self.pixel_width,
            (self.viewport.max_y - point.y) / self.viewport.height * self.pixel_height,
        )


def _line_points(first: tuple[int, int], second: tuple[int, int]) -> Iterable[tuple[int, int]]:
    x, y = first
    target_x, target_y = second
    delta_x = abs(target_x - x)
    step_x = 1 if x < target_x else -1
    delta_y = -abs(target_y - y)
    step_y = 1 if y < target_y else -1
    error = delta_x + delta_y
    while True:
        yield x, y
        if x == target_x and y == target_y:
            return
        doubled = 2 * error
        if doubled >= delta_y:
            error += delta_y
            x += step_x
        if doubled <= delta_x:
            error += delta_x
            y += step_y


__all__ = [
    'GeographicCanvas',
    'GeographicFrame',
    'ProjectedPolygon',
    'preferred_geographic_height',
    'projected_aspect_ratio',
]
