from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

from .geojson import GeoJSONError, geometry_bounds, normalize_geojson
from .geometry import haversine_m

STANDARD_METADATA_KEYS = {
    "phase_id",
    "phase_name",
    "source_type",
    "source_name",
    "source_url",
    "retrieved_at",
    "confidence",
    "warnings",
    "assumptions",
    "dependencies",
    "placement_rationale",
    "evidence",
    "candidate_score",
    "constraints_checked",
    "osm_type",
    "osm_id",
    "rejected_alternatives",
    "selected_role",
}


def validate_scenario_payload(
    payload: dict[str, Any],
    *,
    validation_rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rules = validation_rules or {}
    max_features = int(rules.get("max_features", 10_000))
    issues: list[dict[str, Any]] = []

    if not payload.get("scenario_id"):
        _add_issue(issues, "error", "missing_scenario_id", "Scenario payload is missing scenario_id.")
    if not payload.get("scenario_name"):
        _add_issue(issues, "error", "missing_scenario_name", "Scenario payload is missing scenario_name.")

    geojson = payload.get("geojson")
    if isinstance(geojson, dict):
        try:
            normalize_geojson(geojson)
        except GeoJSONError as exc:
            _add_issue(issues, "error", "invalid_geojson", str(exc), path="geojson")
    else:
        _add_issue(issues, "error", "missing_geojson", "Scenario payload is missing combined GeoJSON.")

    layers = [item for item in payload.get("layers", []) if isinstance(item, dict)]
    objects = [item for item in payload.get("objects", []) if isinstance(item, dict)]
    total_features = _feature_count(geojson) if isinstance(geojson, dict) else 0

    if total_features > max_features:
        _add_issue(
            issues,
            "warning",
            "feature_count_high",
            f"Scenario has {total_features} features, above the configured limit of {max_features}.",
        )

    route_rules = rules.get("route_quality", {})
    placement_rules = rules.get("placement_reasoning", {})
    layer_reports = [
        _validate_layer(
            layer,
            index,
            issues,
            max_features=max_features,
            route_rules=route_rules,
            placement_rules=placement_rules,
        )
        for index, layer in enumerate(layers)
    ]
    object_reports = [
        _validate_object(item, index, issues, bounds=_scenario_bounds(payload), placement_rules=placement_rules)
        for index, item in enumerate(objects)
    ]
    _check_duplicate_names(layers, "layer", issues)
    _check_duplicate_names(objects, "object", issues)

    phase_reports = _phase_reports(layer_reports, object_reports, issues)
    warning_count = sum(1 for issue in issues if issue["severity"] == "warning")
    error_count = sum(1 for issue in issues if issue["severity"] == "error")

    return {
        "status": "error" if error_count else "warning" if warning_count else "pass",
        "summary": {
            "scenario_id": payload.get("scenario_id"),
            "scenario_name": payload.get("scenario_name"),
            "layer_count": len(layers),
            "object_count": len(objects),
            "feature_count": total_features,
            "warning_count": warning_count,
            "error_count": error_count,
        },
        "issues": issues,
        "layers": layer_reports,
        "objects": object_reports,
        "phases": phase_reports,
    }


def _validate_layer(
    layer: dict[str, Any],
    index: int,
    issues: list[dict[str, Any]],
    *,
    max_features: int,
    route_rules: Any,
    placement_rules: Any,
) -> dict[str, Any]:
    layer_id = str(layer.get("id") or f"layer_{index + 1}")
    metadata = _layer_metadata(layer)
    geojson = layer.get("geojson")
    feature_count = _feature_count(geojson) if isinstance(geojson, dict) else 0
    geometry_types = _geometry_types(geojson) if isinstance(geojson, dict) else []
    pipeline = str(layer.get("plan", {}).get("pipeline", ""))
    phase_id = _optional_str(metadata.get("phase_id"))
    route_metrics = _route_metrics(layer)

    if not layer.get("id"):
        _add_issue(issues, "error", "missing_layer_id", "Layer is missing id.", path=f"layers[{index}]")
    if not layer.get("type"):
        _add_issue(issues, "error", "missing_layer_type", "Layer is missing type.", path=f"layers[{index}]", layer_id=layer_id)
    if not layer.get("name"):
        _add_issue(issues, "warning", "missing_layer_name", "Layer is missing name.", path=f"layers[{index}]", layer_id=layer_id)
    if not layer.get("style"):
        _add_issue(issues, "warning", "missing_layer_style", "Layer is missing style.", path=f"layers[{index}]", layer_id=layer_id, phase_id=phase_id)

    if not isinstance(geojson, dict):
        _add_issue(issues, "error", "missing_layer_geojson", "Layer is missing GeoJSON.", path=f"layers[{index}]", layer_id=layer_id, phase_id=phase_id)
    else:
        try:
            normalize_geojson(geojson)
        except GeoJSONError as exc:
            _add_issue(issues, "error", "invalid_layer_geojson", str(exc), path=f"layers[{index}].geojson", layer_id=layer_id, phase_id=phase_id)
        if feature_count == 0:
            _add_issue(issues, "warning", "empty_layer", "Layer produced no features.", path=f"layers[{index}].geojson", layer_id=layer_id, phase_id=phase_id)
        if feature_count > max_features:
            _add_issue(
                issues,
                "warning",
                "layer_feature_count_high",
                f"Layer has {feature_count} features, above the configured limit of {max_features}.",
                path=f"layers[{index}].geojson",
                layer_id=layer_id,
                phase_id=phase_id,
            )

    source_type = str(metadata.get("source_type") or pipeline)
    if pipeline == "real_world" or source_type == "real_world":
        if not metadata.get("source_name") and not metadata.get("source_url"):
            _add_issue(
                issues,
                "warning",
                "missing_real_world_source",
                "Real-world layer is missing source_name or source_url metadata.",
                path=f"layers[{index}].metadata",
                layer_id=layer_id,
                phase_id=phase_id,
            )
    if pipeline == "abstract" and not metadata.get("assumptions"):
        _add_issue(
            issues,
            "warning",
            "missing_generated_assumptions",
            "Generated layer is missing assumptions metadata.",
            path=f"layers[{index}].metadata",
            layer_id=layer_id,
            phase_id=phase_id,
        )
    if isinstance(route_rules, dict) and route_rules.get("enabled"):
        _validate_route_quality(layer, index, layer_id, phase_id, route_metrics, route_rules, issues)
    if isinstance(placement_rules, dict) and placement_rules.get("enabled"):
        _validate_placement_rationale(
            metadata,
            issues,
            rules=placement_rules,
            path=f"layers[{index}].metadata",
            layer_id=layer_id,
            phase_id=phase_id,
        )

    report = {
        "id": layer_id,
        "name": layer.get("name"),
        "type": layer.get("type"),
        "phase_id": phase_id,
        "phase_name": metadata.get("phase_name"),
        "source_type": source_type or None,
        "source_name": metadata.get("source_name"),
        "confidence": metadata.get("confidence"),
        "placement_rationale": metadata.get("placement_rationale"),
        "warnings": list(metadata.get("warnings", [])) if isinstance(metadata.get("warnings"), list) else [],
        "feature_count": feature_count,
        "geometry_types": geometry_types,
    }
    report.update(route_metrics)
    return report


def _validate_route_quality(
    layer: dict[str, Any],
    index: int,
    layer_id: str,
    phase_id: str | None,
    metrics: dict[str, Any],
    rules: dict[str, Any],
    issues: list[dict[str, Any]],
) -> None:
    if not metrics:
        return
    max_width = float(rules.get("max_corridor_width_m", 500))
    max_segment = float(rules.get("max_segment_m", 5000))
    width = metrics.get("corridor_width_m")
    if width is not None and float(width) > max_width:
        _add_issue(
            issues,
            "warning",
            "route_corridor_width_high",
            f"Route corridor width is {float(width):.0f} m, above the configured limit of {max_width:.0f} m.",
            path=f"layers[{index}].plan.parameters.width_m",
            layer_id=layer_id,
            phase_id=phase_id,
        )
    max_actual_segment = metrics.get("route_max_segment_m")
    if max_actual_segment is not None and float(max_actual_segment) > max_segment:
        _add_issue(
            issues,
            "warning",
            "route_vertex_spacing_high",
            f"Route has a {float(max_actual_segment):.0f} m segment, above the configured limit of {max_segment:.0f} m.",
            path=f"layers[{index}].plan.parameters.coordinates",
            layer_id=layer_id,
            phase_id=phase_id,
        )
    if rules.get("require_verified_avoidance") and _route_asks_for_avoidance(layer):
        source_type = str(_layer_metadata(layer).get("source_type") or "")
        if source_type not in {"real_world", "routing", "osm_routing", "user_verified"}:
            _add_issue(
                issues,
                "warning",
                "route_avoidance_unverified",
                "Route declares avoidance constraints but is not marked as routing/user verified.",
                path=f"layers[{index}].metadata",
                layer_id=layer_id,
                phase_id=phase_id,
            )


def _validate_object(
    item: dict[str, Any],
    index: int,
    issues: list[dict[str, Any]],
    *,
    bounds: list[float] | None,
    placement_rules: Any,
) -> dict[str, Any]:
    object_id = str(item.get("id") or f"object_{index + 1}")
    metadata = _object_metadata(item)
    phase_id = _optional_str(metadata.get("phase_id"))
    geom = item.get("geometry")

    if not item.get("id"):
        _add_issue(issues, "error", "missing_object_id", "Object is missing id.", path=f"objects[{index}]")
    if not item.get("type"):
        _add_issue(issues, "error", "missing_object_type", "Object is missing type.", path=f"objects[{index}]", object_id=object_id)
    if not item.get("style"):
        _add_issue(issues, "warning", "missing_object_style", "Object is missing style.", path=f"objects[{index}]", object_id=object_id, phase_id=phase_id)

    if not isinstance(geom, dict):
        _add_issue(issues, "error", "missing_object_geometry", "Object is missing geometry.", path=f"objects[{index}].geometry", object_id=object_id, phase_id=phase_id)
    else:
        try:
            normalize_geojson(geom)
        except GeoJSONError as exc:
            _add_issue(issues, "error", "invalid_object_geometry", str(exc), path=f"objects[{index}].geometry", object_id=object_id, phase_id=phase_id)
        if bounds is not None and not _geometry_inside_bounds(geom, bounds):
            _add_issue(
                issues,
                "warning",
                "object_out_of_bounds",
                "Object geometry falls outside scenario bounds.",
                path=f"objects[{index}].geometry",
                object_id=object_id,
                phase_id=phase_id,
            )
    if isinstance(placement_rules, dict) and placement_rules.get("enabled"):
        _validate_placement_rationale(
            metadata,
            issues,
            rules=placement_rules,
            path=f"objects[{index}].metadata",
            object_id=object_id,
            phase_id=phase_id,
        )

    return {
        "id": object_id,
        "name": item.get("name"),
        "type": item.get("type"),
        "phase_id": phase_id,
        "phase_name": metadata.get("phase_name"),
        "source_type": metadata.get("source_type"),
        "source_name": metadata.get("source_name"),
        "confidence": metadata.get("confidence"),
        "placement_rationale": metadata.get("placement_rationale"),
        "status": item.get("properties", {}).get("status") if isinstance(item.get("properties"), dict) else None,
    }


def _validate_placement_rationale(
    metadata: dict[str, Any],
    issues: list[dict[str, Any]],
    *,
    rules: dict[str, Any],
    path: str,
    layer_id: str | None = None,
    object_id: str | None = None,
    phase_id: str | None = None,
) -> None:
    rationale = metadata.get("placement_rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        _add_issue(
            issues,
            "warning",
            "missing_placement_rationale",
            "Element is missing placement_rationale metadata.",
            path=path,
            layer_id=layer_id,
            object_id=object_id,
            phase_id=phase_id,
        )
    if rules.get("require_evidence") and not _has_evidence(metadata):
        _add_issue(
            issues,
            "warning",
            "missing_placement_evidence",
            "Element placement is missing evidence metadata.",
            path=path,
            layer_id=layer_id,
            object_id=object_id,
            phase_id=phase_id,
        )
    if rules.get("require_rejected_alternatives") and not isinstance(metadata.get("rejected_alternatives"), list):
        _add_issue(
            issues,
            "warning",
            "missing_rejected_alternatives",
            "Element placement is missing rejected_alternatives metadata.",
            path=path,
            layer_id=layer_id,
            object_id=object_id,
            phase_id=phase_id,
        )
    min_score = rules.get("min_candidate_score")
    if min_score is not None:
        try:
            score = float(metadata.get("candidate_score"))
            threshold = float(min_score)
        except (TypeError, ValueError):
            _add_issue(
                issues,
                "warning",
                "missing_candidate_score",
                "Element placement is missing candidate_score metadata.",
                path=path,
                layer_id=layer_id,
                object_id=object_id,
                phase_id=phase_id,
            )
        else:
            if score < threshold:
                _add_issue(
                    issues,
                    "warning",
                    "candidate_score_low",
                    f"Element placement candidate score is {score:.1f}, below {threshold:.1f}.",
                    path=path,
                    layer_id=layer_id,
                    object_id=object_id,
                    phase_id=phase_id,
                )


def _has_evidence(metadata: dict[str, Any]) -> bool:
    evidence = metadata.get("evidence")
    if isinstance(evidence, list) and evidence:
        return True
    return bool(metadata.get("source_url") or metadata.get("osm_id"))


def _check_duplicate_names(items: list[dict[str, Any]], role: str, issues: list[dict[str, Any]]) -> None:
    names = [str(item.get("name", "")).strip().lower() for item in items if str(item.get("name", "")).strip()]
    for name, count in Counter(names).items():
        if count > 1:
            _add_issue(issues, "warning", f"duplicate_{role}_name", f"Duplicate {role} name: {name}.")


def _route_metrics(layer: dict[str, Any]) -> dict[str, Any]:
    plan = layer.get("plan", {})
    if not isinstance(plan, dict):
        return {}
    operation = str(plan.get("operation") or "")
    layer_type = str(layer.get("type") or "")
    if operation not in {"line", "corridor", "osrm_route"} and layer_type not in {"route", "corridor"}:
        return {}
    parameters = plan.get("parameters", {})
    if not isinstance(parameters, dict):
        return {}
    coordinates = parameters.get("coordinates")
    if operation == "osrm_route":
        coordinates = _line_coordinates(layer.get("geojson")) or coordinates
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        coordinates = _line_coordinates(layer.get("geojson")) or coordinates
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return {"route_coordinate_count": len(coordinates) if isinstance(coordinates, list) else 0}
    segments = [
        haversine_m(coordinates[index], coordinates[index + 1])
        for index in range(len(coordinates) - 1)
        if _is_coord(coordinates[index]) and _is_coord(coordinates[index + 1])
    ]
    if not segments:
        return {"route_coordinate_count": len(coordinates)}
    metrics: dict[str, Any] = {
        "route_coordinate_count": len(coordinates),
        "route_length_m": round(sum(segments), 3),
        "route_max_segment_m": round(max(segments), 3),
    }
    width = parameters.get("width_m") or parameters.get("width")
    if width is not None:
        try:
            metrics["corridor_width_m"] = float(width)
        except (TypeError, ValueError):
            pass
    return metrics


def _line_coordinates(geojson: Any) -> list[Any] | None:
    if not isinstance(geojson, dict):
        return None
    if geojson.get("type") == "Feature":
        geometry_obj = geojson.get("geometry")
        if isinstance(geometry_obj, dict) and geometry_obj.get("type") == "LineString":
            coordinates = geometry_obj.get("coordinates")
            return coordinates if isinstance(coordinates, list) else None
    if geojson.get("type") == "FeatureCollection":
        for item in geojson.get("features", []):
            if isinstance(item, dict):
                coordinates = _line_coordinates(item)
                if coordinates:
                    return coordinates
    if geojson.get("type") == "LineString":
        coordinates = geojson.get("coordinates")
        return coordinates if isinstance(coordinates, list) else None
    return None


def _route_asks_for_avoidance(layer: dict[str, Any]) -> bool:
    metadata = _layer_metadata(layer)
    if metadata.get("avoid_water") is True:
        return True
    avoid = metadata.get("avoid_features") or metadata.get("avoid")
    if isinstance(avoid, str):
        return bool(avoid)
    if isinstance(avoid, list):
        return bool(avoid)
    return False


def _is_coord(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= 2
        and isinstance(value[0], (int, float))
        and isinstance(value[1], (int, float))
    )


def _phase_reports(
    layer_reports: list[dict[str, Any]],
    object_reports: list[dict[str, Any]],
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    phase_ids = {
        str(item["phase_id"])
        for item in [*layer_reports, *object_reports]
        if item.get("phase_id")
    }
    reports = []
    for phase_id in sorted(phase_ids):
        phase_layers = [item for item in layer_reports if item.get("phase_id") == phase_id]
        phase_objects = [item for item in object_reports if item.get("phase_id") == phase_id]
        phase_issues = [item for item in issues if item.get("phase_id") == phase_id]
        phase_name = None
        for item in [*phase_layers, *phase_objects]:
            if item.get("phase_name"):
                phase_name = item["phase_name"]
                break
        reports.append(
            {
                "id": phase_id,
                "name": phase_name,
                "layer_count": len(phase_layers),
                "object_count": len(phase_objects),
                "warning_count": sum(1 for item in phase_issues if item["severity"] == "warning"),
                "error_count": sum(1 for item in phase_issues if item["severity"] == "error"),
            }
        )
    return reports


def _scenario_bounds(payload: dict[str, Any]) -> list[float] | None:
    map_context = payload.get("map_context")
    if not isinstance(map_context, dict):
        return None
    bounds = map_context.get("bounds")
    if not isinstance(bounds, list) or len(bounds) != 4:
        return None
    return [float(item) for item in bounds]


def _geometry_inside_bounds(geometry: dict[str, Any], bounds: list[float]) -> bool:
    west, south, east, north = bounds
    min_lon, min_lat, max_lon, max_lat = geometry_bounds(geometry)
    return west <= min_lon <= east and west <= max_lon <= east and south <= min_lat <= north and south <= max_lat <= north


def _layer_metadata(layer: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    plan = layer.get("plan", {})
    if isinstance(plan, dict) and isinstance(plan.get("metadata"), dict):
        metadata.update(deepcopy(plan["metadata"]))
    if isinstance(layer.get("metadata"), dict):
        metadata.update(deepcopy(layer["metadata"]))
    geojson = layer.get("geojson")
    if isinstance(geojson, dict):
        props = _first_properties(geojson)
        metadata.update({key: deepcopy(props[key]) for key in STANDARD_METADATA_KEYS if key in props})
    return metadata


def _object_metadata(item: dict[str, Any]) -> dict[str, Any]:
    metadata = deepcopy(item.get("metadata", {})) if isinstance(item.get("metadata"), dict) else {}
    properties = item.get("properties", {})
    if isinstance(properties, dict):
        metadata.update({key: deepcopy(properties[key]) for key in STANDARD_METADATA_KEYS if key in properties})
    return metadata


def _first_properties(geojson: dict[str, Any]) -> dict[str, Any]:
    if geojson.get("type") == "Feature":
        return geojson.get("properties", {}) if isinstance(geojson.get("properties"), dict) else {}
    if geojson.get("type") == "FeatureCollection":
        for item in geojson.get("features", []):
            if isinstance(item, dict) and isinstance(item.get("properties"), dict):
                return item["properties"]
    return {}


def _feature_count(geojson: Any) -> int:
    if not isinstance(geojson, dict):
        return 0
    if geojson.get("type") == "FeatureCollection":
        return len(geojson.get("features", []))
    if geojson.get("type") == "Feature":
        return 1 if geojson.get("geometry") else 0
    if geojson.get("type") in {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"}:
        return 1
    return 0


def _geometry_types(geojson: Any) -> list[str]:
    if not isinstance(geojson, dict):
        return []
    if geojson.get("type") == "FeatureCollection":
        types = {
            str(item.get("geometry", {}).get("type"))
            for item in geojson.get("features", [])
            if isinstance(item, dict) and isinstance(item.get("geometry"), dict)
        }
        return sorted(types)
    if geojson.get("type") == "Feature" and isinstance(geojson.get("geometry"), dict):
        return [str(geojson["geometry"].get("type"))]
    if geojson.get("type"):
        return [str(geojson["type"])]
    return []


def _add_issue(
    issues: list[dict[str, Any]],
    severity: str,
    code: str,
    message: str,
    *,
    path: str | None = None,
    layer_id: str | None = None,
    object_id: str | None = None,
    phase_id: str | None = None,
) -> None:
    issue = {
        "severity": severity,
        "code": code,
        "message": message,
    }
    if path is not None:
        issue["path"] = path
    if layer_id is not None:
        issue["layer_id"] = layer_id
    if object_id is not None:
        issue["object_id"] = object_id
    if phase_id is not None:
        issue["phase_id"] = phase_id
    issues.append(issue)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
