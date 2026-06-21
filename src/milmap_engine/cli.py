from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent import SpatialAgent
from .scenario import ScenarioAgent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute a MILMAP SpatialPlan or ScenarioPlan.")
    parser.add_argument("plan", nargs="?", help="Path to a JSON plan file. Reads stdin when omitted.")
    parser.add_argument("--precision", type=int, default=6, help="Coordinate precision for output GeoJSON.")
    parser.add_argument(
        "--scenario",
        action="store_true",
        help="Treat the input as a ScenarioPlan even if it also resembles a SpatialPlan.",
    )
    args = parser.parse_args(argv)

    if args.plan:
        payload = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    else:
        payload = json.loads(sys.stdin.read())

    if args.scenario or is_scenario_payload(payload):
        result = ScenarioAgent(precision=args.precision).execute(payload)
    else:
        agent = SpatialAgent(precision=args.precision)
        result = agent.execute_many(payload) if isinstance(payload, list) else agent.execute(payload)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def is_scenario_payload(payload: object) -> bool:
    return (
        isinstance(payload, dict)
        and "pipeline" not in payload
        and any(key in payload for key in ("scenario_name", "map_context", "objects", "layers"))
    )


if __name__ == "__main__":
    raise SystemExit(main())
