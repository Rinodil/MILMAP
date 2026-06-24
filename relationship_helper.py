#!/usr/bin/env python3
"""Add basic layer/object relationships and effects notes to MILMAP scenarios."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


EFFECTS_NOTES = [
    "Coverage zones define areas of primary interest.",
    "Approach corridors indicate main access routes.",
    "Priority nodes require focused attention.",
]


def load_scenario(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def add_relationships(scenario: dict[str, Any]) -> dict[str, Any]:
    metadata = scenario.setdefault("metadata", {})
    relationships: list[dict[str, str]] = []

    layers = {
        str(layer.get("name")): layer
        for layer in scenario.get("layers", [])
        if isinstance(layer, dict) and layer.get("name")
    }
    objects = {
        str(obj.get("name")): obj
        for obj in scenario.get("objects", [])
        if isinstance(obj, dict) and obj.get("name")
    }

    if "Primary Coverage Zone" in layers and "Priority Node - Coastal" in objects:
        relationships.append(
            {
                "from": "Primary Coverage Zone",
                "to": "Priority Node - Coastal",
                "relationship": "covers",
            }
        )

    if "Primary Coverage Zone" in layers and "Priority Node" in objects:
        relationships.append(
            {
                "from": "Primary Coverage Zone",
                "to": "Priority Node",
                "relationship": "covers",
            }
        )

    if "Main Approach Corridor" in layers and "Main Coordination Hub" in objects:
        relationships.append(
            {
                "from": "Main Approach Corridor",
                "to": "Main Coordination Hub",
                "relationship": "provides_access_to",
            }
        )

    if "Main Approach Corridor" in layers and "Main Operating Hub" in objects:
        relationships.append(
            {
                "from": "Main Approach Corridor",
                "to": "Main Operating Hub",
                "relationship": "provides_access_to",
            }
        )

    metadata["relationships"] = relationships
    metadata["effects_notes"] = list(EFFECTS_NOTES)
    return scenario


def process_file(input_path: str | Path, output_path: str | Path | None = None) -> dict[str, Any]:
    scenario = add_relationships(load_scenario(input_path))
    output = Path(output_path) if output_path else _default_output_path(Path(input_path))
    output.write_text(json.dumps(scenario, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Scenario with relationships saved to: {output}")
    return scenario


def _default_output_path(input_path: Path) -> Path:
    return input_path.parent / f"{input_path.stem}_with_relationships{input_path.suffix}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Add basic relationships to MILMAP scenario JSON.")
    parser.add_argument("--input", required=True, help="Input scenario JSON path.")
    parser.add_argument("--output", default=None, help="Output path. Defaults to <input>_with_relationships.json.")
    args = parser.parse_args(argv)

    process_file(args.input, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
