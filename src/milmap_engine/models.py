from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SpatialPlan:
    pipeline: str
    operation: str
    parameters: dict[str, Any] = field(default_factory=dict)
    properties: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "SpatialPlan":
        return cls(
            pipeline=str(value["pipeline"]),
            operation=str(value["operation"]),
            parameters=dict(value.get("parameters", {})),
            properties=dict(value.get("properties", {})),
            metadata=dict(value.get("metadata", {})),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "pipeline": self.pipeline,
            "operation": self.operation,
            "parameters": dict(self.parameters),
            "properties": dict(self.properties),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PlanResult:
    plan: SpatialPlan
    geojson: dict[str, Any]


@dataclass(frozen=True)
class ScenarioObjectPlan:
    type: str
    placement: dict[str, Any] = field(default_factory=dict)
    id: str | None = None
    name: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    style: dict[str, Any] = field(default_factory=dict)
    visible: bool = True

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "ScenarioObjectPlan":
        return cls(
            id=_optional_str(value.get("id")),
            type=str(value["type"]),
            name=_optional_str(value.get("name")),
            placement=dict(value.get("placement", {})),
            properties=dict(value.get("properties", {})),
            metadata=dict(value.get("metadata", {})),
            style=dict(value.get("style", {})),
            visible=bool(value.get("visible", True)),
        )

    def to_mapping(self) -> dict[str, Any]:
        return _without_none({
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "placement": dict(self.placement),
            "properties": dict(self.properties),
            "metadata": dict(self.metadata),
            "style": dict(self.style),
            "visible": self.visible,
        })


@dataclass(frozen=True)
class ScenarioLayerPlan:
    type: str
    parameters: dict[str, Any] = field(default_factory=dict)
    id: str | None = None
    name: str | None = None
    pipeline: str | None = None
    operation: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    style: dict[str, Any] = field(default_factory=dict)
    visible: bool = True

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "ScenarioLayerPlan":
        layer_type = value.get("type") or value.get("operation")
        if layer_type is None:
            raise KeyError("Scenario layer requires type or operation.")
        return cls(
            id=_optional_str(value.get("id")),
            type=str(layer_type),
            name=_optional_str(value.get("name")),
            pipeline=_optional_str(value.get("pipeline")),
            operation=_optional_str(value.get("operation")),
            parameters=dict(value.get("parameters", {})),
            properties=dict(value.get("properties", {})),
            metadata=dict(value.get("metadata", {})),
            style=dict(value.get("style", {})),
            visible=bool(value.get("visible", True)),
        )

    def to_mapping(self) -> dict[str, Any]:
        return _without_none({
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "pipeline": self.pipeline,
            "operation": self.operation,
            "parameters": dict(self.parameters),
            "properties": dict(self.properties),
            "metadata": dict(self.metadata),
            "style": dict(self.style),
            "visible": self.visible,
        })


@dataclass(frozen=True)
class ScenarioPlan:
    scenario_name: str
    map_context: dict[str, Any] = field(default_factory=dict)
    objects: list[ScenarioObjectPlan] = field(default_factory=list)
    layers: list[ScenarioLayerPlan] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "ScenarioPlan":
        return cls(
            scenario_name=str(value.get("scenario_name", "scenario")),
            map_context=dict(value.get("map_context", {})),
            objects=[
                item if isinstance(item, ScenarioObjectPlan) else ScenarioObjectPlan.from_mapping(item)
                for item in value.get("objects", [])
            ],
            layers=[
                item if isinstance(item, ScenarioLayerPlan) else ScenarioLayerPlan.from_mapping(item)
                for item in value.get("layers", [])
            ],
            metadata=dict(value.get("metadata", {})),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "scenario_name": self.scenario_name,
            "map_context": dict(self.map_context),
            "objects": [item.to_mapping() for item in self.objects],
            "layers": [item.to_mapping() for item in self.layers],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ScenarioResult:
    plan: ScenarioPlan
    payload: dict[str, Any]


@dataclass(frozen=True)
class ScenarioBrief:
    scenario_name: str
    location_name: str | None = None
    mode: str = "simulation"
    purpose: str | None = None
    center: list[float] | None = None
    bounds: list[float] | None = None
    time_horizon: str | None = None
    assumptions: list[Any] = field(default_factory=list)
    requested_outputs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "ScenarioBrief":
        return cls(
            scenario_name=str(value.get("scenario_name") or value.get("name") or "scenario"),
            location_name=_optional_str(value.get("location_name")),
            mode=str(value.get("mode", "simulation")),
            purpose=_optional_str(value.get("purpose")),
            center=_optional_float_list(value.get("center")),
            bounds=_optional_float_list(value.get("bounds")),
            time_horizon=_optional_str(value.get("time_horizon")),
            assumptions=_optional_list(value.get("assumptions")),
            requested_outputs=[str(item) for item in _optional_list(value.get("requested_outputs"))],
            metadata=dict(value.get("metadata", {})),
        )

    def to_mapping(self) -> dict[str, Any]:
        return _without_none({
            "scenario_name": self.scenario_name,
            "location_name": self.location_name,
            "mode": self.mode,
            "purpose": self.purpose,
            "center": list(self.center) if self.center is not None else None,
            "bounds": list(self.bounds) if self.bounds is not None else None,
            "time_horizon": self.time_horizon,
            "assumptions": list(self.assumptions),
            "requested_outputs": list(self.requested_outputs),
            "metadata": dict(self.metadata),
        })


@dataclass(frozen=True)
class LayerPhase:
    id: str
    name: str
    order: int = 0
    objective: str | None = None
    layers: list[ScenarioLayerPlan] = field(default_factory=list)
    objects: list[ScenarioObjectPlan] = field(default_factory=list)
    required: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "LayerPhase":
        order = int(value.get("order", 0))
        name = str(value.get("name") or value.get("id") or f"Phase {order}")
        return cls(
            id=str(value.get("id") or name),
            name=name,
            order=order,
            objective=_optional_str(value.get("objective")),
            layers=[
                item if isinstance(item, ScenarioLayerPlan) else ScenarioLayerPlan.from_mapping(item)
                for item in _optional_list(value.get("layers"))
            ],
            objects=[
                item if isinstance(item, ScenarioObjectPlan) else ScenarioObjectPlan.from_mapping(item)
                for item in _optional_list(value.get("objects"))
            ],
            required=bool(value.get("required", True)),
            metadata=dict(value.get("metadata", {})),
        )

    def to_mapping(self) -> dict[str, Any]:
        return _without_none({
            "id": self.id,
            "name": self.name,
            "order": self.order,
            "objective": self.objective,
            "layers": [item.to_mapping() for item in self.layers],
            "objects": [item.to_mapping() for item in self.objects],
            "required": self.required,
            "metadata": dict(self.metadata),
        })


@dataclass(frozen=True)
class LayerBuildPlan:
    scenario_name: str
    phases: list[LayerPhase] = field(default_factory=list)
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    validation_rules: dict[str, Any] = field(default_factory=dict)
    map_context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    brief: ScenarioBrief | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "LayerBuildPlan":
        brief_value = value.get("brief")
        brief = (
            brief_value
            if isinstance(brief_value, ScenarioBrief)
            else ScenarioBrief.from_mapping(brief_value)
            if isinstance(brief_value, dict)
            else None
        )
        dependencies = {
            str(key): [str(item) for item in _optional_list(items)]
            for key, items in dict(value.get("dependencies") or {}).items()
        }
        return cls(
            scenario_name=str(value.get("scenario_name") or (brief.scenario_name if brief else "scenario")),
            phases=[
                item if isinstance(item, LayerPhase) else LayerPhase.from_mapping(item)
                for item in _optional_list(value.get("phases"))
            ],
            dependencies=dependencies,
            validation_rules=dict(value.get("validation_rules", {})),
            map_context=dict(value.get("map_context", {})),
            metadata=dict(value.get("metadata", {})),
            brief=brief,
        )

    def to_mapping(self) -> dict[str, Any]:
        return _without_none({
            "scenario_name": self.scenario_name,
            "phases": [item.to_mapping() for item in self.phases],
            "dependencies": {key: list(value) for key, value in self.dependencies.items()},
            "validation_rules": dict(self.validation_rules),
            "map_context": dict(self.map_context),
            "metadata": dict(self.metadata),
            "brief": self.brief.to_mapping() if self.brief is not None else None,
        })


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_float_list(value: Any) -> list[float] | None:
    if value is None:
        return None
    return [float(item) for item in value]


def _optional_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _without_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}
