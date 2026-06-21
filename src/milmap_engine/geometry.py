from __future__ import annotations

import math
from collections.abc import Callable
from typing import Iterable

from .geojson import GeoJSONError, feature, feature_collection, normalize_geometry
from .projection import LocalProjector, projector_for_bounds, projector_for_coordinates

Coordinate = list[float] | tuple[float, float]
Geometry = dict[str, object]

EARTH_RADIUS_M = 6_371_008.8
METERS_PER_MILE = 1609.344


def point(coord: Coordinate) -> Geometry:
    return normalize_geometry({"type": "Point", "coordinates": list(coord)})


def line_string(coords: Iterable[Coordinate]) -> Geometry:
    coordinates = [list(coord) for coord in coords]
    if len(coordinates) < 2:
        raise GeoJSONError("A LineString needs at least two coordinates.")
    return normalize_geometry({"type": "LineString", "coordinates": coordinates})


def polygon(rings: Iterable[Iterable[Coordinate]]) -> Geometry:
    coordinates = [[list(coord) for coord in ring] for ring in rings]
    if not coordinates:
        raise GeoJSONError("A Polygon needs at least one ring.")
    return normalize_geometry({"type": "Polygon", "coordinates": coordinates})


def bbox_polygon(bounds: Coordinate | list[float] | tuple[float, float, float, float]) -> Geometry:
    west, south, east, north = _bounds(bounds)
    return polygon([
        [
            [west, south],
            [east, south],
            [east, north],
            [west, north],
        ]
    ])


def buffer_point(center: Coordinate, radius_m: float, *, steps: int = 64) -> Geometry:
    _require_positive(radius_m, "radius_m")
    if steps < 8:
        raise GeoJSONError("Buffer steps must be at least 8.")
    ring = [
        destination_point(center, bearing, radius_m)
        for bearing in _linspace(0.0, 360.0, steps, endpoint=False)
    ]
    return polygon([ring])


def range_ring(center: Coordinate, radius_m: float, *, steps: int = 64) -> Geometry:
    _require_positive(radius_m, "radius_m")
    if steps < 8:
        raise GeoJSONError("Range-ring steps must be at least 8.")
    coordinates = [
        destination_point(center, bearing, radius_m)
        for bearing in _linspace(0.0, 360.0, steps + 1, endpoint=True)
    ]
    return line_string(coordinates)


def sector(
    center: Coordinate,
    radius_m: float,
    start_bearing: float,
    end_bearing: float,
    *,
    steps: int = 32,
) -> Geometry:
    _require_positive(radius_m, "radius_m")
    if steps < 2:
        raise GeoJSONError("Sector steps must be at least 2.")
    sweep = (float(end_bearing) - float(start_bearing)) % 360.0
    if math.isclose(sweep, 0.0):
        sweep = 360.0
    bearings = _linspace(float(start_bearing), float(start_bearing) + sweep, steps + 1)
    ring = [list(center)]
    ring.extend(destination_point(center, bearing, radius_m) for bearing in bearings)
    return polygon([ring])


def regular_polygon(
    center: Coordinate,
    radius_m: float,
    sides: int,
    *,
    rotation_deg: float = 0.0,
) -> Geometry:
    _require_positive(radius_m, "radius_m")
    if sides < 3:
        raise GeoJSONError("A regular polygon needs at least three sides.")
    ring = [
        destination_point(center, rotation_deg + (360.0 * idx / sides), radius_m)
        for idx in range(sides)
    ]
    return polygon([ring])


def corridor(
    coords: Iterable[Coordinate],
    width_m: float,
    *,
    precision: int = 6,
) -> Geometry:
    _require_positive(width_m, "width_m")
    coordinates = _dedupe_consecutive([list(coord) for coord in coords])
    if len(coordinates) < 2:
        raise GeoJSONError("A corridor needs at least two unique coordinates.")

    projector = projector_for_coordinates(coordinates)
    points = [projector.project(coord) for coord in coordinates]
    radius = width_m / 2.0
    left = _offset_side(points, radius, side=1.0)
    right = _offset_side(points, radius, side=-1.0)
    ring_points = left + list(reversed(right))
    ring = [projector.unproject(point) for point in ring_points]
    return normalize_geometry({"type": "Polygon", "coordinates": [ring]}, precision=precision)


def square_grid(
    bounds: list[float] | tuple[float, float, float, float],
    cell_size_m: float,
    *,
    precision: int = 6,
    max_features: int = 10_000,
) -> dict[str, object]:
    _require_positive(cell_size_m, "cell_size_m")
    west, south, east, north = _bounds(bounds)
    projector = projector_for_bounds([west, south, east, north])
    min_x, min_y = projector.project([west, south])
    max_x, max_y = projector.project([east, north])
    features = []
    row = 0
    y = min_y
    while y < max_y:
        col = 0
        x = min_x
        while x < max_x:
            ring = [
                projector.unproject((x, y)),
                projector.unproject((min(x + cell_size_m, max_x), y)),
                projector.unproject((min(x + cell_size_m, max_x), min(y + cell_size_m, max_y))),
                projector.unproject((x, min(y + cell_size_m, max_y))),
            ]
            features.append(
                feature(
                    {"type": "Polygon", "coordinates": [ring]},
                    {"grid": "square", "row": row, "col": col},
                    precision=precision,
                )
            )
            _require_feature_limit(features, max_features)
            x += cell_size_m
            col += 1
        y += cell_size_m
        row += 1
    return feature_collection(features, precision=precision)


def hex_grid(
    bounds: list[float] | tuple[float, float, float, float],
    radius_m: float,
    *,
    precision: int = 6,
    max_features: int = 10_000,
) -> dict[str, object]:
    _require_positive(radius_m, "radius_m")
    west, south, east, north = _bounds(bounds)
    projector = projector_for_bounds([west, south, east, north])
    min_x, min_y = projector.project([west, south])
    max_x, max_y = projector.project([east, north])

    x_spacing = 1.5 * radius_m
    y_spacing = math.sqrt(3.0) * radius_m
    clip_bounds = (min_x, min_y, max_x, max_y)
    features = []
    col = 0
    x = min_x - radius_m
    while x <= max_x + radius_m:
        y_offset = (col % 2) * (y_spacing / 2.0)
        row = 0
        y = min_y - y_spacing + y_offset
        while y <= max_y + y_spacing:
            ring_points = [
                (
                    x + radius_m * math.cos(math.radians(angle)),
                    y + radius_m * math.sin(math.radians(angle)),
                )
                for angle in range(0, 360, 60)
            ]
            clipped_points = _clip_polygon_to_rect(ring_points, clip_bounds)
            if len(clipped_points) >= 3 and abs(_polygon_area(clipped_points)) > 1.0:
                ring = [projector.unproject(point) for point in clipped_points]
                features.append(
                    feature(
                        {"type": "Polygon", "coordinates": [ring]},
                        {"grid": "hex", "row": row, "col": col},
                        precision=precision,
                    )
                )
                _require_feature_limit(features, max_features)
            y += y_spacing
            row += 1
        x += x_spacing
        col += 1
    return feature_collection(features, precision=precision)


def destination_point(origin: Coordinate, bearing_deg: float, distance_m: float) -> list[float]:
    lon1 = math.radians(float(origin[0]))
    lat1 = math.radians(float(origin[1]))
    bearing = math.radians(float(bearing_deg))
    angular_distance = float(distance_m) / EARTH_RADIUS_M

    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_distance)
        + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
    )
    lon = (math.degrees(lon2) + 540.0) % 360.0 - 180.0
    lat = math.degrees(lat2)
    return [lon, lat]


def haversine_m(a: Coordinate, b: Coordinate) -> float:
    lon1, lat1 = map(math.radians, [float(a[0]), float(a[1])])
    lon2, lat2 = map(math.radians, [float(b[0]), float(b[1])])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    value = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(value))


def meters_from_parameters(parameters: dict[str, object], base_name: str) -> float:
    for suffix, multiplier in {
        "_m": 1.0,
        "_meters": 1.0,
        "_km": 1000.0,
        "_kilometers": 1000.0,
        "_miles": METERS_PER_MILE,
    }.items():
        key = f"{base_name}{suffix}"
        if key in parameters:
            return float(parameters[key]) * multiplier
    if base_name in parameters:
        return float(parameters[base_name])
    raise GeoJSONError(f"Missing distance parameter for {base_name}.")


def _offset_side(points: list[tuple[float, float]], radius: float, *, side: float) -> list[tuple[float, float]]:
    normals = [_segment_normal(points[idx], points[idx + 1], side) for idx in range(len(points) - 1)]
    result: list[tuple[float, float]] = []
    for idx, point_value in enumerate(points):
        if idx == 0:
            result.append(_add(point_value, _mul(normals[0], radius)))
            continue
        if idx == len(points) - 1:
            result.append(_add(point_value, _mul(normals[-1], radius)))
            continue

        prev_a = _add(points[idx - 1], _mul(normals[idx - 1], radius))
        prev_b = _add(points[idx], _mul(normals[idx - 1], radius))
        curr_a = _add(points[idx], _mul(normals[idx], radius))
        curr_b = _add(points[idx + 1], _mul(normals[idx], radius))
        intersection = _line_intersection(prev_a, prev_b, curr_a, curr_b)
        if intersection is None or _distance(intersection, point_value) > radius * 6.0:
            averaged = _unit(_add(normals[idx - 1], normals[idx]))
            if averaged == (0.0, 0.0):
                averaged = normals[idx]
            intersection = _add(point_value, _mul(averaged, radius))
        result.append(intersection)
    return result


def _segment_normal(a: tuple[float, float], b: tuple[float, float], side: float) -> tuple[float, float]:
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    length = math.hypot(dx, dy)
    if math.isclose(length, 0.0):
        raise GeoJSONError("Line coordinates must not contain repeated points only.")
    return (-dy / length * side, dx / length * side)


def _line_intersection(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
) -> tuple[float, float] | None:
    x1, y1 = a1
    x2, y2 = a2
    x3, y3 = b1
    x4, y4 = b2
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if math.isclose(denominator, 0.0):
        return None
    px = (
        (x1 * y2 - y1 * x2) * (x3 - x4)
        - (x1 - x2) * (x3 * y4 - y3 * x4)
    ) / denominator
    py = (
        (x1 * y2 - y1 * x2) * (y3 - y4)
        - (y1 - y2) * (x3 * y4 - y3 * x4)
    ) / denominator
    return px, py


def _dedupe_consecutive(coords: list[list[float]]) -> list[list[float]]:
    result: list[list[float]] = []
    for coord in coords:
        if not result or result[-1][:2] != coord[:2]:
            result.append(coord)
    return result


def _bounds(bounds: Coordinate | list[float] | tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    if len(bounds) != 4:
        raise GeoJSONError("Bounds must be [west, south, east, north].")
    west, south, east, north = [float(value) for value in bounds]
    if west >= east:
        raise GeoJSONError("Bounds west value must be smaller than east value.")
    if south >= north:
        raise GeoJSONError("Bounds south value must be smaller than north value.")
    return west, south, east, north


def _linspace(start: float, stop: float, count: int, endpoint: bool = True) -> list[float]:
    if count <= 0:
        return []
    if count == 1:
        return [start]
    divisor = count - 1 if endpoint else count
    step = (stop - start) / divisor
    return [start + step * idx for idx in range(count)]


def _require_positive(value: float, name: str) -> None:
    if float(value) <= 0.0:
        raise GeoJSONError(f"{name} must be positive.")


def _require_feature_limit(features: list[object], max_features: int) -> None:
    if max_features <= 0:
        raise GeoJSONError("max_features must be positive.")
    if len(features) > max_features:
        raise GeoJSONError(f"Generated grid exceeds max_features={max_features}.")


def _clip_polygon_to_rect(
    points: list[tuple[float, float]],
    bounds: tuple[float, float, float, float],
) -> list[tuple[float, float]]:
    min_x, min_y, max_x, max_y = bounds

    def clip(
        candidates: list[tuple[float, float]],
        inside: Callable[[tuple[float, float]], bool],
        intersect: Callable[[tuple[float, float], tuple[float, float]], tuple[float, float]],
    ) -> list[tuple[float, float]]:
        if not candidates:
            return []
        output: list[tuple[float, float]] = []
        previous = candidates[-1]
        previous_inside = inside(previous)
        for current in candidates:
            current_inside = inside(current)
            if current_inside:
                if not previous_inside:
                    output.append(intersect(previous, current))
                output.append(current)
            elif previous_inside:
                output.append(intersect(previous, current))
            previous = current
            previous_inside = current_inside
        return output

    clipped = points
    clipped = clip(clipped, lambda p: p[0] >= min_x, lambda a, b: _intersect_vertical(a, b, min_x))
    clipped = clip(clipped, lambda p: p[0] <= max_x, lambda a, b: _intersect_vertical(a, b, max_x))
    clipped = clip(clipped, lambda p: p[1] >= min_y, lambda a, b: _intersect_horizontal(a, b, min_y))
    clipped = clip(clipped, lambda p: p[1] <= max_y, lambda a, b: _intersect_horizontal(a, b, max_y))
    return clipped


def _intersect_vertical(
    a: tuple[float, float],
    b: tuple[float, float],
    x: float,
) -> tuple[float, float]:
    dx = b[0] - a[0]
    if math.isclose(dx, 0.0):
        return b
    ratio = (x - a[0]) / dx
    return x, a[1] + ratio * (b[1] - a[1])


def _intersect_horizontal(
    a: tuple[float, float],
    b: tuple[float, float],
    y: float,
) -> tuple[float, float]:
    dy = b[1] - a[1]
    if math.isclose(dy, 0.0):
        return b
    ratio = (y - a[1]) / dy
    return a[0] + ratio * (b[0] - a[0]), y


def _polygon_area(points: list[tuple[float, float]]) -> float:
    area = 0.0
    for idx, point_value in enumerate(points):
        next_value = points[(idx + 1) % len(points)]
        area += point_value[0] * next_value[1] - next_value[0] * point_value[1]
    return area / 2.0


def _add(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return a[0] + b[0], a[1] + b[1]


def _mul(a: tuple[float, float], scalar: float) -> tuple[float, float]:
    return a[0] * scalar, a[1] * scalar


def _unit(a: tuple[float, float]) -> tuple[float, float]:
    length = math.hypot(a[0], a[1])
    if math.isclose(length, 0.0):
        return 0.0, 0.0
    return a[0] / length, a[1] / length


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])
