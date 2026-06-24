#!/usr/bin/env python3
"""
MILMAP Phase Coordinator

Assigns layers and objects to planning phases.
Phases can be customized via metadata.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_PHASES = ["setup", "deployment", "operations"]


def load_scenario(path: str | Path) -> dict[str, Any]:
    """Load scenario JSON from disk."""
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def get_phases(scenario: dict[str, Any]) -> list[str]:
    """Get phases from metadata or use defaults."""
    return scenario.get("metadata", {}).get("planning_phases") or DEFAULT_PHASES


def assign_to_phase(item: dict[str, Any], phases: list[str]) -> str:
    """Determine which phase an item belongs to based on its type."""
    item_type = str(item.get("type", ""))

    if item_type in {"threat_dome", "coverage_zone", "hub", "base"}:
        return phases[0] if len(phases) > 0 else "setup"
    elif item_type in {"strike_corridor", "movement_corridor", "approach_corridor"}:
        return phases[1] if len(phases) > 1 else "deployment"
    else:
        return phases[-1] if phases else "operations"


def assign_phases(scenario: dict[str, Any]) -> dict[str, Any]:
    """Assign all layers and objects in the scenario to planning phases."""
    phases = get_phases(scenario)
    metadata = scenario.setdefault("metadata", {})

    phase_plan: dict[str, dict[str, list[str]]] = {
        phase: {"layers": [], "objects": []} for phase in phases
    }

    for layer in scenario.get("layers", []):
        if not isinstance(layer, dict):
            continue
        phase = assign_to_phase(layer, phases)
        if phase in phase_plan:
            phase_plan[phase]["layers"].append(layer.get("name") or "unnamed_layer")
        layer.setdefault("metadata", {})["phase_id"] = phase

    for obj in scenario.get("objects", []):
        if not isinstance(obj, dict):
            continue
        phase = assign_to_phase(obj, phases)
        if phase in phase_plan:
            phase_plan[phase]["objects"].append(obj.get("name") or "unnamed_object")
        obj.setdefault("metadata", {})["phase_id"] = phase

    metadata["phase_plan"] = phase_plan
    metadata["suggested_phases"] = phases

    return scenario


def process_file(input_path: str | Path, output_path: str | Path | None = None) -> dict[str, Any]:
    """Load, enhance, and save a scenario file with phase information."""
    scenario = assign_phases(load_scenario(input_path))

    output = (
        Path(output_path)
        if output_path
        else Path(input_path).parent / f"{Path(input_path).stem}_phased{Path(input_path).suffix}"
    )
    output.write_text(json.dumps(scenario, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Phased scenario saved to: {output}")
    return scenario


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Organize MILMAP scenario into phases.")
    parser.add_argument("--input", required=True, help="Input scenario JSON.")
    parser.add_argument("--output", help="Output scenario JSON.")
    args = parser.parse_args(argv)

    process_file(args.input, args.output)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
