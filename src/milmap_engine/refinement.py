from __future__ import annotations

from copy import deepcopy
from typing import Any

from .geojson import GeoJSONError
from .models import ScenarioLayerPlan, ScenarioObjectPlan, ScenarioPlan
from .scenario import ScenarioAgent, slug_id
from .store import ScenarioStore
from .validation import validate_scenario_payload


DEFAULT_REFINEMENT_RULES: dict[str, Any] = {
    "route_quality": {
        "enabled": True,
        "max_corridor_width_m": 500,
        "max_segment_m": 5000,
    }
}


class ScenarioRefiner:
    """Apply one layer/object replacement and rebuild the scenario.

    Refinement is intentionally element-scoped: callers replace a single layer or
    object, the engine recompiles the scenario, QA runs, and the store receives a
    new version. This gives an LLM or operator a tight loop without rebuilding
    unrelated layers.
    """

    def __init__(
        self,
        *,
        agent: ScenarioAgent | None = None,
        store: ScenarioStore | None = None,
    ) -> None:
        self.agent = agent or ScenarioAgent()
        self.store = store or ScenarioStore()

    def refine(self, scenario_id: str, request: dict[str, Any]) -> dict[str, Any]:
        record = self.store.get(scenario_id)
        plan = deepcopy(record["plan"])
        target = _target(request)
        kind = target["kind"]
        item_key = "layers" if kind == "layer" else "objects"
        items = plan.setdefault(item_key, [])
        index = _target_index(items, target, kind)
        before = deepcopy(items[index])
        after = _replacement(request, before, kind)

        note = request.get("note") or request.get("instruction")
        if note:
            after.setdefault("metadata", {})
            after["metadata"].setdefault("refinement_note", str(note))
        after.setdefault("metadata", {})
        after["metadata"].setdefault("refined_from", before.get("id") or before.get("name"))

        items[index] = after
        scenario_plan = ScenarioPlan.from_mapping(plan)
        payload = self.agent.execute_plan(scenario_plan).payload
        rules = _merge_rules(DEFAULT_REFINEMENT_RULES, request.get("validation_rules"))
        qa = validate_scenario_payload(payload, validation_rules=rules)
        payload["qa"] = qa
        save = bool(request.get("save", True))
        saved = self.store.save(scenario_plan, payload, scenario_id=record["id"]) if save else None

        return {
            "type": "ScenarioRefinement",
            "scenario_id": payload["scenario_id"],
            "scenario_name": payload["scenario_name"],
            "target": {
                "kind": kind,
                "id": before.get("id"),
                "name": before.get("name"),
                "index": index,
            },
            "before": before,
            "after": after,
            "plan": scenario_plan.to_mapping(),
            "payload": payload,
            "qa": qa,
            "record": saved,
        }


def _target(request: dict[str, Any]) -> dict[str, str]:
    raw = request.get("target")
    if isinstance(raw, dict):
        kind = str(raw.get("kind") or raw.get("type") or "").lower()
        target_id = raw.get("id") or raw.get("layer_id") or raw.get("object_id")
        target_name = raw.get("name")
    else:
        kind = str(request.get("kind") or "").lower()
        target_id = request.get("id") or request.get("layer_id") or request.get("object_id")
        target_name = request.get("name")
    if kind not in {"layer", "object"}:
        raise GeoJSONError("Refinement target kind must be 'layer' or 'object'.")
    if not target_id and not target_name:
        raise GeoJSONError("Refinement target requires id or name.")
    target: dict[str, str] = {"kind": kind}
    if target_id:
        target["id"] = str(target_id)
    if target_name:
        target["name"] = str(target_name)
    return target


def _target_index(items: list[dict[str, Any]], target: dict[str, str], kind: str) -> int:
    target_id = target.get("id")
    target_name = target.get("name")
    for index, item in enumerate(items):
        ids = {
            str(item.get("id") or ""),
            slug_id(str(item.get("id") or "")),
            slug_id(str(item.get("name") or "")),
        }
        names = {str(item.get("name") or ""), slug_id(str(item.get("name") or ""))}
        if target_id and (target_id in ids or slug_id(target_id) in ids):
            return index
        if target_name and (target_name in names or slug_id(target_name) in names):
            return index
    raise GeoJSONError(f"Target {kind} was not found: {target_id or target_name!r}.")


def _replacement(request: dict[str, Any], before: dict[str, Any], kind: str) -> dict[str, Any]:
    raw = request.get("element") or request.get("replacement")
    if not isinstance(raw, dict):
        raise GeoJSONError("Refinement request requires replacement element.")
    after = deepcopy(raw)
    after.setdefault("id", before.get("id"))
    after.setdefault("name", before.get("name"))
    after.setdefault("type", before.get("type"))
    if kind == "layer":
        return ScenarioLayerPlan.from_mapping(after).to_mapping()
    return ScenarioObjectPlan.from_mapping(after).to_mapping()


def _merge_rules(base: dict[str, Any], override: Any) -> dict[str, Any]:
    rules = deepcopy(base)
    if not isinstance(override, dict):
        return rules
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(rules.get(key), dict):
            merged = dict(rules[key])
            merged.update(value)
            rules[key] = merged
        else:
            rules[key] = value
    return rules
