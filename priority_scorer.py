#!/usr/bin/env python3
"""Assign priority scores to nodes in MILMAP scenario JSON files."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(coord1: list[float], coord2: list[float]) -> float:
    lon1, lat1 = map(math.radians, coord1)
    lon2, lat2 = map(math.radians, coord2)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return c * EARTH_RADIUS_M


def calculate_bearing(coord1: list[float], coord2: list[float]) -> float:
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
    dist = haversine_m(center, point)
    if dist > radius_m:
        return False

    bearing = calculate_bearing(center, point)

    if start_bearing <= end_bearing:
        return start_bearing <= bearing <= end_bearing
    else:
        return bearing >= start_bearing or bearing <= end_bearing


def load_scenario(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def score_priority(scenario: dict[str, Any]) -> dict[str, Any]:
    objects = scenario.get("objects", [])
    layers = scenario.get("layers", [])

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
            if params:
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

    hubs = [
        obj
        for obj in objects
        if isinstance(obj, dict) and obj.get("type") in {"hub", "base"}
    ]

    priority_analysis = []

    for obj in objects:
        if not isinstance(obj, dict):
            continue

        node_coord = None
        placement = obj.get("placement")
        if isinstance(placement, dict) and placement.get("mode") == "point":
            node_coord = placement.get("coordinate")

        if not node_coord:
            geometry = obj.get("geometry")
            if isinstance(geometry, dict) and geometry.get("type") == "Point":
                node_coord = geometry.get("coordinates")

        if not node_coord or not isinstance(node_coord, list) or len(node_coord) < 2:
            continue

        score = 50.0
        reasons = []

        # Type-based scoring
        obj_type = str(obj.get("type", ""))
        if obj_type in {"high_value_target", "priority_node"}:
            score += 20
            reasons.append("High-value object type")

        # Hub proximity
        for hub in hubs:
            hub_coord = None
            hub_placement = hub.get("placement")
            if isinstance(hub_placement, dict) and hub_placement.get("mode") == "point":
                hub_coord = hub_placement.get("coordinate")

            if not hub_coord:
                hub_geometry = hub.get("geometry")
                if isinstance(hub_geometry, dict) and hub_geometry.get("type") == "Point":
                    hub_coord = hub_geometry.get("coordinates")

            if hub_coord and isinstance(hub_coord, list) and len(hub_coord) >= 2:
                dist = haversine_m(hub_coord, node_coord)
                if dist < 10000:  # 10km
                    score += 15
                    reasons.append(f"Near hub {hub.get('name')} (<10km)")
                    break
                elif dist < 50000:  # 50km
                    score += 5
                    reasons.append(f"Near hub {hub.get('name')} (<50km)")
                    break

        # Coverage overlap
        for zone in coverage_zones:
            if not zone["center"] or not isinstance(zone["center"], list) or len(zone["center"]) < 2:
                continue

            in_zone = False
            if (
                zone["operation"] == "sector"
                and zone["start_bearing"] is not None
                and zone["end_bearing"] is not None
            ):
                if is_in_sector(
                    node_coord,
                    zone["center"],
                    zone["radius_m"],
                    float(zone["start_bearing"]),
                    float(zone["end_bearing"]),
                ):
                    in_zone = True
            else:
                if haversine_m(zone["center"], node_coord) <= zone["radius_m"]:
                    in_zone = True

            if in_zone:
                score += 15
                reasons.append(f"Inside coverage zone {zone['name']}")
                break

        # Manual overrides in metadata
        obj_metadata = obj.setdefault("metadata", {})
        manual_priority = obj_metadata.get("priority_level")
        if manual_priority == "high":
            score = max(score, 85.0)
            reasons.append("Manual override: High priority")
        elif manual_priority == "medium":
            score = max(score, 65.0)
        elif manual_priority == "low":
            score = min(score, 40.0)
            reasons.append("Manual override: Low priority")

        score = min(max(score, 0), 100)
        obj_metadata["priority_score"] = round(score, 1)
        obj_metadata["priority_reasons"] = reasons

        priority_analysis.append(
            {
                "name": obj.get("name"),
                "type": obj_type,
                "score": obj_metadata["priority_score"],
                "reasons": reasons,
            }
        )

    priority_analysis.sort(key=lambda x: x["score"], reverse=True)
    scenario.setdefault("metadata", {})["priority_analysis"] = priority_analysis

    return scenario


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score priority nodes in MILMAP scenario.")
    parser.add_argument("--input", required=True, help="Input scenario JSON.")
    parser.add_argument("--output", help="Output scenario JSON.")
    parser.add_argument("--analysis-output", help="Priority analysis JSON output.")
    args = parser.parse_args(argv)

    scenario = load_scenario(args.input)
    enhanced = score_priority(scenario)

    output_path = (
        Path(args.output)
        if args.output
        else Path(args.input).parent / f"{Path(args.input).stem}_scored{Path(args.input).suffix}"
    )
    output_path.write_text(
        json.dumps(enhanced, indent=2, sort_keys=True), encoding="utf-8"
    )

    analysis_path = (
        Path(args.analysis_output)
        if args.analysis_output
        else Path(args.input).parent / "priority_analysis.json"
    )
    analysis_data = enhanced["metadata"]["priority_analysis"]
    analysis_path.write_text(
        json.dumps(analysis_data, indent=2, sort_keys=True), encoding="utf-8"
    )

    print(f"Scored scenario saved to: {output_path}")
    print(f"Priority analysis saved to: {analysis_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
