import json
import unittest
from pathlib import Path

from milmap_engine import ScenarioBuilder
from milmap_engine.agent import SpatialAgent
from milmap_engine.geojson import feature, feature_collection
from milmap_engine.scenario import ScenarioAgent
from milmap_engine.tools import ToolRegistry

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "orlando_metro_shtf_buildplan.json"

EXPECTED_PHASE_ORDER = [
    "base_context",
    "command_and_control",
    "hazard_assessment",
    "logistics",
    "life_safety",
    "search_and_rescue",
]


def _stub_overpass_registry() -> ToolRegistry:
    """Registry that returns a deterministic, non-empty boundary offline.

    Keeps the build test free of any live Overpass network dependency while
    still exercising the real-world pipeline branch of the builder.
    """
    boundary = feature_collection(
        [
            feature(
                {
                    "type": "LineString",
                    "coordinates": [
                        [-81.50, 28.40],
                        [-81.20, 28.40],
                        [-81.20, 28.70],
                        [-81.50, 28.70],
                        [-81.50, 28.40],
                    ],
                },
                {"source": "stub-overpass"},
            )
        ]
    )
    registry = ToolRegistry()
    registry.register("overpass_query", lambda _arguments: boundary)
    registry.register("real_world_boundary", lambda _arguments: boundary)
    return registry


class OrlandoMetroShtfScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = json.loads(EXAMPLE.read_text())
        builder = ScenarioBuilder(
            agent=ScenarioAgent(spatial_agent=SpatialAgent(tools=_stub_overpass_registry()))
        )
        self.result = builder.build(self.plan)
        self.payload = self.result["payload"]
        self.qa = self.result["qa"]

    def test_complex_scenario_builds_clean(self):
        self.assertEqual(self.payload["scenario_id"], "orlando_metro_shtf")
        self.assertEqual(self.qa["status"], "pass")
        self.assertEqual(self.qa["summary"]["error_count"], 0)
        self.assertEqual(self.qa["summary"]["warning_count"], 0)
        # A genuinely complex scenario: many layers and objects across phases.
        self.assertEqual(self.qa["summary"]["layer_count"], 16)
        self.assertEqual(self.qa["summary"]["object_count"], 19)
        self.assertGreater(self.qa["summary"]["feature_count"], 40)

    def test_phases_execute_in_order_and_all_pass(self):
        self.assertEqual([p["id"] for p in self.result["phases"]], EXPECTED_PHASE_ORDER)
        self.assertTrue(all(p["status"] == "pass" for p in self.result["phases"]))

    def test_dependencies_are_attached_as_metadata(self):
        corridor = next(
            layer for layer in self.payload["layers"] if layer["name"] == "Airport Air Bridge Corridor"
        )
        self.assertIn("Downtown Emergency Operations Center", corridor["metadata"]["dependencies"])

    def test_generated_layers_carry_assumptions(self):
        # Every abstract (generated) layer should declare assumptions, so QA
        # never emits missing_generated_assumptions for this scenario.
        for layer in self.payload["layers"]:
            if layer["plan"]["pipeline"] == "abstract":
                self.assertTrue(
                    layer["metadata"].get("assumptions"),
                    f"layer {layer['id']} is missing assumptions",
                )


if __name__ == "__main__":
    unittest.main()
