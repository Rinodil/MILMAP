#!/usr/bin/env python3
"""Generate, validate, and export a MILMAP scenario from a built-in template."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent / "src"))

from milmap_engine import ScenarioAgent, ScenarioPlan, ScenarioStore
from milmap_engine.notify import NotifyError, notify_screenshot
from milmap_engine.validation import validate_scenario_payload


TEMPLATES: dict[str, dict[str, Any]] = {
    "regional_coordination": {
        "scenario_name": "Regional Coordination Scenario",
        "map_context": {
            "center": [35.0, 33.5],
            "zoom": 7,
            "purpose": "operational_planning",
        },
        "layers": [
            {
                "name": "Primary Coverage Zone",
                "type": "coverage_zone",
                "operation": "sector",
                "parameters": {
                    "center": [35.5, 33.8],
                    "radius_km": 120,
                    "start_bearing": 180,
                    "end_bearing": 270,
                    "steps": 36,
                },
                "metadata": {
                    "assumptions": ["Coverage is modeled as a deterministic sector for planning review."],
                    "source_name": "Built-in regional coordination template",
                    "placement_rationale": "Centered on the main coordination hub to show a primary planning area.",
                    "candidate_score": 82,
                    "confidence": "medium",
                },
            },
            {
                "name": "Main Movement Corridor",
                "type": "movement_corridor",
                "operation": "corridor",
                "parameters": {
                    "coordinates": [[51.4, 35.7], [48.0, 34.5], [40.0, 34.0], [35.5, 33.8]],
                    "width_m": 15000,
                },
                "metadata": {
                    "assumptions": ["Corridor width is illustrative and generated from the provided centerline."],
                    "source_name": "Built-in regional coordination template",
                    "placement_rationale": "Connects the outer route points to the main coordination hub.",
                    "candidate_score": 80,
                    "confidence": "medium",
                },
            },
            {
                "name": "Search Grid Area",
                "type": "search_grid",
                "operation": "square_grid",
                "parameters": {
                    "bounds": [35.0, 33.0, 36.5, 34.5],
                    "cell_size_m": 10000,
                    "max_features": 300,
                },
                "metadata": {
                    "assumptions": ["Grid cells are generated at a fixed size inside the provided bounding box."],
                    "source_name": "Built-in regional coordination template",
                    "placement_rationale": "Bounds cover the area around the primary hub for structured review.",
                    "candidate_score": 84,
                    "confidence": "medium",
                },
            },
        ],
        "objects": [
            {
                "name": "Main Hub",
                "type": "hub",
                "placement": {"mode": "point", "coordinate": [35.5, 33.8]},
                "metadata": {
                    "source_name": "Built-in regional coordination template",
                    "placement_rationale": "Primary reference point for the generated coverage zone.",
                    "candidate_score": 85,
                    "confidence": "medium",
                },
            },
            {
                "name": "Priority Node",
                "type": "priority_node",
                "placement": {"mode": "point", "coordinate": [35.5, 33.9]},
                "metadata": {
                    "source_name": "Built-in regional coordination template",
                    "placement_rationale": "Placed near the main hub to demonstrate a related priority point.",
                    "candidate_score": 78,
                    "confidence": "medium",
                },
            },
        ],
        "metadata": {
            "scenario_type": "regional_coordination",
            "phase": "planning",
        },
    }
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MILMAP Scenario Generator")
    parser.add_argument("--template", required=True, choices=sorted(TEMPLATES), help="Template name.")
    parser.add_argument(
        "--output",
        help="Output JSON path. Defaults to generated_<template>.json.",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Save the scenario and send a Telegram screenshot of the running workspace.",
    )
    parser.add_argument("--caption", default="", help="Notification caption.")
    parser.add_argument(
        "--server",
        default=None,
        help="Workspace URL for --notify. Defaults to MILMAP_SERVER or the notifier default.",
    )
    args = parser.parse_args(argv)

    data = TEMPLATES[args.template]
    plan = ScenarioPlan.from_mapping(data)

    print(f"Generating scenario: {plan.scenario_name}")
    result = ScenarioAgent().execute_plan(plan)
    qa = validate_scenario_payload(result.payload)
    result.payload["qa"] = qa

    score = qa["score"]
    print(f"QA Score: {score['value']}/100 | Grade: {score['grade']} | Status: {qa['status']}")
    print(f"Layers processed: {len(result.payload['layers'])}")
    print(f"Objects processed: {len(result.payload['objects'])}")

    output_file = Path(args.output or f"generated_{args.template}.json")
    output_file.write_text(json.dumps(result.payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Result saved to: {output_file}")

    if args.notify:
        record = ScenarioStore().save(plan, result.payload)
        caption = args.caption or f"{plan.scenario_name} | QA {score['value']}/100 {score['grade']}"
        try:
            notify_args = {"scenario": record["id"], "caption": caption}
            if args.server:
                notify_args["server"] = args.server
            notify_result = notify_screenshot(**notify_args)
        except NotifyError as exc:
            print(f"Notification failed: {exc}", file=sys.stderr)
            return 1
        print(f"Notification sent for saved scenario: {record['id']}")
        print(f"Screenshot source: {notify_result['url']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
