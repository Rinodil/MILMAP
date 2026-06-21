from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from . import geometry
from .agent import SpatialAgent
from .geojson import GeoJSONError, feature, feature_collection, normalize_geojson, normalize_geometry
from .models import ScenarioLayerPlan, ScenarioObjectPlan, ScenarioPlan, ScenarioResult, SpatialPlan
from .tools import ToolRegistry


DIRECT_OPERATIONS = {"point", "line", "polygon", "bbox"}
ABSTRACT_OPERATIONS = {
    "buffer",
    "range_ring",
    "sector",
    "regular_polygon",
    "corridor",
    "square_grid",
    "hex_grid",
}
REAL_WORLD_OPERATIONS = {"real_world_boundary", "overpass_query", "osrm_route"}


@dataclass(frozen=True)
class CompiledScenarioLayer:
    id: str
    name: str
    source: ScenarioLayerPlan
    plan: SpatialPlan


class ScenarioCompiler:
    def compile_layers(self, scenario: ScenarioPlan) -> list[CompiledScenarioLayer]:
        scenario_id = slug_id(scenario.scenario_name)
        used_ids: set[str] = set()
        compiled = []

        for index, layer in enumerate(scenario.layers, start=1):
            layer_id = unique_id(layer.id or layer.name or f"{layer.type}_{index}", used_ids)
            layer_name = layer.name or humanize_id(layer_id)
            operation = layer.operation or layer.type
            pipeline = layer.pipeline or infer_pipeline(operation)
            properties = {
                **layer.metadata,
                **layer.properties,
                "scenario_role": "layer",
                "scenario_id": scenario_id,
                "layer_id": layer_id,
                "layer_type": layer.type,
                "name": layer_name,
            }
            metadata = {
                **layer.metadata,
                "scenario_id": scenario_id,
                "layer_id": layer_id,
                "layer_type": layer.type,
            }
            compiled.append(
                CompiledScenarioLayer(
                    id=layer_id,
                    name=layer_name,
                    source=layer,
                    plan=SpatialPlan(
                        pipeline=pipeline,
                        operation=operation,
                        parameters=dict(layer.parameters),
                        properties=properties,
                        metadata=metadata,
                    ),
                )
            )

        return compiled


class StyleEngine:
    def style_for(
        self,
        item_type: str,
        *,
        geometry_type: str | None = None,
        explicit: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        style = dict(DEFAULT_STYLE)
        style.update(GEOMETRY_STYLES.get(geometry_type or "", {}))
        style.update(TYPE_STYLES.get(item_type, {}))
        if explicit:
            style.update(explicit)
        return style


class ScenarioAgent:
    def __init__(
        self,
        tools: ToolRegistry | None = None,
        *,
        precision: int = 6,
        spatial_agent: SpatialAgent | None = None,
        compiler: ScenarioCompiler | None = None,
        style_engine: StyleEngine | None = None,
    ) -> None:
        self.spatial_agent = spatial_agent or SpatialAgent(tools=tools, precision=precision)
        self.precision = self.spatial_agent.precision
        self.compiler = compiler or ScenarioCompiler()
        self.style_engine = style_engine or StyleEngine()

    def execute(self, scenario_or_mapping: ScenarioPlan | dict[str, Any]) -> dict[str, Any]:
        scenario = (
            scenario_or_mapping
            if isinstance(scenario_or_mapping, ScenarioPlan)
            else ScenarioPlan.from_mapping(scenario_or_mapping)
        )
        return self.execute_plan(scenario).payload

    def execute_plan(self, scenario: ScenarioPlan) -> ScenarioResult:
        scenario_id = slug_id(scenario.scenario_name)
        layers, layer_features = self._execute_layers(scenario, scenario_id)
        objects, object_features = self._execute_objects(scenario, scenario_id)
        payload = {
            "type": "Scenario",
            "scenario_id": scenario_id,
            "scenario_name": scenario.scenario_name,
            "map_context": dict(scenario.map_context),
            "metadata": dict(scenario.metadata),
            "objects": objects,
            "layers": layers,
            "geojson": feature_collection(layer_features + object_features, precision=self.precision),
        }
        return ScenarioResult(plan=scenario, payload=payload)

    def _execute_layers(
        self,
        scenario: ScenarioPlan,
        scenario_id: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        layers = []
        all_features = []
        for compiled in self.compiler.compile_layers(scenario):
            geojson = self.spatial_agent.execute_plan(compiled.plan).geojson
            style = self.style_engine.style_for(
                compiled.source.type,
                geometry_type=primary_geometry_type(geojson),
                explicit=compiled.source.style,
            )
            geojson = decorate_geojson(
                geojson,
                {
                    **compiled.source.metadata,
                    "scenario_id": scenario_id,
                    "scenario_role": "layer",
                    "layer_id": compiled.id,
                    "layer_type": compiled.source.type,
                    "layer_name": compiled.name,
                    "visible": compiled.source.visible,
                    "style": style,
                },
                precision=self.precision,
            )
            layers.append(
                {
                    "id": compiled.id,
                    "type": compiled.source.type,
                    "name": compiled.name,
                    "visible": compiled.source.visible,
                    "style": style,
                    "plan": compiled.plan.to_mapping(),
                    "metadata": dict(compiled.source.metadata),
                    "geojson": geojson,
                }
            )
            all_features.extend(features_from_geojson(geojson))

        return layers, all_features

    def execute_layers(
        self,
        scenario_or_mapping: ScenarioPlan | dict[str, Any],
        *,
        scenario_id: str | None = None,
    ) -> list[dict[str, Any]]:
        scenario = (
            scenario_or_mapping
            if isinstance(scenario_or_mapping, ScenarioPlan)
            else ScenarioPlan.from_mapping(scenario_or_mapping)
        )
        layers, _features = self._execute_layers(scenario, scenario_id or slug_id(scenario.scenario_name))
        return layers

    def _execute_objects(
        self,
        scenario: ScenarioPlan,
        scenario_id: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        used_ids: set[str] = set()
        objects = []
        features = []

        for index, item in enumerate(scenario.objects, start=1):
            object_id = unique_id(item.id or item.name or f"{item.type}_{index}", used_ids)
            object_name = item.name or humanize_id(object_id)
            geom = object_geometry(item, precision=self.precision)
            style = self.style_engine.style_for(
                item.type,
                geometry_type=str(geom.get("type")),
                explicit=item.style,
            )
            metadata = dict(item.metadata)
            props = {
                **metadata,
                **item.properties,
                "scenario_id": scenario_id,
                "scenario_role": "object",
                "object_id": object_id,
                "object_type": item.type,
                "name": object_name,
                "visible": item.visible,
                "style": style,
            }
            item_feature = feature(geom, props, feature_id=object_id, precision=self.precision)
            features.append(item_feature)
            objects.append(
                {
                    "id": object_id,
                    "type": item.type,
                    "name": object_name,
                    "visible": item.visible,
                    "geometry": item_feature["geometry"],
                    "properties": dict(item.properties),
                    "metadata": metadata,
                    "style": style,
                }
            )

        return objects, features

    def execute_objects(
        self,
        scenario_or_mapping: ScenarioPlan | dict[str, Any],
        *,
        scenario_id: str | None = None,
    ) -> list[dict[str, Any]]:
        scenario = (
            scenario_or_mapping
            if isinstance(scenario_or_mapping, ScenarioPlan)
            else ScenarioPlan.from_mapping(scenario_or_mapping)
        )
        objects, _features = self._execute_objects(scenario, scenario_id or slug_id(scenario.scenario_name))
        return objects


def object_geometry(item: ScenarioObjectPlan, *, precision: int = 6) -> dict[str, Any]:
    placement = item.placement
    mode = placement.get("mode")
    if mode is None:
        if "coordinate" in placement:
            mode = "point"
        elif "geometry" in placement:
            mode = "geometry"

    if mode == "point":
        return normalize_geometry(
            {"type": "Point", "coordinates": placement["coordinate"]},
            precision=precision,
        )
    if mode == "line":
        return normalize_geometry(geometry.line_string(placement["coordinates"]), precision=precision)
    if mode == "polygon":
        return normalize_geometry(geometry.polygon(placement["rings"]), precision=precision)
    if mode == "bbox":
        return normalize_geometry(geometry.bbox_polygon(placement["bounds"]), precision=precision)
    if mode == "geometry":
        return normalize_geometry(deepcopy(placement["geometry"]), precision=precision)

    raise GeoJSONError(
        "Scenario object placement must use mode point, line, polygon, bbox, or geometry."
    )


def infer_pipeline(operation: str) -> str:
    if operation in DIRECT_OPERATIONS:
        return "direct"
    if operation in ABSTRACT_OPERATIONS:
        return "abstract"
    if operation in REAL_WORLD_OPERATIONS:
        return "real_world"
    raise GeoJSONError(
        f"Cannot infer pipeline for scenario layer operation {operation!r}. "
        "Provide pipeline and operation explicitly."
    )


def decorate_geojson(
    geojson: dict[str, Any],
    properties: dict[str, Any],
    *,
    precision: int = 6,
) -> dict[str, Any]:
    data = normalize_geojson(geojson, precision=precision)
    if data["type"] == "FeatureCollection":
        for item in data["features"]:
            item["properties"] = {**item.get("properties", {}), **properties}
        return data
    if data["type"] == "Feature":
        data["properties"] = {**data.get("properties", {}), **properties}
        return data
    return feature(data, properties, precision=precision)


def features_from_geojson(geojson: dict[str, Any]) -> list[dict[str, Any]]:
    if geojson["type"] == "FeatureCollection":
        return list(geojson["features"])
    if geojson["type"] == "Feature":
        return [geojson]
    return [feature(geojson)]


def primary_geometry_type(geojson: dict[str, Any]) -> str | None:
    if geojson["type"] == "Feature":
        geometry_obj = geojson.get("geometry")
        return str(geometry_obj.get("type")) if isinstance(geometry_obj, dict) else None
    if geojson["type"] == "FeatureCollection":
        for item in geojson.get("features", []):
            geometry_obj = item.get("geometry")
            if isinstance(geometry_obj, dict):
                return str(geometry_obj.get("type"))
        return None
    return str(geojson.get("type"))


def slug_id(value: str, *, fallback: str = "item") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", str(value).strip().lower()).strip("_")
    return slug or fallback


def unique_id(value: str, used: set[str]) -> str:
    base = slug_id(value)
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def humanize_id(value: str) -> str:
    return str(value).replace("_", " ").replace("-", " ").strip().title()


DEFAULT_STYLE = {
    "stroke_color": "#475569",
    "stroke_width": 2,
    "fill_color": "#94a3b8",
    "fill_opacity": 0.12,
    "marker_color": "#475569",
    "marker_size": 10,
}

GEOMETRY_STYLES = {
    "Point": {"marker_size": 12},
    "LineString": {"fill_opacity": 0.0, "stroke_width": 3},
    "MultiLineString": {"fill_opacity": 0.0, "stroke_width": 3},
    "Polygon": {"fill_opacity": 0.18},
    "MultiPolygon": {"fill_opacity": 0.18},
}

TYPE_STYLES = {
    "base": {
        "icon": "warehouse",
        "marker_color": "#2563eb",
        "stroke_color": "#1d4ed8",
        "label": True,
    },
    "outpost": {
        "icon": "tent",
        "marker_color": "#0f766e",
        "stroke_color": "#0f766e",
        "label": True,
    },
    "checkpoint": {
        "icon": "shield-check",
        "marker_color": "#f59e0b",
        "stroke_color": "#b45309",
        "label": True,
    },
    "supply_node": {
        "icon": "package",
        "marker_color": "#16a34a",
        "stroke_color": "#15803d",
        "label": True,
    },
    "objective_marker": {
        "icon": "flag",
        "marker_color": "#dc2626",
        "stroke_color": "#b91c1c",
        "label": True,
    },
    "label": {
        "icon": "tag",
        "marker_color": "#111827",
        "text_color": "#111827",
        "label": True,
    },
    "annotation": {
        "icon": "message-square",
        "marker_color": "#6b7280",
        "text_color": "#111827",
        "label": True,
    },
    "route": {
        "stroke_color": "#2563eb",
        "stroke_width": 4,
        "fill_opacity": 0.0,
    },
    "corridor": {
        "stroke_color": "#0369a1",
        "stroke_width": 2,
        "fill_color": "#0ea5e9",
        "fill_opacity": 0.18,
    },
    "buffer": {
        "stroke_color": "#1d4ed8",
        "stroke_width": 2,
        "fill_color": "#2563eb",
        "fill_opacity": 0.16,
    },
    "perimeter": {
        "stroke_color": "#1d4ed8",
        "stroke_width": 2,
        "fill_color": "#2563eb",
        "fill_opacity": 0.16,
        "line_dasharray": [4, 2],
    },
    "range_ring": {
        "stroke_color": "#1d4ed8",
        "stroke_width": 2,
        "fill_opacity": 0.0,
        "line_dasharray": [4, 3],
    },
    "sector": {
        "stroke_color": "#a16207",
        "stroke_width": 2,
        "fill_color": "#eab308",
        "fill_opacity": 0.2,
    },
    "observation_zone": {
        "stroke_color": "#a16207",
        "stroke_width": 2,
        "fill_color": "#eab308",
        "fill_opacity": 0.2,
    },
    "restricted_zone": {
        "stroke_color": "#c2410c",
        "stroke_width": 2,
        "fill_color": "#f97316",
        "fill_opacity": 0.22,
    },
    "search_area": {
        "stroke_color": "#64748b",
        "stroke_width": 1,
        "fill_color": "#e2e8f0",
        "fill_opacity": 0.1,
    },
    "square_grid": {
        "stroke_color": "#64748b",
        "stroke_width": 1,
        "fill_color": "#e2e8f0",
        "fill_opacity": 0.08,
    },
    "hex_grid": {
        "stroke_color": "#64748b",
        "stroke_width": 1,
        "fill_color": "#e2e8f0",
        "fill_opacity": 0.08,
    },
    "grid_cell": {
        "stroke_color": "#64748b",
        "stroke_width": 1,
        "fill_color": "#e2e8f0",
        "fill_opacity": 0.08,
    },
    "region_boundary": {
        "stroke_color": "#111827",
        "stroke_width": 3,
        "fill_opacity": 0.0,
    },
    "real_world_boundary": {
        "stroke_color": "#111827",
        "stroke_width": 3,
        "fill_opacity": 0.0,
    },
}
