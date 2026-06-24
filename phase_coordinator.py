#!/usr/bin/env python3
"""Organize MILMAP scenario elements into logical planning phases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_PHASE_MAPPING = {
    "hub": "setup",
    "base": "setup",
    "coverage_zone": "deployment",
    "threat_dome": "deployment",
    "movement_corridor": "deployment",
    "strike_corridor": "deployment",
    "approach_corridor": "deployment",
    "search_grid": "operations",
    "priority_node": "operations",
    "high_value_target": "operations",
}

PHASE_ORDER = ["setup", "deployment", "operations"]


def load_scenario(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def organize_phases(scenario: dict[str, Any]) -> dict[str, Any]:
    layers = scenario.get("layers", [])
    objects = scenario.get("objects", [])

    phases: dict[str, dict[str, Any]] = {
        name: {"id": name, "elements": []} for name in PHASE_ORDER
    }

    for layer in layers:
        if not isinstance(layer, dict):
            continue
        ltype = layer.get("type")
        phase_id = DEFAULT_PHASE_MAPPING.get(ltype, "deployment")
        if phase_id not in phases:
            phases[phase_id] = {"id": phase_id, "elements": []}

        phases[phase_id]["elements"].append({"type": "layer", "name": layer.get("name"), "id": layer.get("id") or layer.get("name")})
        layer.setdefault("metadata", {})["phase_id"] = phase_id

    for obj in objects:
        if not isinstance(obj, dict):
            continue
        otype = obj.get("type")
        phase_id = DEFAULT_PHASE_MAPPING.get(otype, "operations")
        if phase_id not in phases:
            phases[phase_id] = {"id": phase_id, "elements": []}

        phases[phase_id]["elements"].append({"type": "object", "name": obj.get("name"), "id": obj.get("id") or obj.get("name")})
        obj.setdefault("metadata", {})["phase_id"] = phase_id

    execution_plan = []
    for pid in PHASE_ORDER:
        if pid in phases and phases[pid]["elements"]:
            execution_plan.append(phases[pid])

    # Add any other phases not in default order
    for pid, phase in phases.items():
        if pid not in PHASE_ORDER and phase["elements"]:
            execution_plan.append(phase)

    scenario.setdefault("metadata", {})["execution_plan"] = execution_plan
    scenario["metadata"]["suggested_phases"] = [p["id"] for p in execution_plan]

    return scenario


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Organize MILMAP scenario into phases.")
    parser.add_argument("--input", required=True, help="Input scenario JSON.")
    parser.add_argument("--output", help="Output scenario JSON.")
    args = parser.parse_args(argv)

    scenario = load_scenario(args.input)
    enhanced = organize_phases(scenario)

    output_path = (
        Path(args.output)
        if args.output
        else Path(args.input).parent / f"{Path(args.input).stem}_phased{Path(args.input).suffix}"
    )
    output_path.write_text(
        json.dumps(enhanced, indent=2, sort_keys=True), encoding="utf-8"
    )

    print(f"Phased scenario saved to: {output_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
