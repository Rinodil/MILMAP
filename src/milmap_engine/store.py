from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .geojson import GeoJSONError
from .models import ScenarioPlan
from .scenario import slug_id


class ScenarioStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.environ.get("MILMAP_STORE_PATH", ".milmap/scenarios.json"))

    def list(self) -> list[dict[str, Any]]:
        data = self._load()
        records = list(data["records"].values())
        records.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        return [scenario_summary(record) for record in records]

    def get(self, scenario_id: str) -> dict[str, Any]:
        data = self._load()
        key = slug_id(scenario_id)
        if key not in data["records"]:
            raise GeoJSONError(f"Scenario {scenario_id!r} was not found.")
        return deepcopy(data["records"][key])

    def get_versions(self, scenario_id: str) -> list[dict[str, Any]]:
        record = self.get(scenario_id)
        versions = list(record.get("versions", []))
        versions.append(
            {
                "version": record.get("version", 1),
                "updated_at": record.get("updated_at"),
                "plan": record.get("plan"),
                "payload": record.get("payload"),
            }
        )
        return deepcopy(versions)

    def save(
        self,
        plan: ScenarioPlan | dict[str, Any],
        payload: dict[str, Any],
        *,
        scenario_id: str | None = None,
    ) -> dict[str, Any]:
        plan_obj = plan if isinstance(plan, ScenarioPlan) else ScenarioPlan.from_mapping(plan)
        key = slug_id(scenario_id or str(payload.get("scenario_id") or plan_obj.scenario_name))
        now = utc_now()
        data = self._load()
        existing = data["records"].get(key)
        version = int(existing.get("version", 0)) + 1 if existing else 1
        versions = list(existing.get("versions", [])) if existing else []

        if existing:
            versions.append(
                {
                    "version": existing["version"],
                    "updated_at": existing["updated_at"],
                    "plan": existing["plan"],
                    "payload": existing["payload"],
                }
            )

        record = {
            "id": key,
            "scenario_name": plan_obj.scenario_name,
            "map_context": dict(payload.get("map_context", plan_obj.map_context)),
            "created_at": existing.get("created_at", now) if existing else now,
            "updated_at": now,
            "version": version,
            "plan": plan_obj.to_mapping(),
            "payload": deepcopy(payload),
            "versions": versions,
        }
        data["records"][key] = record
        self._write(data)
        return deepcopy(record)

    def save_phase(
        self,
        scenario_id: str,
        phase: dict[str, Any],
        plan: ScenarioPlan | dict[str, Any],
        payload: dict[str, Any],
        *,
        qa: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        plan_obj = plan if isinstance(plan, ScenarioPlan) else ScenarioPlan.from_mapping(plan)
        key = slug_id(scenario_id)
        phase_id = slug_id(str(phase.get("id") or phase.get("name") or "phase"))
        now = utc_now()
        data = self._load()
        phase_records = data.setdefault("phase_records", {}).setdefault(key, [])
        record = {
            "scenario_id": key,
            "phase_id": phase_id,
            "phase_name": phase.get("name", phase_id),
            "updated_at": now,
            "phase": deepcopy(phase),
            "plan": plan_obj.to_mapping(),
            "payload": deepcopy(payload),
            "qa": deepcopy(qa) if qa is not None else None,
        }
        phase_records.append(record)
        self._write(data)
        return deepcopy(record)

    def delete(self, scenario_id: str) -> dict[str, Any]:
        data = self._load()
        key = slug_id(scenario_id)
        if key not in data["records"]:
            raise GeoJSONError(f"Scenario {scenario_id!r} was not found.")
        record = data["records"].pop(key)
        self._write(data)
        return deepcopy(record)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"records": {}}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("records"), dict):
            raise GeoJSONError(f"Invalid scenario store file: {self.path}")
        return raw

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(self.path)


def scenario_summary(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload", {})
    return {
        "id": record["id"],
        "scenario_name": record.get("scenario_name", record["id"]),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "version": record.get("version", 1),
        "map_context": deepcopy(record.get("map_context", {})),
        "object_count": len(payload.get("objects", [])) if isinstance(payload, dict) else 0,
        "layer_count": len(payload.get("layers", [])) if isinstance(payload, dict) else 0,
        "feature_count": len(payload.get("geojson", {}).get("features", [])) if isinstance(payload, dict) else 0,
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
