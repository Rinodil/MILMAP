#!/usr/bin/env python3
"""
MILMAP Priority Scorer

Calculates priority scores for objects based on spatial relationships
and metadata. Scores are stored in object metadata.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Calculate the great circle distance between two points in meters."""
    R = 6371008.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


def calculate_bearing(coord1: list[float], coord2: list[float]) -> float:
    """Calculate the initial bearing from point 1 to point 2."""
    lon1, lat1 = map(math.radians, coord1)
    lon2, lat2 = map(math.radians, coord2)
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    bearing = math.atan2(y, x)
    return (math.degrees(bearing) + 360) % 360


def is_in_sector(
    point: list[float],
    center: list[float],
    radius_m: float,
    start_bearing: float,
    end_bearing: float,
) -> bool:
    """Determine if a point is within a circular sector."""
    dist = haversine_m(point[0], point[1], center[0], center[1])
    if dist > radius_m:
        return False

    bearing = calculate_bearing(center, point)

    if start_bearing <= end_bearing:
        return start_bearing <= bearing <= end_bearing
    else:
        return bearing >= start_bearing or bearing <= end_bearing


def get_coordinate(item: dict[str, Any]) -> list[float] | None:
    """Safely extract [lon, lat] from different placement formats."""
    placement = item.get("placement")
    if isinstance(placement, dict):
        if "coordinate" in placement:
            return placement["coordinate"]
        if placement.get("mode") == "point" and "coordinate" in placement:
            return placement["coordinate"]

    # Fallback to GeoJSON geometry
    geometry = item.get("geometry")
    if isinstance(geometry, dict) and geometry.get("type") == "Point":
        coords = geometry.get("coordinates")
        if isinstance(coords, list) and len(coords) >= 2:
            return [float(coords[0]), float(coords[1])]

    return None


def calculate_priority_score(
    obj: dict[str, Any], hubs: list[dict[str, Any]], coverage_zones: list[dict[str, Any]]
) -> tuple[float, list[str]]:
    """Calculate a priority score (0-100) for a map object."""
    score = 50.0
    reasons: list[str] = []

    obj_type = str(obj.get("type", ""))
    if obj_type in {"high_value_target", "priority_node"}:
        score += 20
        reasons.append("High-value object type")

    obj_coord = get_coordinate(obj)
    if not obj_coord:
        return 0.0, ["No valid coordinate found"]

    # Find closest hub
    min_dist = float("inf")
    closest_hub_name = "Unknown Hub"
    for hub in hubs:
        hub_coord = get_coordinate(hub)
        if hub_coord:
            dist = haversine_m(obj_coord[0], obj_coord[1], hub_coord[0], hub_coord[1])
            if dist < min_dist:
                min_dist = dist
                closest_hub_name = str(hub.get("name", "Unknown Hub"))

    if min_dist < 10000:
        score += 15
        reasons.append(f"Very close to hub: {closest_hub_name}")
    elif min_dist < 50000:
        score += 8
        reasons.append(f"Within operational range of hub: {closest_hub_name}")

    # Coverage zone overlap
    for zone in coverage_zones:
        in_zone = False
        if (
            zone["operation"] == "sector"
            and zone["start_bearing"] is not None
            and zone["end_bearing"] is not None
        ):
            if is_in_sector(
                obj_coord,
                zone["center"],
                zone["radius_m"],
                float(zone["start_bearing"]),
                float(zone["end_bearing"]),
            ):
                in_zone = True
        else:
            if haversine_m(obj_coord[0], obj_coord[1], zone["center"][0], zone["center"][1]) <= zone["radius_m"]:
                in_zone = True

        if in_zone:
            score += 12
            reasons.append(f"Located within coverage area: {zone['name']}")
            break

    # Manual override from metadata
    meta = obj.get("metadata", {})
    priority = str(meta.get("priority_level", "")).lower()
    if priority == "high":
        score = max(score, 80.0)
        reasons.append("Manual override: High priority")
    elif priority == "medium":
        score = max(score, 60.0)
    elif priority == "low":
        score = min(score, 40.0)
        reasons.append("Manual override: Low priority")

    final_score = min(max(score, 0.0), 100.0)
    return round(final_score, 1), reasons


def score_priority(scenario: dict[str, Any]) -> dict[str, Any]:
    """Analyze and score all priority nodes in the scenario."""
    objects = scenario.get("objects", [])
    layers = scenario.get("layers", [])

    hubs = [o for o in objects if isinstance(o, dict) and o.get("type") in {"hub", "base"}]

    coverage_zones = []
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        if layer.get("type") in {"threat_dome", "coverage_zone"}:
            params = layer.get("parameters") or (
                layer.get("plan", {}).get("parameters")
                if isinstance(layer.get("plan"), dict)
                else {}
            )
            if params and params.get("center"):
                radius_km = params.get("radius_km")
                radius = params.get("radius")
                radius_m = 0.0
                if radius_km is not None:
                    radius_m = float(radius_km) * 1000.0
                elif radius is not None:
                    radius_m = float(radius)

                coverage_zones.append(
                    {
                        "name": layer.get("name"),
                        "center": params.get("center"),
                        "radius_m": radius_m,
                        "start_bearing": params.get("start_bearing"),
                        "end_bearing": params.get("end_bearing"),
                        "operation": layer.get("operation"),
                    }
                )

    priority_results = []

    for obj in scenario.get("objects", []):
        if not isinstance(obj, dict):
            continue

        if obj.get("type") in {"high_value_target", "priority_node"}:
            score, reasons = calculate_priority_score(obj, hubs, coverage_zones)

            if reasons and reasons[0] == "No valid coordinate found":
                continue

            obj_metadata = obj.setdefault("metadata", {})
            obj_metadata["priority_score"] = score
            obj_metadata["priority_reasons"] = reasons

            priority_results.append({
                "name": obj.get("name"),
                "type": obj.get("type"),
                "score": score,
                "reasons": reasons
            })

    priority_results.sort(key=lambda x: x["score"], reverse=True)

    metadata = scenario.setdefault("metadata", {})
    metadata["priority_analysis"] = priority_results
    return scenario


def process_file(input_path: str | Path, output_path: str | Path | None = None) -> dict[str, Any]:
    """Load, enhance, and save a scenario file with priority scores."""
    with Path(input_path).open("r", encoding="utf-8") as handle:
        scenario = json.load(handle)

    scenario = score_priority(scenario)

    output = (
        Path(output_path)
        if output_path
        else Path(input_path).parent / f"{Path(input_path).stem}_scored{Path(input_path).suffix}"
    )
    output.write_text(json.dumps(scenario, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Saved scored scenario to: {output}")
    return scenario


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Score priority nodes in MILMAP scenario.")
    parser.add_argument("--input", required=True, help="Input scenario JSON.")
    parser.add_argument("--output", help="Output scenario JSON.")
    args = parser.parse_args()

    process_file(args.input, args.output)
