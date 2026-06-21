import tempfile
import unittest
from pathlib import Path

from milmap_engine import ScenarioBrief, ScenarioBuilder, ScenarioStore
from milmap_engine.validation import validate_scenario_payload

try:
    from fastapi.testclient import TestClient

    from milmap_engine.server import create_app
except (ModuleNotFoundError, RuntimeError):  # pragma: no cover
    TestClient = None
    create_app = None


def staged_plan():
    return {
        "scenario_name": "Staged Civil Emergency",
        "map_context": {
            "mode": "civil_emergency",
            "center": [0.0, 0.0],
            "bounds": [-1.0, -1.0, 1.0, 1.0],
        },
        "phases": [
            {
                "id": "response_network",
                "name": "Response Network",
                "order": 2,
                "objective": "Place civilian support nodes.",
                "objects": [
                    {
                        "id": "central_shelter",
                        "type": "supply_node",
                        "name": "Central Shelter",
                        "placement": {
                            "mode": "point",
                            "coordinate": [0.0, 0.0],
                        },
                        "properties": {"status": "planned"},
                    }
                ],
            },
            {
                "id": "base_context",
                "name": "Base Context",
                "order": 1,
                "objective": "Establish the operating area.",
                "layers": [
                    {
                        "id": "operating_area",
                        "type": "perimeter",
                        "name": "Operating Area",
                        "operation": "buffer",
                        "parameters": {
                            "center": [0.0, 0.0],
                            "radius_m": 1000,
                            "steps": 16,
                        },
                        "metadata": {
                            "source_type": "generated",
                            "source_name": "training fixture",
                            "confidence": "medium",
                            "assumptions": ["Synthetic 1 km planning perimeter."],
                        },
                    }
                ],
            },
        ],
    }


def map_context_feature_collection():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "osm_type": "node",
                    "osm_id": 101,
                    "name": "Central Transit",
                    "railway": "station",
                    "public_transport": "station",
                },
                "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
            },
            {
                "type": "Feature",
                "properties": {
                    "osm_type": "way",
                    "osm_id": 102,
                    "name": "Retail Mall",
                    "shop": "mall",
                    "landuse": "retail",
                },
                "geometry": {"type": "Point", "coordinates": [0.06, 0.01]},
            },
            {
                "type": "Feature",
                "properties": {
                    "osm_type": "node",
                    "osm_id": 103,
                    "name": "North Comms Tower",
                    "man_made": "communications_tower",
                },
                "geometry": {"type": "Point", "coordinates": [0.02, 0.02]},
            },
            {
                "type": "Feature",
                "properties": {
                    "osm_type": "way",
                    "osm_id": 104,
                    "name": "Training Lake",
                    "natural": "water",
                    "water": "lake",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0.03, 0.02], [0.04, 0.02], [0.04, 0.03], [0.03, 0.02]]],
                },
            },
        ],
    }


def map_aware_plan():
    return {
        "scenario_name": "Map Aware Civil Emergency",
        "map_context": {
            "mode": "civil_emergency",
            "center": [0.0, 0.0],
            "bounds": [-0.1, -0.1, 0.1, 0.1],
            "feature_source_name": "offline fixture",
            "feature_collection": map_context_feature_collection(),
        },
        "validation_rules": {
            "placement_reasoning": {
                "enabled": True,
                "require_evidence": True,
                "require_rejected_alternatives": True,
                "min_candidate_score": 40,
            }
        },
        "phases": [
            {
                "id": "response_network",
                "name": "Response Network",
                "order": 1,
                "metadata": {
                    "assumptions": ["Offline OSM-like fixture is used for deterministic test selection."]
                },
                "layers": [
                    {
                        "id": "comms_coverage",
                        "type": "range_ring",
                        "name": "Comms Coverage",
                        "operation": "range_ring",
                        "parameters": {"radius_km": 3, "steps": 24},
                        "metadata": {
                            "map_context_role": "comms_relay_candidate",
                            "map_context_constraints": {
                                "near": [0.0, 0.0],
                                "preferred_max_distance_m": 8000,
                            },
                            "placement_rationale": "Select the highest-scored mapped communications relay candidate near the operating center.",
                        },
                    }
                ],
                "objects": [
                    {
                        "id": "pickup_node",
                        "type": "supply_node",
                        "name": "Pickup Node",
                        "placement": {"mode": "point"},
                        "metadata": {
                            "map_context_role": "pickup_hub",
                            "map_context_constraints": {
                                "near": [0.0, 0.0],
                                "preferred_max_distance_m": 8000,
                                "avoid_roles": ["avoidance_zone"],
                                "avoid_within_m": 500,
                            },
                            "placement_rationale": "Select the best mapped pickup hub near the origin and outside mapped avoidance zones.",
                        },
                    }
                ],
            }
        ],
    }


class ScenarioBuilderTests(unittest.TestCase):
    def test_builder_executes_ordered_phases_and_adds_metadata(self):
        result = ScenarioBuilder().build(staged_plan())
        payload = result["payload"]

        self.assertEqual(result["type"], "ScenarioBuild")
        self.assertEqual(payload["scenario_id"], "staged_civil_emergency")
        self.assertEqual(len(payload["layers"]), 1)
        self.assertEqual(len(payload["objects"]), 1)
        self.assertEqual(result["qa"]["status"], "pass")

        layer = payload["layers"][0]
        self.assertEqual(layer["metadata"]["phase_id"], "base_context")
        self.assertEqual(layer["metadata"]["phase_name"], "Base Context")
        self.assertEqual(layer["geojson"]["properties"]["phase_id"], "base_context")

        obj = payload["objects"][0]
        self.assertEqual(obj["metadata"]["phase_id"], "response_network")
        self.assertEqual(payload["geojson"]["features"][1]["properties"]["phase_id"], "response_network")
        self.assertEqual([item["id"] for item in result["phases"]], ["base_context", "response_network"])

    def test_builder_accepts_brief_without_inventing_geometry(self):
        brief = ScenarioBrief(
            scenario_name="Brief Extent",
            location_name="Fixture City",
            mode="civil_emergency",
            bounds=[-1.0, -1.0, 1.0, 1.0],
            assumptions=["Bounds supplied by caller."],
        )

        result = ScenarioBuilder().build(brief)
        layer = result["payload"]["layers"][0]

        self.assertEqual(layer["plan"]["operation"], "bbox")
        self.assertEqual(layer["plan"]["parameters"]["bounds"], [-1.0, -1.0, 1.0, 1.0])
        self.assertEqual(layer["metadata"]["source_name"], "ScenarioBrief.bounds")

    def test_builder_saves_final_record_and_phase_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ScenarioStore(Path(tmp) / "scenarios.json")
            result = ScenarioBuilder(store=store).build(staged_plan())
            record = store.get("staged_civil_emergency")
            versions = store.get_versions("staged_civil_emergency")

            self.assertEqual(record["payload"]["qa"]["status"], "pass")
            self.assertEqual(record["id"], result["record"]["id"])
            self.assertEqual(len(versions), 1)
            self.assertIn("phase_records", store._load())
            self.assertEqual(len(store._load()["phase_records"]["staged_civil_emergency"]), 2)

    def test_builder_resolves_map_context_roles_into_placements_and_metadata(self):
        result = ScenarioBuilder().build(map_aware_plan())
        payload = result["payload"]

        self.assertEqual(result["qa"]["status"], "pass")
        self.assertEqual(payload["map_context"]["map_context_feature_count"], 4)
        self.assertGreaterEqual(payload["map_context"]["map_context_roles"]["pickup_hub"], 2)

        obj = payload["objects"][0]
        self.assertEqual(obj["geometry"]["coordinates"], [0.0, 0.0])
        self.assertTrue(obj["metadata"]["map_context_resolved"])
        self.assertEqual(obj["metadata"]["selected_role"], "pickup_hub")
        self.assertGreater(obj["metadata"]["candidate_score"], 40)
        self.assertEqual(obj["metadata"]["evidence"][0]["name"], "Central Transit")
        self.assertTrue(obj["metadata"]["rejected_alternatives"])

        layer = payload["layers"][0]
        self.assertEqual(layer["plan"]["parameters"]["center"], [0.02, 0.02])
        self.assertTrue(layer["metadata"]["map_context_resolved"])
        self.assertEqual(layer["metadata"]["selected_role"], "comms_relay_candidate")


class ScenarioValidationTests(unittest.TestCase):
    def test_validation_reports_empty_real_world_layer_and_out_of_bounds_object(self):
        qa = validate_scenario_payload(
            {
                "type": "Scenario",
                "scenario_id": "qa_fixture",
                "scenario_name": "QA Fixture",
                "map_context": {"bounds": [-1.0, -1.0, 1.0, 1.0]},
                "layers": [
                    {
                        "id": "empty_boundary",
                        "type": "real_world_boundary",
                        "name": "Empty Boundary",
                        "style": {"stroke_color": "#111827"},
                        "plan": {"pipeline": "real_world", "metadata": {}},
                        "metadata": {"phase_id": "base_context", "phase_name": "Base Context"},
                        "geojson": {"type": "FeatureCollection", "features": []},
                    }
                ],
                "objects": [
                    {
                        "id": "outside_shelter",
                        "type": "shelter",
                        "name": "Outside Shelter",
                        "style": {"marker_color": "#2563eb"},
                        "properties": {},
                        "metadata": {"phase_id": "response_network"},
                        "geometry": {"type": "Point", "coordinates": [2.0, 2.0]},
                    }
                ],
                "geojson": {"type": "FeatureCollection", "features": []},
            }
        )
        codes = {issue["code"] for issue in qa["issues"]}

        self.assertEqual(qa["status"], "warning")
        self.assertIn("empty_layer", codes)
        self.assertIn("missing_real_world_source", codes)
        self.assertIn("object_out_of_bounds", codes)


@unittest.skipIf(TestClient is None, "FastAPI test client is not installed.")
class ScenarioApiBuildTests(unittest.TestCase):
    def test_build_endpoint_saves_scenario_and_qa_endpoint_returns_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ScenarioStore(Path(tmp) / "scenarios.json")
            client = TestClient(create_app(store=store))

            response = client.post("/scenario/build", json=staged_plan())
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["scenario_id"], "staged_civil_emergency")

            qa_response = client.get("/scenario/staged_civil_emergency/qa")
            self.assertEqual(qa_response.status_code, 200)
            self.assertEqual(qa_response.json()["summary"]["layer_count"], 1)


if __name__ == "__main__":
    unittest.main()
