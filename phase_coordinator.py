#!/usr/bin/env python3
"""
MILMAP Phase Coordinator

Organizes scenario layers and objects into planning phases.
Phases can be customized via scenario metadata.
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


def assign_phases(scenario: dict[str, Any]) -> dict[str, Any]:
    """Organize scenario layers and objects into planning phases."""
    phases = get_phases(scenario)
    metadata = scenario.setdefault("metadata", {})

    # Initialize phase plan with requested phases
    phase_plan: dict[str, dict[str, list[str]]] = {
        phase: {"layers": [], "objects": []} for phase in phases
    }

    # Fallback for elements that don't fit in the requested phases
    # (though in this implementation we assume standard phases are present)
    for phase in DEFAULT_PHASES:
        if phase not in phase_plan:
            phase_plan[phase] = {"layers": [], "objects": []}

    # Layer assignment logic
    for layer in scenario.get("layers", []):
        if not isinstance(layer, dict):
            continue

        layer_type = str(layer.get("type", ""))
        layer_name = str(layer.get("name") or layer.get("id") or "unnamed_layer")

        target_phase = "operations"
        if layer_type in {"threat_dome", "coverage_zone"}:
            target_phase = "setup"
        elif layer_type in {"strike_corridor", "movement_corridor", "approach_corridor"}:
            target_phase = "deployment"

        # Ensure we assign to an existing phase in our plan
        if target_phase not in phase_plan:
            target_phase = phases[0] if phases else "setup"

        phase_plan[target_phase]["layers"].append(layer_name)
        layer.setdefault("metadata", {})["phase_id"] = target_phase

    # Object assignment logic
    for obj in scenario.get("objects", []):
        if not isinstance(obj, dict):
            continue

        obj_type = str(obj.get("type", ""))
        obj_name = str(obj.get("name") or obj.get("id") or "unnamed_object")

        target_phase = "operations"
        if obj_type in {"hub", "base"}:
            target_phase = "setup"

        if target_phase not in phase_plan:
            target_phase = phases[-1] if phases else "operations"

        phase_plan[target_phase]["objects"].append(obj_name)
        obj.setdefault("metadata", {})["phase_id"] = target_phase

    metadata["phase_plan"] = phase_plan
    metadata["suggested_phases"] = phases
    return scenario


def process_file(input_path: str | Path, output_path: str | Path | None = None) -> dict[str, Any]:
    """Load, enhance, and save a scenario file with phase information."""
    scenario = assign_phases(load_scenario(input_path))

    output = Path(output_path) if output_path else _default_output_path(Path(input_path))
    output.write_text(json.dumps(scenario, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Phased scenario saved to: {output}")
    return scenario


def _default_output_path(input_path: Path) -> Path:
    return input_path.parent / f"{input_path.stem}_phased{input_path.suffix}"


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
