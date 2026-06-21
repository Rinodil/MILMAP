from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from .geojson import feature, feature_collection
from .routing import OSRMRoutingClient

ToolCallable = Callable[[dict[str, Any]], dict[str, Any]]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolCallable] = {}

    def register(self, name: str, tool: ToolCallable) -> None:
        self._tools[name] = tool

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in self._tools:
            raise KeyError(f"No spatial tool registered for {name!r}.")
        return self._tools[name](arguments)


class OverpassClient:
    def __init__(
        self,
        endpoint: str = "https://overpass-api.de/api/interpreter",
        timeout_s: int = 30,
        user_agent: str = "MILMAP Engine/0.1",
    ) -> None:
        self.endpoint = endpoint
        self.timeout_s = timeout_s
        self.user_agent = user_agent

    def boundary_query(self, name: str, admin_level: str | None = None) -> str:
        clauses = ['["boundary"="administrative"]', f'["name"="{_escape_overpass(name)}"]']
        if admin_level:
            clauses.append(f'["admin_level"="{_escape_overpass(admin_level)}"]')
        selector = "".join(clauses)
        return f"[out:json][timeout:{self.timeout_s}];rel{selector};out geom;"

    def execute_query(self, query: str) -> dict[str, Any]:
        body = urllib.parse.urlencode({"data": query}).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={"User-Agent": self.user_agent},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            return json.loads(response.read().decode("utf-8"))

    def boundary_geojson(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = self.boundary_query(
            str(arguments["name"]),
            str(arguments["admin_level"]) if arguments.get("admin_level") is not None else None,
        )
        raw = self.execute_query(query)
        return overpass_json_to_geojson(raw)

    def query_geojson(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw = self.execute_query(str(arguments["query"]))
        return overpass_json_to_geojson(raw)


def overpass_tool_registry(client: OverpassClient | None = None) -> ToolRegistry:
    overpass = client or OverpassClient()
    registry = ToolRegistry()
    registry.register("real_world_boundary", overpass.boundary_geojson)
    registry.register("overpass_query", overpass.query_geojson)
    return registry


def default_tool_registry(
    *,
    overpass: OverpassClient | None = None,
    router: OSRMRoutingClient | None = None,
) -> ToolRegistry:
    registry = overpass_tool_registry(overpass)
    osrm = router or OSRMRoutingClient()
    registry.register("osrm_route", osrm.route_geojson)
    return registry


def overpass_json_to_geojson(raw: dict[str, Any]) -> dict[str, Any]:
    features = []
    for element in raw.get("elements", []):
        element_type = element.get("type")
        tags = element.get("tags") or {}
        properties = {
            "source": "overpass",
            "osm_type": element_type,
            "osm_id": element.get("id"),
            **tags,
        }

        if element_type == "node" and "lon" in element and "lat" in element:
            features.append(feature({"type": "Point", "coordinates": [element["lon"], element["lat"]]}, properties))
            continue

        if element_type == "way" and element.get("geometry"):
            coords = [[point["lon"], point["lat"]] for point in element["geometry"]]
            geom_type = "Polygon" if coords and coords[0] == coords[-1] else "LineString"
            coordinates = [coords] if geom_type == "Polygon" else coords
            features.append(feature({"type": geom_type, "coordinates": coordinates}, properties))
            continue

        if element_type == "way" and isinstance(element.get("center"), dict):
            center = element["center"]
            if "lon" in center and "lat" in center:
                features.append(feature({"type": "Point", "coordinates": [center["lon"], center["lat"]]}, properties))
                continue

        if element_type == "relation":
            if isinstance(element.get("center"), dict):
                center = element["center"]
                if "lon" in center and "lat" in center and not element.get("members"):
                    features.append(feature({"type": "Point", "coordinates": [center["lon"], center["lat"]]}, properties))
                    continue
            lines = []
            for member in element.get("members", []):
                if member.get("geometry"):
                    lines.append([[point["lon"], point["lat"]] for point in member["geometry"]])
            if lines:
                features.append(feature({"type": "MultiLineString", "coordinates": lines}, properties))
                continue
            if isinstance(element.get("center"), dict):
                center = element["center"]
                if "lon" in center and "lat" in center:
                    features.append(feature({"type": "Point", "coordinates": [center["lon"], center["lat"]]}, properties))

    return feature_collection(features)


def _escape_overpass(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
