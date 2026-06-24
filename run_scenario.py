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
    args = parser.parse_args(argv)

    scenario_file = Path(f"generated_{args.template}.json")
    planned_file = Path(f"generated_{args.template}_planned.json")
    relationships_file = Path(f"generated_{args.template}_planned_with_relationships.json")

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

    if args.relationships:
        print("\n=== Step 3: Adding relationships and effects notes ===", flush=True)
        subprocess.run(
            [
                "python3",
                "relationship_helper.py",
                "--input",
                str(planned_file),
                "--output",
                str(relationships_file),
            ],
            check=True,
        )
        print(f"\nFinal relationship file: {relationships_file}")

    print("\n=== Done ===")
    print(f"Final planned file: {planned_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
