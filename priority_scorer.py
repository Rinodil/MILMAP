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


def haversine_m(coord1: list[float], coord2: list[float]) -> float:
    """Calculate the great circle distance between two points in meters."""
    R = 6371008.8
    lon1, lat1 = map(math.radians, coord1)
    lon2, lat2 = map(math.radians, coord2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return c * R


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
    dist = haversine_m(center, point)
    if dist > radius_m:
        return False

    bearing = calculate_bearing(center, point)

    if start_bearing <= end_bearing:
        return start_bearing <= bearing <= end_bearing
    else:
        return bearing >= start_bearing or bearing <= end_bearing


def get_coordinate(obj: dict[str, Any]) -> list[float] | None:
    """Extract [lon, lat] from different possible placement formats."""
    placement = obj.get("placement")
    if isinstance(placement, dict):
        coord = placement.get("coordinate")
        if isinstance(coord, list) and len(coord) >= 2:
            return [float(coord[0]), float(coord[1])]

    # Fallback to GeoJSON geometry
    geometry = obj.get("geometry")
    if isinstance(geometry, dict) and geometry.get("type") == "Point":
        coord = geometry.get("coordinates")
        if isinstance(coord, list) and len(coord) >= 2:
            return [float(coord[0]), float(coord[1])]

    return None


def calculate_priority_score(
    obj: dict[str, Any], hubs: list[dict[str, Any]], coverage_zones: list[dict[str, Any]]
) -> tuple[float, list[str]]:
    """Calculate a priority score (0-100) for a map object."""
    score = 50.0
    reasons = []

    obj_type = str(obj.get("type", ""))
    if obj_type in {"high_value_target", "priority_node"}:
        score += 20
        reasons.append("High-value object type")

    obj_coord = get_coordinate(obj)
    if not obj_coord:
        return 0.0, ["No valid coordinate found"]

    # Find closest hub
    min_distance = float("inf")
    closest_hub_name = "Unknown Hub"
    for hub in hubs:
        hub_coord = get_coordinate(hub)
        if hub_coord:
            dist = haversine_m(obj_coord, hub_coord)
            if dist < min_distance:
                min_distance = dist
                closest_hub_name = str(hub.get("name", "Unknown Hub"))

    if min_distance < 10000:
        score += 15
        reasons.append(f"Close to hub {closest_hub_name} (<10km)")
    elif min_distance < 50000:
        score += 5
        reasons.append(f"Within 50km of hub {closest_hub_name}")

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
            if haversine_m(zone["center"], obj_coord) <= zone["radius_m"]:
                in_zone = True

        if in_zone:
            score += 15
            reasons.append(f"Inside coverage zone: {zone['name']}")
            break

    # Manual override
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

    hubs = [obj for obj in objects if isinstance(obj, dict) and obj.get("type") in {"hub", "base"}]

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

    priority_list = []

    for obj in objects:
        if not isinstance(obj, dict):
            continue

        score, reasons = calculate_priority_score(obj, hubs, coverage_zones)

        if reasons and reasons[0] == "No valid coordinate found":
            continue

        obj_metadata = obj.setdefault("metadata", {})
        obj_metadata["priority_score"] = score
        obj_metadata["priority_reasons"] = reasons

        priority_list.append(
            {
                "name": obj.get("name"),
                "type": obj.get("type"),
                "score": score,
                "reasons": reasons,
            }
        )

    # Sort by score descending
    priority_list.sort(key=lambda x: x["score"], reverse=True)

    metadata = scenario.setdefault("metadata", {})
    metadata["priority_analysis"] = priority_list
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

    analysis_path = Path(input_path).parent / "priority_analysis.json"
    analysis_data = scenario["metadata"]["priority_analysis"]
    analysis_path.write_text(json.dumps(analysis_data, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Scored scenario saved to: {output}")
    print(f"Priority analysis saved to: {analysis_path}")
    return scenario


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score priority nodes in MILMAP scenario.")
    parser.add_argument("--input", required=True, help="Input scenario JSON.")
    parser.add_argument("--output", help="Output scenario JSON.")
    args = parser.parse_args(argv)

    process_file(args.input, args.output)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
