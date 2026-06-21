from __future__ import annotations

import json
from typing import Any, Protocol

from .models import SpatialPlan


class JSONLLMClient(Protocol):
    def complete_json(self, *, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Return parsed JSON that conforms to the supplied schema."""


SPATIAL_ROUTER_SYSTEM_PROMPT = """You are a spatial intent router.
Output only JSON matching the provided schema.
Never invent coordinate loops.
Use [longitude, latitude] order for every coordinate.
Route abstract shapes to pipeline=abstract.
Route caller-provided raw coordinates to pipeline=direct.
Route public map-feature retrieval to pipeline=real_world.
Use operation=osrm_route for road-following routes when caller provides waypoints.
When coordinates, bounds, radius, width, bearings, or names are missing, ask for the missing field instead of guessing.
"""


PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["pipeline", "operation", "parameters"],
    "properties": {
        "pipeline": {"type": "string", "enum": ["abstract", "direct", "real_world"]},
        "operation": {
            "type": "string",
            "enum": [
                "point",
                "line",
                "polygon",
                "bbox",
                "buffer",
                "range_ring",
                "sector",
                "regular_polygon",
                "corridor",
                "square_grid",
                "hex_grid",
                "real_world_boundary",
                "overpass_query",
                "osrm_route",
            ],
        },
        "parameters": {"type": "object"},
        "properties": {"type": "object"},
        "metadata": {"type": "object"},
    },
}


class LLMIntentRouter:
    def __init__(self, client: JSONLLMClient, *, schema: dict[str, Any] | None = None) -> None:
        self.client = client
        self.schema = schema or PLAN_SCHEMA

    def route(self, request: str) -> SpatialPlan:
        payload = self.client.complete_json(
            system=SPATIAL_ROUTER_SYSTEM_PROMPT,
            user=request,
            schema=self.schema,
        )
        return SpatialPlan.from_mapping(payload)



ELEMENT_REFINEMENT_SYSTEM_PROMPT = """You refine one MILMAP scenario element at a time.
Output only JSON matching the provided schema.
Return exactly one replacement layer or object, not a full scenario.
Use [longitude, latitude] order for every coordinate.
For routes, prefer narrow centerline layers and only use corridors when a real width is required.
Do not invent street geometry as verified fact. If coordinates are synthetic, set metadata.source_type="generated", metadata.confidence="low" or "medium", and include assumptions.
If the request requires water avoidance, road following, or turn-by-turn accuracy, use caller-provided route/routing data or mark the route as unverified.
Preserve the target element id unless the caller explicitly asks for a new element.
"""

ELEMENT_REFINEMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["target", "action", "element"],
    "properties": {
        "target": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "id"],
            "properties": {
                "kind": {"type": "string", "enum": ["layer", "object"]},
                "id": {"type": "string"},
                "name": {"type": "string"},
            },
        },
        "action": {"type": "string", "enum": ["replace"]},
        "element": {"type": "object"},
        "note": {"type": "string"},
        "validation_rules": {"type": "object"},
    },
}


class LLMElementRefiner:
    def __init__(self, client: JSONLLMClient, *, schema: dict[str, Any] | None = None) -> None:
        self.client = client
        self.schema = schema or ELEMENT_REFINEMENT_SCHEMA

    def propose(self, *, scenario: dict[str, Any], target: dict[str, Any], instruction: str) -> dict[str, Any]:
        user_payload = {
            "instruction": instruction,
            "target": target,
            "scenario": _scenario_refinement_context(scenario, target),
        }
        return self.client.complete_json(
            system=ELEMENT_REFINEMENT_SYSTEM_PROMPT,
            user=json.dumps(user_payload, sort_keys=True),
            schema=self.schema,
        )


def _scenario_refinement_context(scenario: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    payload = scenario.get("payload", scenario)
    kind = str(target.get("kind") or "")
    item_key = "layers" if kind == "layer" else "objects"
    items = payload.get(item_key, []) if isinstance(payload, dict) else []
    target_id = str(target.get("id") or "")
    target_name = str(target.get("name") or "")
    selected = None
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "") == target_id or str(item.get("name") or "") == target_name:
            selected = item
            break
    return {
        "scenario_id": payload.get("scenario_id"),
        "scenario_name": payload.get("scenario_name"),
        "map_context": payload.get("map_context", {}),
        "target": selected,
        "layer_summaries": [
            {"id": item.get("id"), "name": item.get("name"), "type": item.get("type")}
            for item in payload.get("layers", [])
            if isinstance(item, dict)
        ],
        "object_summaries": [
            {"id": item.get("id"), "name": item.get("name"), "type": item.get("type")}
            for item in payload.get("objects", [])
            if isinstance(item, dict)
        ],
    }
