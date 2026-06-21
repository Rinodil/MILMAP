from __future__ import annotations

import json
import re
from typing import Any

from . import geometry
from .geojson import GeoJSONError, feature, feature_collection, merge_feature_properties, normalize_geojson
from .models import PlanResult, SpatialPlan
from .tools import ToolRegistry


class SpatialAgent:
    def __init__(self, tools: ToolRegistry | None = None, *, precision: int = 6) -> None:
        self.tools = tools or ToolRegistry()
        self.precision = precision

    def execute(self, plan_or_mapping: SpatialPlan | dict[str, Any]) -> dict[str, Any]:
        plan = (
            plan_or_mapping
            if isinstance(plan_or_mapping, SpatialPlan)
            else SpatialPlan.from_mapping(plan_or_mapping)
        )
        result = self.execute_plan(plan).geojson
        return normalize_geojson(result, precision=self.precision)

    def execute_plan(self, plan: SpatialPlan) -> PlanResult:
        if plan.pipeline in {"abstract", "direct"}:
            geojson = self._execute_geometry(plan)
        elif plan.pipeline == "real_world":
            geojson = self._execute_tool(plan)
        else:
            raise GeoJSONError(f"Unsupported pipeline: {plan.pipeline!r}")

        if plan.properties:
            geojson = merge_feature_properties(geojson, plan.properties)
        return PlanResult(plan=plan, geojson=normalize_geojson(geojson, precision=self.precision))

    def execute_many(self, plans: list[SpatialPlan | dict[str, Any]]) -> dict[str, Any]:
        features = []
        for item in plans:
            geojson = self.execute(item)
            if geojson["type"] == "FeatureCollection":
                features.extend(geojson["features"])
            elif geojson["type"] == "Feature":
                features.append(geojson)
            else:
                features.append(feature(geojson, precision=self.precision))
        return feature_collection(features, precision=self.precision)

    def _execute_geometry(self, plan: SpatialPlan) -> dict[str, Any]:
        p = plan.parameters
        operation = plan.operation

        if operation == "point":
            return feature(geometry.point(p["coordinate"]), {"operation": operation}, precision=self.precision)

        if operation == "line":
            return feature(geometry.line_string(p["coordinates"]), {"operation": operation}, precision=self.precision)

        if operation == "polygon":
            return feature(geometry.polygon(p["rings"]), {"operation": operation}, precision=self.precision)

        if operation == "bbox":
            return feature(geometry.bbox_polygon(p["bounds"]), {"operation": operation}, precision=self.precision)

        if operation == "buffer":
            geom = geometry.buffer_point(
                p["center"],
                geometry.meters_from_parameters(p, "radius"),
                steps=int(p.get("steps", 64)),
            )
            return feature(geom, {"operation": operation}, precision=self.precision)

        if operation == "range_ring":
            geom = geometry.range_ring(
                p["center"],
                geometry.meters_from_parameters(p, "radius"),
                steps=int(p.get("steps", 64)),
            )
            return feature(geom, {"operation": operation}, precision=self.precision)

        if operation == "sector":
            geom = geometry.sector(
                p["center"],
                geometry.meters_from_parameters(p, "radius"),
                float(p["start_bearing"]),
                float(p["end_bearing"]),
                steps=int(p.get("steps", 32)),
            )
            return feature(geom, {"operation": operation}, precision=self.precision)

        if operation == "regular_polygon":
            geom = geometry.regular_polygon(
                p["center"],
                geometry.meters_from_parameters(p, "radius"),
                int(p["sides"]),
                rotation_deg=float(p.get("rotation_deg", 0.0)),
            )
            return feature(geom, {"operation": operation}, precision=self.precision)

        if operation == "corridor":
            geom = geometry.corridor(
                p["coordinates"],
                geometry.meters_from_parameters(p, "width"),
                precision=self.precision,
            )
            return feature(geom, {"operation": operation}, precision=self.precision)

        if operation == "square_grid":
            return geometry.square_grid(
                p["bounds"],
                geometry.meters_from_parameters(p, "cell_size"),
                precision=self.precision,
                max_features=int(p.get("max_features", 10_000)),
            )

        if operation == "hex_grid":
            return geometry.hex_grid(
                p["bounds"],
                geometry.meters_from_parameters(p, "radius"),
                precision=self.precision,
                max_features=int(p.get("max_features", 10_000)),
            )

        raise GeoJSONError(f"Unsupported geometry operation: {operation!r}")

    def _execute_tool(self, plan: SpatialPlan) -> dict[str, Any]:
        if plan.operation == "real_world_boundary":
            return self.tools.execute("real_world_boundary", plan.parameters)
        if plan.operation == "overpass_query":
            return self.tools.execute("overpass_query", plan.parameters)
        if plan.operation == "osrm_route":
            return self.tools.execute("osrm_route", plan.parameters)
        raise GeoJSONError(f"Unsupported real-world operation: {plan.operation!r}")


class HeuristicIntentRouter:
    """Offline router for tests and demos.

    Production systems should replace this with an LLM structured-output router
    using schemas/agent_plan.schema.json. This class intentionally refuses to
    infer missing coordinates.
    """

    _coord_pattern = re.compile(r"\[?\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]?")

    def route(self, request: str | dict[str, Any]) -> SpatialPlan:
        if isinstance(request, dict):
            return SpatialPlan.from_mapping(request)

        text = request.strip()
        if text.startswith("{"):
            return SpatialPlan.from_mapping(json.loads(text))

        lower = text.lower()
        coords = self._extract_coordinates(text)

        if "hex" in lower and "grid" in lower:
            numbers = self._numbers(text)
            if len(numbers) >= 5:
                return SpatialPlan(
                    pipeline="abstract",
                    operation="hex_grid",
                    parameters={"bounds": numbers[:4], "radius_m": numbers[4]},
                )

        if ("buffer" in lower or "radius" in lower or "circle" in lower) and coords:
            radius = self._extract_distance_m(lower)
            if radius is not None:
                return SpatialPlan(
                    pipeline="abstract",
                    operation="buffer",
                    parameters={"center": coords[0], "radius_m": radius},
                )

        if ("line" in lower or "route" in lower) and len(coords) >= 2:
            return SpatialPlan(
                pipeline="direct",
                operation="line",
                parameters={"coordinates": coords},
            )

        raise GeoJSONError(
            "Request could not be routed without guessing coordinates. "
            "Provide a structured SpatialPlan or include explicit coordinates."
        )

    def _extract_coordinates(self, text: str) -> list[list[float]]:
        return [[float(match.group(1)), float(match.group(2))] for match in self._coord_pattern.finditer(text)]

    def _numbers(self, text: str) -> list[float]:
        return [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", text)]

    def _extract_distance_m(self, lower_text: str) -> float | None:
        match = re.search(r"(\d+(?:\.\d+)?)\s*(miles?|mi|kilometers?|km|meters?|m)\b", lower_text)
        if not match:
            return None
        value = float(match.group(1))
        unit = match.group(2)
        if unit in {"mile", "miles", "mi"}:
            return value * geometry.METERS_PER_MILE
        if unit in {"kilometer", "kilometers", "km"}:
            return value * 1000.0
        return value
