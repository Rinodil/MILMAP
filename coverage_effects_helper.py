#!/usr/bin/env python3
"""Add basic coverage, corridor, and grid analysis to MILMAP scenarios."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


COVERAGE_LAYER_TYPES = {"threat_dome", "coverage_zone"}
APPROACH_LAYER_TYPES = {"strike_corridor", "movement_corridor", "approach_corridor"}
GRID_LAYER_TYPES = {"search_grid"}


def load_scenario(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def analyze_coverage(scenario: dict[str, Any]) -> dict[str, Any]:
    metadata = scenario.setdefault("metadata", {})
    analysis_notes: list[str] = []
    coverage_count = 0
    corridor_count = 0
    grid_count = 0

    for layer in scenario.get("layers", []):
        if not isinstance(layer, dict):
            continue
        layer_type = str(layer.get("type", ""))
        name = str(layer.get("name") or layer_type or "unnamed layer")
        params = _layer_parameters(layer)

        if layer_type in COVERAGE_LAYER_TYPES:
            coverage_count += 1
            radius = params.get("radius_km") or params.get("radius")
            if radius is not None:
                analysis_notes.append(
                    f"Coverage zone '{name}' provides approximately {radius} km radius of influence."
                )
            else:
                analysis_notes.append(f"Coverage zone '{name}' defines a primary area of influence.")

        elif layer_type in APPROACH_LAYER_TYPES:
            corridor_count += 1
            width = params.get("width_m") or params.get("width")
            if width is not None:
                analysis_notes.append(f"Approach path '{name}' has a width of {width} meters.")
            else:
                analysis_notes.append(f"Approach path '{name}' defines a main access route.")

        elif layer_type in GRID_LAYER_TYPES:
            grid_count += 1
            cell_size = params.get("cell_size_m") or params.get("cell_size")
            max_features = params.get("max_features")
            if cell_size is not None and max_features is not None:
                analysis_notes.append(
                    f"Search grid '{name}' uses {cell_size} m cells (max {max_features} cells)."
                )
            elif cell_size is not None:
                analysis_notes.append(f"Search grid '{name}' uses {cell_size} m cells.")
            else:
                analysis_notes.append(f"Search grid '{name}' supports structured area analysis.")

    metadata["coverage_analysis"] = {
        "coverage_zones": coverage_count,
        "approach_paths": corridor_count,
        "search_grids": grid_count,
        "notes": analysis_notes,
    }
    return scenario


def process_file(input_path: str | Path, output_path: str | Path | None = None) -> dict[str, Any]:
    scenario = analyze_coverage(load_scenario(input_path))
    output = Path(output_path) if output_path else _default_output_path(Path(input_path))
    output.write_text(json.dumps(scenario, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Scenario with coverage analysis saved to: {output}")
    return scenario


def _layer_parameters(layer: dict[str, Any]) -> dict[str, Any]:
    if isinstance(layer.get("parameters"), dict):
        return layer["parameters"]
    plan = layer.get("plan")
    if isinstance(plan, dict) and isinstance(plan.get("parameters"), dict):
        return plan["parameters"]
    return {}


def _default_output_path(input_path: Path) -> Path:
    return input_path.parent / f"{input_path.stem}_with_analysis{input_path.suffix}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Add coverage/effects analysis to MILMAP scenario JSON.")
    parser.add_argument("--input", required=True, help="Input scenario JSON path.")
    parser.add_argument("--output", default=None, help="Output path. Defaults to <input>_with_analysis.json.")
    args = parser.parse_args(argv)

    process_file(args.input, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
