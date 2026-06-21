from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

JsonDict = dict[str, Any]
Position = list[float]


class GeoJSONError(ValueError):
    """Raised when geometry cannot be normalized into valid GeoJSON."""


def feature(
    geometry: JsonDict,
    properties: JsonDict | None = None,
    feature_id: str | int | None = None,
    *,
    precision: int = 6,
) -> JsonDict:
    item: JsonDict = {
        "type": "Feature",
        "properties": properties or {},
        "geometry": geometry,
    }
    if feature_id is not None:
        item["id"] = feature_id
    return normalize_geojson(item, precision=precision)


def feature_collection(
    features: Iterable[JsonDict],
    *,
    precision: int = 6,
) -> JsonDict:
    return normalize_geojson(
        {"type": "FeatureCollection", "features": list(features)},
        precision=precision,
    )


def normalize_geojson(obj: JsonDict, *, precision: int = 6) -> JsonDict:
    data = deepcopy(obj)
    kind = data.get("type")

    if kind == "FeatureCollection":
        data["features"] = [
            normalize_geojson(item, precision=precision)
            for item in data.get("features", [])
        ]
        return data

    if kind == "Feature":
        if "properties" not in data or data["properties"] is None:
            data["properties"] = {}
        data["geometry"] = normalize_geometry(data["geometry"], precision=precision)
        return data

    return normalize_geometry(data, precision=precision)


def normalize_geometry(geometry: JsonDict, *, precision: int = 6) -> JsonDict:
    if not isinstance(geometry, dict):
        raise GeoJSONError("GeoJSON geometry must be an object.")

    kind = geometry.get("type")
    if kind == "GeometryCollection":
        return {
            "type": "GeometryCollection",
            "geometries": [
                normalize_geometry(item, precision=precision)
                for item in geometry.get("geometries", [])
            ],
        }

    if kind not in {
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
    }:
        raise GeoJSONError(f"Unsupported GeoJSON geometry type: {kind!r}")

    coordinates = _round_coordinates(geometry.get("coordinates"), precision)

    if kind == "Point":
        _validate_position(coordinates)
    elif kind in {"MultiPoint", "LineString"}:
        for position in coordinates:
            _validate_position(position)
    elif kind in {"MultiLineString", "Polygon"}:
        for line in coordinates:
            for position in line:
                _validate_position(position)
    elif kind == "MultiPolygon":
        for polygon in coordinates:
            for ring in polygon:
                for position in ring:
                    _validate_position(position)

    if kind == "Polygon":
        coordinates = [_close_ring(ring) for ring in coordinates]
    elif kind == "MultiPolygon":
        coordinates = [
            [_close_ring(ring) for ring in polygon]
            for polygon in coordinates
        ]

    return {"type": kind, "coordinates": coordinates}


def geometry_bounds(geometry: JsonDict) -> tuple[float, float, float, float]:
    normalized = normalize_geometry(geometry)
    positions = list(_iter_positions(normalized["coordinates"]))
    if not positions:
        raise GeoJSONError("Cannot compute bounds for empty geometry.")
    lons = [pos[0] for pos in positions]
    lats = [pos[1] for pos in positions]
    return min(lons), min(lats), max(lons), max(lats)


def merge_feature_properties(item: JsonDict, properties: JsonDict) -> JsonDict:
    data = normalize_geojson(item)
    if data["type"] == "FeatureCollection":
        for child in data["features"]:
            child["properties"] = {**properties, **child.get("properties", {})}
        return data
    if data["type"] == "Feature":
        data["properties"] = {**properties, **data.get("properties", {})}
        return data
    return feature(data, properties)


def _round_coordinates(value: Any, precision: int) -> Any:
    if _is_number(value):
        return round(float(value), precision)
    if isinstance(value, tuple):
        return [_round_coordinates(item, precision) for item in value]
    if isinstance(value, list):
        return [_round_coordinates(item, precision) for item in value]
    raise GeoJSONError("Coordinates must be nested numeric arrays.")


def _close_ring(ring: list[Position]) -> list[Position]:
    if len(ring) < 3:
        raise GeoJSONError("A polygon ring needs at least three positions.")
    closed = [list(position) for position in ring]
    if closed[0][:2] != closed[-1][:2]:
        closed.append(list(closed[0]))
    if len(closed) < 4:
        raise GeoJSONError("A closed polygon ring needs at least four positions.")
    return closed


def _iter_positions(value: Any) -> Iterable[Position]:
    if _is_position(value):
        yield value
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_positions(item)


def _is_position(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= 2
        and _is_number(value[0])
        and _is_number(value[1])
    )


def _validate_position(position: Any) -> None:
    if not _is_position(position):
        raise GeoJSONError(f"Invalid GeoJSON position: {position!r}")
    lon = float(position[0])
    lat = float(position[1])
    if not -180.0 <= lon <= 180.0:
        raise GeoJSONError(f"Longitude out of range: {lon}")
    if not -90.0 <= lat <= 90.0:
        raise GeoJSONError(f"Latitude out of range: {lat}")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)

