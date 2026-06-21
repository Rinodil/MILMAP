import tempfile
import unittest
from pathlib import Path

from milmap_engine import ScenarioAgent, ScenarioPlan, ScenarioRefiner, ScenarioStore
from milmap_engine.llm import ELEMENT_REFINEMENT_SCHEMA, LLMElementRefiner
from milmap_engine.validation import validate_scenario_payload


def route_plan():
    return {
        "scenario_name": "Route Refinement Fixture",
        "map_context": {"center": [0.0, 0.0], "zoom": 10},
        "layers": [
            {
                "id": "wide_corridor",
                "type": "corridor",
                "name": "Wide Corridor",
                "operation": "corridor",
                "parameters": {
                    "coordinates": [[0.0, 0.0], [0.20, 0.0]],
                    "width_m": 1600,
                },
                "metadata": {"assumptions": ["Synthetic broad route."]},
            },
            {
                "id": "support_ring",
                "type": "perimeter",
                "name": "Support Ring",
                "operation": "buffer",
                "parameters": {"center": [0.0, 0.0], "radius_m": 500, "steps": 16},
                "metadata": {"assumptions": ["Fixture support ring."]},
            },
        ],
    }


class ScenarioRefinerTests(unittest.TestCase):
    def test_refiner_replaces_one_layer_and_saves_new_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ScenarioStore(Path(tmp) / "scenarios.json")
            agent = ScenarioAgent()
            payload = agent.execute_plan(ScenarioPlan.from_mapping(route_plan())).payload
            payload["qa"] = validate_scenario_payload(payload)
            store.save(route_plan(), payload)

            result = ScenarioRefiner(agent=agent, store=store).refine(
                "route_refinement_fixture",
                {
                    "target": {"kind": "layer", "id": "wide_corridor"},
                    "note": "Replace broad corridor with detailed street-level route.",
                    "element": {
                        "type": "corridor",
                        "operation": "corridor",
                        "parameters": {
                            "coordinates": [[0.0, 0.0], [0.04, 0.0], [0.08, 0.01], [0.12, 0.01], [0.16, 0.0], [0.20, 0.0]],
                            "width_m": 250,
                        },
                        "metadata": {"assumptions": ["Detailed fixture route."], "source_type": "generated"},
                    },
                },
            )

            self.assertEqual(result["type"], "ScenarioRefinement")
            self.assertEqual(result["record"]["version"], 2)
            self.assertEqual(result["qa"]["status"], "pass")
            self.assertEqual(result["after"]["id"], "wide_corridor")
            self.assertEqual(result["payload"]["layers"][1]["id"], "support_ring")
            route_report = next(layer for layer in result["qa"]["layers"] if layer["id"] == "wide_corridor")
            self.assertEqual(route_report["corridor_width_m"], 250.0)
            self.assertEqual(route_report["route_coordinate_count"], 6)

    def test_route_quality_rules_flag_wide_sparse_route(self):
        payload = ScenarioAgent().execute(route_plan())
        qa = validate_scenario_payload(
            payload,
            validation_rules={"route_quality": {"enabled": True, "max_corridor_width_m": 500, "max_segment_m": 5000}},
        )
        codes = {issue["code"] for issue in qa["issues"]}
        self.assertIn("route_corridor_width_high", codes)
        self.assertIn("route_vertex_spacing_high", codes)

    def test_placement_reasoning_rules_flag_missing_rationale(self):
        payload = ScenarioAgent().execute(route_plan())
        qa = validate_scenario_payload(
            payload,
            validation_rules={"placement_reasoning": {"enabled": True}},
        )
        codes = {issue["code"] for issue in qa["issues"]}
        self.assertIn("missing_placement_rationale", codes)


class LLMElementRefinerTests(unittest.TestCase):
    def test_llm_refiner_requests_one_replacement_element(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def complete_json(self, *, system, user, schema):
                self.calls.append({"system": system, "user": user, "schema": schema})
                return {
                    "target": {"kind": "layer", "id": "route"},
                    "action": "replace",
                    "element": {
                        "id": "route",
                        "type": "route",
                        "operation": "line",
                        "parameters": {"coordinates": [[0, 0], [0.01, 0.01]]},
                    },
                }

        client = FakeClient()
        proposal = LLMElementRefiner(client).propose(
            scenario={"scenario_id": "fixture", "layers": [{"id": "route", "type": "route"}], "objects": []},
            target={"kind": "layer", "id": "route"},
            instruction="Make the route more detailed.",
        )

        self.assertEqual(proposal["action"], "replace")
        self.assertIs(client.calls[0]["schema"], ELEMENT_REFINEMENT_SCHEMA)
        self.assertIn("one MILMAP scenario element", client.calls[0]["system"])


if __name__ == "__main__":
    unittest.main()
