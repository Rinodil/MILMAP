#!/usr/bin/env python3
"""Add planning structure and priority marking to MILMAP scenario JSON files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


COVERAGE_LAYER_TYPES = {"threat_dome", "coverage_zone"}
APPROACH_LAYER_TYPES = {"strike_corridor", "movement_corridor", "approach_corridor"}
PRIORITY_OBJECT_TYPES = {"high_value_target", "priority_node"}


def load_scenario(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def enhance_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    """Add planning structure and priority information."""
    metadata = scenario.setdefault("metadata", {})
    metadata["planning_version"] = "1.1"
    metadata["has_priority_nodes"] = False
    metadata["has_coverage_zones"] = False
    metadata["has_approach_paths"] = False

    for layer in scenario.get("layers", []):
        if not isinstance(layer, dict):
            continue
        layer_type = str(layer.get("type", ""))
        if layer_type in COVERAGE_LAYER_TYPES:
            metadata["has_coverage_zones"] = True
        elif layer_type in APPROACH_LAYER_TYPES:
            metadata["has_approach_paths"] = True

    for obj in scenario.get("objects", []):
        if not isinstance(obj, dict):
            continue
        if str(obj.get("type", "")) in PRIORITY_OBJECT_TYPES:
            metadata["has_priority_nodes"] = True
            obj_metadata = obj.setdefault("metadata", {})
            obj_metadata["priority_level"] = "high"
            obj_metadata["requires_focus"] = True

    metadata["suggested_planning_phases"] = [
        "coverage_establishment",
        "access_and_positioning",
        "area_analysis",
    ]
    return scenario


def process_file(input_path: str | Path, output_path: str | Path | None = None) -> dict[str, Any]:
    scenario = enhance_scenario(load_scenario(input_path))
    output = Path(output_path) if output_path else _default_output_path(Path(input_path))
    output.write_text(json.dumps(scenario, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Enhanced scenario saved to: {output}")
    return scenario


def _default_output_path(input_path: Path) -> Path:
    return input_path.parent / f"{input_path.stem}_planned{input_path.suffix}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enhance MILMAP scenario JSON with planning metadata.")
    parser.add_argument("--input", required=True, help="Input scenario JSON path.")
    parser.add_argument("--output", default=None, help="Output path. Defaults to <input>_planned.json.")
    args = parser.parse_args(argv)

    process_file(args.input, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
