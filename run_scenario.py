#!/usr/bin/env python3
"""Run MILMAP scenario generation and planning enhancement with one command."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate and enhance a MILMAP scenario.")
    parser.add_argument("--template", required=True, help="Template name for generate_scenario.py.")
    parser.add_argument("--notify", action="store_true", help="Send clean screenshot notification.")
    parser.add_argument("--caption", default="", help="Notification caption.")
    parser.add_argument(
        "--relationships",
        action="store_true",
        help="Also write a relationship/effects JSON file from the planned scenario.",
    )
    parser.add_argument(
        "--analysis",
        action="store_true",
        help="Also write a coverage/effects analysis JSON file from the planned scenario.",
    )
    parser.add_argument(
        "--priority",
        action="store_true",
        help="Also run priority node scoring and ranking.",
    )
    parser.add_argument(
        "--phases",
        action="store_true",
        help="Also organize the scenario into planning phases.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run planning, priority, phases, relationships, and coverage/effects analysis.",
    )
    args = parser.parse_args(argv)

    scenario_file = Path(f"generated_{args.template}.json")
    planned_file = Path(f"generated_{args.template}_planned.json")
    scored_file = Path(f"generated_{args.template}_planned_scored.json")
    phased_file = Path(f"generated_{args.template}_planned_phased.json")
    relationships_file = Path(f"generated_{args.template}_planned_with_relationships.json")
    analysis_file = Path(f"generated_{args.template}_planned_with_analysis.json")

    include_priority = args.priority or args.full
    include_phases = args.phases or args.full
    include_relationships = args.relationships or args.full
    include_analysis = args.analysis or args.full

    cmd = ["python3", "generate_scenario.py", "--template", args.template]
    if args.notify:
        cmd.append("--notify")
    if args.caption:
        cmd.extend(["--caption", args.caption])

    print("=== Step 1: Generating scenario ===", flush=True)
    subprocess.run(cmd, check=True)

    print("\n=== Step 2: Adding planning structure ===", flush=True)
    subprocess.run(
        [
            "python3",
            "planning_coordinator.py",
            "--input",
            str(scenario_file),
            "--output",
            str(planned_file),
        ],
        check=True,
    )

    current_input = planned_file
    step_number = 3

    if include_priority:
        print(f"\n=== Step {step_number}: Scoring priority nodes ===", flush=True)
        subprocess.run(
            [
                "python3",
                "priority_scorer.py",
                "--input",
                str(current_input),
                "--output",
                str(scored_file),
            ],
            check=True,
        )
        current_input = scored_file
        step_number += 1
        print(f"Scored file: {scored_file}")

    if include_phases:
        print(f"\n=== Step {step_number}: Organizing planning phases ===", flush=True)
        subprocess.run(
            [
                "python3",
                "phase_coordinator.py",
                "--input",
                str(current_input),
                "--output",
                str(phased_file),
            ],
            check=True,
        )
        current_input = phased_file
        step_number += 1
        print(f"Phased file: {phased_file}")

    if include_relationships:
        print(f"\n=== Step {step_number}: Adding relationships and effects notes ===", flush=True)
        subprocess.run(
            [
                "python3",
                "relationship_helper.py",
                "--input",
                str(current_input),
                "--output",
                str(relationships_file),
            ],
            check=True,
        )
        step_number += 1
        print(f"Relationship file: {relationships_file}")

    if include_analysis:
        print(f"\n=== Step {step_number}: Adding coverage and effects analysis ===", flush=True)
        subprocess.run(
            [
                "python3",
                "coverage_effects_helper.py",
                "--input",
                str(current_input),
                "--output",
                str(analysis_file),
            ],
            check=True,
        )
        print(f"Analysis file: {analysis_file}")

    print("\n=== Done ===")
    print(f"Final planned file: {planned_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
