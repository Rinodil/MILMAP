from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

from .map_context import MapContext, MapContextBuilder
from .models import (
    LayerBuildPlan,
    LayerPhase,
    ScenarioBrief,
    ScenarioLayerPlan,
    ScenarioObjectPlan,
    ScenarioPlan,
)
from .scenario import ScenarioAgent, slug_id
from .store import ScenarioStore
from .validation import validate_scenario_payload


class ScenarioBuilder:
    def __init__(
        self,
        *,
        agent: ScenarioAgent | None = None,
        store: ScenarioStore | None = None,
        map_context_builder: MapContextBuilder | None = None,
    ) -> None:
        self.agent = agent or ScenarioAgent()
        self.store = store
        self.map_context_builder = map_context_builder or MapContextBuilder()

    def build(self, brief_or_plan: ScenarioBrief | LayerBuildPlan | dict[str, Any]) -> dict[str, Any]:
        original_build_plan = self._coerce_build_plan(brief_or_plan)
        build_plan = self._resolve_map_context_placements(original_build_plan)
        scenario_plan = self._scenario_plan(build_plan)
        phase_reports = self._execute_phases(build_plan)
        result = self.agent.execute_plan(scenario_plan)
        payload = result.payload
        qa = validate_scenario_payload(payload, validation_rules=build_plan.validation_rules)
        payload["qa"] = qa
        payload["build"] = {
            "plan": build_plan.to_mapping(),
            "phases": phase_reports,
        }

        record = self.store.save(scenario_plan, payload) if self.store is not None else None
        return {
            "type": "ScenarioBuild",
            "scenario_id": payload["scenario_id"],
            "scenario_name": payload["scenario_name"],
            "build_plan": build_plan.to_mapping(),
            "plan": scenario_plan.to_mapping(),
            "payload": payload,
            "qa": qa,
            "phases": phase_reports,
            "record": record,
        }

    def _execute_phases(self, build_plan: LayerBuildPlan) -> list[dict[str, Any]]:
        reports = []
        layers: list[ScenarioLayerPlan] = []
        objects: list[ScenarioObjectPlan] = []
        for phase in self._ordered_phases(build_plan):
            phase_layers, phase_objects = self._phase_items(build_plan, phase)
            layers.extend(phase_layers)
            objects.extend(phase_objects)
            phase_plan = ScenarioPlan(
                scenario_name=build_plan.scenario_name,
                map_context=self._map_context(build_plan),
                layers=list(layers),
                objects=list(objects),
                metadata=self._scenario_metadata(build_plan),
            )
            payload = self.agent.execute_plan(phase_plan).payload
            qa = validate_scenario_payload(payload, validation_rules=build_plan.validation_rules)
            phase_id = slug_id(phase.id)
            report = {
                "id": phase_id,
                "name": phase.name,
                "order": phase.order,
                "required": phase.required,
                "layer_count": len(phase_layers),
                "object_count": len(phase_objects),
                "status": _phase_status(qa, phase_id),
                "warning_count": _phase_issue_count(qa, phase_id, "warning"),
                "error_count": _phase_issue_count(qa, phase_id, "error"),
            }
            reports.append(report)
            if self.store is not None:
                self.store.save_phase(build_plan.scenario_name, report, phase_plan, payload, qa=qa)
        return reports

    def _scenario_plan(self, build_plan: LayerBuildPlan) -> ScenarioPlan:
        layers: list[ScenarioLayerPlan] = []
        objects: list[ScenarioObjectPlan] = []
        for phase in self._ordered_phases(build_plan):
            phase_layers, phase_objects = self._phase_items(build_plan, phase)
            layers.extend(phase_layers)
            objects.extend(phase_objects)
        return ScenarioPlan(
            scenario_name=build_plan.scenario_name,
            map_context=self._map_context(build_plan),
            layers=layers,
            objects=objects,
            metadata=self._scenario_metadata(build_plan),
        )

    def _phase_items(
        self,
        build_plan: LayerBuildPlan,
        phase: LayerPhase,
    ) -> tuple[list[ScenarioLayerPlan], list[ScenarioObjectPlan]]:
        phase_id = slug_id(phase.id)
        base_metadata = {
            **phase.metadata,
            "phase_id": phase_id,
            "phase_name": phase.name,
            "phase_order": phase.order,
            "phase_required": phase.required,
        }
        if phase.objective:
            base_metadata["phase_objective"] = phase.objective

        layers = []
        for layer in phase.layers:
            metadata = {**base_metadata, **layer.metadata}
            metadata["phase_id"] = phase_id
            metadata["phase_name"] = phase.name
            dependencies = self._dependencies_for(build_plan, layer.id, layer.name)
            if dependencies and "dependencies" not in metadata:
                metadata["dependencies"] = dependencies
            layers.append(replace(layer, metadata=metadata))

        objects = []
        for item in phase.objects:
            metadata = {**base_metadata, **item.metadata}
            metadata["phase_id"] = phase_id
            metadata["phase_name"] = phase.name
            dependencies = self._dependencies_for(build_plan, item.id, item.name)
            if dependencies and "dependencies" not in metadata:
                metadata["dependencies"] = dependencies
            objects.append(replace(item, metadata=metadata))

        return layers, objects

    def _resolve_map_context_placements(self, build_plan: LayerBuildPlan) -> LayerBuildPlan:
        context = self._feature_context_for(build_plan)
        if context is None:
            return build_plan

        phases = []
        for phase in build_plan.phases:
            layers = [self._resolve_layer(layer, context) for layer in phase.layers]
            objects = [self._resolve_object(item, context) for item in phase.objects]
            phases.append(replace(phase, layers=layers, objects=objects))
        return replace(
            build_plan,
            phases=phases,
            map_context={
                **deepcopy(build_plan.map_context),
                "map_context_roles": context.roles(),
                "map_context_feature_count": len(context.features),
            },
        )

    def _feature_context_for(self, build_plan: LayerBuildPlan) -> MapContext | None:
        context = self._map_context(build_plan)
        source_name = str(context.get("feature_source_name") or context.get("source_name") or "map_context")
        if isinstance(context.get("feature_collection"), dict):
            return MapContext.from_geojson(
                deepcopy(context["feature_collection"]),
                source_name=source_name,
                bounds=_optional_bounds(context.get("bounds")),
            )
        if isinstance(context.get("features_geojson"), dict):
            return MapContext.from_geojson(
                deepcopy(context["features_geojson"]),
                source_name=source_name,
                bounds=_optional_bounds(context.get("bounds")),
            )
        if isinstance(context.get("overpass_json"), dict):
            return MapContext.from_overpass_json(
                deepcopy(context["overpass_json"]),
                source_name=source_name,
                bounds=_optional_bounds(context.get("bounds")),
            )
        if context.get("fetch_overpass") and isinstance(context.get("bounds"), list):
            return self.map_context_builder.build_from_overpass(context["bounds"])
        return None

    def _resolve_layer(self, layer: ScenarioLayerPlan, context: MapContext) -> ScenarioLayerPlan:
        spec = _selection_spec(layer.metadata)
        if spec is None:
            return layer
        selection = context.select_candidate(**spec["select"])
        metadata = {
            **layer.metadata,
            **selection.metadata(spec["rationale"]),
            "map_context_resolved": True,
        }
        parameters = dict(layer.parameters)
        target_parameter = spec["target_parameter"] or _default_layer_target_parameter(layer)
        if target_parameter:
            parameters[target_parameter] = list(selection.selected.feature.coordinate)
        return replace(layer, parameters=parameters, metadata=metadata)

    def _resolve_object(self, item: ScenarioObjectPlan, context: MapContext) -> ScenarioObjectPlan:
        spec = _selection_spec(item.metadata)
        if spec is None:
            return item
        selection = context.select_candidate(**spec["select"])
        metadata = {
            **item.metadata,
            **selection.metadata(spec["rationale"]),
            "map_context_resolved": True,
        }
        placement = dict(item.placement)
        if placement.get("mode") in {None, "point"}:
            placement["mode"] = "point"
            placement["coordinate"] = list(selection.selected.feature.coordinate)
        return replace(item, placement=placement, metadata=metadata)

    def _coerce_build_plan(self, value: ScenarioBrief | LayerBuildPlan | dict[str, Any]) -> LayerBuildPlan:
        if isinstance(value, LayerBuildPlan):
            return value
        if isinstance(value, ScenarioBrief):
            return self._build_plan_from_brief(value)
        if not isinstance(value, dict):
            raise TypeError("ScenarioBuilder.build expects ScenarioBrief, LayerBuildPlan, or mapping.")
        if "phases" in value:
            return LayerBuildPlan.from_mapping(value)
        if "layers" in value or "objects" in value:
            return LayerBuildPlan.from_mapping(
                {
                    "scenario_name": value.get("scenario_name", "scenario"),
                    "map_context": value.get("map_context", {}),
                    "metadata": value.get("metadata", {}),
                    "phases": [
                        {
                            "id": "single_phase",
                            "name": "Single Phase",
                            "order": 1,
                            "layers": value.get("layers", []),
                            "objects": value.get("objects", []),
                        }
                    ],
                }
            )
        return self._build_plan_from_brief(ScenarioBrief.from_mapping(value))

    def _build_plan_from_brief(self, brief: ScenarioBrief) -> LayerBuildPlan:
        layers = []
        if brief.bounds is not None:
            layers.append(
                ScenarioLayerPlan(
                    id="scenario_extent",
                    type="region_boundary",
                    name="Scenario Extent",
                    pipeline="direct",
                    operation="bbox",
                    parameters={"bounds": list(brief.bounds)},
                    metadata={
                        "source_type": "user_provided",
                        "source_name": "ScenarioBrief.bounds",
                        "confidence": "high",
                        "assumptions": list(brief.assumptions),
                    },
                )
            )
        return LayerBuildPlan(
            scenario_name=brief.scenario_name,
            brief=brief,
            map_context=self._map_context_from_brief(brief),
            metadata={"brief": brief.to_mapping()},
            phases=[
                LayerPhase(
                    id="base_context",
                    name="Base Context",
                    order=1,
                    objective="Establish operating geography from supplied brief.",
                    layers=layers,
                    metadata={
                        "source_type": "user_provided",
                        "source_name": "ScenarioBrief",
                        "confidence": "high",
                        "assumptions": list(brief.assumptions),
                    },
                )
            ],
        )

    def _map_context(self, build_plan: LayerBuildPlan) -> dict[str, Any]:
        context = {}
        if build_plan.brief is not None:
            context.update(self._map_context_from_brief(build_plan.brief))
        context.update(deepcopy(build_plan.map_context))
        return context

    def _map_context_from_brief(self, brief: ScenarioBrief) -> dict[str, Any]:
        context: dict[str, Any] = {"mode": brief.mode}
        if brief.location_name:
            context["location_name"] = brief.location_name
        if brief.center is not None:
            context["center"] = list(brief.center)
        if brief.bounds is not None:
            context["bounds"] = list(brief.bounds)
        if brief.time_horizon:
            context["time_horizon"] = brief.time_horizon
        return context

    def _scenario_metadata(self, build_plan: LayerBuildPlan) -> dict[str, Any]:
        metadata = deepcopy(build_plan.metadata)
        metadata["build"] = {
            "phase_count": len(build_plan.phases),
            "validation_rules": deepcopy(build_plan.validation_rules),
            "dependencies": deepcopy(build_plan.dependencies),
        }
        if build_plan.brief is not None and "brief" not in metadata:
            metadata["brief"] = build_plan.brief.to_mapping()
        return metadata

    def _ordered_phases(self, build_plan: LayerBuildPlan) -> list[LayerPhase]:
        return sorted(build_plan.phases, key=lambda item: (item.order, item.id))

    def _dependencies_for(
        self,
        build_plan: LayerBuildPlan,
        item_id: str | None,
        item_name: str | None,
    ) -> list[str]:
        candidates = (
            item_id,
            item_name,
            slug_id(item_id or "") if item_id else None,
            slug_id(item_name or "") if item_name else None,
        )
        for value in candidates:
            if value and value in build_plan.dependencies:
                return list(build_plan.dependencies[value])
        return []


def _phase_issue_count(qa: dict[str, Any], phase_id: str, severity: str) -> int:
    return sum(1 for issue in qa.get("issues", []) if issue.get("phase_id") == phase_id and issue.get("severity") == severity)


def _phase_status(qa: dict[str, Any], phase_id: str) -> str:
    if _phase_issue_count(qa, phase_id, "error"):
        return "error"
    if _phase_issue_count(qa, phase_id, "warning"):
        return "warning"
    return "pass"


def _selection_spec(metadata: dict[str, Any]) -> dict[str, Any] | None:
    role = metadata.get("map_context_role") or metadata.get("selected_role")
    if not role:
        return None
    constraints = dict(metadata.get("map_context_constraints") or {})
    rationale = metadata.get("placement_rationale")
    target_parameter = constraints.pop("target_parameter", metadata.get("map_context_target_parameter", None))
    select = {
        "role": str(role),
        "near": constraints.pop("near", None),
        "preferred_max_distance_m": float(constraints.pop("preferred_max_distance_m", 25_000)),
        "far_from": constraints.pop("far_from", None),
        "avoid_roles": constraints.pop("avoid_roles", None),
        "avoid_within_m": float(constraints.pop("avoid_within_m", 500)),
        "required_tags": constraints.pop("required_tags", None),
    }
    select.update(constraints)
    return {
        "select": select,
        "rationale": str(rationale) if rationale else f"Selected highest-scored map-context candidate for {role}.",
        "target_parameter": str(target_parameter) if target_parameter else None,
    }


def _default_layer_target_parameter(layer: ScenarioLayerPlan) -> str | None:
    operation = layer.operation or layer.type
    if operation in {"buffer", "range_ring", "sector", "regular_polygon"}:
        return "center"
    if operation == "point":
        return "coordinate"
    return None


def _optional_bounds(value: Any) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    return [float(item) for item in value]
